#!/usr/bin/env bash
# =============================================================================
# scripts/test-extendidas.sh — pruebas extendidas E-xx (sección 9.2). Cada una es
# una función; se invoca con el ID o 'all'.
#
#   E03  backends heterogéneos (compose.weighted.yml): round_robin, least_conn,
#        random_two y round-robin ponderado (weight 3:1)
#   E04  peticiones de costo variable (/api/mixed): round_robin vs least_conn
#   E05  trampa de ip_hash vs hash_client (afinidad L7)
#   E06  hash consistente al quitar un nodo (5 -> 4 réplicas): hash_client vs ip_hash
#   E07  modos de falla bajo carga: stop, kill, pause, crash, error500, slow, hang
#   E08  matriz timeouts x reintentos bajo 'hang' (read_timeout 3s/10s, next_upstream on/off)
#   E09  falla múltiple y total (2 de 3, 3 de 3, regreso)
#   E10  escalado en caliente bajo carga (3 -> 6 -> 2)
#   E11  recarga de configuración bajo carga (cambio de política con reload)
#   E12  keepalive hacia upstream on/off
#   E14  pico súbito (spike.yml)
#   E15  resistencia (soak.yml, 15 min)
#
# Uso: scripts/test-extendidas.sh <E03|E04|...|all>      Variables: REPS=2 COOLDOWN=20
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

REPS="${REPS:-2}"; [ "${QUICK:-0}" = "1" ] && REPS=1
COOLDOWN="${COOLDOWN:-20}"
BASE="${BACKEND_REPLICAS:-3}"
S="$ROOT_DIR/scripts"

recreate_lb() { compose up -d --no-deps --force-recreate lb >/dev/null; wait_healthy lb 1 60; }

# Lanza run-test en segundo plano y espera a artillery_start; deja RUN_DIR y t_start
start_bg_run() {
  local before
  before=$(cat "$CURRENT_RUN_FILE" 2>/dev/null || true)
  "$S/run-test.sh" "$@" &
  BG_PID=$!
  for _ in $(seq 1 60); do
    local cur; cur=$(cat "$CURRENT_RUN_FILE" 2>/dev/null || true)
    if [ -n "$cur" ] && [ "$cur" != "$before" ] && grep -q artillery_start "$RESULTS_DIR/$cur/events.csv" 2>/dev/null; then break; fi
    sleep 1
  done
  RUN_DIR="$RESULTS_DIR/$(cat "$CURRENT_RUN_FILE")"; export RUN_DIR
  T_START=$(awk -F, '/artillery_start/ {print $1}' "$RUN_DIR/events.csv" | head -1)
}
at() { # at <segundos desde artillery_start>: duerme hasta ese instante
  local d; d=$(awk -v a="$T_START" -v t="$1" -v n="$(date +%s.%N)" 'BEGIN{d=a+t-n; printf "%.2f", (d>0?d:0)}')
  sleep "$d"
}
finish_bg_run() { wait "$BG_PID" || true; }

# ---------------------------------------------------------------------------
E03() {
  log "===== E-03 backends heterogéneos (compose.weighted.yml) ====="
  export COMPOSE_EXTRA_ARGS="-f docker-compose.yml -f compose.weighted.yml"
  compose up -d --build --remove-orphans >/dev/null; wait_healthy lb 1 90; wait_healthy backend-slow 1 60
  for rep in $(seq 1 "$REPS"); do
    for pol in $(shuffle round_robin least_conn random_two); do
      LB_WEIGHT_FAST=1 LB_WEIGHT_SLOW=1 "$S/set-policy.sh" "$pol"
      cooldown "$COOLDOWN"; NOTES="heterogéneo: 1 lento (${SLOW_BACKEND_DELAY_MS:-150}ms, ${SLOW_BACKEND_CPUS:-0.25} cpu)" "$S/run-test.sh" E03 rampa.yml "rep$rep"
    done
    # round-robin ponderado: 3 (rápido) : 1 (lento)
    export LB_WEIGHT_FAST=3 LB_WEIGHT_SLOW=1
    "$S/set-policy.sh" round_robin
    cooldown "$COOLDOWN"; NOTES="round-robin ponderado weight fast=3 slow=1" "$S/run-test.sh" E03 rampa.yml "weighted31_rep$rep"
    unset LB_WEIGHT_FAST LB_WEIGHT_SLOW
  done
  compose rm -sf backend-slow >/dev/null || true
  unset COMPOSE_EXTRA_ARGS
  "$S/set-policy.sh" round_robin
}

E04() {
  log "===== E-04 costo variable (/api/mixed) ====="
  WORK_PATH=/api/mixed ID=E04 POLICIES="round_robin least_conn random_two" REPS="$REPS" "$S/test-algoritmos.sh"
}

E05() {
  log "===== E-05 trampa de ip_hash vs afinidad L7 (hash_client, hash_remote_addr) ====="
  ID=E05 POLICIES="ip_hash hash_client hash_remote_addr" REPS="$REPS" "$S/test-algoritmos.sh"
}

E06() {
  log "===== E-06 hash consistente al quitar un nodo (5 -> 4) ====="
  for pol in hash_client ip_hash; do
    "$S/scale.sh" 5; "$S/set-policy.sh" "$pol"; cooldown "$COOLDOWN"
    start_bg_run E06 constante.yml "$pol"
    at 60; "$S/inject-fault.sh" rm 5
    finish_bg_run
  done
  "$S/scale.sh" "$BASE"; "$S/set-policy.sh" round_robin
}

E07() {
  log "===== E-07 modos de falla bajo carga constante ====="
  "$S/scale.sh" "$BASE"; "$S/set-policy.sh" round_robin
  for action in stop kill pause crash fault:error500 fault:slow fault:hang; do
    cooldown "$COOLDOWN"
    ID=E07 "$S/test-resiliencia.sh" round_robin "$action" 60 120
    "$S/scale.sh" "$BASE"   # asegura N réplicas sanas antes del siguiente modo
  done
}

E08() {
  log "===== E-08 matriz timeouts x reintentos bajo 'hang' ====="
  "$S/scale.sh" "$BASE"; "$S/set-policy.sh" round_robin
  for rt in 3s 10s; do
    for nu in "error timeout http_502 http_503 http_504" "off"; do
      "$S/set-env.sh" LB_READ_TIMEOUT "$rt"
      "$S/set-env.sh" LB_NEXT_UPSTREAM "$nu" --recreate-lb
      cooldown "$COOLDOWN"
      label="hang_rt${rt}_nu$([ "$nu" = off ] && echo off || echo on)"
      NOTES="read_timeout=$rt next_upstream=$nu" ID=E08 LABEL="$label" "$S/test-resiliencia.sh" round_robin fault:hang 60 120
    done
  done
  "$S/set-env.sh" LB_READ_TIMEOUT 10s
  "$S/set-env.sh" LB_NEXT_UPSTREAM "error timeout http_502 http_503 http_504" --recreate-lb
}

E09() {
  log "===== E-09 falla múltiple y total ====="
  "$S/scale.sh" 3; "$S/set-policy.sh" round_robin; cooldown "$COOLDOWN"
  start_bg_run E09 constante.yml multiple
  at 40;  "$S/inject-fault.sh" rm 1
  at 70;  "$S/inject-fault.sh" rm 1       # queda 1 de 3
  at 100; "$S/inject-fault.sh" rm 1       # 0 de 3 -> página de mantenimiento (502)
  at 130; log_event "$RUN_DIR" backend_restore_start "scale 3 (inicio)"; "$S/scale.sh" 3; log_event "$RUN_DIR" backend_restored "scale 3 (healthy)"
  finish_bg_run
}

E10() {
  log "===== E-10 escalado en caliente bajo carga (3 -> 6 -> 2) ====="
  "$S/scale.sh" 3; "$S/set-policy.sh" round_robin; cooldown "$COOLDOWN"
  start_bg_run E10 constante.yml hotscale
  at 60;  log_event "$RUN_DIR" scale_start "3->6 (inicio)"; "$S/scale.sh" 6; log_event "$RUN_DIR" scaled "3->6 healthy (sin recargar NGINX: resolve)"
  at 120; log_event "$RUN_DIR" scale_start "6->2 (inicio)"; "$S/scale.sh" 2; log_event "$RUN_DIR" scaled "6->2 (scale-in)"
  finish_bg_run
  "$S/scale.sh" "$BASE"
}

E11() {
  log "===== E-11 recarga de configuración bajo carga ====="
  "$S/scale.sh" "$BASE"; "$S/set-policy.sh" round_robin; cooldown "$COOLDOWN"
  start_bg_run E11 constante.yml reload
  at 60
  # Cambio de política SIN recrear: edita el .env y regenera dentro del contenedor + reload
  lb_exec sh -c 'export LB_POLICY=least_conn; /docker-entrypoint.d/20-envsubst-on-templates.sh >/dev/null 2>&1; nginx -t && nginx -s reload'
  log_event "$RUN_DIR" reload "política round_robin->least_conn con nginx -s reload"
  at 120
  lb_exec sh -c 'export LB_POLICY=round_robin; /docker-entrypoint.d/20-envsubst-on-templates.sh >/dev/null 2>&1; nginx -t && nginx -s reload'
  log_event "$RUN_DIR" reload "política least_conn->round_robin con nginx -s reload"
  finish_bg_run
}

E12() {
  log "===== E-12 keepalive hacia upstream on/off ====="
  "$S/scale.sh" "$BASE"; "$S/set-policy.sh" round_robin
  for rep in $(seq 1 "$REPS"); do
    for ka in $(shuffle on off); do
      "$S/set-env.sh" LB_UPSTREAM_KEEPALIVE "$ka" --recreate-lb
      cooldown "$COOLDOWN"
      NOTES="keepalive=$ka" "$S/run-test.sh" E12 rampa.yml "ka${ka}_rep$rep"
    done
  done
  "$S/set-env.sh" LB_UPSTREAM_KEEPALIVE on --recreate-lb
}

E14() {
  log "===== E-14 pico súbito ====="
  "$S/scale.sh" "$BASE"; "$S/set-policy.sh" round_robin; cooldown "$COOLDOWN"
  "$S/run-test.sh" E14 spike.yml
}

E15() {
  log "===== E-15 resistencia 15 min ====="
  "$S/scale.sh" "$BASE"; "$S/set-policy.sh" round_robin; cooldown "$COOLDOWN"
  "$S/run-test.sh" E15 soak.yml
}

# ---------------------------------------------------------------------------
WHICH="${1:-}"
[ -n "$WHICH" ] || die "uso: $0 <E03|E04|E05|E06|E07|E08|E09|E10|E11|E12|E14|E15|all>"
if [ "$WHICH" = "all" ]; then
  for e in E03 E04 E05 E06 E07 E08 E09 E10 E11 E12 E14 E15; do "$e"; done
else
  declare -F "$WHICH" >/dev/null || die "prueba desconocida: $WHICH"
  "$WHICH"
fi
ok "===== extendidas ($WHICH) terminadas. Ahora: make analyze ====="
