'use strict';
/**
 * backend/tienda.js — aplicación web con estado detrás del balanceador.
 *
 * Una tienda de equipos de red con catálogo, búsqueda, inicio de sesión, carrito y
 * compra. Usa PostgreSQL (compartido por todas las réplicas) y guarda las sesiones
 * en Redis (compartido) o en la memoria de cada réplica, según SESSION_STORE.
 *
 * Esto permite estudiar lo que una página estática no muestra:
 *   - con SESSION_STORE=memory la sesión vive en UNA réplica: si el balanceador manda
 *     la siguiente petición a otra (round_robin, least_conn…), la sesión "se pierde";
 *   - con SESSION_STORE=redis cualquier réplica atiende a cualquier usuario;
 *   - la base de datos es un recurso compartido: escalar backends no la escala.
 *
 * Endpoints (JSON salvo /):
 *   GET  /                        página de la tienda (public/index.html)
 *   GET  /api/categories          categorías con número de productos
 *   GET  /api/products?q=&category=&page=&size=
 *   GET  /api/products/:id
 *   POST /api/login   {username, password}   -> cookie sid
 *   POST /api/logout
 *   GET  /api/me
 *   GET  /api/cart
 *   POST /api/cart    {productId, qty}
 *   DELETE /api/cart
 *   POST /api/orders              compra el carrito (transacción)
 *   GET  /api/orders              últimos pedidos del usuario
 *   GET  /api/stats               pedidos por réplica en los últimos 5 minutos
 *
 * Variables: DATABASE_URL, DB_POOL_MAX (10), DB_CONNECT_TIMEOUT_MS (2000),
 *   DB_STATEMENT_TIMEOUT_MS (5000), SESSION_STORE (redis|memory), REDIS_URL,
 *   SESSION_TTL_S (1800), TIENDA_ENABLED (1)
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

function toInt(value, fallback) {
  const n = parseInt(value, 10);
  return Number.isFinite(n) ? n : fallback;
}

class HttpError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

// ---------------------------------------------------------------------------
// Almacenes de sesión
// ---------------------------------------------------------------------------
function memoryStore(ttlS) {
  const map = new Map();
  const timer = setInterval(() => {
    const now = Date.now();
    for (const [k, v] of map) if (v.exp < now) map.delete(k);
  }, 60000);
  timer.unref();
  return {
    kind: 'memory',
    async get(sid) {
      const e = map.get(sid);
      if (!e || e.exp < Date.now()) return null;
      return e.data;
    },
    async set(sid, data) {
      map.set(sid, { data, exp: Date.now() + ttlS * 1000 });
    },
    async del(sid) {
      map.delete(sid);
    },
    async ping() {
      return true;
    },
    size: () => map.size,
    async close() {
      clearInterval(timer);
    },
  };
}

function redisStore(url, ttlS, log) {
  const { createClient } = require('redis');
  let lastErr = 0;
  const client = createClient({
    url,
    // Sin cola offline: si Redis no está, el comando falla de inmediato en lugar de
    // dejar la petición HTTP colgada hasta que vuelva la conexión.
    disableOfflineQueue: true,
    socket: { connectTimeout: 2000, reconnectStrategy: (retries) => Math.min(200 + retries * 200, 2000) },
  });
  client.on('error', (e) => {
    if (Date.now() - lastErr > 5000) {
      lastErr = Date.now();
      log(`redis: ${e.message}`);
    }
  });
  client.connect().catch(() => {});
  const key = (sid) => `sess:${sid}`;
  return {
    kind: 'redis',
    async get(sid) {
      const raw = await client.get(key(sid));
      return raw ? JSON.parse(raw) : null;
    },
    async set(sid, data) {
      await client.set(key(sid), JSON.stringify(data), { EX: ttlS });
    },
    async del(sid) {
      await client.del(key(sid));
    },
    async ping() {
      return (await client.ping()) === 'PONG';
    },
    size: () => -1,
    async close() {
      try {
        await client.quit();
      } catch (_) {
        /* ignorar */
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Fábrica
// ---------------------------------------------------------------------------
function create({ nodeName, send, readBody, log = console.log }) {
  const enabled = (process.env.TIENDA_ENABLED || '1') !== '0' && !!process.env.DATABASE_URL;
  const ttlS = toInt(process.env.SESSION_TTL_S, 1800);
  const storeKind = (process.env.SESSION_STORE || 'redis').toLowerCase() === 'memory' ? 'memory' : 'redis';

  const metrics = {
    dbQueries: new Map(), // op -> count
    dbErrors: 0,
    dbDurationSum: 0,
    dbDurationCount: 0,
    sessionsCreated: 0,
    sessionsLost: 0, // cookie presente pero la sesión no existe en el almacén
    sessionErrors: 0, // el almacén no respondió (Redis caído)
    orders: 0,
    ordersFailed: 0,
    logins: 0,
    loginFailures: 0,
  };

  if (!enabled) {
    return {
      enabled: false,
      handle: async () => false,
      serveIndex: () => false,
      ready: async () => ({ ok: true, tienda: 'deshabilitada' }),
      metricsText: () => '',
      close: async () => {},
    };
  }

  const { Pool } = require('pg');
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    max: toInt(process.env.DB_POOL_MAX, 10),
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: toInt(process.env.DB_CONNECT_TIMEOUT_MS, 2000),
    statement_timeout: toInt(process.env.DB_STATEMENT_TIMEOUT_MS, 5000),
    application_name: `tienda-${nodeName}`.slice(0, 63),
  });
  // Un cliente inactivo que pierde la conexión (p. ej. Postgres reiniciado) no debe
  // tumbar el proceso.
  pool.on('error', (e) => log(`postgres (cliente inactivo): ${e.message}`));

  const sessions = storeKind === 'redis' ? redisStore(process.env.REDIS_URL || 'redis://redis:6379', ttlS, log) : memoryStore(ttlS);

  const indexPath = path.join(__dirname, 'public', 'index.html');
  let indexHtml = null;
  try {
    indexHtml = fs.readFileSync(indexPath, 'utf8');
  } catch (e) {
    log(`no se pudo leer ${indexPath}: ${e.message}`);
  }

  // -------------------------------------------------------------------------
  // Utilidades
  // -------------------------------------------------------------------------
  async function q(op, text, params) {
    const t0 = process.hrtime.bigint();
    metrics.dbQueries.set(op, (metrics.dbQueries.get(op) || 0) + 1);
    try {
      return await pool.query(text, params);
    } catch (e) {
      metrics.dbErrors += 1;
      throw dbError(e);
    } finally {
      metrics.dbDurationSum += Number(process.hrtime.bigint() - t0) / 1e9;
      metrics.dbDurationCount += 1;
    }
  }

  function dbError(e) {
    if (e instanceof HttpError) return e;
    // Errores de conexión / timeout: la base de datos no está disponible
    return new HttpError(503, 'DB_UNAVAILABLE', `base de datos no disponible: ${e.message}`);
  }

  function parseCookies(req) {
    const out = {};
    const raw = req.headers.cookie || '';
    for (const part of raw.split(';')) {
      const i = part.indexOf('=');
      if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
    }
    return out;
  }

  async function readJson(req) {
    const raw = await readBody(req);
    if (!raw) return {};
    try {
      return JSON.parse(raw);
    } catch (_) {
      throw new HttpError(400, 'BAD_JSON', 'JSON inválido');
    }
  }

  /** Devuelve { sid, data } o lanza 401 con el motivo exacto (sin cookie / sesión perdida). */
  async function requireSession(req) {
    const sid = parseCookies(req).sid;
    if (!sid) throw new HttpError(401, 'NO_SESSION', 'inicie sesión');
    let data;
    try {
      data = await sessions.get(sid);
    } catch (e) {
      metrics.sessionErrors += 1;
      throw new HttpError(503, 'SESSION_STORE_UNAVAILABLE', `almacén de sesiones no disponible: ${e.message}`);
    }
    if (!data) {
      metrics.sessionsLost += 1;
      throw new HttpError(
        401,
        'SESSION_NOT_FOUND',
        `la réplica ${nodeName} no conoce esta sesión (almacén: ${sessions.kind}); con sesiones en memoria hace falta afinidad en el balanceador`,
      );
    }
    return { sid, data };
  }

  async function saveSession(sid, data) {
    try {
      await sessions.set(sid, data);
    } catch (e) {
      metrics.sessionErrors += 1;
      throw new HttpError(503, 'SESSION_STORE_UNAVAILABLE', `almacén de sesiones no disponible: ${e.message}`);
    }
  }

  function hashPassword(salt, password) {
    return crypto.createHash('sha256').update(salt + password).digest('hex');
  }

  function cartCount(cart) {
    return Object.values(cart || {}).reduce((a, b) => a + b, 0);
  }

  // -------------------------------------------------------------------------
  // Manejadores
  // -------------------------------------------------------------------------
  async function categories() {
    const r = await q(
      'categories',
      'SELECT category, count(*)::int AS products, round(avg(price), 2)::float AS avg_price FROM products GROUP BY category ORDER BY category',
    );
    return { node: nodeName, categories: r.rows };
  }

  async function products(url) {
    const qtext = (url.searchParams.get('q') || '').trim().slice(0, 60) || null;
    const category = (url.searchParams.get('category') || '').trim().slice(0, 40) || null;
    const size = Math.min(50, Math.max(1, toInt(url.searchParams.get('size'), 20)));
    const page = Math.max(1, toInt(url.searchParams.get('page'), 1));
    const r = await q(
      'products',
      `SELECT id, sku, name, category, price::float AS price, stock, count(*) OVER()::int AS total
         FROM products
        WHERE ($1::text IS NULL OR name ILIKE '%' || $1 || '%')
          AND ($2::text IS NULL OR category = $2)
        ORDER BY id
        LIMIT $3 OFFSET $4`,
      [qtext, category, size, (page - 1) * size],
    );
    const total = r.rows.length ? r.rows[0].total : 0;
    return {
      node: nodeName,
      page,
      size,
      total,
      items: r.rows.map(({ total: _t, ...rest }) => rest),
    };
  }

  async function product(id) {
    const r = await q(
      'product',
      'SELECT id, sku, name, category, price::float AS price, stock, description FROM products WHERE id = $1',
      [id],
    );
    if (!r.rows.length) throw new HttpError(404, 'NOT_FOUND', 'producto no encontrado');
    return { node: nodeName, product: r.rows[0] };
  }

  async function login(req, res) {
    const body = await readJson(req);
    const username = String(body.username || '').slice(0, 40);
    const password = String(body.password || '');
    metrics.logins += 1;
    const r = await q('login', 'SELECT id, username, salt, pass_hash FROM users WHERE username = $1', [username]);
    const u = r.rows[0];
    const ok =
      u &&
      crypto.timingSafeEqual(Buffer.from(hashPassword(u.salt, password), 'hex'), Buffer.from(u.pass_hash, 'hex'));
    if (!ok) {
      metrics.loginFailures += 1;
      throw new HttpError(401, 'BAD_CREDENTIALS', 'usuario o contraseña incorrectos');
    }
    const sid = crypto.randomBytes(16).toString('hex');
    await saveSession(sid, { userId: u.id, username: u.username, cart: {}, createdBy: nodeName, createdAt: Date.now() });
    metrics.sessionsCreated += 1;
    res.setHeader('Set-Cookie', `sid=${sid}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${ttlS}`);
    return { node: nodeName, user: { id: u.id, username: u.username }, sessionStore: sessions.kind };
  }

  async function logout(req, res) {
    const sid = parseCookies(req).sid;
    if (sid) {
      try {
        await sessions.del(sid);
      } catch (_) {
        /* ignorar */
      }
    }
    res.setHeader('Set-Cookie', 'sid=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0');
    return { node: nodeName, ok: true };
  }

  async function me(req) {
    const { data } = await requireSession(req);
    return {
      node: nodeName,
      user: { id: data.userId, username: data.username },
      cartItems: cartCount(data.cart),
      sessionCreatedBy: data.createdBy,
      sessionStore: sessions.kind,
    };
  }

  async function getCart(req) {
    const { data } = await requireSession(req);
    const ids = Object.keys(data.cart || {}).map(Number);
    let items = [];
    if (ids.length) {
      const r = await q(
        'cart',
        'SELECT id, name, price::float AS price FROM products WHERE id = ANY($1::int[]) ORDER BY id',
        [ids],
      );
      items = r.rows.map((p) => ({ ...p, qty: data.cart[p.id], subtotal: Math.round(p.price * data.cart[p.id] * 100) / 100 }));
    }
    const total = Math.round(items.reduce((a, it) => a + it.subtotal, 0) * 100) / 100;
    return { node: nodeName, user: data.username, items, count: cartCount(data.cart), total, sessionCreatedBy: data.createdBy };
  }

  async function addToCart(req) {
    const { sid, data } = await requireSession(req);
    const body = await readJson(req);
    const productId = toInt(body.productId, 0);
    const qty = Math.min(20, Math.max(1, toInt(body.qty, 1)));
    const r = await q('cart_add', 'SELECT id, stock FROM products WHERE id = $1', [productId]);
    if (!r.rows.length) throw new HttpError(404, 'NOT_FOUND', 'producto no encontrado');
    data.cart = data.cart || {};
    data.cart[productId] = (data.cart[productId] || 0) + qty;
    await saveSession(sid, data);
    return { node: nodeName, count: cartCount(data.cart), cart: data.cart };
  }

  async function clearCart(req) {
    const { sid, data } = await requireSession(req);
    data.cart = {};
    await saveSession(sid, data);
    return { node: nodeName, count: 0 };
  }

  async function checkout(req) {
    const { sid, data } = await requireSession(req);
    const entries = Object.entries(data.cart || {})
      .map(([id, qty]) => [Number(id), qty])
      .sort((a, b) => a[0] - b[0]); // orden fijo de bloqueo: evita interbloqueos entre pedidos
    if (!entries.length) throw new HttpError(400, 'EMPTY_CART', 'el carrito está vacío');

    let client;
    try {
      client = await pool.connect();
    } catch (e) {
      metrics.dbErrors += 1;
      throw dbError(e);
    }
    const t0 = process.hrtime.bigint();
    metrics.dbQueries.set('checkout', (metrics.dbQueries.get('checkout') || 0) + 1);
    try {
      await client.query('BEGIN');
      let total = 0;
      const lines = [];
      for (const [productId, qty] of entries) {
        const r = await client.query(
          'UPDATE products SET stock = stock - $2 WHERE id = $1 AND stock >= $2 RETURNING price::float AS price',
          [productId, qty],
        );
        if (!r.rows.length) throw new HttpError(409, 'OUT_OF_STOCK', `sin existencias del producto ${productId}`);
        total += r.rows[0].price * qty;
        lines.push([productId, qty, r.rows[0].price]);
      }
      total = Math.round(total * 100) / 100;
      const o = await client.query(
        'INSERT INTO orders (user_id, total, items, node) VALUES ($1, $2, $3, $4) RETURNING id, created_at',
        [data.userId, total, cartCount(data.cart), nodeName],
      );
      const orderId = o.rows[0].id;
      const values = [];
      const params = [];
      lines.forEach(([pid, qty, price], i) => {
        values.push(`($1, $${i * 3 + 2}, $${i * 3 + 3}, $${i * 3 + 4})`);
        params.push(pid, qty, price);
      });
      await client.query(`INSERT INTO order_items (order_id, product_id, qty, price) VALUES ${values.join(',')}`, [orderId, ...params]);
      await client.query('COMMIT');
      data.cart = {};
      await saveSession(sid, data);
      metrics.orders += 1;
      return { status: 201, body: { node: nodeName, orderId: String(orderId), total, items: lines.length } };
    } catch (e) {
      metrics.ordersFailed += 1;
      try {
        await client.query('ROLLBACK');
      } catch (_) {
        /* la conexión puede estar rota */
      }
      if (!(e instanceof HttpError)) metrics.dbErrors += 1;
      throw dbError(e);
    } finally {
      client.release();
      metrics.dbDurationSum += Number(process.hrtime.bigint() - t0) / 1e9;
      metrics.dbDurationCount += 1;
    }
  }

  async function myOrders(req) {
    const { data } = await requireSession(req);
    const r = await q(
      'orders',
      'SELECT id::text, total::float AS total, items, node, created_at FROM orders WHERE user_id = $1 ORDER BY created_at DESC LIMIT 10',
      [data.userId],
    );
    return { node: nodeName, orders: r.rows };
  }

  async function stats() {
    const r = await q(
      'stats',
      `SELECT node, count(*)::int AS orders, round(sum(total), 2)::float AS amount
         FROM orders WHERE created_at > now() - interval '5 minutes'
        GROUP BY node ORDER BY node`,
    );
    const t = await q('stats_total', 'SELECT count(*)::int AS orders FROM orders');
    return { node: nodeName, window: '5 minutes', byNode: r.rows, totalOrders: t.rows[0].orders };
  }

  // -------------------------------------------------------------------------
  // Enrutador
  // -------------------------------------------------------------------------
  const routes = [
    ['GET', /^\/api\/categories$/, () => categories()],
    ['GET', /^\/api\/products$/, (req, res, url) => products(url)],
    ['GET', /^\/api\/products\/(\d+)$/, (req, res, url, m) => product(toInt(m[1], 0))],
    ['POST', /^\/api\/login$/, (req, res) => login(req, res)],
    ['POST', /^\/api\/logout$/, (req, res) => logout(req, res)],
    ['GET', /^\/api\/me$/, (req) => me(req)],
    ['GET', /^\/api\/cart$/, (req) => getCart(req)],
    ['POST', /^\/api\/cart$/, (req) => addToCart(req)],
    ['DELETE', /^\/api\/cart$/, (req) => clearCart(req)],
    ['POST', /^\/api\/orders$/, (req) => checkout(req)],
    ['GET', /^\/api\/orders$/, (req) => myOrders(req)],
    ['GET', /^\/api\/stats$/, () => stats()],
  ];

  async function handle(req, res, url) {
    for (const [method, re, fn] of routes) {
      const m = url.pathname.match(re);
      if (!m) continue;
      if (req.method !== method) {
        // misma ruta, otro método: buscar si otra entrada lo atiende
        if (routes.some(([mm, rr]) => mm === req.method && rr.test(url.pathname))) continue;
        send(res, 405, { node: nodeName, error: 'método no permitido' });
        return true;
      }
      try {
        const out = await fn(req, res, url, m);
        if (out && out.status) send(res, out.status, out.body);
        else send(res, 200, out);
      } catch (e) {
        const status = e.status || 500;
        if (status >= 500 && status !== 503) log(`error en ${url.pathname}: ${e.message}`);
        send(res, status, { node: nodeName, error: e.message, code: e.code || 'INTERNAL' });
      }
      return true;
    }
    return false;
  }

  function serveIndex(res) {
    if (!indexHtml) return false;
    send(res, 200, indexHtml, { 'Content-Type': 'text/html; charset=utf-8' });
    return true;
  }

  async function ready() {
    const out = { node: nodeName, sessionStore: sessions.kind, db: false, sessions: false };
    try {
      await pool.query('SELECT 1');
      out.db = true;
    } catch (e) {
      out.dbError = e.message;
    }
    try {
      out.sessions = await sessions.ping();
    } catch (e) {
      out.sessionsError = e.message;
    }
    out.ok = out.db && out.sessions;
    return out;
  }

  function metricsText(l) {
    const lines = [
      '# HELP tienda_db_queries_total Consultas a PostgreSQL por operación.',
      '# TYPE tienda_db_queries_total counter',
    ];
    for (const [op, n] of metrics.dbQueries) lines.push(`tienda_db_queries_total{${l},op="${op}"} ${n}`);
    lines.push(
      '# HELP tienda_db_errors_total Errores de base de datos.',
      '# TYPE tienda_db_errors_total counter',
      `tienda_db_errors_total{${l}} ${metrics.dbErrors}`,
      '# HELP tienda_db_query_seconds Duración de las consultas.',
      '# TYPE tienda_db_query_seconds summary',
      `tienda_db_query_seconds_sum{${l}} ${metrics.dbDurationSum.toFixed(6)}`,
      `tienda_db_query_seconds_count{${l}} ${metrics.dbDurationCount}`,
      '# HELP tienda_db_pool_connections Conexiones del pool por estado.',
      '# TYPE tienda_db_pool_connections gauge',
      `tienda_db_pool_connections{${l},state="total"} ${pool.totalCount}`,
      `tienda_db_pool_connections{${l},state="idle"} ${pool.idleCount}`,
      `tienda_db_pool_connections{${l},state="waiting"} ${pool.waitingCount}`,
      '# HELP tienda_sessions_total Eventos de sesión.',
      '# TYPE tienda_sessions_total counter',
      `tienda_sessions_total{${l},event="created"} ${metrics.sessionsCreated}`,
      `tienda_sessions_total{${l},event="lost"} ${metrics.sessionsLost}`,
      `tienda_sessions_total{${l},event="store_error"} ${metrics.sessionErrors}`,
      '# HELP tienda_orders_total Pedidos por resultado.',
      '# TYPE tienda_orders_total counter',
      `tienda_orders_total{${l},result="ok"} ${metrics.orders}`,
      `tienda_orders_total{${l},result="failed"} ${metrics.ordersFailed}`,
      '# HELP tienda_logins_total Intentos de inicio de sesión.',
      '# TYPE tienda_logins_total counter',
      `tienda_logins_total{${l},result="ok"} ${metrics.logins - metrics.loginFailures}`,
      `tienda_logins_total{${l},result="failed"} ${metrics.loginFailures}`,
      '# HELP tienda_session_store Almacén de sesiones en uso (1 = activo).',
      '# TYPE tienda_session_store gauge',
      `tienda_session_store{${l},store="${sessions.kind}"} 1`,
    );
    return lines.join('\n') + '\n';
  }

  async function close() {
    await Promise.allSettled([pool.end(), sessions.close()]);
  }

  log(`tienda habilitada: sesiones=${sessions.kind}, pool PostgreSQL max=${toInt(process.env.DB_POOL_MAX, 10)}`);
  return { enabled: true, handle, serveIndex, ready, metricsText, close, sessionKind: sessions.kind };
}

module.exports = { create };
