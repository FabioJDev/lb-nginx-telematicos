#!/usr/bin/env bash
# =============================================================================
# scripts/test-escalabilidad.sh — E-01 / E-02: misma carga con N = 1, 2, 3, 5, 7
# backends. Mide throughput, p95/p99 y eficiencia de escalado
# (Throughput(N) / (N · Throughput(1))). N=1 es la línea base "sin balanceo" (E-01).
#
# Variables: NS="1 2 3 5 7"  REPS=2  SCENARIO=rampa.yml  POLICY=round_robin  COOLDOWN=20
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

NS="${NS:-1 2 3 5 7}"
REPS="${REPS:-2}"; [ "${QUICK:-0}" = "1" ] && REPS=1
SCENARIO="${SCENARIO:-rampa.yml}"
POLICY="${POLICY:-round_robin}"
COOLDOWN="${COOLDOWN:-20}"
BASE="${BACKEND_REPLICAS:-3}"

"$ROOT_DIR/scripts/set-policy.sh" "$POLICY"
log "===== E-02 escalabilidad: N=[$NS] · $SCENARIO · REPS=$REPS ====="
for rep in $(seq 1 "$REPS"); do
  # shellcheck disable=SC2086
  for n in $(shuffle $NS); do
    "$ROOT_DIR/scripts/scale.sh" "$n"
    # Recrear lb para que el pool arranque limpio con las N réplicas resueltas
    compose up -d --no-deps --force-recreate lb >/dev/null; wait_healthy lb 1 60
    cooldown "$COOLDOWN"
    # ID (opcional) permite reutilizar el lote, p. ej. ID=E17 con la tienda
    id="${ID:-E02}"; [ "$n" = "1" ] && [ -z "${ID:-}" ] && id="E01"
    "$ROOT_DIR/scripts/run-test.sh" "$id" "$SCENARIO" "rep$rep"
  done
done
"$ROOT_DIR/scripts/scale.sh" "$BASE"
ok "===== E-02 terminado. Ahora: make analyze ====="
