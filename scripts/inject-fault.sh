#!/usr/bin/env bash
# scripts/inject-fault.sh — inyección de fallos en UN backend (M-03, E-07, E-09).
#
# Uso: scripts/inject-fault.sh <acción> [índice=1]
#   rm        docker rm -f: el contenedor DESAPARECE (no vuelve solo; reponer con scale)
#   stop      docker stop (SIGTERM, apagado elegante; no vuelve por restart policy)
#   start     docker start del contenedor detenido con 'stop'
#   kill      docker kill (SIGKILL). OJO: restart: unless-stopped lo REINICIA solo
#   pause     docker pause: el proceso se congela (conexiones aceptadas por el kernel,
#             nunca respondidas -> timeout, no "connection refused")
#   unpause   docker unpause
#   crash     POST /admin/crash (exit 1): Docker lo reinicia por la política restart
#   fault:MODE  POST /admin/fault {"mode":MODE} con MODE = none|error500|slow|hang|unhealthy
#   restore   fault:none
#
# Registra el evento en events.csv de la corrida en curso (si la hay) y anota en Grafana.
source "$(dirname "$0")/lib.sh"
load_env

ACTION="${1:?acción}"; IDX="${2:-1}"

name=$(backend_name_by_index "$IDX")
if [ -z "$name" ] && [[ "$ACTION" != "start" ]]; then
  die "no hay backend con índice $IDX (activos: $(backend_count))"
fi
if [ "$ACTION" = "start" ]; then
  # Contenedores detenidos no aparecen en 'running': buscar entre todos
  name=$(docker ps -a --format '{{.Names}}' --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}" \
         --filter "label=com.docker.compose.service=backend" --filter "status=exited" | sort -V | sed -n "${IDX}p")
  [ -n "$name" ] || die "no hay backend detenido con índice $IDX"
fi
node=$(container_hostname "$name")

record() {
  local dir
  if dir=$(current_run_dir 2>/dev/null) && [ -d "$dir" ]; then
    log_event "$dir" "$1" "node=$node container=$name $2"
  else
    log "evento (sin corrida en curso): $1 node=$node $2"
  fi
  grafana_annotate "$1 $node $2" "falla,$1"
}

t0=$(date +%s.%N)
case "$ACTION" in
  rm)      docker rm -f "$name" >/dev/null; record backend_removed "accion=rm" ;;
  stop)    docker stop -t 10 "$name" >/dev/null; record backend_stopped "accion=stop(SIGTERM)" ;;
  start)   docker start "$name" >/dev/null; record backend_started "accion=start" ;;
  kill)    docker kill "$name" >/dev/null; record backend_killed "accion=kill(SIGKILL,restart automático)" ;;
  pause)   docker pause "$name" >/dev/null; record backend_paused "accion=pause" ;;
  unpause) docker unpause "$name" >/dev/null; record backend_unpaused "accion=unpause" ;;
  crash)   docker exec "$name" wget -qO- --post-data='{}' http://127.0.0.1:3000/admin/crash >/dev/null || true
           record backend_crashed "accion=crash(exit 1,restart automático)" ;;
  fault:*) mode="${ACTION#fault:}"
           out=$(docker exec "$name" wget -qO- --header='Content-Type: application/json' \
                 --post-data="{\"mode\":\"$mode\"}" http://127.0.0.1:3000/admin/fault) || die "no se pudo cambiar el modo"
           record "fault_$mode" "accion=fault respuesta=$out" ;;
  restore) out=$(docker exec "$name" wget -qO- --header='Content-Type: application/json' \
                 --post-data='{"mode":"none"}' http://127.0.0.1:3000/admin/fault) || die "no se pudo restaurar"
           record fault_none "accion=restore respuesta=$out" ;;
  *) die "acción desconocida: $ACTION" ;;
esac
ok "$ACTION aplicado a $name (nodo $node) en $(awk -v a="$t0" -v b="$(date +%s.%N)" 'BEGIN{printf "%.2f", b-a}') s"
