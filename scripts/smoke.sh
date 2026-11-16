#!/usr/bin/env bash
# scripts/smoke.sh — M-00: N peticiones a /api/info a través del balanceador y
# conteo por nodo (cabecera/campo "node"). Falla si:
#   - alguna petición falla, o
#   - con políticas que reparten (round_robin, least_conn, hash_client, random_two)
#     responden menos de min(3, réplicas) nodos distintos.
# Con ip_hash / hash_remote_addr se ESPERA un solo nodo (todas las peticiones salen
# de la misma IP) y así se informa.
#
# Uso: scripts/smoke.sh [N=30] [ruta=/api/info]
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

N="${1:-30}"
PATH_URL="${2:-/api/info}"

[ -n "$(service_containers lb)" ] || die "el servicio lb no está corriendo (make up)"

replicas=$(backend_count)
policy=$(current_policy)
feature=$(current_feature)
log "smoke: $N peticiones a $PATH_URL · política=$policy · feature=$feature · backends activos=$replicas"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
compose exec -T lb sh -s "$N" "$PATH_URL" 1 < "$ROOT_DIR/scripts/in-container/smoke-loop.sh" > "$tmp"

fails=$(grep -c '^__FAIL__$' "$tmp" || true)
echo
echo "Peticiones por nodo (X-Backend-Node):"
grep -v '^__FAIL__$' "$tmp" | sort | uniq -c | sort -rn | awk '{printf "  %5d  %s\n", $1, $2}'
distinct=$(grep -v '^__FAIL__$' "$tmp" | sort -u | wc -l | tr -d ' ')
echo "  nodos distintos: $distinct · fallos: $fails"
echo

case "$policy" in
  ip_hash|hash_remote_addr)
    expected=1
    log "con $policy todas las peticiones de una misma IP (/24 o IP completa) van al mismo backend: se espera 1 nodo"
    ;;
  *)
    expected=$(( replicas < 3 ? replicas : 3 ))
    ;;
esac

[ "$fails" -eq 0 ] || die "smoke: $fails peticiones fallaron"
[ "$distinct" -ge "$expected" ] || die "smoke: respondieron $distinct nodos, se esperaban al menos $expected"
ok "smoke superado ($distinct nodos, 0 fallos, política $policy)"

echo
compose ps --format 'table {{.Service}}\t{{.Name}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || compose ps
