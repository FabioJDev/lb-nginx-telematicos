// artillery/lib/vip-probe.js — A-04: sonda de la IP flotante.
// Hace una petición cada INTERVAL_MS a la URL indicada durante DURATION_S y escribe
// en stdout un CSV: epoch_ms,status,lb_host,backend,latency_ms
//   status = código HTTP, o "error" si no hubo respuesta (timeout/conexión)
//   lb_host = cabecera X-LB-Host (qué NGINX tenía la VIP)
// Uso: node vip-probe.js <url> [duration_s=180] [interval_ms=100] [timeout_ms=1000]
'use strict';
const http = require('http');

const url = process.argv[2];
const durationS = Number(process.argv[3] || 180);
const intervalMs = Number(process.argv[4] || 100);
const timeoutMs = Number(process.argv[5] || 1000);
if (!url) { console.error('uso: node vip-probe.js <url> [s] [ms] [timeout_ms]'); process.exit(2); }

// Sin keep-alive: cada sonda abre una conexión nueva, como un cliente que llega
const agent = new http.Agent({ keepAlive: false });
const end = Date.now() + durationS * 1000;
process.stdout.write('epoch_ms,status,lb_host,backend,latency_ms\n');

function probe() {
  const t0 = Date.now();
  let done = false;
  const finish = (status, host, backend) => {
    if (done) return;
    done = true;
    process.stdout.write(`${t0},${status},${host || ''},${backend || ''},${Date.now() - t0}\n`);
  };
  const req = http.get(url, { agent, timeout: timeoutMs }, (res) => {
    res.resume();
    res.on('end', () => finish(res.statusCode, res.headers['x-lb-host'], res.headers['x-backend-node']));
  });
  req.on('timeout', () => { req.destroy(); finish('error'); });
  req.on('error', () => finish('error'));
}

const timer = setInterval(() => {
  if (Date.now() >= end) { clearInterval(timer); setTimeout(() => process.exit(0), timeoutMs + 200); return; }
  probe();
}, intervalMs);
