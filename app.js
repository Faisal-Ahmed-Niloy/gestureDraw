'use strict';

const BRIDGE_WS_URL = 'ws://localhost:8765';

const DISP_W = 320;
const DISP_H = 240;
const HDR_H  = 28;
const DRAW_H = DISP_H - HDR_H;   

const SRC_W  = 640;               
const SRC_H  = 480;               


const espCanvas = document.getElementById('esp-canvas');
const espCtx    = espCanvas.getContext('2d');
espCanvas.width  = DISP_W;
espCanvas.height = DRAW_H;
espCtx.fillStyle = '#000';
espCtx.fillRect(0, 0, DISP_W, DRAW_H);


const pcCanvas = document.getElementById('pc-canvas');
const pcCtx    = pcCanvas.getContext('2d');
pcCanvas.width  = SRC_W;
pcCanvas.height = SRC_H;
pcCtx.fillStyle = '#000';
pcCtx.fillRect(0, 0, SRC_W, SRC_H);


function scaleDisplay() {
  const wrap  = document.getElementById('view-esp');
  const frame = document.getElementById('display-frame');
  if (!wrap || !frame) return;
  const availW = wrap.clientWidth  - 32;
  const availH = wrap.clientHeight - 32;
  const scale  = Math.min(availW / DISP_W, availH / DISP_H, 2.0);
  frame.style.transform = `scale(${scale})`;
}

scaleDisplay();
window.addEventListener('resize', scaleDisplay);


function mapEspCoord(rawX, rawY) {
  const sx = Math.round((rawX / SRC_W) * DISP_W);
  const sy = Math.round((rawY / SRC_H) * DRAW_H);
  return [sx, sy];
}


function drawStrokeEsp(points) {
  if (!points || points.length < 2) return;
  espCtx.beginPath();
  espCtx.strokeStyle = '#ffffff';
  espCtx.lineWidth   = 1.5;
  espCtx.lineJoin    = 'round';
  espCtx.lineCap     = 'round';
  const [x0, y0] = mapEspCoord(points[0][0], points[0][1]);
  espCtx.moveTo(x0, y0);
  for (let i = 1; i < points.length; i++) {
    const [x, y] = mapEspCoord(points[i][0], points[i][1]);
    espCtx.lineTo(x, y);
  }
  espCtx.stroke();
}


function drawStrokePc(points) {
  if (!points || points.length < 2) return;
  pcCtx.beginPath();
  pcCtx.strokeStyle = '#ffffff';
  pcCtx.lineWidth   = 2;
  pcCtx.lineJoin    = 'round';
  pcCtx.lineCap     = 'round';
  pcCtx.moveTo(points[0][0], points[0][1]);
  for (let i = 1; i < points.length; i++) {
    pcCtx.lineTo(points[i][0], points[i][1]);
  }
  pcCtx.stroke();
}


function clearBothCanvases() {
  espCtx.fillStyle = '#000';
  espCtx.fillRect(0, 0, DISP_W, DRAW_H);
  pcCtx.fillStyle = '#000';
  pcCtx.fillRect(0, 0, SRC_W, SRC_H);
}

let currentView = 'esp';

const viewEsp      = document.getElementById('view-esp');
const viewPc       = document.getElementById('view-pc');
const toggleBtn    = document.getElementById('btn-toggle-view');
const toggleLabel  = document.getElementById('toggle-btn-label');
const rightLabel   = document.getElementById('right-panel-label');
const rightTag     = document.getElementById('right-panel-tag');

function switchView() {
  if (currentView === 'esp') {
    //show pc canvas
    viewEsp.style.display = 'none';
    viewPc.style.display  = 'flex';
    toggleLabel.textContent  = 'SWITCH TO ESP32';
    rightLabel.textContent   = '🖥 PC Canvas';
    rightTag.textContent     = `${SRC_W}×${SRC_H}`;
    currentView = 'pc';
  } else {
    // show esp mirror
    viewPc.style.display  = 'none';
    viewEsp.style.display = 'flex';
    toggleLabel.textContent  = 'SWITCH TO PC CANVAS';
    rightLabel.textContent   = '🖥 ESP32 Display Mirror';
    rightTag.textContent     = 'ILI9341 · 320×240';
    currentView = 'esp';
    
    scaleDisplay();
  }
}

toggleBtn.addEventListener('click', switchView);


let msgCount    = 0;
let strokeCount = 0;
let totalPts    = 0;

function updateStats(cmd, pts) {
  msgCount++;
  document.getElementById('stat-msgs').textContent = msgCount;
  document.getElementById('stat-cmd').textContent  = cmd.toUpperCase();
  document.getElementById('stat-time').textContent = new Date().toLocaleTimeString();

  if (cmd === 'draw' && pts) {
    strokeCount++;
    totalPts += pts.length;
  }
  if (cmd === 'clear') {
    strokeCount = 0;
    totalPts    = 0;
  }
  document.getElementById('stat-strokes').textContent = strokeCount;
  document.getElementById('stat-pts').textContent     = totalPts;
}

function setWsPill(state) {
  const pill  = document.getElementById('pill-ws');
  const label = document.getElementById('pill-ws-label');
  pill.className    = `pill ${state}`;
  label.textContent = state === 'ok'  ? 'WS: CONNECTED'
                    : state === 'err' ? 'WS: DISCONNECTED'
                    :                   'WS: --';
}

function setSenderPill(state) {
  const pill  = document.getElementById('pill-sender');
  const label = document.getElementById('pill-sender-label');
  if (state === 'busy') {
    pill.className    = 'pill ok';
    label.textContent = 'SENDER: SENDING…';
  } else if (state === 'err') {
    pill.className    = 'pill err';
    label.textContent = 'SENDER: FAILED';
  } else {
    pill.className    = 'pill ok';
    label.textContent = 'SENDER: IDLE';
  }
}

function setGestureBadge(g) {
  const el = document.getElementById('gesture-badge');
  el.textContent = `GESTURE: ${g || '—'}`;
  el.className   = `gesture-badge${g && g !== 'IDLE' ? ' active' : ''}`;
}

function setEspStatus(ip, wsOk) {
  if (ip) {
    document.getElementById('esp-title').textContent = `Gesture Draw|${ip}`;
    document.getElementById('stat-ip').textContent   = ip;
  }
  document.getElementById('esp-status-bar').textContent =
    `WiFi:OK WS:${wsOk ? 'OK' : '--'}`;
}

function flashPanel(id) {
  const el = document.getElementById(id);
  el.classList.remove('flash-send');
  void el.offsetWidth;
  el.classList.add('flash-send');
}

const camImg         = document.getElementById('camera-feed');
const camPlaceholder = document.getElementById('cam-placeholder');
const camRes         = document.getElementById('cam-res');

function showFrame(b64jpeg) {
  camImg.src = `data:image/jpeg;base64,${b64jpeg}`;
  if (camImg.style.display === 'none') {
    camImg.style.display         = 'block';
    camPlaceholder.style.display = 'none';
  }
}

camImg.onload = () => {
  camRes.textContent = `${camImg.naturalWidth}×${camImg.naturalHeight}`;
};


let bridgeWs    = null;
let reconnTimer = null;

function connectBridge() {
  if (bridgeWs) return;

  bridgeWs = new WebSocket(BRIDGE_WS_URL);

  bridgeWs.onopen = () => {
    console.log('[Bridge] Connected');
    setWsPill('ok');
    if (reconnTimer) { clearTimeout(reconnTimer); reconnTimer = null; }
  };

  bridgeWs.onclose = () => {
    console.log('[Bridge] Disconnected — retrying in 2 s');
    setWsPill('err');
    bridgeWs    = null;
    reconnTimer = setTimeout(connectBridge, 2000);
  };

  bridgeWs.onerror = (e) => console.warn('[Bridge] Error', e);

  bridgeWs.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }

    switch (msg.type) {

      case 'frame':
        showFrame(msg.data);
        break;

      case 'draw':
        drawStrokeEsp(msg.points);
        drawStrokePc(msg.points);
        updateStats('draw', msg.points);
        flashPanel('panel-display');
        break;

      case 'clear':
        clearBothCanvases();
        updateStats('clear', null);
        flashPanel('panel-display');
        break;

      case 'status':
        setGestureBadge(msg.gesture);
        setSenderPill(msg.sender_busy ? 'busy' : !msg.sender_ok ? 'err' : 'ok');
        setEspStatus(msg.esp_ip, msg.ws_connected);
        if (msg.strokes !== undefined) {
          document.getElementById('stat-strokes').textContent = msg.strokes;
          document.getElementById('stat-pts').textContent     = msg.pts;
          strokeCount = msg.strokes;
          totalPts    = msg.pts;
        }
        break;
    }
  };
}


setWsPill('idle');
setSenderPill('ok');
connectBridge();

setInterval(() => {
  document.getElementById('stat-time').textContent = new Date().toLocaleTimeString();
}, 1000);