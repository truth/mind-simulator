// 机载摄像头视频流：飞机收到 streamon 后，把第一视角画面以 960×720 渲染并用 WebCodecs 编码为
// H.264（Annex-B，与真机相同），逐帧 POST 给模拟器，由模拟器按 1460 字节分片转发到客户端 UDP 11111。
// 编码在浏览器中完成，因此需要保持 3D 界面打开；WebCodecs 仅在安全上下文（127.0.0.1 / localhost）可用。
import * as THREE from 'three';

const WIDTH = 960, HEIGHT = 720, FPS = 25, GOP = FPS;   // 每秒一个关键帧，客户端中途加入也能尽快出画面
const CODEC = 'avc1.42001f';                              // H.264 Baseline Level 3.1
const MAX_BACKLOG = 8;                                     // 待发送帧积压超过该值时丢弃，等下一个关键帧

export function createVideoStreamer({ scene, fpvCam, placeFpv, hideWhileRendering }) {
  const canvas = document.createElement('canvas');
  canvas.width = WIDTH; canvas.height = HEIGHT;
  let renderer = null;              // 首次推流时才创建，避免平时多占一个 WebGL 上下文
  const cam = fpvCam.clone();
  cam.aspect = WIDTH / HEIGHT;
  cam.updateProjectionMatrix();

  const streams = new Map();        // 飞机序号 → { encoder, queue, sending, frames, last, error }
  let support = null;               // null 未检测 / true / 错误说明

  async function checkSupport() {
    if (support !== null) return;
    support = '检测中';
    if (typeof VideoEncoder === 'undefined') {
      support = window.isSecureContext ? '浏览器不支持 WebCodecs' : '请用 http://127.0.0.1:8080 打开（WebCodecs 需安全上下文）';
      return;
    }
    try {
      const r = await VideoEncoder.isConfigSupported(config());
      support = r.supported ? true : '浏览器不支持 H.264 编码';
    } catch (e) {
      support = '浏览器不支持 H.264 编码：' + e.message;
    }
  }

  function config() {
    return { codec: CODEC, width: WIDTH, height: HEIGHT, bitrate: 1_500_000, framerate: FPS,
      latencyMode: 'realtime', avc: { format: 'annexb' } };
  }

  function start(i) {
    const st = { queue: [], sending: false, frames: 0, last: 0, waitKey: false };
    st.encoder = new VideoEncoder({
      output: (chunk) => {
        if (st.waitKey && chunk.type !== 'key') return;
        st.waitKey = false;
        const buf = new Uint8Array(chunk.byteLength);
        chunk.copyTo(buf);
        if (st.queue.length >= MAX_BACKLOG) { st.queue.length = 0; st.waitKey = true; st.forceKey = true; return; }
        st.queue.push(buf);
        pump(i, st);
      },
      error: (e) => { st.error = e.message; },
    });
    st.encoder.configure(config());
    streams.set(i, st);
  }

  function stop(i) {
    const st = streams.get(i);
    if (!st) return;
    try { st.encoder.close(); } catch { /* 已关闭 */ }
    streams.delete(i);
  }

  // 顺序发送，保证帧序（并发请求在多线程 HTTP 服务端可能乱序）
  async function pump(i, st) {
    if (st.sending) return;
    st.sending = true;
    while (st.queue.length && streams.get(i) === st) {
      const body = st.queue.shift();
      try {
        await fetch(`/api/video?drone=${i}`, { method: 'POST', body,
          headers: { 'Content-Type': 'application/octet-stream' } });
      } catch { /* 模拟器重启中，丢弃 */ }
    }
    st.sending = false;
  }

  // 每个渲染帧调用一次；states 为最新状态快照中的 drones，models 为对应的 3D 模型
  function tick(states, models) {
    const now = performance.now();
    states.forEach((s, i) => {
      const want = s.stream && models[i] && models[i].pos;
      if (!want) { stop(i); return; }
      checkSupport();
      if (support !== true) return;
      if (!streams.has(i)) start(i);
      const st = streams.get(i);
      if (st.error || now - st.last < 1000 / FPS || st.encoder.encodeQueueSize > 2) return;
      st.last = now;
      if (!renderer) renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
      placeFpv(cam, models[i]);
      hideWhileRendering(models[i], () => renderer.render(scene, cam));
      const vf = new VideoFrame(canvas, { timestamp: Math.round(now * 1000) });
      const keyFrame = st.frames % GOP === 0 || st.forceKey;
      st.forceKey = false;
      st.encoder.encode(vf, { keyFrame });
      vf.close();
      st.frames++;
    });
    for (const i of streams.keys()) if (i >= states.length) stop(i);
  }

  // 画中画标签用的状态说明
  function status(i) {
    const st = streams.get(i);
    if (st) return st.error ? '编码出错：' + st.error : `推流中 ${WIDTH}×${HEIGHT}`;
    return typeof support === 'string' && support !== '检测中' ? support : '';
  }

  return { tick, status };
}
