#!/usr/bin/env bash
# =============================================================================
# scripts/test-ratelimit.sh — A-01: limitación de tasa por cliente.
# Mismo escenario (ratelimit.yml: un cliente abusivo a ~80 req/s y clientes normales a
# ~40 req/s en total) con LB_FEATURE=none y LB_FEATURE=ratelimit, en orden aleatorio.
# Mide 429 por tipo de cliente (metrics-by-endpoint), peticiones que llegan a los
# backends (log de NGINX) y latencia de los clientes normales.
# Variables: REPS=2  COOLDOWN=20  POLICY=round_robin
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

REPS="${REPS:-2}"; [ "${QUICK:-0}" = "1" ] && REPS=1
COOLDOWN="${COOLDOWN:-20}"
"$ROOT_DIR/scripts/set-policy.sh" "${POLICY:-round_robin}"
for rep in $(seq 1 "$REPS"); do
  for feat in $(shuffle none ratelimit); do
    "$ROOT_DIR/scripts/set-env.sh" LB_FEATURE "$feat" --recreate-lb
    cooldown "$COOLDOWN"
    NOTES="A-01 LB_FEATURE=$feat" "$ROOT_DIR/scripts/run-test.sh" A01 ratelimit.yml "ratelimit-${feat}_rep$rep"
  done
done
"$ROOT_DIR/scripts/set-env.sh" LB_FEATURE none --recreate-lb
ok "===== A-01 terminado. Ahora: make analyze ====="
