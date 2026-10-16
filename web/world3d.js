// 场景对象 → Three.js 网格（普通视图与场景编辑器共用）
// 仿真坐标（cm）：X 前 / Y 左 / Z 上，yaw 俯视顺时针为正  →  Three.js（m）：x = X, y = Z, z = -Y, rotation.y = -yaw
import * as THREE from 'three';

export const DEG = Math.PI / 180;

/** 各类对象的默认参数（编辑器"添加"面板使用） */
export const PRESETS = {
  box: { label: '长方体', type: 'box', w: 60, d: 60, h: 100, z: 0, yaw: 0 },
  wall: { label: '墙', type: 'box', w: 10, d: 200, h: 200, z: 0, yaw: 0, color: '#8a817c' },
  cylinder: { label: '圆柱', type: 'cylinder', r: 20, h: 150, z: 0 },
  gate: { label: '门框', type: 'gate', w: 100, h: 150, t: 8, z: 0, yaw: 0, color: '#f3a712' },
  pad: { label: '挑战卡' },
};

export const TYPE_NAMES = { box: '长方体', cylinder: '圆柱', gate: '门框' };

const padTextures = new Map();
function padTexture(id) {
  if (padTextures.has(id)) return padTextures.get(id);
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
  padTextures.set(id, t);
  return t;
}

function solid(geo, color, x, y, z) {
  const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color, roughness: 0.8 }));
  m.position.set(x, y, z);
  m.castShadow = m.receiveShadow = true;
  return m;
}

/** 把对象组放到 (x, y, z) 并按 yaw 旋转 */
export function placeObject(obj, o) {
  obj.position.set(o.x / 100, (o.z || 0) / 100, -o.y / 100);
  obj.rotation.set(0, -(o.yaw || 0) * DEG, 0);
}

/** 障碍物：返回以底面中心为原点的 Group */
export function obstacleMesh(o) {
  const g = new THREE.Group();
  const c = o.color || '#8a817c';
  if (o.type === 'box') {
    g.add(solid(new THREE.BoxGeometry(o.w / 100, o.h / 100, o.d / 100), c, 0, o.h / 200, 0));
  } else if (o.type === 'cylinder') {
    g.add(solid(new THREE.CylinderGeometry(o.r / 100, o.r / 100, o.h / 100, 32), c, 0, o.h / 200, 0));
  } else if (o.type === 'gate') {
    const t = o.t / 100, w = o.w / 100, h = o.h / 100;
    const off = w / 2 + t / 2;
    for (const s of [1, -1]) g.add(solid(new THREE.BoxGeometry(t, h, t), c, 0, h / 2, -s * off));
    g.add(solid(new THREE.BoxGeometry(t, t, w + 2 * t), c, 0, h + t / 2, 0));
  }
  placeObject(g, o);
  return g;
}

export function padMesh(p) {
  const g = new THREE.Group();
  const m = new THREE.Mesh(new THREE.PlaneGeometry(0.2, 0.2),
    new THREE.MeshStandardMaterial({ map: padTexture(p.id), roughness: 0.9 }));
  m.rotation.set(-Math.PI / 2, 0, -Math.PI / 2);  // 纹理上方（箭头）指向 +X
  m.position.y = 0.003;
  m.receiveShadow = true;
  g.add(m);
  placeObject(g, { x: p.x, y: p.y, z: p.z || 0, yaw: 0 });
  return g;
}

/** 起飞点标记：地面圆环 + 指向机头方向的箭头 */
export function startMarker(start) {
  const g = new THREE.Group();
  const mat = new THREE.MeshBasicMaterial({ color: 0x2f6fde, transparent: true, opacity: 0.85, depthWrite: false });
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.14, 0.17, 40), mat);
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.004;
  g.add(ring);
  const arrow = new THREE.Mesh(new THREE.ShapeGeometry(new THREE.Shape([
    new THREE.Vector2(0.24, 0), new THREE.Vector2(0.17, 0.05), new THREE.Vector2(0.17, -0.05),
  ])), mat);
  arrow.rotation.x = -Math.PI / 2;
  arrow.position.y = 0.004;
  g.add(arrow);
  placeObject(g, { x: start.x, y: start.y, z: 0, yaw: start.yaw });
  return g;
}

function dispose(obj) {
  obj.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) o.material.dispose();  // 挑战卡纹理有缓存，不释放
  });
}

/** 按场景数据重建整个世界；每个可选中对象的 userData = { kind, index } */
export function buildWorld(group, w) {
  for (const child of [...group.children]) { dispose(child); group.remove(child); }
  w.obstacles.forEach((o, i) => {
    const m = obstacleMesh(o);
    m.userData = { kind: 'obstacle', index: i };
    group.add(m);
  });
  w.pads.forEach((p, i) => {
    const m = padMesh(p);
    m.userData = { kind: 'pad', index: i };
    group.add(m);
  });
  const s = startMarker(w.start);
  s.userData = { kind: 'start', index: 0 };
  group.add(s);
}

/** 从 Three.js 对象位置回写到场景数据 */
export function readPlacement(obj) {
  // 用局部 X 轴的朝向求偏航，避免欧拉角在 ±90° 外分解出 x/z = π 的情况
  const v = new THREE.Vector3(1, 0, 0).applyQuaternion(obj.quaternion);
  const yaw = Math.round(-Math.atan2(-v.z, v.x) / DEG * 10) / 10;
  return {
    x: Math.round(obj.position.x * 1000) / 10,
    y: Math.round(-obj.position.z * 1000) / 10,
    yaw: ((yaw + 540) % 360) - 180,
  };
}
