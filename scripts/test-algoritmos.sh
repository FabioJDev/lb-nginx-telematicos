#!/usr/bin/env bash
# =============================================================================
# scripts/test-algoritmos.sh — comparación de políticas con el MISMO escenario,
# REPS repeticiones por política en orden aleatorio (R-12, M-05, E-04, E-05).
#
# Variables:
#   POLICIES="round_robin least_conn ip_hash hash_client random_two"
#   REPS=3  SCENARIO=rampa.yml  WORK_PATH=/api/work?ms=20  ID=ALG  COOLDOWN=20
# Ejemplos:
#   make test-algoritmos                                   # las 5 políticas
#   WORK_PATH=/api/mixed ID=E04 scripts/test-algoritmos.sh # E-04 costo variable
#   POLICIES="ip_hash hash_client" ID=E05 scripts/test-algoritmos.sh   # E-05 trampa ip_hash
# =============================================================================
source "$(dirname "$0")/lib.sh"
load_env

POLICIES="${POLICIES:-round_robin least_conn ip_hash hash_client random_two}"
REPS="${REPS:-3}"; [ "${QUICK:-0}" = "1" ] && REPS=1
SCENARIO="${SCENARIO:-rampa.yml}"
ID="${ID:-ALG}"
COOLDOWN="${COOLDOWN:-20}"
export WORK_PATH="${WORK_PATH:-/api/work?ms=20}"

log "===== $ID: $SCENARIO · políticas=[$POLICIES] · REPS=$REPS · WORK_PATH=$WORK_PATH ====="
for rep in $(seq 1 "$REPS"); do
  # shellcheck disable=SC2086
  for pol in $(shuffle $POLICIES); do
    "$ROOT_DIR/scripts/set-policy.sh" "$pol"
    cooldown "$COOLDOWN"
    "$ROOT_DIR/scripts/run-test.sh" "$ID" "$SCENARIO" "rep$rep"
  done
done
"$ROOT_DIR/scripts/set-policy.sh" round_robin
ok "===== $ID terminado. Ahora: make analyze ====="
