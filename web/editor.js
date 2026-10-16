// 场景编辑器 + 场景库面板
import * as THREE from 'three';
import { TransformControls } from './vendor/TransformControls.js';
import { DEG, PRESETS, TYPE_NAMES, obstacleMesh, padMesh, readPlacement } from './world3d.js';

const $ = (id) => document.getElementById(id);
const PALETTE = ['#e4572e', '#29335c', '#f3a712', '#669bbc', '#8a817c', '#2a9d8f'];
const UNDO_MAX = 50;

// 属性面板字段：[键, 标签, 最小, 最大, 步长]
const FIELDS = {
  box: [['x', 'X 前后', -100000, 100000, 1], ['y', 'Y 左右', -100000, 100000, 1], ['z', '离地高度', 0, 10000, 1],
    ['w', '长（自身 X）', 1, 5000, 1], ['d', '宽（自身 Y）', 1, 5000, 1], ['h', '高', 1, 5000, 1], ['yaw', '旋转°', -180, 180, 1]],
  cylinder: [['x', 'X 前后', -100000, 100000, 1], ['y', 'Y 左右', -100000, 100000, 1], ['z', '离地高度', 0, 10000, 1],
    ['r', '半径', 1, 2500, 1], ['h', '高', 1, 5000, 1]],
  gate: [['x', 'X 前后', -100000, 100000, 1], ['y', 'Y 左右', -100000, 100000, 1], ['z', '离地高度', 0, 10000, 1],
    ['w', '门洞宽', 20, 2000, 1], ['h', '门洞高', 20, 2000, 1], ['t', '框粗', 2, 100, 1], ['yaw', '旋转°', -180, 180, 1]],
  pad: [['x', 'X 前后', -100000, 100000, 1], ['y', 'Y 左右', -100000, 100000, 1], ['z', '所在高度', 0, 10000, 1]],
  start: [['x', 'X 前后', -100000, 100000, 1], ['y', 'Y 左右', -100000, 100000, 1], ['yaw', '机头朝向°', -180, 180, 1]],
};

export function createEditor(ctx) {
  const { camera, canvas, controls, ground, worldGroup } = ctx;
  const ed = { active: false };
  let selection = null;          // { kind: 'obstacle' | 'pad' | 'start', index }
  let placing = null;            // PRESETS 键
  let ghost = null;
  let dragging = false;
  let pending = 0;               // 未完成的提交请求数
  let pushTimer = null;
  let scenes = [];
  let listSelected = null;
  const undoStack = [];

  // ---------------------------------------------------------------- Transform 手柄
  const transform = new TransformControls(camera, canvas);
  transform.setSize(0.8);
  transform.addEventListener('dragging-changed', (e) => {
    controls.enabled = !e.value;
    dragging = e.value;
    if (e.value) snapshot();
    else push(true);
  });
  transform.addEventListener('objectChange', () => {
    const obj = transform.object;
    if (!obj || !selection) return;
    const item = selectedItem();
    const p = readPlacement(obj);
    item.x = p.x; item.y = p.y;
    if (selection.kind !== 'pad' && !(selection.kind === 'obstacle' && item.type === 'cylinder')) item.yaw = p.yaw;
    syncForm();
    markDirty();
    push(false);
  });
  ctx.scene3d.add(transform);
  applySnap();

  function applySnap() {
    const on = $('snap').checked;
    transform.setTranslationSnap(on ? 0.1 : null);
    transform.setRotationSnap(on ? 15 * DEG : null);
  }
  $('snap').onchange = applySnap;

  function setMode(mode) {
    const canRotate = selection && selection.kind !== 'pad'
      && !(selection.kind === 'obstacle' && selectedItem().type === 'cylinder');
    if (mode === 'rotate' && !canRotate) mode = 'translate';
    transform.setMode(mode);
    transform.showX = mode === 'translate';
    transform.showZ = mode === 'translate';
    transform.showY = mode === 'rotate';
    document.querySelectorAll('#modeBtns button').forEach((b) => b.classList.toggle('active', b.dataset.mode === mode));
  }
  document.querySelectorAll('#modeBtns button').forEach((b) => { b.onclick = () => setMode(b.dataset.mode); });

  // ---------------------------------------------------------------- 数据
  const world = () => ctx.getWorld();
  const content = () => {
    const w = world();
    return { title: w.title, description: w.description || '', start: w.start, obstacles: w.obstacles, pads: w.pads };
  };

  function selectedItem() {
    const w = world();
    if (!selection) return null;
    if (selection.kind === 'start') return w.start;
    return selection.kind === 'pad' ? w.pads[selection.index] : w.obstacles[selection.index];
  }

  function snapshot() {
    undoStack.push(JSON.stringify(content()));
    if (undoStack.length > UNDO_MAX) undoStack.shift();
  }

  function undo() {
    const s = undoStack.pop();
    if (!s) return;
    Object.assign(world(), JSON.parse(s));
    select(null);
    changed();
  }

  function markDirty() {
    world().dirty = true;
    renderDirty();
  }

  /** 数据已修改：重建网格并提交到模拟器 */
  function changed() {
    markDirty();
    ctx.rebuild();
    reattach();
    renderList();
    syncForm();
    push(true);
  }

  /** 提交到模拟器。拖动中节流（120ms），其余立即发送 */
  function push(now) {
    if (pushTimer) clearTimeout(pushTimer);
    pushTimer = setTimeout(send, now ? 0 : 120);
  }

  async function send() {
    pushTimer = null;
    pending++;
    try {
      const r = await ctx.post('/api/world', content());
      if (r.data && r.data.version !== undefined) ctx.setVersion(r.data.version);
    } finally {
      pending--;
    }
  }

  ed.busy = () => ed.active && (dragging || pending > 0 || pushTimer !== null);

  // ---------------------------------------------------------------- 选中
  function findObject(sel) {
    if (!sel) return null;
    return worldGroup.children.find((c) => c.userData.kind === sel.kind && c.userData.index === sel.index) || null;
  }

  function reattach() {
    const obj = findObject(selection);
    if (obj) transform.attach(obj);
    else { transform.detach(); selection = null; }
  }

  function select(sel) {
    selection = sel;
    if (sel && ed.active) {
      reattach();
      setMode(transform.mode);
    } else {
      transform.detach();
    }
    renderForm();
    renderList();
  }

  function pick(ev) {
    const hit = raycast(ev, worldGroup.children, true);
    if (!hit) return null;
    let o = hit.object;
    while (o && !o.userData.kind) o = o.parent;
    return o ? { kind: o.userData.kind, index: o.userData.index } : null;
  }

  const raycaster = new THREE.Raycaster();
  function raycast(ev, objects, recursive = false) {
    const rect = canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((ev.clientX - rect.left) / rect.width) * 2 - 1,
      -((ev.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    return raycaster.intersectObjects(objects, recursive)[0] || null;
  }

  function groundPoint(ev) {
    const hit = raycast(ev, [ground]);
    if (!hit) return null;
    let x = hit.point.x * 100, y = -hit.point.z * 100;
    if ($('snap').checked) { x = Math.round(x / 10) * 10; y = Math.round(y / 10) * 10; }
    return { x, y };
  }

  // ---------------------------------------------------------------- 放置
  function newItem(key, x, y) {
    const w = world();
    if (key === 'pad') {
      const used = new Set(w.pads.map((p) => p.id));
      const id = [1, 2, 3, 4, 5, 6, 7, 8].find((n) => !used.has(n)) || 1;
      return { id, x, y, z: 0 };
    }
    const { label, ...preset } = PRESETS[key];
    return { color: PALETTE[w.obstacles.length % PALETTE.length], ...preset, x, y };
  }

  function startPlacing(key) {
    cancelPlacing();
    placing = key;
    const item = newItem(key, 0, 0);
    ghost = key === 'pad' ? padMesh(item) : obstacleMesh(item);
    ghost.traverse((o) => {
      if (o.material) { o.material = o.material.clone(); o.material.transparent = true; o.material.opacity = 0.45; }
      o.castShadow = false;
    });
    ghost.visible = false;
    ctx.scene3d.add(ghost);
    canvas.style.cursor = 'crosshair';
    document.querySelectorAll('#palette button').forEach((b) => b.classList.toggle('active', b.dataset.add === key));
    $('editHint').textContent = '在地面上单击放置（按住 Shift 连续放置，Esc 取消）';
  }

  function cancelPlacing() {
    placing = null;
    if (ghost) { ctx.scene3d.remove(ghost); ghost = null; }
    canvas.style.cursor = '';
    document.querySelectorAll('#palette button').forEach((b) => b.classList.remove('active'));
    $('editHint').textContent = '';
  }

  function place(ev) {
    const p = groundPoint(ev);
    if (!p) return;
    snapshot();
    const w = world();
    const item = newItem(placing, p.x, p.y);
    let sel;
    if (placing === 'pad') { w.pads.push(item); sel = { kind: 'pad', index: w.pads.length - 1 }; }
    else { w.obstacles.push(item); sel = { kind: 'obstacle', index: w.obstacles.length - 1 }; }
    if (!ev.shiftKey) cancelPlacing();
    changed();
    select(sel);
  }

  document.querySelectorAll('#palette button').forEach((b) => {
    b.onclick = () => (placing === b.dataset.add ? cancelPlacing() : startPlacing(b.dataset.add));
  });

  // ---------------------------------------------------------------- 指针
  let downAt = null;
  canvas.addEventListener('pointerdown', (ev) => {
    if (!ed.active || ev.button !== 0) return;
    downAt = transform.axis ? null : { x: ev.clientX, y: ev.clientY };  // 点在手柄上时交给 TransformControls
  });
  canvas.addEventListener('pointerup', (ev) => {
    if (!ed.active || !downAt || dragging) return;
    const moved = Math.hypot(ev.clientX - downAt.x, ev.clientY - downAt.y);
    downAt = null;
    if (moved > 5) return;  // 拖动视角，不算点击
    if (placing) place(ev);
    else select(pick(ev));
  });
  canvas.addEventListener('pointermove', (ev) => {
    if (!ed.active || !ghost) return;
    const p = groundPoint(ev);
    ghost.visible = !!p;
    if (p) ghost.position.set(p.x / 100, ghost.position.y, -p.y / 100);
  });

  // ---------------------------------------------------------------- 编辑操作
  function removeSelected() {
    if (!selection || selection.kind === 'start') return;
    snapshot();
    const w = world();
    (selection.kind === 'pad' ? w.pads : w.obstacles).splice(selection.index, 1);
    select(null);
    changed();
  }

  function duplicateSelected() {
    if (!selection || selection.kind === 'start') return;
    snapshot();
    const w = world();
    const list = selection.kind === 'pad' ? w.pads : w.obstacles;
    const copy = { ...list[selection.index] };
    copy.x += 30; copy.y -= 30;
    list.push(copy);
    changed();
    select({ kind: selection.kind, index: list.length - 1 });
  }

  $('propDelete').onclick = removeSelected;
  $('propDuplicate').onclick = duplicateSelected;
  $('undoBtn').onclick = undo;

  ed.handleKey = (e) => {
    if (!ed.active) return false;
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 'z') { undo(); return true; }
    if ((e.ctrlKey || e.metaKey) && k === 'd') { duplicateSelected(); return true; }
    if (k === 'delete' || k === 'backspace') { removeSelected(); return true; }
    if (k === 'escape') { if (placing) cancelPlacing(); else select(null); return true; }
    if (k === 'w' || k === 'g') { setMode('translate'); return true; }
    if (k === 'e' || k === 'r') { setMode('rotate'); return true; }
    return false;
  };

  // ---------------------------------------------------------------- 属性面板
  function renderForm() {
    const box = $('props');
    const item = selectedItem();
    $('propActions').hidden = !item || selection.kind === 'start';
    $('modeBtns').hidden = !item;
    if (!item) { box.innerHTML = '<div class="muted">在 3D 视图中单击对象，或从下方列表选择</div>'; return; }
    const kind = selection.kind === 'obstacle' ? item.type : selection.kind;
    const title = selection.kind === 'start' ? '起飞点' : selection.kind === 'pad' ? '挑战卡' : TYPE_NAMES[item.type];
    let html = `<div class="prop-title">${title}</div><div class="prop-grid">`;
    if (selection.kind === 'pad') {
      html += '<label>编号<select data-key="id">' +
        [1, 2, 3, 4, 5, 6, 7, 8].map((n) => `<option value="${n}"${n === item.id ? ' selected' : ''}>m${n}</option>`).join('') +
        '</select></label>';
    }
    for (const [key, label, min, max, step] of FIELDS[kind]) {
      html += `<label>${label}<input type="number" data-key="${key}" min="${min}" max="${max}" step="${step}"></label>`;
    }
    if (selection.kind === 'obstacle') html += `<label>颜色<input type="color" data-key="color"></label>`;
    html += '</div><div class="muted unit">单位：cm</div>';
    box.innerHTML = html;
    box.querySelectorAll('[data-key]').forEach((input) => {
      input.onchange = () => {
        const it = selectedItem();
        if (!it) return;
        snapshot();
        const key = input.dataset.key;
        if (key === 'color') it.color = input.value;
        else {
          let v = Number(input.value);
          if (!Number.isFinite(v)) v = 0;
          v = Math.min(Number(input.max ?? v) || v, Math.max(Number(input.min ?? v) || 0, v));
          if (key === 'id') v = Math.round(v);
          it[key] = v;
        }
        changed();
      };
    });
    syncForm();
  }

  function syncForm() {
    const item = selectedItem();
    if (!item) return;
    $('props').querySelectorAll('[data-key]').forEach((input) => {
      if (document.activeElement === input) return;
      const v = item[input.dataset.key];
      input.value = input.dataset.key === 'color' ? (v || '#8a817c') : (v ?? 0);
    });
  }

  // ---------------------------------------------------------------- 对象列表
  function renderList() {
    const w = world();
    if (!w) return;
    const rows = [{ kind: 'start', index: 0, text: '起飞点', color: '#2f6fde' }];
    w.obstacles.forEach((o, i) => rows.push({
      kind: 'obstacle', index: i, color: o.color,
      text: `${TYPE_NAMES[o.type]} #${i + 1}  (${Math.round(o.x)}, ${Math.round(o.y)})`,
    }));
    w.pads.forEach((p, i) => rows.push({
      kind: 'pad', index: i, color: '#e9e9e4', text: `挑战卡 m${p.id}  (${Math.round(p.x)}, ${Math.round(p.y)})`,
    }));
    const el = $('objList');
    el.innerHTML = '';
    for (const r of rows) {
      const div = document.createElement('div');
      div.className = 'obj-row' + (selection && selection.kind === r.kind && selection.index === r.index ? ' active' : '');
      div.innerHTML = `<i style="background:${r.color}"></i>`;
      div.appendChild(document.createTextNode(r.text));
      div.onclick = () => select({ kind: r.kind, index: r.index });
      el.appendChild(div);
    }
    $('objCount').textContent = `${w.obstacles.length} 个障碍物 · ${w.pads.length} 张挑战卡`;
  }

  // ---------------------------------------------------------------- 场景库
  async function refreshScenes() {
    const r = await fetch('/api/scenes').then((x) => x.json());
    scenes = r.scenes;
    ctx.onScenes(scenes, r.current);
    renderScenes(r.current);
  }

  function renderScenes(current) {
    const el = $('sceneList');
    el.innerHTML = '';
    for (const s of scenes) {
      const div = document.createElement('div');
      div.className = 'scene-row' + (s.id === listSelected ? ' active' : '') + (s.id === current ? ' current' : '');
      div.title = s.description || '';
      div.innerHTML = `<span class="tag ${s.builtin ? 'builtin' : 'user'}">${s.builtin ? '内置' : '我的'}</span>`;
      div.appendChild(document.createTextNode(s.title));
      if (s.id === current) div.insertAdjacentHTML('beforeend', '<span class="cur">当前</span>');
      div.onclick = () => { listSelected = s.id; renderScenes(current); updateSceneButtons(); };
      div.ondblclick = () => { listSelected = s.id; loadSelected(); };
      el.appendChild(div);
    }
    updateSceneButtons();
  }

  function updateSceneButtons() {
    const s = scenes.find((x) => x.id === listSelected);
    $('scLoad').disabled = !s;
    $('scDelete').disabled = !s || s.builtin;
  }

  function confirmDiscard() {
    return !world().dirty || confirm('当前场景有未保存的修改，确定放弃吗？');
  }

  async function loadSelected() {
    if (!listSelected || !confirmDiscard()) return;
    await ctx.post('/api/scene', { name: listSelected });
    select(null);
    undoStack.length = 0;
    await ctx.reloadWorld();
  }

  $('scLoad').onclick = loadSelected;
  $('scNew').onclick = async () => {
    if (!confirmDiscard()) return;
    await ctx.post('/api/scene/new');
    select(null);
    undoStack.length = 0;
    await ctx.reloadWorld();
  };
  $('scDelete').onclick = async () => {
    const s = scenes.find((x) => x.id === listSelected);
    if (!s || s.builtin || !confirm(`删除场景「${s.title}」？此操作不可恢复。`)) return;
    await ctx.post('/api/scenes/delete', { id: s.id });
    listSelected = null;
    await refreshScenes();
  };

  async function save(title, saveAs) {
    if (pushTimer || pending) { await send(); }
    let r = await ctx.post('/api/scenes/save', { title, save_as: saveAs });
    if (r.status === 409) {
      if (!confirm(`已存在名为「${title}」的场景，覆盖它吗？`)) return;
      r = await ctx.post('/api/scenes/save', { title, save_as: saveAs, overwrite: true });
    }
    if (r.status !== 200) { alert('保存失败：' + (r.data.error || r.status)); return; }
    listSelected = r.data.id;
    await ctx.reloadWorld();
  }

  async function saveAs() {
    const w = world();
    const name = prompt('保存为新场景，名称：', w.builtin || !w.scene ? w.title + ' (副本)' : w.title + ' 2');
    if (name && name.trim()) await save(name.trim(), true);
  }

  $('scSave').onclick = () => {
    const w = world();
    if (w.builtin || !w.scene) return saveAs();  // 内置场景 / 新建场景：先起名
    return save($('sceneTitle').value.trim() || w.title, false);
  };
  $('scSaveAs').onclick = saveAs;

  $('sceneTitle').onchange = () => {
    snapshot();
    world().title = $('sceneTitle').value.trim() || '未命名场景';
    markDirty();
    push(true);
  };

  $('scExport').onclick = () => {
    const blob = new Blob([JSON.stringify(content(), null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (world().title || 'scene') + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
  };
  $('scImport').onclick = () => $('importFile').click();
  $('importFile').onchange = async (e) => {
    const f = e.target.files[0];
    e.target.value = '';
    if (!f || !confirmDiscard()) return;
    let data;
    try { data = JSON.parse(await f.text()); } catch { alert('不是有效的 JSON 文件'); return; }
    if (!data.title) data.title = f.name.replace(/\.json$/i, '');
    const r = await ctx.post('/api/scene/new');
    if (r.status === 200) {
      const r2 = await ctx.post('/api/world', data);
      if (r2.status !== 200) { alert('导入失败：' + (r2.data.error || r2.status)); return; }
    }
    select(null);
    undoStack.length = 0;
    await ctx.reloadWorld();
  };

  function renderDirty() {
    const w = world();
    const where = w.builtin ? '内置场景（只读，保存时会另存）' : w.scene ? '我的场景' : '尚未保存';
    $('dirtyMark').textContent = w.dirty ? '● 未保存' : '';
    $('sceneWhere').textContent = where;
  }

  // ---------------------------------------------------------------- 对外
  ed.onWorldLoaded = (w) => {
    if (document.activeElement !== $('sceneTitle')) $('sceneTitle').value = w.title;
    renderDirty();
    if (selection) {
      const list = selection.kind === 'pad' ? w.pads : selection.kind === 'obstacle' ? w.obstacles : [w.start];
      if (!list[selection.index]) selection = null;
    }
    if (ed.active) reattach();
    renderForm();
    renderList();
  };

  ed.refreshScenes = refreshScenes;
  ed.gizmo = transform;

  ed.setActive = (on) => {
    ed.active = on;
    if (!on) { cancelPlacing(); transform.detach(); controls.enabled = true; }
    else { refreshScenes(); if (selection) reattach(); }
    renderForm();
    renderList();
  };

  return ed;
}
