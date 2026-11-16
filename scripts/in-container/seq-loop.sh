#!/bin/sh
# scripts/in-container/seq-loop.sh — N peticiones SECUENCIALES (una tras otra) desde
# dentro de lb. Imprime "epoch_ms,node,status_ok" por petición (M-02).
N="${1:-1000}"
PATH_URL="${2:-/api/info}"
i=0
while [ "$i" -lt "$N" ]; do
  i=$((i + 1))
  out=$(wget -qO- --timeout=5 --header="X-Client-Id: seq-$i" "http://127.0.0.1:80$PATH_URL" 2>/dev/null) && okf=1 || okf=0
  node=$(printf '%s' "$out" | sed -n 's/.*"node":"\([^"]*\)".*/\1/p')
  echo "$(date +%s%3N 2>/dev/null || date +%s),${node:-__FAIL__},$okf"
done
