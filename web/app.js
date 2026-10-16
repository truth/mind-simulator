// RoboMaster TT 模拟器 3D 前端（Three.js）
// 仿真坐标（cm）：X 前 / Y 左 / Z 上  →  Three.js（m）：x = X, y = Z, z = -Y
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const $ = (id) => document.getElementById(id);
const toV3 = (p) => new THREE.Vector3(p[0] / 100, p[2] / 100, -p[1] / 100);
const MODEL_SCALE = 2;          // 模型放大倍数，便于观察（碰撞半径已按放大后尺寸设定）
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
  const root = new THREE.Group();     // 位置 + 偏航
  const body = new THREE.Group();     // 倾斜 / 翻滚
  root.add(body);
  const shell = new THREE.MeshStandardMaterial({ color: 0xd9dcdf, roughness: 0.45, metalness: 0.1 });
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

  body.scale.setScalar(MODEL_SCALE);

  // 标签
  const label = makeLabel('#' + (index + 1));
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
  const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color: [0x2f6fde, 0xe4572e, 0x2a9d8f, 0xf3a712][index % 4] }));
  trail.frustumCulled = false;
  scene.add(trail);

  scene.add(root);
  return {
    label, root, body, props, pixels, led, ledMat, ledLight, statusLed, hull, shell, blob, beam, trail,
    trailCount: 0, trailMax, lastTrail: null,
    pos: null, yaw: 0, tilt: [0, 0], spin: 0, state: null,
  };
}

function makeLabel(text) {
  const c = document.createElement('canvas');
  c.width = 128; c.height = 64;
  const g = c.getContext('2d');
  g.fillStyle = 'rgba(15,20,25,.75)';
  g.beginPath(); g.roundRect(24, 8, 80, 44, 12); g.fill();
  g.fillStyle = '#fff'; g.font = 'bold 30px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(text, 64, 31);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
  s.scale.set(0.16, 0.08, 1);
  return s;
}

// ------------------------------------------------------------------ 世界（障碍物 / 挑战卡）
const worldGroup = new THREE.Group();
scene.add(worldGroup);
let worldVersion = -1;

function padTexture(id) {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const g = c.getContext('2d');
  g.fillStyle = '#e9e9e4'; g.fillRect(0, 0, 256, 256);
  g.strokeStyle = '#222'; g.lineWidth = 10; g.strokeRect(8, 8, 240, 240);
  g.fillStyle = '#d63a2f';
  g.beginPath(); g.moveTo(128, 30); g.lineTo(150, 70); g.lineTo(106, 70); g.fill();  // 指向 +X 的箭头
  g.fillStyle = '#222'; g.font = 'bold 110px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(String(id), 128, 150);
  g.font = 'bold 28px sans-serif'; g.fillText('M' + id, 128, 220);
  const t = new THREE.CanvasTexture(c);
  t.anisotropy = 4;
  return t;
}

async function loadWorld() {
  const w = await (await fetch('/api/world')).json();
  worldVersion = w.version;
  worldGroup.clear();
  for (const o of w.obstacles) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(o.w / 100, o.h / 100, o.d / 100),
      new THREE.MeshStandardMaterial({ color: o.color, roughness: 0.8 }));
    m.position.set(o.x / 100, (o.z + o.h / 2) / 100, -o.y / 100);
    m.castShadow = m.receiveShadow = true;
    worldGroup.add(m);
  }
  for (const p of w.pads) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(0.2, 0.2),
      new THREE.MeshStandardMaterial({ map: padTexture(p.id), roughness: 0.9 }));
    m.rotation.x = -Math.PI / 2;
    m.rotation.z = -Math.PI / 2;  // 纹理上方（箭头）指向 +X
    m.position.set(p.x / 100, p.z / 100 + 0.003, -p.y / 100);
    m.receiveShadow = true;
    worldGroup.add(m);
  }
  const sel = $('scene');
  if (!sel.options.length) {
    for (const [k, v] of Object.entries(w.scenes)) sel.add(new Option(v, k));
  }
  sel.value = w.scene;
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

function syncDrones(list) {
  while (drones.length < list.length) drones.push(makeDrone(drones.length));
  const tabs = $('droneTabs');
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
  let dy = ((s.yaw - d.yaw + 540) % 360) - 180;
  d.yaw += dy * Math.min(1, k * 1.5);
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
  d.shell.color.setHex(hit && Math.floor(t * 10) % 2 === 0 ? 0xff3b30 : 0xd9dcdf);

  // 阴影圈
  const floorY = Math.max(0, (s.pos[2] - s.tof_down) / 100);
  d.blob.position.set(d.pos.x, s.tof_down <= 10 ? d.pos.y + 0.003 : floorY + 0.003, d.pos.z);
  const hgt = Math.max(0, d.pos.y - floorY);
  d.blob.scale.setScalar(1 + hgt * 0.3);
  d.blob.material.opacity = Math.max(0.06, 0.3 - hgt * 0.06);

  // ToF 光束
  d.beam.visible = $('tofBeam').checked;
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

  d.trail.visible = $('trail').checked;
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

  $('hud').textContent =
    `#${selected + 1}  ${s.flying ? '飞行中' : '地面'}   电量 ${s.battery}%\n` +
    `高度 ${s.height}cm  航向 ${Math.round(s.yaw)}°\n` +
    `ToF ${s.tof_front >= 8192 ? '--' : s.tof_front + 'mm'}   ${s.task ? '▶ ' + s.task : ''}`;
  $('pipLabel').textContent = s.stream ? 'TT 摄像头 ● 视频流已开启' : 'TT 摄像头（streamoff）';
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
  es.onopen = () => { $('conn').textContent = '模拟器在线'; $('conn').className = 'badge on'; };
  es.onerror = () => { $('conn').textContent = '模拟器离线'; $('conn').className = 'badge off'; };
  es.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    latest = data;
    simTime = data.t;
    if (resetId !== null && data.reset_id !== resetId) drones.forEach(clearTrail);
    resetId = data.reset_id;
    syncDrones(data.drones);
    appendLogs(data.logs);
    if (data.world_version !== worldVersion) loadWorld();
    $('pause').textContent = data.paused ? '继续' : '暂停';
    $('timescale').value = String(data.time_scale);
  };
}

// ------------------------------------------------------------------ 交互
const post = (url, body = {}) => fetch(url, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
}).then((r) => r.json());
const sendCmd = (cmd) => post('/api/command', { drone: selected, cmd });

$('scene').onchange = (e) => post('/api/scene', { name: e.target.value });
$('timescale').onchange = (e) => post('/api/timescale', { value: +e.target.value });
$('pause').onclick = () => post('/api/pause', { paused: !(latest && latest.paused) });
$('reset').onclick = () => post('/api/reset');
$('charge').onclick = () => post('/api/battery');
$('camModes').onclick = (e) => {
  const b = e.target.closest('button');
  if (!b) return;
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
  if (!$('keyboard').checked || e.target.tagName === 'INPUT' && e.target.type !== 'checkbox') return;
  const k = e.key.toLowerCase();
  if (k === 't') return sendCmd('takeoff');
  if (k === 'l') return sendCmd('land');
  if (['w', 'a', 's', 'd', 'q', 'e', 'arrowup', 'arrowdown'].includes(k)) {
    keys.add(k); sendRc(); e.preventDefault();
  }
});
window.addEventListener('keyup', (e) => {
  if (!$('keyboard').checked) return;
  keys.delete(e.key.toLowerCase()); sendRc();
});

// Shift + 点击地面放置障碍物
const raycaster = new THREE.Raycaster();
canvas.addEventListener('pointerdown', (e) => {
  if (!e.shiftKey) return;
  const rect = canvas.getBoundingClientRect();
  const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const hit = raycaster.intersectObject(ground)[0];
  if (!hit) return;
  post('/api/obstacle', { x: hit.point.x * 100, y: -hit.point.z * 100, w: 40, d: 40, h: 120 });
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

function placeFpv(cam, d) {
  const yawR = THREE.MathUtils.degToRad(d.yaw);
  const fwd = new THREE.Vector3(Math.cos(yawR), 0, Math.sin(yawR));
  cam.position.copy(d.pos).add(new THREE.Vector3(0, d.body.position.y, 0)).addScaledVector(fwd, 0.08);
  const look = cam.position.clone().addScaledVector(fwd, 1);
  look.y -= Math.tan(THREE.MathUtils.degToRad(d.tilt[0])) * 0.6;
  cam.lookAt(look);
}

const clock = new THREE.Clock();
const chasePos = new THREE.Vector3();
function frame() {
  requestAnimationFrame(frame);
  const dt = Math.min(clock.getDelta(), 0.1);
  const t = performance.now() / 1000;
  drones.forEach((d, i) => {
    animateDrone(d, dt, t);
    d.label.visible = camMode === 'orbit' || i !== selected;
  });
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

  if (d && d.pos) {
    placeFpv(fpvCam, d);
    d.root.visible = false;
    pipRenderer.render(scene, fpvCam);
    d.root.visible = true;
  }
  updatePanel(t);
}

resize();
loadWorld();
connect();
frame();
