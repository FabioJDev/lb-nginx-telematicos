'use strict';
/**
 * backend/server.js — Backend HTTP instrumentado (Proyecto 2, sección 7.1).
 *
 * Servidor Node.js que usa ÚNICAMENTE el módulo 'http' (sin dependencias).
 * Cada réplica identifica el nodo que responde (cabecera X-Backend-Node),
 * simula costo controlado (latencia y CPU), permite inyectar fallos y expone
 * métricas en formato Prometheus. Soporta alta concurrencia porque la latencia
 * simulada usa temporizadores (setTimeout), nunca bloqueo.
 *
 * Endpoints:
 *   GET  /               Tienda web (public/index.html) si hay base de datos; si no, /nodo
 *   GET  /nodo           Página HTML que identifica el nodo (color por hostname)
 *   GET  /ready          200 si PostgreSQL y el almacén de sesiones responden
 *   /api/products, /api/login, /api/cart, /api/orders…  tienda (ver tienda.js)
 *   GET  /api/info       JSON: node, hostname, ip, pid, uptime, requests_served, inflight
 *   GET  /api/work?ms=N&cpu=M  Espera N ms y/o consume M ms de CPU
 *   GET  /api/mixed      90 % rápidas (~5 ms) / 10 % lentas (~300 ms)
 *   GET  /health         200 si sano; 503 si modo 'unhealthy' o apagándose
 *   GET  /metrics        Métricas Prometheus
 *   GET  /admin/fault    Modo de falla actual
 *   POST /admin/fault    {"mode": none|error500|slow|hang|unhealthy, "delayMs": n}
 *   POST /admin/crash    Termina el proceso con código 1 (Docker lo reinicia)
 *
 * Variables de entorno:
 *   PORT (3000), NODE_NAME (hostname), NODE_LABEL (prefijo del nombre),
 *   BASE_DELAY_MS (0), FAULT_MODE (none), FAULT_DELAY_MS (2000),
 *   SHUTDOWN_TIMEOUT_MS (10000)
 */

const http = require('http');
const os = require('os');
const crypto = require('crypto');

// ---------------------------------------------------------------------------
// Configuración
// ---------------------------------------------------------------------------
const PORT = toInt(process.env.PORT, 3000);
const HOSTNAME = os.hostname();
const NODE_LABEL = (process.env.NODE_LABEL || '').trim();
const NODE_NAME = (process.env.NODE_NAME || '').trim() || (NODE_LABEL ? `${NODE_LABEL}-${HOSTNAME}` : HOSTNAME);
const BASE_DELAY_MS = Math.max(0, toInt(process.env.BASE_DELAY_MS, 0));
const SHUTDOWN_TIMEOUT_MS = toInt(process.env.SHUTDOWN_TIMEOUT_MS, 10000);
const MAX_WORK_MS = 60000; // tope de espera por petición
const MAX_CPU_MS = 5000; // tope de CPU por petición

const VALID_MODES = ['none', 'error500', 'slow', 'hang', 'unhealthy'];

/** Estado de inyección de fallos (E-07, E-08). */
const fault = {
  mode: VALID_MODES.includes(process.env.FAULT_MODE) ? process.env.FAULT_MODE : 'none',
  delayMs: Math.max(0, toInt(process.env.FAULT_DELAY_MS, 2000)),
};

// ---------------------------------------------------------------------------
// Estado y métricas
// ---------------------------------------------------------------------------
const startedAt = Date.now();
let requestsServed = 0;
let inflight = 0;
let shuttingDown = false;

/** Contadores por código de estado. */
const requestsByStatus = new Map();
/** Histograma de duración (segundos) para Grafana (histogram_quantile). */
const BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10];
const bucketCounts = new Array(BUCKETS.length).fill(0);
let durationSum = 0;
let durationCount = 0;

/** Respuestas "colgadas" (modo hang) para poder cerrarlas al apagar. */
const hangingResponses = new Set();

const IP = firstIPv4();
const COLOR = colorFromName(NODE_NAME);

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------
function toInt(value, fallback) {
  const n = parseInt(value, 10);
  return Number.isFinite(n) ? n : fallback;
}

function firstIPv4() {
  const ifaces = os.networkInterfaces();
  for (const name of Object.keys(ifaces)) {
    for (const addr of ifaces[name] || []) {
      if (addr.family === 'IPv4' && !addr.internal) return addr.address;
    }
  }
  return '127.0.0.1';
}

/** Color HSL estable derivado del nombre del nodo (cada réplica tiene su color). */
function colorFromName(name) {
  const hash = crypto.createHash('md5').update(name).digest();
  const hue = ((hash[0] << 8) | hash[1]) % 360;
  return `hsl(${hue}, 65%, 45%)`;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Consume CPU durante 'ms' milisegundos (bucle activo, a propósito). */
function burnCpu(ms) {
  const end = process.hrtime.bigint() + BigInt(ms) * 1000000n;
  let x = 0;
  while (process.hrtime.bigint() < end) {
    x = (x + Math.sqrt(x + 1)) % 1000003;
  }
  return x;
}

function observeDuration(seconds) {
  durationSum += seconds;
  durationCount += 1;
  for (let i = 0; i < BUCKETS.length; i++) {
    if (seconds <= BUCKETS[i]) bucketCounts[i] += 1;
  }
}

function readBody(req, limit = 64 * 1024) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (chunk) => {
      data += chunk;
      if (data.length > limit) {
        reject(new Error('body demasiado grande'));
        req.destroy();
      }
    });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

function baseHeaders(extra = {}) {
  return {
    'X-Backend-Node': NODE_NAME,
    'X-Backend-Inflight': String(inflight),
    'Cache-Control': 'no-store',
    ...extra,
  };
}

function send(res, status, body, headers = {}) {
  if (res.writableEnded || res.destroyed) return;
  const isObject = typeof body === 'object' && body !== null && !Buffer.isBuffer(body);
  const payload = isObject ? JSON.stringify(body) : body;
  const type = isObject ? 'application/json; charset=utf-8' : headers['Content-Type'] || 'text/plain; charset=utf-8';
  res.writeHead(status, baseHeaders({ ...headers, 'Content-Type': type, 'Content-Length': Buffer.byteLength(payload) }));
  res.end(payload);
}

function infoPayload() {
  return {
    node: NODE_NAME,
    hostname: HOSTNAME,
    ip: IP,
    pid: process.pid,
    uptime_s: Math.round((Date.now() - startedAt) / 1000),
    requests_served: requestsServed,
    inflight,
    fault_mode: fault.mode,
    base_delay_ms: BASE_DELAY_MS,
    shutting_down: shuttingDown,
    time: new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// Página HTML (GET /)
// ---------------------------------------------------------------------------
function htmlPage() {
  const info = infoPayload();
  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Backend ${NODE_NAME}</title>
<style>
  :root { color-scheme: light dark; }
  body { margin:0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         background:${COLOR}; color:#fff; min-height:100vh; display:flex;
         align-items:center; justify-content:center; }
  main { background:rgba(0,0,0,.35); padding:2rem 2.5rem; border-radius:16px;
         max-width:38rem; width:calc(100% - 2rem); box-shadow:0 10px 40px rgba(0,0,0,.3); }
  h1 { margin:0 0 .25rem; font-size:1.1rem; letter-spacing:.08em; text-transform:uppercase; opacity:.85; }
  .node { font-size:2.4rem; font-weight:700; margin:0 0 1rem; word-break:break-all; }
  dl { display:grid; grid-template-columns:auto 1fr; gap:.35rem 1rem; margin:0; font-size:.95rem; }
  dt { opacity:.75; } dd { margin:0; font-family: ui-monospace, Consolas, monospace; }
  .lb { margin-top:1rem; padding-top:1rem; border-top:1px solid rgba(255,255,255,.25); font-size:.85rem; }
  button { margin-top:1rem; padding:.5rem 1rem; border:0; border-radius:8px; cursor:pointer; font-weight:600; }
</style>
</head>
<body>
<main>
  <h1>Respondió el nodo</h1>
  <p class="node">${NODE_NAME}</p>
  <dl>
    <dt>Hostname</dt><dd>${HOSTNAME}</dd>
    <dt>IP</dt><dd>${IP}</dd>
    <dt>PID</dt><dd>${process.pid}</dd>
    <dt>Peticiones atendidas</dt><dd>${info.requests_served}</dd>
    <dt>En vuelo</dt><dd>${info.inflight}</dd>
    <dt>Modo de falla</dt><dd>${fault.mode}</dd>
    <dt>Hora</dt><dd>${info.time}</dd>
  </dl>
  <div class="lb" id="lb">Balanceador: consultando cabeceras…</div>
  <button onclick="location.reload()">Recargar (cambia de nodo con round-robin)</button>
</main>
<script>
  // Lee las cabeceras de diagnóstico que agrega NGINX (X-LB-Policy, X-Upstream-Addr).
  // Ojo: es una petición NUEVA a /api/info, que el balanceador reparte por su cuenta;
  // con round-robin la atiende otro nodo, y eso es justamente lo que se muestra.
  fetch('/api/info', {cache:'no-store'}).then(r => {
    const p = r.headers.get('x-lb-policy'), u = r.headers.get('x-upstream-addr');
    const n = r.headers.get('x-backend-node') || '?';
    const mismo = n === ${JSON.stringify(info.node)} ? 'el mismo nodo' : 'otro nodo';
    document.getElementById('lb').textContent = p
      ? 'Balanceador: política=' + p + ' · la siguiente petición (/api/info) la atendió ' + n
        + ' (' + mismo + ', upstream=' + u + ')'
      : 'Acceso directo (sin pasar por el balanceador)';
  }).catch(() => {});
</script>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Métricas Prometheus (GET /metrics)
// ---------------------------------------------------------------------------
function metricsText() {
  const l = `node="${NODE_NAME}"`;
  const lines = [
    '# HELP backend_requests_total Peticiones atendidas por código de estado.',
    '# TYPE backend_requests_total counter',
  ];
  for (const [status, count] of requestsByStatus) {
    lines.push(`backend_requests_total{${l},status="${status}"} ${count}`);
  }
  if (requestsByStatus.size === 0) lines.push(`backend_requests_total{${l},status="200"} 0`);
  lines.push(
    '# HELP backend_inflight Peticiones en vuelo.',
    '# TYPE backend_inflight gauge',
    `backend_inflight{${l}} ${inflight}`,
    '# HELP backend_request_duration_seconds Duración de las peticiones.',
    '# TYPE backend_request_duration_seconds histogram',
  );
  for (let i = 0; i < BUCKETS.length; i++) {
    lines.push(`backend_request_duration_seconds_bucket{${l},le="${BUCKETS[i]}"} ${bucketCounts[i]}`);
  }
  lines.push(
    `backend_request_duration_seconds_bucket{${l},le="+Inf"} ${durationCount}`,
    `backend_request_duration_seconds_sum{${l}} ${durationSum.toFixed(6)}`,
    `backend_request_duration_seconds_count{${l}} ${durationCount}`,
    '# HELP backend_up 1 si el backend acepta tráfico.',
    '# TYPE backend_up gauge',
    `backend_up{${l}} ${shuttingDown || fault.mode === 'unhealthy' ? 0 : 1}`,
    '# HELP backend_fault_mode Modo de falla activo (1 en el modo actual).',
    '# TYPE backend_fault_mode gauge',
  );
  for (const m of VALID_MODES) lines.push(`backend_fault_mode{${l},mode="${m}"} ${fault.mode === m ? 1 : 0}`);
  lines.push(
    '# HELP backend_uptime_seconds Segundos desde el arranque.',
    '# TYPE backend_uptime_seconds gauge',
    `backend_uptime_seconds{${l}} ${((Date.now() - startedAt) / 1000).toFixed(0)}`,
    '# HELP backend_process_rss_bytes Memoria residente del proceso.',
    '# TYPE backend_process_rss_bytes gauge',
    `backend_process_rss_bytes{${l}} ${process.memoryUsage().rss}`,
    '# HELP backend_base_delay_ms Latencia artificial configurada (BASE_DELAY_MS).',
    '# TYPE backend_base_delay_ms gauge',
    `backend_base_delay_ms{${l}} ${BASE_DELAY_MS}`,
  );
  return lines.join('\n') + '\n' + tienda.metricsText(l);
}

// ---------------------------------------------------------------------------
// Endpoints de administración (solo alcanzables en la red interna)
// ---------------------------------------------------------------------------
async function handleAdmin(req, res, url) {
  if (url.pathname === '/admin/fault') {
    if (req.method === 'GET') return send(res, 200, { node: NODE_NAME, ...fault });
    if (req.method !== 'POST') return send(res, 405, { error: 'método no permitido' });
    let body = {};
    try {
      const raw = await readBody(req);
      body = raw ? JSON.parse(raw) : {};
    } catch (e) {
      return send(res, 400, { error: 'JSON inválido', detail: e.message });
    }
    if (body.mode !== undefined) {
      if (!VALID_MODES.includes(body.mode)) {
        return send(res, 400, { error: `modo inválido; use uno de ${VALID_MODES.join('|')}` });
      }
      fault.mode = body.mode;
    }
    if (body.delayMs !== undefined) fault.delayMs = Math.max(0, toInt(body.delayMs, fault.delayMs));
    console.log(`[${NODE_NAME}] modo de falla -> ${fault.mode} (delayMs=${fault.delayMs})`);
    // Al salir del modo hang, liberar las respuestas colgadas
    if (fault.mode !== 'hang') releaseHanging(503);
    return send(res, 200, { node: NODE_NAME, ...fault });
  }
  if (url.pathname === '/admin/crash') {
    if (req.method !== 'POST') return send(res, 405, { error: 'método no permitido' });
    console.error(`[${NODE_NAME}] /admin/crash recibido: terminando con código 1`);
    send(res, 202, { node: NODE_NAME, crashing: true });
    setTimeout(() => process.exit(1), 50);
    return undefined;
  }
  return send(res, 404, { error: 'no encontrado' });
}

function releaseHanging(status) {
  for (const res of hangingResponses) {
    try {
      send(res, status, { node: NODE_NAME, error: 'liberada por cambio de modo o apagado' });
    } catch (_) {
      /* ignorar */
    }
  }
  hangingResponses.clear();
}

// ---------------------------------------------------------------------------
// Manejador principal
// ---------------------------------------------------------------------------
async function handle(req, res) {
  const url = new URL(req.url, 'http://localhost');
  const path = url.pathname;

  // --- Endpoints de infraestructura: nunca se ven afectados por BASE_DELAY ni por
  //     los modos de falla (salvo 'unhealthy' en /health). No cuentan como tráfico.
  if (path === '/health') {
    const ok = !shuttingDown && fault.mode !== 'unhealthy';
    return send(res, ok ? 200 : 503, { node: NODE_NAME, status: ok ? 'ok' : 'unhealthy', fault_mode: fault.mode });
  }
  if (path === '/metrics') {
    return send(res, 200, metricsText(), { 'Content-Type': 'text/plain; version=0.0.4; charset=utf-8' });
  }
  // Disponibilidad de dependencias (PostgreSQL y almacén de sesiones). /health solo
  // indica que el proceso vive; /ready que además puede atender la tienda.
  if (path === '/ready') {
    const r = await tienda.ready();
    return send(res, r.ok ? 200 : 503, r);
  }
  if (path.startsWith('/admin/')) return handleAdmin(req, res, url);

  // --- Tráfico de aplicación: instrumentado
  const t0 = process.hrtime.bigint();
  inflight += 1;
  let status = 200;
  try {
    // Modos de falla (E-07)
    if (fault.mode === 'hang') {
      // Nunca responde: la petición queda abierta hasta que NGINX agote proxy_read_timeout
      hangingResponses.add(res);
      res.on('close', () => hangingResponses.delete(res));
      return;
    }
    if (BASE_DELAY_MS > 0) await sleep(BASE_DELAY_MS);
    if (fault.mode === 'slow') await sleep(fault.delayMs);
    if (fault.mode === 'error500') {
      status = 500;
      return send(res, 500, { node: NODE_NAME, error: 'falla inyectada (error500)' });
    }

    if (path === '/') {
      // Con la tienda habilitada, / es la tienda; la página de identificación del nodo pasa a /nodo
      if (tienda.serveIndex(res)) return undefined;
      return send(res, 200, htmlPage(), { 'Content-Type': 'text/html; charset=utf-8' });
    }
    if (path === '/nodo') {
      return send(res, 200, htmlPage(), { 'Content-Type': 'text/html; charset=utf-8' });
    }
    if (path === '/api/info') {
      return send(res, 200, infoPayload());
    }
    if (path === '/api/work') {
      const ms = Math.min(MAX_WORK_MS, Math.max(0, toInt(url.searchParams.get('ms'), 0)));
      const cpu = Math.min(MAX_CPU_MS, Math.max(0, toInt(url.searchParams.get('cpu'), 0)));
      if (ms > 0) await sleep(ms);
      if (cpu > 0) burnCpu(cpu);
      return send(res, 200, {
        node: NODE_NAME,
        waited_ms: ms,
        cpu_ms: cpu,
        elapsed_ms: Number(process.hrtime.bigint() - t0) / 1e6,
      });
    }
    if (path === '/api/mixed') {
      const slow = Math.random() < 0.1;
      await sleep(slow ? 300 : 5);
      return send(res, 200, { node: NODE_NAME, kind: slow ? 'slow' : 'fast', elapsed_ms: Number(process.hrtime.bigint() - t0) / 1e6 });
    }
    // Rutas de la tienda (PostgreSQL + sesiones)
    if (await tienda.handle(req, res, url)) return undefined;
    status = 404;
    return send(res, 404, { node: NODE_NAME, error: 'no encontrado', path });
  } catch (err) {
    status = 500;
    console.error(`[${NODE_NAME}] error interno:`, err);
    return send(res, 500, { node: NODE_NAME, error: 'error interno' });
  } finally {
    if (fault.mode !== 'hang' || res.writableEnded) {
      inflight -= 1;
      requestsServed += 1;
      const code = res.statusCode || status;
      requestsByStatus.set(code, (requestsByStatus.get(code) || 0) + 1);
      observeDuration(Number(process.hrtime.bigint() - t0) / 1e9);
    } else {
      // Petición colgada: se contabiliza cuando se cierre el socket
      res.once('close', () => {
        inflight -= 1;
        requestsServed += 1;
        requestsByStatus.set(499, (requestsByStatus.get(499) || 0) + 1);
        observeDuration(Number(process.hrtime.bigint() - t0) / 1e9);
      });
    }
  }
}

// ---------------------------------------------------------------------------
// Tienda web con estado (backend/tienda.js): PostgreSQL + sesiones en Redis o memoria.
// Si no hay DATABASE_URL (o TIENDA_ENABLED=0) queda deshabilitada y el backend se
// comporta como antes (solo endpoints de prueba).
// ---------------------------------------------------------------------------
const tienda = require('./tienda').create({
  nodeName: NODE_NAME,
  send,
  readBody,
  log: (msg) => console.log(`[${NODE_NAME}] ${msg}`),
});

const server = http.createServer((req, res) => {
  handle(req, res).catch((err) => {
    console.error(`[${NODE_NAME}] error no controlado:`, err);
    send(res, 500, { node: NODE_NAME, error: 'error interno' });
  });
});

// Keep-alive hacia NGINX (keepalive 64 en el upstream): mantener conexiones abiertas
server.keepAliveTimeout = 65000;
server.headersTimeout = 70000;

// ---------------------------------------------------------------------------
// Apagado elegante: SIGTERM (docker stop) deja de aceptar conexiones y termina
// las peticiones en vuelo; SIGKILL (docker kill) no pasa por aquí.
// ---------------------------------------------------------------------------
function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log(`[${NODE_NAME}] ${signal} recibido: dejando de aceptar conexiones (inflight=${inflight})`);
  releaseHanging(503);
  server.close(() => {
    console.log(`[${NODE_NAME}] todas las peticiones en vuelo terminaron; saliendo`);
    tienda.close().finally(() => process.exit(0));
  });
  if (typeof server.closeIdleConnections === 'function') server.closeIdleConnections();
  setTimeout(() => {
    console.error(`[${NODE_NAME}] tiempo de gracia agotado (${SHUTDOWN_TIMEOUT_MS} ms); forzando salida`);
    process.exit(0);
  }, SHUTDOWN_TIMEOUT_MS).unref();
}
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

server.listen(PORT, '0.0.0.0', () => {
  console.log(
    `[${NODE_NAME}] escuchando en :${PORT} (hostname=${HOSTNAME} ip=${IP} pid=${process.pid} ` +
      `base_delay=${BASE_DELAY_MS}ms fault=${fault.mode})`,
  );
});
