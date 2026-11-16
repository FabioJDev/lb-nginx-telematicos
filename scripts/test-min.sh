#!/usr/bin/env bash
# =============================================================================
# scripts/test-min.sh — Pruebas mínimas del enunciado M-00 … M-06 (sección 9.1),
# siguiendo la metodología de la sección 8: calentamiento (lo descarta el análisis),
# REPS repeticiones por configuración, orden aleatorio y enfriamiento entre corridas.
#
#   M-00  smoke de despliegue
#   M-01  stub_status por algoritmo (lo captura run-test.sh en stub_status.csv)
#   M-02  1000 peticiones secuenciales con round_robin (test-seq.sh)
#   M-03  resiliencia: eliminar un backend en caliente (test-resiliencia.sh) x2 políticas
#   M-04  1000 usuarios concurrentes 60 s (p04-1000-usuarios.yml x REPS + p04b-abierto.yml)
#   M-05  rampa.yml x REPS por política (round_robin, least_conn, ip_hash)
#   M-06  distribución real por backend: sale de nginx_access.jsonl de M-05 (make analyze)
#
# Variables: REPS (3), QUICK=1 (1 repetición), POLICIES ("round_robin least_conn ip_hash"),
#            BEST_POLICY (round_robin), COOLDOWN (20), SKIP="M03 M04" para saltar bloques.
# Duración aproximada con REPS=3: ~1 h de máquina.
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

REPS="${REPS:-3}"; [ "${QUICK:-0}" = "1" ] && REPS=1
POLICIES="${POLICIES:-round_robin least_conn ip_hash}"
BEST_POLICY="${BEST_POLICY:-round_robin}"
COOLDOWN="${COOLDOWN:-20}"
SKIP="${SKIP:-}"
BASE_REPLICAS="${BACKEND_REPLICAS:-3}"
skip() { [[ " $SKIP " == *" $1 "* ]]; }

BATCH_LOG="$RESULTS_DIR/lote_test-min_$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$RESULTS_DIR"
exec > >(tee -a "$BATCH_LOG") 2>&1
log "===== test-min: REPS=$REPS políticas=[$POLICIES] réplicas base=$BASE_REPLICAS ====="

# Punto de partida reproducible
"$ROOT_DIR/scripts/scale.sh" "$BASE_REPLICAS"
"$ROOT_DIR/scripts/set-policy.sh" round_robin

# ---- M-00 -------------------------------------------------------------------
log "----- M-00 smoke -----"
"$ROOT_DIR/scripts/smoke.sh" 30
"$ROOT_DIR/scripts/run-test.sh" M00 smoke.yml

# ---- M-02 -------------------------------------------------------------------
if ! skip M02; then
  log "----- M-02 1000 peticiones secuenciales (round_robin) -----"
  "$ROOT_DIR/scripts/test-seq.sh" 1000
fi

# ---- M-05 / M-01 / M-06 -------------------------------------------------------
if ! skip M05; then
  log "----- M-05 rampa.yml x $REPS por política (orden aleatorio) -----"
  for rep in $(seq 1 "$REPS"); do
    # shellcheck disable=SC2086
    for pol in $(shuffle $POLICIES); do
      "$ROOT_DIR/scripts/set-policy.sh" "$pol"
      cooldown "$COOLDOWN"
      "$ROOT_DIR/scripts/run-test.sh" M05 rampa.yml "rep$rep"
    done
  done
fi

# ---- M-03 -------------------------------------------------------------------
if ! skip M03; then
  log "----- M-03 resiliencia (round_robin y least_conn) -----"
  for pol in round_robin least_conn; do
    cooldown "$COOLDOWN"
    "$ROOT_DIR/scripts/test-resiliencia.sh" "$pol"
  done
fi

# ---- M-04 -------------------------------------------------------------------
if ! skip M04; then
  log "----- M-04 1000 usuarios concurrentes 60 s ($BEST_POLICY) x $REPS -----"
  "$ROOT_DIR/scripts/scale.sh" "$BASE_REPLICAS"
  "$ROOT_DIR/scripts/set-policy.sh" "$BEST_POLICY"
  for rep in $(seq 1 "$REPS"); do
    cooldown "$COOLDOWN"
    "$ROOT_DIR/scripts/run-test.sh" M04 p04-1000-usuarios.yml "rep$rep"
  done
  cooldown "$COOLDOWN"
  "$ROOT_DIR/scripts/run-test.sh" M04b p04b-abierto.yml
fi

"$ROOT_DIR/scripts/set-policy.sh" round_robin
ok "===== test-min terminado. Ahora: make analyze ====="
echo "log del lote: $BATCH_LOG"
