/**
 * 《借星》· 网师园的轨道移植 —— 网页漫游应用逻辑
 * 由 esbuild 打包为 app.bundle.js（IIFE，不依赖 CDN、不依赖 ES module 环境）
 * 支持三种运行方式：
 *   1. http 本地服务（start.command）
 *   2. file:// 直接双击 standalone.html（模型与脚本全部内嵌）
 *   3. 部署到任意静态托管
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { PointerLockControls } from 'three/examples/jsm/controls/PointerLockControls.js';

const EYE = 1.65;
const SPEED = 3.4, RUN = 7.0, FLY = 9.0;
const BOUND = { x: 28.5, z: 18.5 };

/**
 * 主要建筑的阻挡盒（glTF / Three.js 坐标，XZ 平面）。
 * 坐标换算规则：Blender(Z-up) -> glTF(Y-up) 为 gx=x, gy=z, gz=-y。
 */
const COLLIDERS = [
  // 主厅（南面 z=-6 留月洞门缺口 x∈(0.4,3.6)）
  [-4.3, -14.3,  8.3, -13.7],   // 北墙
  [-4.3, -14.3, -3.7,  -7.7],   // 西墙
  [ 7.7, -14.3,  8.3,  -7.7],   // 东墙
  [-4.3,  -6.3,  0.4,  -5.7],   // 南墙左段
  [ 3.6,  -6.3,  8.3,  -5.7],   // 南墙右段
  // 门厅（南面 z=-3.5 留门洞 x∈(-20.5,-17.5)）
  [-22.3, -8.7, -15.7, -8.1],   // 北墙
  [-22.3, -8.7, -21.7, -3.3],   // 西墙
  [-16.3, -8.7, -15.7, -3.3],   // 东墙
  [-22.3, -3.7, -20.5, -3.1],   // 南墙左垛
  [-17.5, -3.7, -15.7, -3.1],   // 南墙右垛
  // 殿春簃（Blender 中心 (-13,-12) -> glTF (-13,12)；东面开敞）
  [-17.5,   7.85, -8.5,  8.15], // 北墙（Blender y=-8 -> glTF z=8）
  [-17.65, 8.0,  -17.35, 16.0], // 西墙（Blender x=-17.5）
  // 濯缨水阁（Blender 中心 (-3.2,-8) -> glTF (-3.2,8)；东面临水开敞）
  [-5.7,   9.85, -0.7, 10.15],  // 南墙（Blender y=-10 -> glTF z=10）
  [-5.85, 6.0,  -5.55, 10.0],   // 西墙（Blender x=-5.7）
  // 彩霞池水面（几何池岸 x∈(-2,14), z∈(-2.5,9.5)；碰撞盒贴岸留 0.03 容差）
  // 引静桥处留南北通道 x∈(10.7,12.3)，桥面几何贯通
  [-1.97, -2.53, 10.7,  9.53],  // 池西
  [12.3,  -2.53, 13.97, 9.53],  // 池东
];

function blocked(x, z){
  if (Math.abs(x) > BOUND.x || Math.abs(z) > BOUND.z) return true;
  for (const c of COLLIDERS){
    if (x > c[0] && x < c[2] && z > c[1] && z < c[3]) return true;
  }
  return false;
}

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x070a11, 0.0075);
const camera = new THREE.PerspectiveCamera(62, innerWidth/innerHeight, 0.1, 900);
const renderer = new THREE.WebGLRenderer({ antialias:true, powerPreference:'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
document.body.appendChild(renderer.domElement);

scene.add(new THREE.HemisphereLight(0x8fb6e8, 0x0d1018, 0.55));
scene.add(new THREE.AmbientLight(0x35405a, 0.9));
const sun = new THREE.DirectionalLight(0xdfe8ff, 1.15);
sun.position.set(-40, 90, 60); scene.add(sun);
const rim = new THREE.DirectionalLight(0x4f7fbf, 0.5);
rim.position.set(60, 40, -80); scene.add(rim);
const lamp = new THREE.PointLight(0xffd9a0, 26, 26, 2);
lamp.position.set(2, 4.2, -8); scene.add(lamp);

const controls = new PointerLockControls(camera, document.body);
const SPAWN = new THREE.Vector3(2, EYE, -8);   // 主厅内，正对南面月洞门
camera.position.copy(SPAWN);
camera.rotation.set(0, Math.PI, 0);            // 朝南（月洞门 / 舷窗方向）
camera.rotation.order = "YXZ";

let anchors = [], visited = new Set(), flying = false;
let started = false, dragging = false, lastX = 0, lastY = 0;

const card = document.getElementById('card');
const toast = document.getElementById('toast');

function showToast(t){
  toast.textContent = t; toast.style.opacity = 1;
  clearTimeout(showToast._t); showToast._t = setTimeout(()=>toast.style.opacity=0, 1400);
}

/* ---------- 罗盘方向（世界坐标 8 向） ---------- */
function compass(dx, dz){
  const a = Math.atan2(dx, -dz);           // 0=北(-z), π/2=东(+x), π=南(+z)
  const names = ['北','东北','东','东南','南','西南','西','西北'];
  let i = Math.round(a / (Math.PI / 4));
  i = ((i % 8) + 8) % 8;
  return names[i];
}

/* ---------- 锚点卡片 ---------- */
function updateCard(){
  const p = camera.position;
  let hit = null;
  for (const a of anchors){
    const d = Math.hypot(p.x - a.pos[0], p.z - a.pos[2]);
    if (d < a.radius){ hit = a; break; }
  }
  if (hit){
    card.querySelector('.id').textContent = hit.id + ' · 空间语法';
    card.querySelector('h2').textContent = hit.title;
    card.querySelector('.sub').textContent = hit.sub;
    card.querySelector('p').textContent = hit.text;
    card.classList.add('on');
    if (!visited.has(hit.id)){
      visited.add(hit.id);
      document.getElementById('cnt').textContent = visited.size;
      const idx = anchors.indexOf(hit);
      const el = document.querySelector('#rail span[data-i="'+idx+'"]');
      if (el) el.classList.add('on');
    }
  } else {
    card.classList.remove('on');
  }
}

/* ---------- 导航：当前位置高亮 + 下一处引导 ---------- */
function updateGuide(){
  if (!anchors.length) return;
  const p = camera.position;
  let near = 0, nd = 1e9;
  anchors.forEach((a, i) => {
    const d = Math.hypot(p.x - a.pos[0], p.z - a.pos[2]);
    if (d < nd){ nd = d; near = i; }
  });
  document.querySelectorAll('#rail span').forEach((el, i) => {
    el.classList.toggle('cur', i === near);
  });
  const g = document.getElementById('guide');
  if (visited.size >= anchors.length){
    g.textContent = '已遍览五处空间 · 按 F 飞起俯瞰全园';
    return;
  }
  let next = null, ndd = 1e9;
  anchors.forEach(a => {
    if (visited.has(a.id)) return;
    const d = Math.hypot(p.x - a.pos[0], p.z - a.pos[2]);
    if (d < ndd){ ndd = d; next = a; }
  });
  if (next){
    const dx = next.pos[0] - p.x, dz = next.pos[2] - p.z;
    g.textContent = '下一处 · ' + next.title.split(' · ')[0] +
      '（' + compass(dx, dz) + ' ' + Math.round(ndd) + ' 米）';
  }
}

/* ---------- 模型加载（支持内嵌 base64，供 standalone.html 使用） ---------- */
function b64ToBuf(b64){
  const s = atob(b64), n = s.length, u8 = new Uint8Array(n);
  for (let i = 0; i < n; i++) u8[i] = s.charCodeAt(i);
  return u8.buffer;
}

const bar = document.getElementById('bar'), pct = document.getElementById('pct');
let slowTip = null;

function failLoading(msg){
  document.querySelector('#loading .t').innerHTML = msg;
  clearTimeout(slowTip);
}

function loadModel(){
  if (window.__EMBEDDED_GLB__){
    try {
      const buf = b64ToBuf(window.__EMBEDDED_GLB__);
      new GLTFLoader().parse(buf, '', (gltf) => {
        gltf.scene.traverse(o => {
          if (o.isMesh){ o.castShadow = false; o.receiveShadow = false; o.frustumCulled = false; }
        });
        scene.add(gltf.scene);
        document.getElementById('loading').classList.add('hide');
        document.getElementById('intro').classList.remove('hide');
      }, (err) => { failLoading('内嵌模型解析失败，请使用 start.command 方式打开。'); console.error(err); });
    } catch (e){
      failLoading('内嵌模型解析失败，请使用 start.command 方式打开。');
      console.error(e);
    }
    return;
  }
  const loader = new GLTFLoader();
  loader.load('assets/garden.glb?v=4', (gltf) => {
    const model = gltf.scene;
    model.traverse(o => {
      if (o.isMesh){ o.castShadow = false; o.receiveShadow = false; o.frustumCulled = false; }
    });
    scene.add(model);
    document.getElementById('loading').classList.add('hide');
    document.getElementById('intro').classList.remove('hide');
  }, (e) => {
    if (e.total){ const k = Math.round(e.loaded / e.total * 100); bar.style.width = k+'%'; pct.textContent = k+'%'; }
  }, (err) => {
    failLoading('模型加载失败：请通过 start.command 启动本地服务后访问，或双击 standalone.html。');
    console.error(err);
  });
}

function loadAnchors(){
  // standalone.html 注入的 __EMBEDDED_ANCHORS__ 可能是已解析的对象，也可能是 JSON 文本，
  // 两种形态都要兼容：对对象直接 JSON.parse 会因 "[object Object]" 抛异常，导致
  // standalone 模式下五个叙事锚点全部失效。
  const raw = window.__EMBEDDED_ANCHORS__;
  if (raw){
    try {
      const d = (typeof raw === 'string') ? JSON.parse(raw) : raw;
      anchors = (d && d.anchors) || [];
      if (d && d.spawn) SPAWN.set(d.spawn[0], d.spawn[1], d.spawn[2]);
    } catch (e){ console.warn('内嵌锚点解析失败'); }
    return;
  }
  fetch('assets/anchors.json?v=4').then(r => r.json()).then(d => {
    anchors = d.anchors || [];
    if (d.spawn) SPAWN.set(d.spawn[0], d.spawn[1], d.spawn[2]);
  }).catch(()=>{ console.warn('anchors.json 未加载，使用内置默认值'); });
}

loadModel();
loadAnchors();
slowTip = setTimeout(() => {
  if (!document.getElementById('loading').classList.contains('hide')){
    failLoading('加载较慢（超过 15 秒）… 请确认使用 Chrome / Edge 打开，并等待进度条走完。');
  }
}, 15000);

/* ---------- 交互 ---------- */
document.getElementById('intro').addEventListener('click', () => {
  document.getElementById('intro').classList.add('hide');
  started = true;
  camera.position.copy(SPAWN);
  camera.rotation.set(0, Math.PI, 0);
  try { controls.lock(); } catch (e) { showToast('鼠标锁定不可用，按住左键拖动即可转向'); }
});
controls.addEventListener('lock', () => { started = true; });
controls.addEventListener('unlock', () => {
  if (started) showToast('已释放鼠标 · 点击画面重新锁定');
});
renderer.domElement.addEventListener('mousedown', (e) => {
  if (!started) return;
  if (!controls.isLocked){ try { controls.lock(); } catch (err) {} }
  dragging = true; lastX = e.clientX; lastY = e.clientY;
});
window.addEventListener('mouseup', () => { dragging = false; });
window.addEventListener('mousemove', (e) => {
  if (!dragging || controls.isLocked) return;
  const dx = e.clientX - lastX, dy = e.clientY - lastY;
  lastX = e.clientX; lastY = e.clientY;
  camera.rotation.y -= dx * 0.0032;
  camera.rotation.x -= dy * 0.0032;
  camera.rotation.x = Math.max(-Math.PI / 2 + 0.05, Math.min(Math.PI / 2 - 0.05, camera.rotation.x));
});

const keys = {};
let flyTargetY = EYE, lastFlyY = 7.6;

/* 切换飞行观察：首次自动升舱；之后记住上次飞行高度，不再来回甩 */
function setFlying(on){
  flying = on;
  if (on){
    flyTargetY = Math.max(7.6, lastFlyY);
  } else {
    lastFlyY = Math.max(flyTargetY, camera.position.y);
    flyTargetY = EYE;
  }
  document.body.classList.toggle('flying', on);
  const b = document.getElementById('btn-fly');
  if (b){ b.textContent = on ? '行走模式' : '飞行观察'; b.classList.toggle('on', on); }
  showToast(on ? '飞行观察模式 · 已升舱，空格或「上升」「下降」调整高度' : '行走模式');
}

function goHome(){
  camera.position.copy(SPAWN);
  camera.rotation.set(0, Math.PI, 0);
  flyTargetY = flying ? Math.max(7.6, lastFlyY) : EYE;
  showToast('已回到起点');
}

/* 屏幕按钮：鼠标点击即可触发，不依赖键盘焦点（预览面板 / 触屏同样可用） */
(function bindButtons(){
  const hold = (el, code) => {
    if (!el) return;
    el.addEventListener('pointerdown', (e) => { e.preventDefault(); keys[code] = true; });
    const off = () => { keys[code] = false; };
    el.addEventListener('pointerup', off);
    el.addEventListener('pointerleave', off);
    el.addEventListener('pointercancel', off);
  };
  hold(document.getElementById('btn-up'), 'Space');
  hold(document.getElementById('btn-down'), 'KeyC');
  const bf = document.getElementById('btn-fly');
  if (bf) bf.addEventListener('click', () => setFlying(!flying));
  const bh = document.getElementById('btn-home');
  if (bh) bh.addEventListener('click', goHome);
})();

addEventListener('keydown', e => {
  if (e.code === 'Space') e.preventDefault();
  if (e.repeat) return;                 // 长按不重复触发切换（否则长按 F 会反复横跳，像"没反应"）
  if (e.code === 'KeyF') setFlying(!flying);
  if (e.code === 'KeyR') goHome();
  if (e.code === 'KeyM') toggleMap();
  keys[e.code] = true;
});
addEventListener('keyup', e => { keys[e.code] = false; });
addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

const clock = new THREE.Clock();
function tick(){
  requestAnimationFrame(tick);
  const dt = Math.min(clock.getDelta(), 0.05);
  if (started){
    const v = (keys['ShiftLeft']||keys['ShiftRight']) ? RUN : SPEED;
    const s = (flying ? FLY : v) * dt;
    const prev = camera.position.clone();
    if (keys['KeyW']) controls.moveForward(s);
    if (keys['KeyS']) controls.moveForward(-s);
    if (blocked(camera.position.x, camera.position.z)){
      camera.position.x = prev.x; camera.position.z = prev.z;
    }
    const mid = camera.position.clone();
    if (keys['KeyA']) controls.moveRight(-s);
    if (keys['KeyD']) controls.moveRight(s);
    if (blocked(camera.position.x, camera.position.z)){
      camera.position.x = mid.x; camera.position.z = mid.z;
    }
    if (flying){
      if (keys['Space']) flyTargetY = Math.min(28, flyTargetY + 9.0 * dt);
      if (keys['KeyC'])   flyTargetY = Math.max(0.6, flyTargetY - 9.0 * dt);
      lastFlyY = flyTargetY;
      camera.position.y += (flyTargetY - camera.position.y) * Math.min(1, dt * 2.4);
    } else {
      camera.position.y += (EYE - camera.position.y) * Math.min(1, dt * 6.0);
    }
    updateCard();
    updateGuide();
    drawMinimap();
  }
  renderer.render(scene, camera);
}
/* ---------- 探测地图（右下角小地图） ----------
 * 俯视平面图。坐标为 glTF / Three.js XZ 平面（与碰撞盒同一坐标系），
 * 数据与 blend/scripts/build_garden.py 的构件参数一致。 */
const mm = document.getElementById('minimap');
const mctx = mm.getContext('2d');
const MM_W = 230, MM_H = 164;
const DPR = Math.min(window.devicePixelRatio || 1, 2);
mm.width = MM_W * DPR; mm.height = MM_H * DPR;
mctx.scale(DPR, DPR);
const MS = Math.min((MM_W - 18) / 64, (MM_H - 18) / 44);   // ≈3.31 px/m
const mmx = (x) => MM_W / 2 + (x - 1) * MS;
const mmz = (z) => MM_H / 2 + z * MS;

const MAP_ROOMS = [            // [x0, z0, x1, z1]
  [-4.0, -14.0,  8.0, -6.0],   // 主厅
  [-22.0, -8.5, -16.0, -3.5],  // 门厅
  [-17.5,  8.0,  -8.5, 16.0],  // 殿春簃
  [-5.7,   6.0,  -0.7, 10.0],  // 濯缨水阁
];
const MAP_CORRIDOR = [[-16, -4], [-14, 4], [-6, 6], [-4.6, -1]];   // 曲廊
const MAP_STANDS = [ [12.0, 10.5, 2.6], [-9.6, 9.4, 1.9] ];        // 月到风来亭 / 半亭

function toggleMap(){
  const show = mm.style.display === 'none';
  mm.style.display = show ? '' : 'none';
  showToast(show ? '探测地图已打开' : '探测地图已关闭（按 M 重新打开）');
}

function drawMinimap(){
  if (mm.style.display === 'none') return;
  const c = mctx;
  c.clearRect(0, 0, MM_W, MM_H);

  // 舱体圆（轨道舱横截面）
  c.beginPath(); c.arc(mmx(2), mmz(0), 26 * MS, 0, Math.PI * 2);
  c.strokeStyle = 'rgba(140,170,215,.32)'; c.lineWidth = 1;
  c.setLineDash([4, 4]); c.stroke(); c.setLineDash([]);

  // 地面范围
  c.strokeStyle = 'rgba(255,255,255,.10)';
  c.strokeRect(mmx(-30), mmz(-20), 60 * MS, 40 * MS);

  // 彩霞池
  c.fillStyle = 'rgba(30,80,128,.92)';
  c.fillRect(mmx(-2), mmz(-2.5), 16 * MS, 12 * MS);
  c.strokeStyle = 'rgba(96,165,225,.55)'; c.lineWidth = 1;
  c.strokeRect(mmx(-2), mmz(-2.5), 16 * MS, 12 * MS);

  // 建筑体量
  c.fillStyle = 'rgba(54,65,88,.95)';
  for (const r of MAP_ROOMS){
    c.fillRect(mmx(r[0]), mmz(r[1]), (r[2] - r[0]) * MS, (r[3] - r[1]) * MS);
  }
  // 攒尖亭（六角示意）
  for (const t of MAP_STANDS){
    c.beginPath();
    for (let k = 0; k < 6; k++){
      const a = Math.PI / 6 + k * Math.PI / 3;
      const px = mmx(t[0]) + Math.cos(a) * t[2] * MS;
      const pz = mmz(t[1]) + Math.sin(a) * t[2] * MS;
      k ? c.lineTo(px, pz) : c.moveTo(px, pz);
    }
    c.closePath(); c.fill();
  }
  // 曲廊
  c.strokeStyle = 'rgba(74,88,116,.95)'; c.lineWidth = 2.9 * MS;
  c.lineJoin = 'round'; c.lineCap = 'round';
  c.beginPath();
  MAP_CORRIDOR.forEach((p, i) => { i ? c.lineTo(mmx(p[0]), mmz(p[1])) : c.moveTo(mmx(p[0]), mmz(p[1])); });
  c.stroke();
  // 引静桥 + 石板路
  c.fillStyle = 'rgba(122,134,158,.95)';
  c.fillRect(mmx(10.75), mmz(-3.2), 1.5 * MS, 13.4 * MS);
  c.fillStyle = 'rgba(122,134,158,.5)';
  c.fillRect(mmx(0.7), mmz(-6.5), 2.6 * MS, 3.75 * MS);

  // 锚点触发区 + 状态点
  for (const a of anchors){
    const x = mmx(a.pos[0]), z = mmz(a.pos[2]);
    c.beginPath(); c.arc(x, z, Math.max(2.5, a.radius * MS), 0, Math.PI * 2);
    c.fillStyle = visited.has(a.id) ? 'rgba(230,200,138,.15)' : 'rgba(111,180,232,.10)';
    c.fill();
    c.beginPath(); c.arc(x, z, 2.6, 0, Math.PI * 2);
    c.fillStyle = visited.has(a.id) ? '#e6c88a' : 'rgba(165,205,240,.9)';
    c.fill();
  }

  // 玩家：视野楔 + 方向箭头
  const p = camera.position;
  const yaw = camera.rotation.y;
  const fx = -Math.sin(yaw), fz = -Math.cos(yaw);
  c.save();
  c.translate(mmx(p.x), mmz(p.z));
  c.rotate(Math.atan2(fz, fx));
  c.beginPath(); c.moveTo(0, 0);
  c.arc(0, 0, 34, -0.52, 0.52);
  c.closePath();
  c.fillStyle = 'rgba(111,180,232,.14)'; c.fill();
  c.beginPath();
  c.moveTo(7.5, 0); c.lineTo(-4.5, 4.2); c.lineTo(-4.5, -4.2);
  c.closePath();
  c.fillStyle = '#ffffff'; c.fill();
  c.restore();

  // 标注
  c.font = '9px "PingFang SC","Hiragino Sans GB",sans-serif';
  c.textAlign = 'center';
  c.fillStyle = 'rgba(154,163,178,.85)';
  c.fillText('舱内平面 · 北', MM_W / 2, 11);
  c.fillStyle = 'rgba(230,200,138,.9)';
  c.textAlign = 'left';
  c.fillText(flying ? ('高度 ' + p.y.toFixed(1) + ' m') : '行走模式', 6, MM_H - 6);
  c.textAlign = 'right';
  c.fillStyle = 'rgba(154,163,178,.7)';
  c.fillText('S1–S5 为叙事锚点', MM_W - 6, MM_H - 6);
  c.textAlign = 'start';
}

tick();

/* 诊断接口：供自动化测试读取场景状态 */
window.__scene = scene;
window.__camera = camera;
window.__started = () => started;
window.__anchors = () => anchors;
