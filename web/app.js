// RoboMaster TT 模拟器 3D 前端（Three.js）
// 仿真坐标（cm）：X 前 / Y 左 / Z 上  →  Three.js（m）：x = X, y = Z, z = -Y
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { buildWorld } from './world3d.js';
import { createEditor } from './editor.js';
import { createVideoStreamer } from './video.js';

const $ = (id) => document.getElementById(id);
const toV3 = (p) => new THREE.Vector3(p[0] / 100, p[2] / 100, -p[1] / 100);
const MODEL_SCALE = 2;

// ------------------------------------------------------------------ 设置（保存在浏览器 localStorage）
const DEFAULT_COLORS = ['#2f6fde', '#e4572e', '#2a9d8f', '#f3a712'];  // #1 蓝 #2 橙 #3 绿 #4 黄
const settings = { trail: true, tofBeam: true, pip: true, hud: true, ultraBeam: false, colors: [...DEFAULT_COLORS] };
try { Object.assign(settings, JSON.parse(localStorage.getItem('ttsim.settings') || '{}')); } catch { /* 忽略损坏的设置 */ }
const saveSettings = () => localStorage.setItem('ttsim.settings', JSON.stringify(settings));
const droneColor = (i) => settings.colors[i] || DEFAULT_COLORS[i % DEFAULT_COLORS.length];
const escapeHtml = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));          // 模型放大倍数，便于观察（碰撞半径已按放大后尺寸设定）
const MATRIX_COLORS = { r: 0xff2a2a, b: 0x2a6bff, p: 0xc040ff };
const MATRIX_CSS = { r: '#ff2a2a', b: '#2a6bff', p: '#c040ff', 0: '#1a1f25' };

// ------------------------------------------------------------------ 渲染器与场景
const canvas = $('scene3d');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const pipCanvas = $('pipCanvas');
const pipRenderer = new THREE.WebGLRenderer({ canvas: pipCanvas, antialias: true });

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xbfd4e6);
scene.fog = new THREE.Fog(0xbfd4e6, 12, 40);

scene.add(new THREE.HemisphereLight(0xffffff, 0x6b7a5a, 0.9));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(4, 8, 3);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -8, right: 8, top: 8, bottom: -8, near: 0.5, far: 30 });
scene.add(sun, sun.target);

// 地面 + 网格
const ground = new THREE.Mesh(new THREE.PlaneGeometry(60, 60),
  new THREE.MeshStandardMaterial({ color: 0x9fb08a, roughness: 1 }));
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);
const grid = new THREE.GridHelper(20, 40, 0x56664a, 0x7f906d);
grid.position.y = 0.002;
scene.add(grid);
const axes = new THREE.AxesHelper(0.6);  // 红 = 前(X)，蓝 = 右(-Y)，绿 = 上
axes.position.y = 0.004;
scene.add(axes);

const camera = new THREE.PerspectiveCamera(55, 1, 0.02, 200);
camera.position.set(-2.2, 1.8, 2.4);
const controls = new OrbitControls(camera, canvas);
controls.target.set(0.5, 0.5, 0);
controls.enableDamping = true;
const fpvCam = new THREE.PerspectiveCamera(70, 16 / 9, 0.02, 100);

// ------------------------------------------------------------------ RMTT 模型
function makePropeller(ccw) {
  const g = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color: 0x2b2b2b, roughness: 0.6 });
  for (let i = 0; i < 2; i++) {
    const blade = new THREE.Mesh(new THREE.BoxGeometry(0.044, 0.0015, 0.007), mat);
    blade.rotation.y = i * Math.PI / 2 + (ccw ? 0.2 : -0.2);
    blade.rotation.x = ccw ? 0.15 : -0.15;
    g.add(blade);
  }
  const disc = new THREE.Mesh(new THREE.CircleGeometry(0.023, 24),
    new THREE.MeshBasicMaterial({ color: 0x333333, transparent: true, opacity: 0, depthWrite: false }));
  disc.rotation.x = -Math.PI / 2;
  g.add(disc);
  g.userData.disc = disc;
  return g;
}

function makeDrone(index) {
  const color = droneColor(index);
  const root = new THREE.Group();     // 位置 + 偏航
  const body = new THREE.Group();     // 倾斜 / 翻滚
  root.add(body);
  const shell = new THREE.MeshStandardMaterial({ color, roughness: 0.45, metalness: 0.1 });  // 机身颜色区分编号
  const dark = new THREE.MeshStandardMaterial({ color: 0x2c3036, roughness: 0.7 });
  const accent = new THREE.MeshStandardMaterial({ color: 0x3a3f46, roughness: 0.5 });

  // 机身
  const hull = new THREE.Mesh(new THREE.BoxGeometry(0.062, 0.026, 0.046), shell);
  hull.castShadow = true;
  body.add(hull);
  const belly = new THREE.Mesh(new THREE.BoxGeometry(0.056, 0.008, 0.04), dark);
  belly.position.y = -0.016;
  body.add(belly);
  const battery = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.006, 0.036), accent);
  battery.position.set(-0.034, 0.002, 0);
  body.add(battery);
  // 前置摄像头
  const cam = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.006, 16), dark);
  cam.rotation.z = Math.PI / 2;
  cam.position.set(0.033, 0.002, 0);
  body.add(cam);
  const lens = new THREE.Mesh(new THREE.CircleGeometry(0.004, 16),
    new THREE.MeshStandardMaterial({ color: 0x1a3550, metalness: 0.9, roughness: 0.1 }));
  lens.rotation.y = Math.PI / 2;
  lens.position.set(0.0365, 0.002, 0);
  body.add(lens);
  // 机头状态灯
  const statusLed = new THREE.Mesh(new THREE.SphereGeometry(0.003, 8, 8),
    new THREE.MeshBasicMaterial({ color: 0x00ff66 }));
  statusLed.position.set(0.031, 0.009, 0.014);
  body.add(statusLed);

  // 机臂 + 电机 + 桨 + 桨保护罩
  const props = [];
  const armMat = new THREE.MeshStandardMaterial({ color: 0xc9ccd0, roughness: 0.5 });
  const guardMat = new THREE.MeshStandardMaterial({ color: 0xe8eaec, roughness: 0.6 });
  [[1, 1], [1, -1], [-1, 1], [-1, -1]].forEach(([sx, sz], i) => {
    const px = sx * 0.042, pz = sz * 0.042;
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.006, 0.008), armMat);
    arm.position.set(px / 2, 0.004, pz / 2);
    arm.rotation.y = -Math.atan2(pz, px);
    arm.castShadow = true;
    body.add(arm);
    const motor = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.012, 12), dark);
    motor.position.set(px, 0.006, pz);
    body.add(motor);
    const prop = makePropeller((i === 0 || i === 3));
    prop.position.set(px, 0.0135, pz);
    body.add(prop);
    props.push(prop);
    const guard = new THREE.Mesh(new THREE.TorusGeometry(0.025, 0.0016, 6, 32), guardMat);
    guard.rotation.x = Math.PI / 2;
    guard.position.set(px, 0.01, pz);
    guard.castShadow = true;
    body.add(guard);
  });

  // ESP32 扩展模块（顶部）
  const ext = new THREE.Group();
  ext.position.y = 0.019;
  body.add(ext);
  const board = new THREE.Mesh(new THREE.BoxGeometry(0.044, 0.012, 0.04),
    new THREE.MeshStandardMaterial({ color: 0x1b1e22, roughness: 0.6 }));
  board.castShadow = true;
  ext.add(board);
  // ToF 传感器（前方）
  const tof = new THREE.Mesh(new THREE.BoxGeometry(0.004, 0.006, 0.01), dark);
  tof.position.set(0.024, 0, 0);
  ext.add(tof);
  const tofEye = new THREE.Mesh(new THREE.CircleGeometry(0.002, 12),
    new THREE.MeshBasicMaterial({ color: 0x551111 }));
  tofEye.rotation.y = Math.PI / 2;
  tofEye.position.set(0.0262, 0, 0);
  ext.add(tofEye);
  // 8x8 点阵：行 0 在机头一侧，列 0 在机身左侧
  const pitch = 0.0042;
  const pixGeo = new THREE.BoxGeometry(0.0034, 0.0012, 0.0034);
  const pixMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const pixels = new THREE.InstancedMesh(pixGeo, pixMat, 64);
  const m4 = new THREE.Matrix4();
  for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
    m4.makeTranslation((3.5 - r) * pitch - 0.002, 0.0066, (c - 3.5) * pitch);
    pixels.setMatrixAt(r * 8 + c, m4);
    pixels.setColorAt(r * 8 + c, new THREE.Color(0x15181c));
  }
  ext.add(pixels);
  // 顶部 RGB 灯
  const ledMat = new THREE.MeshBasicMaterial({ color: 0x111111 });
  const led = new THREE.Mesh(new THREE.SphereGeometry(0.0035, 12, 8), ledMat);
  led.position.set(-0.018, 0.008, 0.014);
  ext.add(led);
  const ledLight = new THREE.PointLight(0x000000, 0, 0.6);
  ledLight.position.copy(led.position);
  ext.add(ledLight);

  const servoPivot = new THREE.Group();
  servoPivot.position.set(0.026, -0.022, 0);
  const servoBody = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.008, 0.012), dark);
  servoBody.position.set(0.026, -0.018, 0);
  body.add(servoBody);
  const servoArm = new THREE.Mesh(new THREE.BoxGeometry(0.032, 0.003, 0.004),
    new THREE.MeshStandardMaterial({ color: 0xf3a712, roughness: 0.5 }));
  servoArm.position.x = 0.016;
  servoPivot.add(servoArm);
  body.add(servoPivot);

  body.scale.setScalar(MODEL_SCALE);

  // 超声波波束（设置中开启）：锥形半透明区域，长度为当前读数
  const ultraCone = new THREE.Mesh(new THREE.ConeGeometry(Math.tan(THREE.MathUtils.degToRad(12)), 1, 24, 1, true),
    new THREE.MeshBasicMaterial({ color: 0x4cc38a, transparent: true, opacity: 0.12, depthWrite: false, side: THREE.DoubleSide }));
  ultraCone.geometry.translate(0, -0.5, 0);
  ultraCone.geometry.rotateZ(Math.PI / 2);   // 锥尖在原点、沿 +X 张开
  ultraCone.visible = false;
  root.add(ultraCone);

  // 标签
  const label = makeLabel('#' + (index + 1), color);
  label.position.y = 0.16;
  root.add(label);

  // 落点阴影圈
  const blob = new THREE.Mesh(new THREE.CircleGeometry(0.1, 32),
    new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.25, depthWrite: false }));
  blob.rotation.x = -Math.PI / 2;
  scene.add(blob);

  // ToF 光束
  const beamGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3(1, 0, 0)]);
  const beam = new THREE.Line(beamGeo, new THREE.LineBasicMaterial({ color: 0xff3030, transparent: true, opacity: 0.8 }));
  scene.add(beam);

  // 轨迹
  const trailMax = 3000;
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(trailMax * 3), 3));
  trailGeo.setDrawRange(0, 0);
  const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color }));
  trail.frustumCulled = false;
  scene.add(trail);

  scene.add(root);
  return {
    servoPivot, ultraCone, color, label, root, body, props, pixels, led, ledMat, ledLight, statusLed, hull, shell, blob, beam, trail,
    trailCount: 0, trailMax, lastTrail: null,
    pos: null, yaw: 0, tilt: [0, 0], spin: 0, state: null,
  };
}

/** 修改某架飞机的颜色（机身、标签、轨迹） */
function applyDroneColor(d, index) {
  d.color = droneColor(index);
  d.shell.color.set(d.color);
  d.trail.material.color.set(d.color);
  const old = d.label;
  d.label = makeLabel('#' + (index + 1), d.color);
  d.label.position.copy(old.position);
  d.root.remove(old);
  old.material.map.dispose();
  old.material.dispose();
  d.root.add(d.label);
}

function makeLabel(text, color = '#0f1419') {
  const c = document.createElement('canvas');
  c.width = 128; c.height = 64;
  const g = c.getContext('2d');
  g.fillStyle = color;
  g.beginPath(); g.roundRect(24, 8, 80, 44, 12); g.fill();
  g.fillStyle = '#fff'; g.font = 'bold 30px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(text, 64, 31);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
  s.scale.set(0.16, 0.08, 1);
  return s;
}

// ------------------------------------------------------------------ 世界（障碍物 / 挑战卡 / 起飞点）
const worldGroup = new THREE.Group();
scene.add(worldGroup);
let worldVersion = -1;
let worldData = null;
let editor = null;

function rebuildWorld() {
  if (worldData) buildWorld(worldGroup, worldData);
}

/** 让相机框住整个场景（top = 俯视）。高度始终高于最高的障碍物，避免被墙挡住视线 */
function frameScene(top = false) {
  const w = worldData;
  if (!w) return;
  const xs = [w.start.x - 150, w.start.x + 150], ys = [w.start.y - 150, w.start.y + 150];
  let hmax = 0;
  for (const o of w.obstacles) {
    const r = o.type === 'cylinder' ? o.r : Math.max(o.w || 0, o.d || 0) / 2 + (o.t || 0);
    xs.push(o.x - r, o.x + r); ys.push(o.y - r, o.y + r);
    hmax = Math.max(hmax, (o.z || 0) + o.h + (o.t || 0));
  }
  for (const p of w.pads) { xs.push(p.x); ys.push(p.y); }
  const cx = (Math.min(...xs) + Math.max(...xs)) / 200, cy = (Math.min(...ys) + Math.max(...ys)) / 200;
  const size = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) / 100;
  const dist = size * 0.75 + 1.2;
  controls.target.set(cx, 0.3, -cy);
  if (top) camera.position.set(cx, Math.max(hmax / 100 + 2, dist * 1.5), -cy + 0.01);
  else camera.position.set(cx - dist * 0.7, Math.max(hmax / 100 + 1.2, dist * 0.8), -cy + dist * 0.7);
  if (camMode !== 'orbit') {
    camMode = 'orbit';
    [...$('camModes').children].forEach((x) => x.classList.toggle('active', x.dataset.cam === 'orbit'));
    controls.enabled = true;
  }
  controls.update();
}
let framedScene = null;

let loadingWorld = null;
function loadWorld() {
  if (!loadingWorld) {
    loadingWorld = (async () => {
      try {
        const w = await (await fetch('/api/world')).json();
        worldData = w;
        worldVersion = w.version;
        rebuildWorld();
        // 切换到另一个场景时自动调整相机（编辑同一场景时保持视角）
        const key = w.scene || '(new)';
        if (key !== framedScene) { framedScene = key; frameScene(); }
        editor.onWorldLoaded(w);
        await editor.refreshScenes();
      } finally {
        loadingWorld = null;
      }
    })();
  }
  return loadingWorld;
}

function fillSceneSelect(scenes, current) {
  const sel = $('scene');
  sel.innerHTML = '';
  for (const [label, builtin] of [['内置场景', true], ['我的场景', false]]) {
    const items = scenes.filter((s) => s.builtin === builtin);
    if (!items.length) continue;
    const g = document.createElement('optgroup');
    g.label = label;
    items.forEach((s) => g.appendChild(new Option(s.title, s.id)));
    sel.appendChild(g);
  }
  if (!current) sel.appendChild(new Option('（未保存的新场景）', ''));
  sel.value = current || '';
}

// ------------------------------------------------------------------ 状态同步
const drones = [];
let selected = 0;
let latest = null;
let camMode = 'orbit';
let simTime = 0;
let resetId = null;

function ledColor(led, t) {
  const [r1, g1, b1] = led.c1, [r2, g2, b2] = led.c2;
  if (led.mode === 'breath') {
    const k = (1 - Math.cos(2 * Math.PI * led.freq * t)) / 2;
    return [r1 * k, g1 * k, b1 * k];
  }
  if (led.mode === 'blink') {
    return (Math.floor(t * led.freq * 2) % 2 === 0) ? [r1, g1, b1] : [r2, g2, b2];
  }
  return [r1, g1, b1];
}

/** 移除一架飞机的全部 3D 对象（切换回单机时） */
function disposeDrone(d) {
  for (const obj of [d.root, d.blob, d.beam, d.trail]) {
    scene.remove(obj);
    obj.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose());
    });
  }
}

function syncDrones(list) {
  while (drones.length < list.length) drones.push(makeDrone(drones.length));
  while (drones.length > list.length) disposeDrone(drones.pop());
  if (selected >= list.length) selected = 0;
  const tabs = $('droneTabs');
  if (list.length <= 1 && tabs.children.length) tabs.innerHTML = '';
  if (list.length > 1 && tabs.children.length !== list.length) {
    tabs.innerHTML = '';
    list.forEach((d, i) => {
      const b = document.createElement('button');
      b.textContent = `#${i + 1} ${d.ip}`;
      b.onclick = () => { selected = i; updateTabs(); };
      tabs.appendChild(b);
    });
    updateTabs();
  }
  if (list.length > 1) {
    [...tabs.children].forEach((b, i) => {
      const s = list[i];
      const t = `#${i + 1} ${s.client ? '●' : '○'} ${s.flying ? '飞行中' : '地面'}`;
      const key = t + droneColor(i);
      if (b.dataset.key !== key) {
        b.dataset.key = key;
        b.innerHTML = `<i class="sw" style="background:${droneColor(i)}"></i>${t}`;
      }
      b.title = s.client ? `已连接：${s.client}` : '等待手机 App / Mind+ 连接';
    });
  }
  list.forEach((s, i) => {
    const d = drones[i];
    if (!d.pos) {
      d.pos = toV3(s.pos); d.yaw = s.yaw;
    }
    d.state = s;
  });
}

function updateTabs() {
  [...$('droneTabs').children].forEach((b, i) => b.classList.toggle('active', i === selected));
}

function clearTrail(d) {
  d.trailCount = 0; d.lastTrail = null;
  d.trail.geometry.setDrawRange(0, 0);
}

function pushTrail(d, v) {
  if (d.lastTrail && d.lastTrail.distanceTo(v) < 0.01) return;
  if (d.trailCount >= d.trailMax) {
    const arr = d.trail.geometry.attributes.position.array;
    arr.copyWithin(0, 3);
    d.trailCount--;
  }
  d.trail.geometry.attributes.position.setXYZ(d.trailCount++, v.x, v.y, v.z);
  d.trail.geometry.attributes.position.needsUpdate = true;
  d.trail.geometry.setDrawRange(0, d.trailCount);
  d.lastTrail = v.clone();
}

const tmpColor = new THREE.Color();

function animateDrone(d, dt, t) {
  const s = d.state;
  if (!s) return;
  const target = toV3(s.pos);
  const k = 1 - Math.pow(0.0001, dt);  // 平滑插值
  d.pos.lerp(target, Math.min(1, k * 1.5));
  let dy = (((s.yaw - d.yaw) % 360 + 540) % 360) - 180;
  d.yaw += dy * Math.min(1, k * 1.5);
  d.yaw = (((d.yaw + 180) % 360 + 360) % 360) - 180;
  d.tilt[0] += (s.tilt[0] - d.tilt[0]) * k;
  d.tilt[1] += (s.tilt[1] - d.tilt[1]) * k;

  d.root.position.copy(d.pos);
  d.root.rotation.set(0, -THREE.MathUtils.degToRad(d.yaw), 0);
  let rx = THREE.MathUtils.degToRad(d.tilt[1]);
  let rz = -THREE.MathUtils.degToRad(d.tilt[0]);
  if (s.flip) {
    const a = THREE.MathUtils.degToRad(s.flip.angle) * s.flip.sign;
    if (s.flip.axis === 'roll') rx += a; else rz -= a;
  }
  d.body.rotation.set(rx, 0, rz, 'YZX');
  d.body.position.y = 0.022 * MODEL_SCALE;  // 起落时机身底部贴地

  // 桨叶
  const spinning = s.motors;
  d.spin = THREE.MathUtils.lerp(d.spin, spinning ? 60 : 0, dt * 3);
  d.props.forEach((p, i) => {
    p.rotation.y += d.spin * dt * (i === 0 || i === 3 ? 1 : -1);
    p.userData.disc.material.opacity = Math.min(0.35, d.spin / 150);
  });

  // 点阵
  const bright = 0.25 + 0.75 * (s.matrix.brightness / 255);
  for (let i = 0; i < 64; i++) {
    const ch = s.matrix.frame[i];
    if (ch === '0') tmpColor.setHex(0x15181c);
    else tmpColor.setHex(MATRIX_COLORS[ch]).multiplyScalar(bright);
    d.pixels.setColorAt(i, tmpColor);
  }
  d.pixels.instanceColor.needsUpdate = true;

  // 顶部 RGB 灯
  const [r, g, b] = ledColor(s.led, t);
  d.ledMat.color.setRGB(Math.max(r, 17) / 255, Math.max(g, 17) / 255, Math.max(b, 17) / 255);
  d.ledLight.color.setRGB(r / 255, g / 255, b / 255);
  d.ledLight.intensity = (r + g + b) > 0 ? 0.3 : 0;

  // 机头状态灯：SDK 模式紫色闪烁（RMTT），否则绿色
  const on = Math.floor(t * 2) % 2 === 0;
  d.statusLed.material.color.setHex(s.sdk ? (on ? 0xb040ff : 0x220830) : (on ? 0x00ff66 : 0x003311));

  // 碰撞闪红
  const hit = s.collision_age !== null && s.collision_age < 0.8;
  // 机身本身有颜色，碰撞时红白交替闪烁
  d.shell.color.set(hit ? (Math.floor(t * 10) % 2 === 0 ? 0xff2020 : 0xffffff) : d.color);

  // 阴影圈
  const floorY = Math.max(0, (s.pos[2] - s.tof_down) / 100);
  d.blob.position.set(d.pos.x, s.tof_down <= 10 ? d.pos.y + 0.003 : floorY + 0.003, d.pos.z);
  const hgt = Math.max(0, d.pos.y - floorY);
  d.blob.scale.setScalar(1 + hgt * 0.3);
  d.blob.material.opacity = Math.max(0.06, 0.3 - hgt * 0.06);

  // ToF 光束
  // 舵机与超声波波束
  d.servoPivot.rotation.z = -THREE.MathUtils.degToRad(s.ext ? s.ext.servo : 90);
  d.ultraCone.visible = settings.ultraBeam && !!s.ext;
  if (d.ultraCone.visible) {
    const len = s.ext.ultrasonic >= 999 ? 4 : s.ext.ultrasonic / 100;
    d.ultraCone.scale.set(len, len, len);
    d.ultraCone.position.set(0.12, d.body.position.y + 0.06, 0);
    d.ultraCone.rotation.set(0, 0, 0);
  }
  d.beam.visible = settings.tofBeam;
  if (d.beam.visible) {
    const yawR = THREE.MathUtils.degToRad(d.yaw);
    const fwd = new THREE.Vector3(Math.cos(yawR), 0, Math.sin(yawR));
    const len = s.tof_front >= 8192 ? 1.2 : s.tof_front / 1000;
    const start = d.pos.clone().add(new THREE.Vector3(0, 0.02 + d.body.position.y, 0)).addScaledVector(fwd, 0.06);
    const pts = d.beam.geometry.attributes.position;
    pts.setXYZ(0, start.x, start.y, start.z);
    const end = start.clone().addScaledVector(fwd, len);
    pts.setXYZ(1, end.x, end.y, end.z);
    pts.needsUpdate = true;
    d.beam.material.opacity = s.tof_front >= 8192 ? 0.2 : 0.9;
  }

  d.trail.visible = settings.trail;
  if (s.motors || s.falling) pushTrail(d, d.pos.clone().add(new THREE.Vector3(0, d.body.position.y, 0)));
}

// ------------------------------------------------------------------ 面板
const matrixCtx = $('matrix2d').getContext('2d');

function updatePanel(t) {
  const s = latest && latest.drones[selected];
  if (!s) return;
  $('ip').textContent = s.ip + ':8889';
  const lan = (latest.lan || []).filter((l) => l.drone === selected).map((l) => l.addr);
  $('lanAddr').textContent = lan.length ? lan.join('  ') : '未开启';
  $('client').textContent = s.client || '等待 Mind+ 连接…';
  $('sdk').textContent = s.sdk ? '已进入' : '未进入';
  $('task').textContent = s.task || '空闲';
  $('bat').textContent = s.battery + '%';
  $('bat').style.color = s.battery < 20 ? '#ff8a8a' : s.battery < 50 ? '#f3c969' : '';
  $('temp').textContent = s.temp + '~' + (s.temp + 2) + '℃';
  $('height').textContent = s.height + ' cm';
  $('yaw').textContent = Math.round(s.yaw) + '°';
  $('xy').textContent = Math.round(s.pos[0]) + ' / ' + Math.round(s.pos[1]);
  $('ftime').textContent = s.time + ' s';
  $('tofDown').textContent = s.tof_down + ' cm';
  $('mid').textContent = !s.mon ? '未开启' : s.mid > 0 ? `m${s.mid} (${s.pad_rel.join(', ')})` : '未识别';
  $('speed').textContent = s.speed + ' cm/s';
  $('fstate').textContent = s.falling ? '坠落' : s.flying ? '飞行中' : s.motors ? '起桨' : '地面';
  $('tofFront').textContent = s.tof_front >= 8192 ? '8192（超量程）' : s.tof_front + ' mm';
  $('tofBar').style.width = (s.tof_front >= 8192 ? 100 : Math.min(100, s.tof_front / 12)) + '%';

  // 2D 点阵
  const cs = 20;
  matrixCtx.fillStyle = '#0a0d10';
  matrixCtx.fillRect(0, 0, 160, 160);
  matrixCtx.globalAlpha = 0.3 + 0.7 * s.matrix.brightness / 255;
  for (let i = 0; i < 64; i++) {
    const ch = s.matrix.frame[i];
    matrixCtx.fillStyle = MATRIX_CSS[ch] || MATRIX_CSS[0];
    matrixCtx.beginPath();
    matrixCtx.arc((i % 8) * cs + cs / 2, Math.floor(i / 8) * cs + cs / 2, cs * 0.4, 0, Math.PI * 2);
    matrixCtx.fill();
  }
  matrixCtx.globalAlpha = 1;
  const [r, g, b] = ledColor(s.led, t);
  const css = `rgb(${r | 0},${g | 0},${b | 0})`;
  $('led2d').style.background = css;
  $('led2d').style.boxShadow = (r + g + b) > 0 ? `0 0 14px ${css}` : 'none';

  if (latest.drones.length > 1) {
    // 多机：每架一行
    $('hud').innerHTML = latest.drones.map((x, i) =>
      `<span style="color:${droneColor(i)}">■ #${i + 1}</span> ${x.client ? '●' : '○'} ${x.flying ? '飞行' : '地面'} ` +
      `${String(x.battery).padStart(3)}% 高${String(x.height).padStart(4)}cm ${x.task ? '▶ ' + escapeHtml(x.task) : ''}`).join('\n');
  } else {
    $('hud').textContent =
    `#${selected + 1}  ${s.flying ? '飞行中' : '地面'}   电量 ${s.battery}%\n` +
    `高度 ${s.height}cm  航向 ${Math.round(s.yaw)}°\n` +
    `ToF ${s.tof_front >= 8192 ? '--' : s.tof_front + 'mm'}   ${s.task ? '▶ ' + s.task : ''}`;
  }
  updateExtPanel(s);
  $('hud').hidden = !settings.hud;
  $('pip').hidden = !settings.pip;
  const vs = video.status(selected);
  $('pipLabel').textContent = s.stream ? `TT 摄像头 ● 视频流已开启${vs ? '（' + vs + '）' : ''}` : 'TT 摄像头（streamoff）';
}

// ------------------------------------------------------------------ 日志
const logEl = $('log');
function appendLogs(entries) {
  if (!entries.length) return;
  const atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 30;
  for (const e of entries) {
    const div = document.createElement('div');
    const err = e.kind === 'out' && /error|unknown/i.test(e.text);
    div.className = e.kind + (err ? ' err' : '');
    const tag = { in: '←', out: '→', warn: '⚠', info: '·' }[e.kind] || '';
    const ts = new Date(e.t * 1000).toTimeString().slice(0, 8);
    const who = latest && latest.drones.length > 1 ? `#${e.drone + 1} ` : '';
    div.innerHTML = `<span class="t">${ts}</span>`;
    div.appendChild(document.createTextNode(`${who}${tag} ${e.text}`));
    logEl.appendChild(div);
  }
  while (logEl.children.length > 400) logEl.firstChild.remove();
  if (atBottom) logEl.scrollTop = logEl.scrollHeight;
}

// ------------------------------------------------------------------ SSE
function connect() {
  const es = new EventSource('/events');
  const setConn = (on) => {
    $('conn').className = 'badge ' + (on ? 'on' : 'off');
    $('conn').querySelector('.txt').textContent = on ? '模拟器在线' : '模拟器离线';
    $('conn').title = on ? '模拟器在线' : '模拟器离线';
  };
  es.onopen = () => { setConn(true); loadWorld(); };
  es.onerror = () => setConn(false);
  es.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    latest = data;
    simTime = data.t;
    if (resetId !== null && data.reset_id !== resetId) drones.forEach(clearTrail);
    resetId = data.reset_id;
    syncDrones(data.drones);
    syncDroneCount(data.drones.length, data.max_drones);
    appendLogs(data.logs);
    // 编辑器正在拖动 / 提交时不从服务器重载，避免打断操作
    if (data.world_version !== worldVersion && !editor.busy()) loadWorld();
    $('pause').textContent = data.paused ? '继续' : '暂停';
    $('timescale').value = String(data.time_scale);
  };
}

// ------------------------------------------------------------------ 交互
const post = (url, body = {}) => fetch(url, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
}).then((r) => r.json());
const sendCmd = (cmd) => post('/api/command', { drone: selected, cmd });
const postFull = async (url, body = {}) => {
  const r = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  let data = {};
  try { data = await r.json(); } catch { /* 空响应 */ }
  return { status: r.status, data };
};

editor = createEditor({
  scene3d: scene, camera, canvas, controls, ground, worldGroup,
  getWorld: () => worldData,
  rebuild: rebuildWorld,
  reloadWorld: loadWorld,
  setVersion: (v) => { worldVersion = v; },
  post: postFull,
  onScenes: fillSceneSelect,
});

// 调试 / 自动化测试用
window.ttDebug = { world: () => worldData, version: () => worldVersion };

$('editToggle').onclick = () => {
  const on = !editor.active;
  if (on) {
    // 编辑时使用环绕视角
    camMode = 'orbit';
    [...$('camModes').children].forEach((x) => x.classList.toggle('active', x.dataset.cam === 'orbit'));
  }
  $('editToggle').classList.toggle('active', on);
  $('dronePanel').hidden = on;
  $('editorPanel').hidden = !on;
  editor.setActive(on);
};

// 单机 / 双机切换
const COUNT_NAMES = { 1: '单机', 2: '双机' };
function syncDroneCount(n, max) {
  const sel = $('droneCount');
  if (sel.options.length !== max) {
    sel.innerHTML = '';
    for (let i = 1; i <= max; i++) sel.add(new Option(COUNT_NAMES[i] || `${i} 架`, String(i)));
  }
  if (document.activeElement !== sel && sel.value !== String(n)) sel.value = String(n);
}
$('droneCount').onchange = async (e) => {
  const n = Number(e.target.value);
  const current = latest ? latest.drones.length : 1;
  if (n < current) {
    const removed = latest.drones.slice(n).filter((d) => d.flying || d.client);
    if (removed.length && !confirm(`将移除飞机 ${removed.map((d) => '#' + (d.index + 1)).join('、')}`
        + `（${removed.some((d) => d.flying) ? '正在飞行' : '已有客户端连接'}），确定切换吗？`)) {
      e.target.value = String(current);
      return;
    }
  }
  const r = await postFull('/api/drones', { count: n });
  if (r.status !== 200) {
    alert('切换失败：' + (r.data.error || r.status));
    e.target.value = String(current);
  }
  e.target.blur();
};

$('scene').onchange = async (e) => {
  if (worldData && worldData.dirty && !confirm('当前场景有未保存的修改，确定切换吗？')) {
    e.target.value = worldData.scene || '';
    return;
  }
  await post('/api/scene', { name: e.target.value });
  loadWorld();
};
$('timescale').onchange = (e) => post('/api/timescale', { value: +e.target.value });
$('pause').onclick = () => post('/api/pause', { paused: !(latest && latest.paused) });
$('reset').onclick = () => post('/api/reset');
$('charge').onclick = () => {
  post('/api/battery');
  $('charge').textContent = '已充满 ✓';
  setTimeout(() => { $('charge').textContent = '所有飞机充满电'; }, 1500);
};

// ------------------------------------------------------------------ 外接模组面板
const GESTURES = [['up', '↑ 上挥'], ['down', '↓ 下挥'], ['wave', '👋 挥手'], ['left', '← 左挥'], ['right', '→ 右挥'],
  ['forward', '⇡ 前推'], ['clockwise', '↻ 顺时针'], ['anticlockwise', '↺ 逆时针'], ['backward', '⇣ 后拉']];
// DFRobot 21 键红外遥控器
const IR_KEYS = [['power', '电源'], ['vol+', 'VOL+'], ['func', 'FUNC'], ['prev', '⏮'], ['play', '⏯'], ['next', '⏭'],
  ['down', '▼'], ['vol-', 'VOL-'], ['up', '▲'], ['0', '0'], ['eq', 'EQ'], ['rept', 'ST/REPT'],
  ['1', '1'], ['2', '2'], ['3', '3'], ['4', '4'], ['5', '5'], ['6', '6'], ['7', '7'], ['8', '8'], ['9', '9']];
for (const [key, label] of GESTURES) {
  const b = document.createElement('button');
  b.textContent = label;
  b.title = `模拟在飞机前做「${key}」手势，程序用 EXT gesture? 读取`;
  b.onclick = () => post('/api/sensor', { drone: selected, gesture: key });
  $('gesturePad').appendChild(b);
}
for (const [key, label] of IR_KEYS) {
  const b = document.createElement('button');
  b.textContent = label;
  b.onclick = () => post('/api/sensor', { drone: selected, ir: key });
  $('irPad').appendChild(b);
}
$('huskyMode').onchange = (e) => sendCmd(`EXT husky mode ${e.target.value}`);
$('ambient').onchange = (e) => post('/api/sensor', { ambient: Number(e.target.value) });
$('ambient').oninput = (e) => { $('ambientVal').textContent = `${e.target.value} lux`; };

const huskyCtx = $('huskyCanvas').getContext('2d');
const HUSKY_COLORS = { color: '#f3a712', tag: '#4cc38a', face: '#9fc3ff' };
function updateExtPanel(s) {
  const x = s.ext;
  if (!x) return;
  $('xUltra').textContent = x.ultrasonic >= 999 ? '超量程' : `${x.ultrasonic} cm`;
  $('xLight').textContent = `${x.light} lux`;
  const [r, g, b, name] = x.color;
  $('xColorSw').style.background = name === 'none' ? 'transparent' : `rgb(${r},${g},${b})`;
  $('xColor').textContent = name === 'none' ? '太高测不到' : name;
  $('xServo').textContent = `${Math.round(x.servo)}°`;
  $('xGesture').textContent = x.gesture ? `● ${x.gesture}` : (x.pending.gesture ? `${x.pending.gesture} 个未读` : '');
  $('xIr').textContent = x.ir ? `● ${x.ir}` : (x.pending.ir ? `${x.pending.ir} 个未读` : '');
  if (document.activeElement !== $('huskyMode')) $('huskyMode').value = x.husky_mode;
  if (worldData && document.activeElement !== $('ambient')) {
    $('ambient').value = worldData.ambient ?? 500;
    $('ambientVal').textContent = `${worldData.ambient ?? 500} lux`;
  }
  // HuskyLens 画面（320×240）
  huskyCtx.fillStyle = '#0a0d10';
  huskyCtx.fillRect(0, 0, 320, 240);
  huskyCtx.strokeStyle = '#1f2832';
  huskyCtx.strokeRect(160, 0, 0.5, 240); huskyCtx.strokeRect(0, 120, 320, 0.5);
  const col = HUSKY_COLORS[x.husky_mode];
  huskyCtx.lineWidth = 2;
  huskyCtx.font = 'bold 14px Consolas, monospace';
  for (const [id, cx, cy, w, h] of x.husky) {
    huskyCtx.strokeStyle = col;
    huskyCtx.strokeRect(cx - w / 2, cy - h / 2, w, h);
    huskyCtx.fillStyle = col;
    huskyCtx.fillText(`ID${id}`, cx - w / 2, Math.max(14, cy - h / 2 - 4));
  }
  $('huskyCount').textContent = x.husky.length ? `识别到 ${x.husky.length} 个` : '未识别到目标';
}

// ------------------------------------------------------------------ 设置窗口
function renderSettings() {
  const n = Math.max(latest ? latest.max_drones : 4, 1);
  const rows = $('colorRows');
  rows.innerHTML = '';
  for (let i = 0; i < n; i++) {
    const label = document.createElement('label');
    label.className = 'color-row';
    label.innerHTML = `<span>#${i + 1}</span><input type="color" value="${droneColor(i)}">`;
    label.querySelector('input').oninput = (e) => {
      settings.colors[i] = e.target.value;
      saveSettings();
      if (drones[i]) applyDroneColor(drones[i], i);
    };
    rows.appendChild(label);
  }
  for (const key of ['trail', 'tofBeam', 'pip', 'hud', 'ultraBeam']) {
    const box = $('set_' + key);
    box.checked = settings[key];
    box.onchange = () => { settings[key] = box.checked; saveSettings(); };
  }
}
function openSettings(on) {
  if (on) renderSettings();
  $('settingsModal').hidden = !on;
}
$('settingsBtn').onclick = () => openSettings(true);
$('settingsClose').onclick = () => openSettings(false);
$('settingsModal').onclick = (e) => { if (e.target === $('settingsModal')) openSettings(false); };
$('colorReset').onclick = () => {
  settings.colors = [...DEFAULT_COLORS];
  saveSettings();
  drones.forEach((d, i) => applyDroneColor(d, i));
  renderSettings();
};
$('camModes').onclick = (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.view) { frameScene(b.dataset.view === 'top'); return; }
  camMode = b.dataset.cam;
  [...$('camModes').children].forEach((x) => x.classList.toggle('active', x === b));
  controls.enabled = camMode === 'orbit';
};
document.querySelectorAll('.quick button').forEach((b) => { b.onclick = () => sendCmd(b.dataset.cmd); });

const history = [];
let histIdx = 0;
$('cmdForm').onsubmit = (e) => {
  e.preventDefault();
  const v = $('cmdInput').value.trim();
  if (!v) return;
  history.push(v); histIdx = history.length;
  sendCmd(v);
  $('cmdInput').value = '';
};
$('cmdInput').onkeydown = (e) => {
  if (e.key === 'ArrowUp' && histIdx > 0) { $('cmdInput').value = history[--histIdx]; e.preventDefault(); }
  if (e.key === 'ArrowDown') { histIdx = Math.min(history.length, histIdx + 1); $('cmdInput').value = history[histIdx] || ''; }
};

// 键盘遥控（rc 指令）
const keys = new Set();
let lastRc = '';
function sendRc() {
  const ax = (a, b) => (keys.has(a) ? 60 : 0) - (keys.has(b) ? 60 : 0);
  const rc = `rc ${ax('d', 'a')} ${ax('w', 's')} ${ax('arrowup', 'arrowdown')} ${ax('e', 'q')}`;
  if (rc !== lastRc) { lastRc = rc; sendCmd(rc); }
}
window.addEventListener('keydown', (e) => {
  const typing = ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName) && e.target.type !== 'checkbox';
  if (typing) return;
  if (!$('settingsModal').hidden) {
    if (e.key === 'Escape') openSettings(false);
    return;
  }
  if (editor.handleKey(e)) { e.preventDefault(); return; }
  if (editor.active || !$('keyboard').checked) return;
  const k = e.key.toLowerCase();
  if (k === 't') return sendCmd('takeoff');
  if (k === 'l') return sendCmd('land');
  if (['w', 'a', 's', 'd', 'q', 'e', 'arrowup', 'arrowdown'].includes(k)) {
    keys.add(k); sendRc(); e.preventDefault();
  }
});
window.addEventListener('keyup', (e) => {
  if (!$('keyboard').checked || editor.active) return;
  keys.delete(e.key.toLowerCase()); sendRc();
});

// ------------------------------------------------------------------ 渲染循环
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  pipRenderer.setSize(pipCanvas.clientWidth, pipCanvas.clientHeight, false);
}
window.addEventListener('resize', resize);
// 标题栏换行等导致 3D 区域尺寸变化时同步调整画布
new ResizeObserver(resize).observe($('viewport'));


function placeFpv(cam, d) {
  const yawR = THREE.MathUtils.degToRad(d.yaw);
  const fwd = new THREE.Vector3(Math.cos(yawR), 0, Math.sin(yawR));
  cam.position.copy(d.pos).add(new THREE.Vector3(0, d.body.position.y, 0)).addScaledVector(fwd, 0.08);
  const look = cam.position.clone().addScaledVector(fwd, 1);
  look.y -= Math.tan(THREE.MathUtils.degToRad(d.tilt[0])) * 0.6;
  cam.lookAt(look);
}

// streamon 后把机载画面编码为 H.264 推给客户端（UDP 11111）
const video = createVideoStreamer({ scene, fpvCam, placeFpv, hideWhileRendering: renderOnboard });

// 机载摄像头画面（画中画与视频流）：隐藏本机模型，以及编辑手柄、ToF 光束、轨迹、编号标签等界面辅助图形
function renderOnboard(d, render) {
  const helpers = [editor.gizmo, ...drones.flatMap((x) => [x.beam, x.trail, x.label])];
  const shown = helpers.map((o) => o.visible);
  helpers.forEach((o) => { o.visible = false; });
  d.root.visible = false;
  render();
  d.root.visible = true;
  helpers.forEach((o, i) => { o.visible = shown[i]; });
}

const clock = new THREE.Clock();
const chasePos = new THREE.Vector3();
function frame() {
  requestAnimationFrame(frame);
  if (!document.hidden) step();
}

// 页面被隐藏（最小化、切到其他标签页、被 Mind+ 等窗口完全遮挡）时 requestAnimationFrame 停止、
// 普通定时器被节流到 1 次/秒；视频推流期间改由 Worker 定时器驱动，只更新飞机并编码画面
const ticker = new Worker(URL.createObjectURL(new Blob(
  ['setInterval(() => postMessage(0), 40);'], { type: 'text/javascript' })));
ticker.onmessage = () => {
  if (document.hidden && latest && latest.drones.some((s) => s.stream)) step(true);
};

function step(hidden = false) {
  const dt = Math.min(clock.getDelta(), 0.1);
  const t = performance.now() / 1000;
  drones.forEach((d, i) => {
    animateDrone(d, dt, t);
    d.label.visible = camMode === 'orbit' || i !== selected;
  });
  if (hidden) {
    video.tick(latest.drones, drones);
    return;
  }
  const d = drones[selected];

  if (d && d.pos) {
    if (camMode === 'orbit') {
      controls.update();
    } else if (camMode === 'chase') {
      const yawR = THREE.MathUtils.degToRad(d.yaw);
      const want = d.pos.clone().add(new THREE.Vector3(-Math.cos(yawR) * 0.9, 0.45, -Math.sin(yawR) * 0.9));
      chasePos.lerp(want, Math.min(1, dt * 4));
      camera.position.copy(chasePos);
      camera.lookAt(d.pos.clone().add(new THREE.Vector3(0, 0.08, 0)));
    } else {
      placeFpv(camera, d);
    }
    // 阴影相机跟随
    sun.target.position.copy(d.pos);
    sun.position.copy(d.pos).add(new THREE.Vector3(4, 8, 3));
  }
  if (camMode === 'chase' && chasePos.lengthSq() === 0 && d) chasePos.copy(camera.position);

  // 第一视角渲染时隐藏自身模型
  const hideSelf = camMode === 'fpv' && d;
  if (hideSelf) d.root.visible = false;
  renderer.render(scene, camera);
  if (hideSelf) d.root.visible = true;

  if (d && d.pos && settings.pip) {
    placeFpv(fpvCam, d);
    renderOnboard(d, () => pipRenderer.render(scene, fpvCam));
  }
  if (latest) video.tick(latest.drones, drones);
  updatePanel(t);
}

resize();
loadWorld();
connect();
frame();
