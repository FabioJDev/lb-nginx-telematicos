#!/usr/bin/env bash
# =============================================================================
# scripts/test-resiliencia.sh — M-03 (R-22): eliminar un backend EN CALIENTE bajo
# carga constante y verificar la continuidad del servicio.
#
#   t = 0 s    constante.yml (100 VU/s, 180 s) con la política indicada
#   t = 60 s   docker rm -f de la réplica 1  -> evento backend_removed
#   t = 120 s  scale a N réplicas (repone)   -> evento backend_restored
#   t = 180 s  fin
#
# Uso: scripts/test-resiliencia.sh [política=round_robin] [acción=rm] [t_falla=60] [t_repo=120]
#   acción: rm | stop | kill | pause | crash | fault:error500 | fault:hang | fault:slow
# El análisis (make analyze) dibuja errores/s y p99/s con líneas en los eventos.
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

POLICY="${1:-round_robin}"
ACTION="${2:-rm}"
T_FAULT="${3:-60}"
T_RESTORE="${4:-120}"
N="${BACKEND_REPLICAS:-3}"
SCENARIO="${SCENARIO:-constante.yml}"
ID="${ID:-M03}"
LABEL="${LABEL:-${ACTION//:/-}}"

"$ROOT_DIR/scripts/scale.sh" "$N"
"$ROOT_DIR/scripts/set-policy.sh" "$POLICY"
log "$ID: $SCENARIO · falla '$ACTION' en t=${T_FAULT}s · reposición en t=${T_RESTORE}s"

before=$(cat "$CURRENT_RUN_FILE" 2>/dev/null || true)
"$ROOT_DIR/scripts/run-test.sh" "$ID" "$SCENARIO" "$LABEL" &
RUN_PID=$!

# Esperar a que run-test.sh registre artillery_start en su events.csv
for _ in $(seq 1 60); do
  cur=$(cat "$CURRENT_RUN_FILE" 2>/dev/null || true)
  if [ -n "$cur" ] && [ "$cur" != "$before" ] && grep -q artillery_start "$RESULTS_DIR/$cur/events.csv" 2>/dev/null; then break; fi
  sleep 1
done
RUN_DIR="$RESULTS_DIR/$(cat "$CURRENT_RUN_FILE")"
export RUN_DIR
t_start=$(awk -F, '/artillery_start/ {print $1}' "$RUN_DIR/events.csv" | head -1)

sleep_until() { # duerme hasta <segundos> después de artillery_start
  local d
  d=$(awk -v a="$t_start" -v t="$1" -v n="$(date +%s.%N)" 'BEGIN{d=a+t-n; printf "%.2f", (d>0?d:0)}')
  sleep "$d"
}

sleep_until "$T_FAULT"
"$ROOT_DIR/scripts/inject-fault.sh" "$ACTION" 1

sleep_until "$T_RESTORE"
case "$ACTION" in
  rm)       log_event "$RUN_DIR" backend_restore_start "accion=scale N=$N (inicio)"
            "$ROOT_DIR/scripts/scale.sh" "$N"; log_event "$RUN_DIR" backend_restored "accion=scale N=$N (réplica healthy)"
            grafana_annotate "backend repuesto (scale $N)" "recuperacion" ;;
  stop)     "$ROOT_DIR/scripts/inject-fault.sh" start 1 ;;
  pause)    "$ROOT_DIR/scripts/inject-fault.sh" unpause 1 ;;
  fault:*)  "$ROOT_DIR/scripts/inject-fault.sh" restore 1 ;;
  kill|crash) log_event "$RUN_DIR" backend_restored "accion=restart automático (restart: unless-stopped)" ;;
esac

wait "$RUN_PID" || true
ok "M-03 ($POLICY, $ACTION) terminado: $RUN_DIR"
