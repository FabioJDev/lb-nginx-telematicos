#!/usr/bin/env bash
# =============================================================================
# scripts/test-tienda.sh — E-16: ¿sobrevive la SESIÓN al balanceo?
#
# Recorrido de compra completo (tienda.yml: catálogo, login, carrito, pedido) con
# cada política y con las sesiones en memoria de cada réplica o en Redis.
#   SESSION_STORE=memory + política sin afinidad -> el carrito se "pierde"
#   SESSION_STORE=memory + ip_hash / hash_client / sticky_cookie -> funciona
#   SESSION_STORE=redis  + cualquier política -> funciona
#
# Variables: SESSIONS="memory redis"  REPS=2  COOLDOWN=15  SCENARIO=tienda.yml
#   POLICIES="round_robin least_conn random_two ip_hash hash_client sticky_cookie"
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

SESSIONS="${SESSIONS:-memory redis}"
POLICIES="${POLICIES:-round_robin least_conn random_two ip_hash hash_client sticky_cookie}"
REPS="${REPS:-2}"; [ "${QUICK:-0}" = "1" ] && REPS=1
COOLDOWN="${COOLDOWN:-15}"
SCENARIO="${SCENARIO:-tienda.yml}"
ID="${ID:-E16}"

"$ROOT_DIR/scripts/scale.sh" "${BACKEND_REPLICAS:-3}"
for store in $SESSIONS; do
  log "===== $ID: sesiones en $store · políticas=[$POLICIES] · REPS=$REPS ====="
  "$ROOT_DIR/scripts/set-env.sh" SESSION_STORE "$store" --recreate-backend
  export SESSION_STORE="$store"
  for rep in $(seq 1 "$REPS"); do
    # shellcheck disable=SC2086
    for pol in $(shuffle $POLICIES); do
      "$ROOT_DIR/scripts/set-policy.sh" "$pol"
      cooldown "$COOLDOWN"
      NOTES="sesiones en $store" "$ROOT_DIR/scripts/run-test.sh" "$ID" "$SCENARIO" "ses-${store}_rep$rep"
    done
  done
done
"$ROOT_DIR/scripts/set-env.sh" SESSION_STORE redis --recreate-backend
"$ROOT_DIR/scripts/set-policy.sh" round_robin
ok "===== $ID terminado. Ahora: make analyze ====="
