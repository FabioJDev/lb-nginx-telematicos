#!/bin/sh
# scripts/in-container/stub-status-loop.sh — se ejecuta DENTRO del contenedor lb:
#   docker compose exec -T lb sh -s <run_name> [intervalo] < scripts/in-container/stub-status-loop.sh
# Sondea /stub_status cada segundo y emite CSV hasta que exista /tmp/stop-<run_name>.
# Formato de stub_status:
#   Active connections: 291
#   server accepts handled requests
#    16630948 16630948 31070465
#   Reading: 6 Writing: 179 Waiting: 106
RUN="${1:-run}"
INTERVAL="${2:-1}"
STOP="/tmp/stop-$RUN"
rm -f "$STOP"
echo "epoch,active,accepts,handled,requests,reading,writing,waiting"
while [ ! -e "$STOP" ]; do
  wget -qO- --timeout=2 http://127.0.0.1:8080/stub_status 2>/dev/null | awk -v ts="$(date +%s)" '
    NR==1 {a=$3}
    NR==3 {ac=$1; h=$2; r=$3}
    NR==4 {rd=$2; wr=$4; wa=$6}
    END { if (a != "") print ts "," a "," ac "," h "," r "," rd "," wr "," wa }'
  sleep "$INTERVAL"
done
rm -f "$STOP"
