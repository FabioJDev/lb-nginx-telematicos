#!/bin/sh
# scripts/in-container/affinity-loop.sh — se ejecuta DENTRO de lb:
#   docker compose exec -T lb sh -s <clientes> <peticiones_por_cliente> < scripts/in-container/affinity-loop.sh
# Imprime "cliente,nodo" por petición; la afinidad se calcula fuera.
C="${1:-20}"; R="${2:-5}"
c=0
while [ "$c" -lt "$C" ]; do
  c=$((c + 1)); i=0
  while [ "$i" -lt "$R" ]; do
    i=$((i + 1))
    out=$(wget -qO- --timeout=5 --header="X-Client-Id: cliente-$c" "http://127.0.0.1:80/api/info" 2>/dev/null) || out=""
    node=$(printf '%s' "$out" | sed -n 's/.*"node":"\([^"]*\)".*/\1/p')
    echo "cliente-$c,${node:-__FAIL__}"
  done
done
