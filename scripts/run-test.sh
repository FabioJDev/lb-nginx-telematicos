#!/usr/bin/env bash
# =============================================================================
# scripts/run-test.sh — corazón de la reproducibilidad (sección 7.9).
#
# Ejecuta UN escenario de Artillery (en su contenedor) y deja la corrida completa en
#   results/<AAAAMMDD-HHMMSS>_<id>_<política>_<N>b[_<etiqueta>]/
#     metadata.json       commit, política, réplicas, variables LB_*, imágenes, host, horas
#     artillery.json      salida --output de Artillery (aggregate + intermediate)
#     artillery.log       consola de Artillery
#     nginx_access.jsonl  SOLO las líneas del log JSON de NGINX de esta corrida
#     stub_status.csv     sondeo de stub_status cada 1 s
#     docker_stats.csv    docker stats cada 2 s
#     events.csv          eventos con marca de tiempo (inicio, fin, fallas, escalados)
#
# Uso:
#   scripts/run-test.sh <id> <escenario.yml> [etiqueta] [-- argumentos extra de artillery]
# Variables de entorno opcionales:
#   TARGET=http://lb        destino (http://haproxy para A-05)
#   WORK_PATH=/api/work?ms=20
#   PUBLISH_METRICS=1       publica métricas en Prometheus (Pushgateway, profile monitoring)
#   NOTES="texto"           nota libre que queda en metadata.json
#   STATS_INTERVAL=2        intervalo de docker stats
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

ID="${1:?id de la prueba (p. ej. M05)}"
SCENARIO="${2:?escenario (p. ej. rampa.yml)}"
shift 2
LABEL=""
if [ $# -gt 0 ] && [ "$1" != "--" ]; then LABEL="$1"; shift; fi
if [ $# -gt 0 ] && [ "$1" = "--" ]; then shift; fi
EXTRA_ARGS=("$@")

SCENARIO_FILE="$ROOT_DIR/artillery/scenarios/$SCENARIO"
[ -f "$SCENARIO_FILE" ] || die "no existe $SCENARIO_FILE"
[ -n "$(service_containers lb)" ] || die "el stack no está corriendo (make up)"

TARGET="${TARGET:-http://lb}"
WORK_PATH="${WORK_PATH:-/api/work?ms=20}"
PUBLISH_METRICS="${PUBLISH_METRICS:-0}"
STATS_INTERVAL="${STATS_INTERVAL:-2}"

# ---------------------------------------------------------------------------
# Identidad de la corrida
# ---------------------------------------------------------------------------
# POLICY_OVERRIDE: para balanceadores distintos de NGINX (p. ej. HAProxy en A-05)
POLICY="${POLICY_OVERRIDE:-$(current_policy)}"; POLICY="${POLICY:-desconocida}"
FEATURE=$(current_feature); FEATURE="${FEATURE:-none}"
REPLICAS=$(backend_count)
STAMP=$(date +%Y%m%d-%H%M%S)
RUN_NAME="${STAMP}_${ID}_${POLICY}_${REPLICAS}b${LABEL:+_$LABEL}"
RUN_DIR="$RESULTS_DIR/$RUN_NAME"
mkdir -p "$RUN_DIR"
echo "$RUN_NAME" > "$CURRENT_RUN_FILE"
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
START_EPOCH=$(date +%s)

log "corrida: $RUN_NAME"
log "escenario=$SCENARIO target=$TARGET work_path=$WORK_PATH política=$POLICY réplicas=$REPLICAS"

# ---------------------------------------------------------------------------
# Offset del log de NGINX (para extraer solo las líneas de esta corrida)
# ---------------------------------------------------------------------------
sleep 1.5   # access_log tiene buffer con flush=1s: esperar a que lo anterior esté en disco
OFFSET=$(lb_exec sh -c 'wc -c < /var/log/nginx/access.json 2>/dev/null || echo 0' | tr -d '[:space:]')
OFFSET="${OFFSET:-0}"

# ---------------------------------------------------------------------------
# Colectores en segundo plano
# ---------------------------------------------------------------------------
compose exec -T lb sh -s "$RUN_NAME" 1 < "$ROOT_DIR/scripts/in-container/stub-status-loop.sh" > "$RUN_DIR/stub_status.csv" &
STUB_PID=$!

(
  echo "epoch,name,cpu_perc,mem_usage,mem_perc,net_io,block_io,pids"
  while :; do
    ts=$(date +%s)
    docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.NetIO}},{{.BlockIO}},{{.PIDs}}' 2>/dev/null \
      | sed "s/^/$ts,/"
    sleep "$STATS_INTERVAL"
  done
) > "$RUN_DIR/docker_stats.csv" &
STATS_PID=$!

stop_collectors() {
  lb_exec sh -c "touch /tmp/stop-$RUN_NAME" 2>/dev/null || true
  kill "$STATS_PID" 2>/dev/null || true
  wait "$STUB_PID" 2>/dev/null || true
  wait "$STATS_PID" 2>/dev/null || true
}
trap stop_collectors EXIT

# ---------------------------------------------------------------------------
# Artillery
# ---------------------------------------------------------------------------
ART_ARGS=(run)
if [ "$PUBLISH_METRICS" = "1" ]; then
  if [ -n "$(service_containers pushgateway)" ]; then
    ART_ARGS+=(--config /scripts/config/publish-prometheus.yml)
  else
    warn "PUBLISH_METRICS=1 pero pushgateway no está corriendo (make monitoring-up); se omite"
  fi
fi
ART_ARGS+=("/scripts/scenarios/$SCENARIO" --output "/results/$RUN_NAME/artillery.json")
[ ${#EXTRA_ARGS[@]} -gt 0 ] && ART_ARGS+=("${EXTRA_ARGS[@]}")

log_event "$RUN_DIR" artillery_start "scenario=$SCENARIO policy=$POLICY replicas=$REPLICAS target=$TARGET"
grafana_annotate "Inicio $ID · $SCENARIO · $POLICY · ${REPLICAS}b" "artillery,inicio,$ID"

set +e
compose run --rm -T --no-deps \
  -e "TARGET=$TARGET" -e "WORK_PATH=$WORK_PATH" -e "TEST_ID=$ID" -e "RUN_NAME=$RUN_NAME" \
  artillery "${ART_ARGS[@]}" 2>&1 | tee "$RUN_DIR/artillery.log"
ART_EXIT=${PIPESTATUS[0]}
set -e

END_EPOCH=$(date +%s)
END_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
log_event "$RUN_DIR" artillery_end "exit=$ART_EXIT duration_s=$((END_EPOCH - START_EPOCH))"
grafana_annotate "Fin $ID (exit=$ART_EXIT)" "artillery,fin,$ID"

# ---------------------------------------------------------------------------
# Recolección final
# ---------------------------------------------------------------------------
sleep 2   # flush=1s del access_log con buffer
stop_collectors
trap - EXIT
lb_exec sh -c "tail -c +$((OFFSET + 1)) /var/log/nginx/access.json 2>/dev/null" > "$RUN_DIR/nginx_access.jsonl" || true
LOG_LINES=$(wc -l < "$RUN_DIR/nginx_access.jsonl" | tr -d ' ')

# ---------------------------------------------------------------------------
# metadata.json (sin jq en el host: se arma a mano con valores simples)
# ---------------------------------------------------------------------------
json_str() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
GIT_COMMIT=$(cd "$ROOT_DIR" && git rev-parse --short HEAD 2>/dev/null || echo "sin-git")
GIT_DIRTY=$(cd "$ROOT_DIR" && { git diff --quiet 2>/dev/null && echo false || echo true; })
DOCKER_VER=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "?")
COMPOSE_VER=$(docker compose version --short 2>/dev/null || echo "?")
HOST_CPUS=$(nproc 2>/dev/null || echo "?")
HOST_MEM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo "?")
HOST_KERNEL=$(uname -r 2>/dev/null || echo "?")
NGINX_VER=$(lb_exec nginx -v 2>&1 | sed 's/.*nginx\///' | tr -d '[:space:]' || echo "?")
KEEPALIVE=$(lb_exec sh -c "grep -o 'keepalive/[a-z]*' /etc/nginx/generated/http.conf | head -1 | cut -d/ -f2" | tr -d '[:space:]')

cat > "$RUN_DIR/metadata.json" <<EOF
{
  "run_name": "$RUN_NAME",
  "test_id": "$ID",
  "label": "$(json_str "$LABEL")",
  "notes": "$(json_str "${NOTES:-}")",
  "scenario": "$SCENARIO",
  "target": "$TARGET",
  "work_path": "$(json_str "$WORK_PATH")",
  "policy": "$POLICY",
  "feature": "$FEATURE",
  "upstream_keepalive": "$KEEPALIVE",
  "replicas": $REPLICAS,
  "warmup_seconds": ${WARMUP_SECONDS:-30},
  "started_at": "$START_ISO",
  "ended_at": "$END_ISO",
  "start_epoch": $START_EPOCH,
  "end_epoch": $END_EPOCH,
  "artillery_exit_code": $ART_EXIT,
  "nginx_log_lines": $LOG_LINES,
  "nginx_log_offset": $OFFSET,
  "publish_metrics": "$PUBLISH_METRICS",
  "git_commit": "$GIT_COMMIT",
  "git_dirty": $GIT_DIRTY,
  "images": {
    "nginx": "$NGINX_IMAGE",
    "nginx_version": "$NGINX_VER",
    "artillery": "$ARTILLERY_IMAGE",
    "backend": "lbnginx-backend:local (node:24-alpine)"
  },
  "env": {
    "NGINX_WORKER_PROCESSES": "$NGINX_WORKER_PROCESSES",
    "NGINX_WORKER_CONNECTIONS": "$NGINX_WORKER_CONNECTIONS",
    "LB_MAX_FAILS": "$LB_MAX_FAILS",
    "LB_FAIL_TIMEOUT": "$LB_FAIL_TIMEOUT",
    "LB_CONNECT_TIMEOUT": "$LB_CONNECT_TIMEOUT",
    "LB_SEND_TIMEOUT": "$LB_SEND_TIMEOUT",
    "LB_READ_TIMEOUT": "$LB_READ_TIMEOUT",
    "LB_NEXT_UPSTREAM": "$(json_str "$LB_NEXT_UPSTREAM")",
    "LB_NEXT_UPSTREAM_TRIES": "$LB_NEXT_UPSTREAM_TRIES",
    "LB_NEXT_UPSTREAM_TIMEOUT": "$LB_NEXT_UPSTREAM_TIMEOUT",
    "BACKEND_CPUS": "$BACKEND_CPUS",
    "BACKEND_MEMORY": "$BACKEND_MEMORY",
    "BACKEND_BASE_DELAY_MS": "$BACKEND_BASE_DELAY_MS",
    "SESSION_STORE": "${SESSION_STORE:-redis}",
    "DB_POOL_MAX": "${DB_POOL_MAX:-10}",
    "DB_CPUS": "${DB_CPUS:-1.0}"
  },
  "host": {
    "docker_server": "$DOCKER_VER",
    "compose": "$COMPOSE_VER",
    "cpus": "$HOST_CPUS",
    "mem_mb": "$HOST_MEM_MB",
    "kernel": "$HOST_KERNEL"
  }
}
EOF

# Resumen rápido en consola (los números definitivos los produce make analyze)
if [ -f "$RUN_DIR/artillery.json" ]; then
  log "resumen rápido (aggregate de Artillery):"
  grep -oE '"(http\.(requests|responses|codes\.[0-9]+)|vusers\.(created|completed|failed))": *[0-9]+' "$RUN_DIR/artillery.json" \
    | head -12 | sed 's/^/    /' || true
fi
echo
ok "corrida guardada en results/$RUN_NAME (artillery exit=$ART_EXIT, $LOG_LINES líneas de log NGINX)"
[ "$ART_EXIT" -eq 0 ] || warn "Artillery terminó con código $ART_EXIT (umbral 'ensure' no cumplido o error): revisar artillery.log"
echo "$RUN_NAME"
