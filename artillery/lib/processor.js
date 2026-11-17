'use strict';
/**
 * artillery/lib/processor.js — hooks de Artillery (sección 7.7).
 *
 *  - setClientId:  asigna a cada usuario virtual (VU) un identificador estable
 *                  (cabecera X-Client-Id) para las políticas hash_client y para
 *                  medir afinidad de sesión.
 *  - trackBackend: cuenta las respuestas por backend (contador backend.<nodo>) a
 *                  partir de la cabecera X-Backend-Node, detecta cambios de nodo
 *                  del mismo cliente (afinidad.cambios_de_backend) y cuenta los
 *                  reintentos que hizo NGINX (lb.reintentos: X-Upstream-Addr con coma).
 *
 * Los contadores aparecen en aggregate.counters del JSON de salida y los lee
 * analysis/analyze.py; deben coincidir con el conteo del log JSON de NGINX (M-06).
 */
const crypto = require('crypto');

function setClientId(context, events, done) {
  context.vars.clientId = crypto.randomUUID();
  context.vars.lastNode = null;
  return done();
}

function trackBackend(requestParams, response, context, events, done) {
  const headers = (response && response.headers) || {};
  const node = headers['x-backend-node'] || 'sin_backend';
  events.emit('counter', `backend.${node}`, 1);

  if (context.vars.lastNode && context.vars.lastNode !== node) {
    events.emit('counter', 'afinidad.cambios_de_backend', 1);
  }
  context.vars.lastNode = node;

  const upstream = headers['x-upstream-addr'] || '';
  if (upstream.includes(',')) events.emit('counter', 'lb.reintentos', 1);

  const policy = headers['x-lb-policy'];
  if (policy) events.emit('counter', `lb.policy.${policy}`, 1);

  if (headers['x-cache-status']) events.emit('counter', `cache.${headers['x-cache-status']}`, 1);

  return done();
}

// ===========================================================================
// Tienda web (escenarios tienda*.yml)
// ===========================================================================
const TERMS = ['Router', 'Switch', 'Pro', 'Lite', 'Cable', 'Max', 'Disco', 'Antena', '42', 'Smart'];
const CATEGORIES = ['redes', 'almacenamiento', 'periféricos', 'energía', 'seguridad', 'servidores', 'audio y video', 'accesorios'];
const rnd = (n) => Math.floor(Math.random() * n);

/** Datos del usuario virtual: credenciales de prueba, productos y términos al azar. */
function setupShopper(context, events, done) {
  context.vars.clientId = crypto.randomUUID();
  context.vars.lastNode = null;
  context.vars.username = `usuario${1 + rnd(1000)}`;
  context.vars.password = 'clave123';
  context.vars.productA = 1 + rnd(2000);
  context.vars.productB = 1 + rnd(2000);
  context.vars.productC = 1 + rnd(2000);
  context.vars.term = TERMS[rnd(TERMS.length)];
  context.vars.category = encodeURIComponent(CATEGORIES[rnd(CATEGORIES.length)]);
  context.vars.page = 1 + rnd(20);
  context.vars.sessionLost = false;
  context.vars.loginNode = null;
  events.emit('counter', 'tienda.recorridos_iniciados', 1);
  return done();
}

/** Añade X-Client-Id a todas las peticiones (para la política hash_client). */
function addClientHeader(requestParams, context, events, done) {
  requestParams.headers = requestParams.headers || {};
  requestParams.headers['X-Client-Id'] = context.vars.clientId;
  return done();
}

function bodyJson(response) {
  try {
    return typeof response.body === 'string' ? JSON.parse(response.body) : response.body || {};
  } catch (_) {
    return {};
  }
}

/** Marca la pérdida de sesión una sola vez por recorrido y por paso. */
function markSessionLost(context, events, step) {
  events.emit('counter', `tienda.sesion_perdida.${step}`, 1);
  if (!context.vars.sessionLost) {
    context.vars.sessionLost = true;
    events.emit('counter', 'tienda.recorridos_con_sesion_perdida', 1);
  }
}

function classify(response, context, events, step) {
  const code = response.statusCode;
  const body = bodyJson(response);
  if (code === 401 && body.code === 'SESSION_NOT_FOUND') {
    markSessionLost(context, events, step);
    return 'lost';
  }
  if (code === 503 && body.code === 'SESSION_STORE_UNAVAILABLE') {
    events.emit('counter', `tienda.almacen_sesiones_caido.${step}`, 1);
    return 'store_down';
  }
  if (code === 503 && body.code === 'DB_UNAVAILABLE') {
    events.emit('counter', `tienda.bd_caida.${step}`, 1);
    return 'db_down';
  }
  if (code >= 500) {
    events.emit('counter', `tienda.error_5xx.${step}`, 1);
    return 'error';
  }
  return code < 400 ? 'ok' : 'client_error';
}

function checkLogin(requestParams, response, context, events, done) {
  if (response.statusCode === 200) {
    events.emit('counter', 'tienda.login_ok', 1);
    context.vars.loginNode = (response.headers || {})['x-backend-node'] || null;
  } else {
    events.emit('counter', 'tienda.login_error', 1);
    classify(response, context, events, 'login');
  }
  return trackBackend(requestParams, response, context, events, done);
}

function checkCartAdd(requestParams, response, context, events, done) {
  const r = classify(response, context, events, 'agregar');
  if (r === 'ok') events.emit('counter', 'tienda.agregar_ok', 1);
  return trackBackend(requestParams, response, context, events, done);
}

/** El carrito debe tener exactamente los 3 productos agregados (A×1 + B×2). */
function verifyCart(requestParams, response, context, events, done) {
  const r = classify(response, context, events, 'carrito');
  if (r === 'ok') {
    const body = bodyJson(response);
    if (Number(body.count) === 3) events.emit('counter', 'tienda.carrito_ok', 1);
    else events.emit('counter', 'tienda.carrito_inconsistente', 1);
  }
  return trackBackend(requestParams, response, context, events, done);
}

function checkOrder(requestParams, response, context, events, done) {
  const r = classify(response, context, events, 'pedido');
  if (response.statusCode === 201) events.emit('counter', 'tienda.pedido_ok', 1);
  else if (response.statusCode === 409) events.emit('counter', 'tienda.pedido_sin_stock', 1);
  else if (response.statusCode === 400) events.emit('counter', 'tienda.pedido_carrito_vacio', 1);
  else if (r !== 'lost') events.emit('counter', 'tienda.pedido_error', 1);
  events.emit('counter', 'tienda.recorridos_completados', 1);
  return trackBackend(requestParams, response, context, events, done);
}

/** Lectura del catálogo: clasifica 503 de base de datos y cuenta caché. */
function checkRead(requestParams, response, context, events, done) {
  classify(response, context, events, 'catalogo');
  return trackBackend(requestParams, response, context, events, done);
}

module.exports = {
  setClientId,
  trackBackend,
  setupShopper,
  addClientHeader,
  checkLogin,
  checkCartAdd,
  verifyCart,
  checkOrder,
  checkRead,
};
