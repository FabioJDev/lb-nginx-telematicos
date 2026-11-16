#!/usr/bin/env bash
# =============================================================================
# scripts/test-quiebre.sh — E-13: punto de quiebre. quiebre.yml sube de 50 a 3000
# llegadas/s en 300 s sin umbral 'ensure'. El análisis encuentra la carga máxima
# sostenible con error < 1 % y p99 < 1 s para cada N ("qué carga hace que la
# aplicación deje de funcionar", pregunta de la presentación del curso).
#
# IMPORTANTE: si Artillery avisa de CPU alta, el generador es el cuello de
# botella; se registra en docker_stats.csv y debe reportarse como limitación.
#
# Variables: NS="1 3 5"  POLICY=round_robin  COOLDOWN=30
# =============================================================================
source "$(dirname "$0")/lib.sh"
load_env

NS="${NS:-1 3 5}"
POLICY="${POLICY:-round_robin}"
COOLDOWN="${COOLDOWN:-30}"
BASE="${BACKEND_REPLICAS:-3}"

"$ROOT_DIR/scripts/set-policy.sh" "$POLICY"
log "===== E-13 punto de quiebre: N=[$NS] ====="
for n in $NS; do
  "$ROOT_DIR/scripts/scale.sh" "$n"
  compose up -d --no-deps --force-recreate lb >/dev/null; wait_healthy lb 1 60
  cooldown "$COOLDOWN"
  "$ROOT_DIR/scripts/run-test.sh" E13 quiebre.yml
done
"$ROOT_DIR/scripts/scale.sh" "$BASE"
ok "===== E-13 terminado. Ahora: make analyze ====="
