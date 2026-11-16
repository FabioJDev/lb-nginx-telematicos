#!/usr/bin/env bash
# scripts/set-env.sh — actualiza una variable en .env y, opcionalmente, recrea
# SOLO el servicio lb para que tome el nuevo valor (sin tocar los backends).
#
# Uso: scripts/set-env.sh <CLAVE> <VALOR> [--recreate-lb]
source "$(dirname "$0")/lib.sh"

KEY="${1:?clave}"; VALUE="${2:?valor}"; RECREATE="${3:-}"
load_env

case "$KEY" in
  LB_FEATURE)
    [ -d "$ROOT_DIR/nginx/extras/features/$VALUE" ] || die "no existe nginx/extras/features/$VALUE (none|ratelimit|microcache)";;
  LB_UPSTREAM_KEEPALIVE)
    [ -f "$ROOT_DIR/nginx/extras/keepalive/$VALUE.conf" ] || die "valor inválido: $VALUE (on|off)";;
  LB_POLICY)
    [ -f "$ROOT_DIR/nginx/policies/$VALUE.conf" ] || die "no existe nginx/policies/$VALUE.conf";;
esac

set_env_var "$KEY" "$VALUE"
ok ".env: $KEY=$VALUE"

if [ "$RECREATE" = "--recreate-lb" ]; then
  log "recreando solo el servicio lb para aplicar $KEY"
  export "$KEY=$VALUE"
  compose up -d --no-deps --force-recreate lb >/dev/null
  wait_healthy lb 1 60
  lb_exec nginx -t 2>&1 | sed 's/^/  /'
fi
