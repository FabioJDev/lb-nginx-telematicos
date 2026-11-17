#!/usr/bin/env bash
# =============================================================================
# scripts/test-cache.sh — A-02: microcaché de 1 s del catálogo público frente a
# la base de datos. Mismo escenario de navegación (tienda-lectura.yml) con
# LB_FEATURE=none y LB_FEATURE=microcache, en orden aleatorio.
# Mide p95, goodput, aciertos de caché (cabecera X-Cache-Status contada por
# Artillery) y CPU de PostgreSQL (docker_stats.csv).
# Variables: REPS=2  COOLDOWN=20  POLICY=round_robin
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

REPS="${REPS:-2}"; [ "${QUICK:-0}" = "1" ] && REPS=1
COOLDOWN="${COOLDOWN:-20}"
"$ROOT_DIR/scripts/set-policy.sh" "${POLICY:-round_robin}"
for rep in $(seq 1 "$REPS"); do
  for feat in $(shuffle none microcache); do
    "$ROOT_DIR/scripts/set-env.sh" LB_FEATURE "$feat" --recreate-lb
    cooldown "$COOLDOWN"
    NOTES="LB_FEATURE=$feat" "$ROOT_DIR/scripts/run-test.sh" A02 tienda-lectura.yml "cache-${feat}_rep$rep"
  done
done
"$ROOT_DIR/scripts/set-env.sh" LB_FEATURE none --recreate-lb
ok "===== A-02 terminado. Ahora: make analyze ====="
