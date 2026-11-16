#!/usr/bin/env bash
# scripts/check-affinity.sh — mide la afinidad de sesión de la política ACTIVA:
# C clientes lógicos (cabecera X-Client-Id distinta) hacen R peticiones cada uno
# desde la misma IP; se reporta el % de clientes que siempre cayeron en el mismo
# backend y cuántos backends distintos respondieron en total.
#   round_robin / least_conn / random_two -> afinidad baja, 3 backends
#   hash_client / hash_client_plain       -> afinidad 100 %, varios backends
#   ip_hash / hash_remote_addr            -> afinidad 100 %, 1 solo backend (misma IP)
# Uso: scripts/check-affinity.sh [clientes=30] [peticiones=5] [--expect-sticky]
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env
C="${1:-30}"; R="${2:-5}"; EXPECT="${3:-}"
[ -n "$(service_containers lb)" ] || die "lb no está corriendo"
policy=$(current_policy)
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
compose exec -T lb sh -s "$C" "$R" < "$ROOT_DIR/scripts/in-container/affinity-loop.sh" > "$tmp"
fails=$(grep -c ',__FAIL__$' "$tmp" || true)
sticky=$(grep -v '__FAIL__' "$tmp" | sort -u | cut -d, -f1 | sort | uniq -c | awk '$1==1{s++} END{print s+0}')
clients=$(cut -d, -f1 "$tmp" | sort -u | wc -l | tr -d ' ')
nodes=$(grep -v '__FAIL__' "$tmp" | cut -d, -f2 | sort -u | wc -l | tr -d ' ')
pct=$(awk -v s="$sticky" -v c="$clients" 'BEGIN{printf "%.1f", (c>0? 100*s/c : 0)}')
echo "política=$policy clientes=$clients peticiones/cliente=$R · clientes fieles a un backend: $sticky ($pct %) · backends distintos: $nodes · fallos: $fails"
[ "$fails" -eq 0 ] || die "hubo peticiones fallidas"
if [ "$EXPECT" = "--expect-sticky" ] && [ "$sticky" -ne "$clients" ]; then
  die "se esperaba afinidad 100 % con $policy y fue $pct %"
fi
