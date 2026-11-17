#!/usr/bin/env bash
# =============================================================================
# scripts/test-haproxy.sh — A-05: NGINX frente a HAProxy con los MISMOS backends,
# el mismo escenario y la misma carga (datos para el criterio C1 de la matriz 4.1).
#   NGINX round_robin / least_conn   vs   HAProxy roundrobin / leastconn
# Compara latencia, goodput y, sobre todo, la CPU del propio balanceador
# (docker_stats.csv: roles "lb" y "haproxy").
# Variables: REPS=2  COOLDOWN=20  SCENARIO=rampa.yml
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

REPS="${REPS:-2}"; [ "${QUICK:-0}" = "1" ] && REPS=1
COOLDOWN="${COOLDOWN:-20}"
SCENARIO="${SCENARIO:-rampa.yml}"
HCOMPOSE=(-f "$ROOT_DIR/docker-compose.yml" -f "$ROOT_DIR/compose.haproxy.yml")

haproxy_up() {
  (cd "$ROOT_DIR" && HAPROXY_BALANCE="$1" docker compose "${HCOMPOSE[@]}" up -d --no-deps --force-recreate haproxy >/dev/null)
  wait_healthy haproxy 1 60
}

for rep in $(seq 1 "$REPS"); do
  for cfg in $(shuffle nginx:round_robin nginx:least_conn haproxy:roundrobin haproxy:leastconn); do
    lbname="${cfg%%:*}"; alg="${cfg#*:}"
    if [ "$lbname" = "nginx" ]; then
      "$ROOT_DIR/scripts/set-policy.sh" "$alg"
      cooldown "$COOLDOWN"
      "$ROOT_DIR/scripts/run-test.sh" A05 "$SCENARIO" "nginx_rep$rep"
    else
      haproxy_up "$alg"
      cooldown "$COOLDOWN"
      TARGET=http://haproxy POLICY_OVERRIDE="haproxy-$alg" \
        "$ROOT_DIR/scripts/run-test.sh" A05 "$SCENARIO" "haproxy_rep$rep"
    fi
  done
done
(cd "$ROOT_DIR" && docker compose "${HCOMPOSE[@]}" rm -sf haproxy >/dev/null) || true
"$ROOT_DIR/scripts/set-policy.sh" round_robin
ok "===== A-05 terminado. Ahora: make analyze ====="
