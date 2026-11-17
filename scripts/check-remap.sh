#!/usr/bin/env bash
# scripts/check-remap.sh — E-06: ¿qué fracción de clientes cambia de backend cuando
# se retira una réplica? Con la política ACTIVA:
#   1. escala a N réplicas y mapea C clientes fijos (X-Client-Id = cliente-1..C),
#   2. elimina la última réplica (docker rm -f) y espera la re-resolución DNS,
#   3. vuelve a mapear los mismos clientes y cuenta cuántos cambiaron de backend.
# Referencia teórica: hash consistente ≈ 1/N (solo los del nodo retirado);
# hash simple (módulo) ≈ (N-1)/N; round-robin no tiene afinidad que conservar.
# Uso: scripts/check-remap.sh [N=5] [clientes=200]
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env
N="${1:-5}"; C="${2:-200}"
policy=$(current_policy)
"$ROOT_DIR/scripts/scale.sh" "$N" >/dev/null
sleep 6   # resolver valid=5s: que NGINX vea las N réplicas
before=$(mktemp); after=$(mktemp); trap 'rm -f "$before" "$after"' EXIT
compose exec -T lb sh -s "$C" 1 < "$ROOT_DIR/scripts/in-container/affinity-loop.sh" | sort > "$before"
victim=$(backend_name_by_index "$N"); vnode=$(container_hostname "$victim")
docker rm -f "$victim" >/dev/null
sleep 7
compose exec -T lb sh -s "$C" 1 < "$ROOT_DIR/scripts/in-container/affinity-loop.sh" | sort > "$after"
on_victim=$(awk -F, -v v="$vnode" '$2==v' "$before" | wc -l | tr -d ' ')
moved=$(join -t, "$before" "$after" | awk -F, '$2!=$3' | wc -l | tr -d ' ')
fails=$(grep -c '__FAIL__' "$after" || true)
pct=$(awk -v m="$moved" -v c="$C" 'BEGIN{printf "%.1f", 100*m/c}')
pv=$(awk -v m="$on_victim" -v c="$C" 'BEGIN{printf "%.1f", 100*m/c}')
echo "política=$policy N=$N->$((N-1)) clientes=$C · estaban en el nodo retirado: $on_victim ($pv %) · cambiaron de backend: $moved ($pct %) · fallos tras retirar: $fails"
"$ROOT_DIR/scripts/scale.sh" "${BACKEND_REPLICAS:-3}" >/dev/null
