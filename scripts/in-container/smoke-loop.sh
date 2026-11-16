#!/bin/sh
# scripts/in-container/smoke-loop.sh — se ejecuta DENTRO del contenedor lb con:
#   docker compose exec -T lb sh -s <N> <ruta> <con_client_id:0|1> < scripts/in-container/smoke-loop.sh
# Hace N peticiones al propio NGINX (127.0.0.1:80) e imprime el nodo que respondió
# (campo "node" del JSON de /api/info) o __FAIL__ si falló.
N="${1:-30}"
PATH_URL="${2:-/api/info}"
WITH_ID="${3:-1}"
i=0
while [ "$i" -lt "$N" ]; do
  i=$((i + 1))
  if [ "$WITH_ID" = "1" ]; then
    out=$(wget -qO- --timeout=5 --header="X-Client-Id: smoke-$i-$$" "http://127.0.0.1:80$PATH_URL" 2>/dev/null) || out=""
  else
    out=$(wget -qO- --timeout=5 "http://127.0.0.1:80$PATH_URL" 2>/dev/null) || out=""
  fi
  node=$(printf '%s' "$out" | sed -n 's/.*"node":"\([^"]*\)".*/\1/p')
  if [ -n "$node" ]; then echo "$node"; else echo "__FAIL__"; fi
done
