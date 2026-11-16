#!/usr/bin/env bash
# scripts/set-policy.sh — cambia la política de balanceo (R-08):
#   1. valida que exista nginx/policies/<P>.conf,
#   2. actualiza LB_POLICY en .env,
#   3. recrea SOLO el servicio lb (docker compose up -d --no-deps --force-recreate lb)
#      para empezar con contadores limpios,
#   4. muestra la cabecera X-LB-Policy de una petición de prueba.
#
# Uso: scripts/set-policy.sh <round_robin|least_conn|ip_hash|hash_client|hash_remote_addr|random_two>
source "$(dirname "$0")/lib.sh"

P="${1:?política}"
load_env
[ -f "$ROOT_DIR/nginx/policies/$P.conf" ] || die "no existe nginx/policies/$P.conf. Disponibles: $(ls "$ROOT_DIR/nginx/policies" | sed 's/\.conf$//' | tr '\n' ' ')"

set_env_var LB_POLICY "$P"
export LB_POLICY="$P"
log "recreando lb con LB_POLICY=$P"
compose up -d --no-deps --force-recreate lb >/dev/null
wait_healthy lb 1 60

applied=$(current_policy)
[ "$applied" = "$P" ] || die "la política aplicada ($applied) no coincide con la pedida ($P)"
hdr=$(lb_exec wget -qS -O /dev/null http://127.0.0.1/api/info 2>&1 | grep -i 'X-LB-Policy' | tr -d '\r' || true)
ok "política activa: $P  (${hdr:-sin cabecera})"
