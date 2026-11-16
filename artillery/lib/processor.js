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

module.exports = { setClientId, trackBackend };
