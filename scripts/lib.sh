#!/usr/bin/env bash
# scripts/lib.sh — funciones comunes para los scripts del proyecto.
# Se carga con:  source "$(dirname "$0")/lib.sh"
# Todo se hace a través de docker / docker compose: nada se instala en el host.
# shellcheck shell=bash

set -euo pipefail

# Git Bash (MSYS) en Windows convierte los argumentos con forma de ruta Unix al llamar a
# docker.exe ("/api/info" -> "C:/Program Files/Git/api/info"). Se desactiva esa conversión
# para que las rutas lleguen intactas a los contenedores. En Linux/WSL no tiene efecto.
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' ;;
esac

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
RESULTS_DIR="$ROOT_DIR/results"
CURRENT_RUN_FILE="$RESULTS_DIR/.current_run"

# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
log()  { printf '\033[1;34m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
ok()   { printf '\033[1;32m[%s] OK\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
warn() { printf '\033[1;33m[%s] AVISO\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die()  { printf '\033[1;31m[%s] ERROR\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------
ensure_env() {
  if [ ! -f "$ENV_FILE" ]; then
    cp "$ROOT_DIR/.env.example" "$ENV_FILE"
    log "creado .env desde .env.example"
  fi
}

# Exporta las variables de .env al entorno del script, sin pisar las que se fijaron
# EXPLÍCITAMENTE (p. ej. TARGET=http://haproxy scripts/run-test.sh …, o un
# `export LB_WEIGHT_FAST=3` de un lote).
#
# Las que vinieron de un load_env anterior (registradas en _LBNGINX_ENV_SNAPSHOT) se
# REFRESCAN desde el .env actual: si set-env.sh cambió el .env a mitad de un lote, los
# scripts hijos y las llamadas a Compose ven el valor nuevo y no el heredado. (Sin esto,
# E-08 corrió sus 4 configuraciones con el mismo timeout: ver docs/hallazgos.md, H-9.)
load_env() {
  ensure_env
  local line key value snap_line
  declare -A _snap=()
  while IFS= read -r snap_line; do
    [ -n "$snap_line" ] && _snap["${snap_line%%=*}"]="${snap_line#*=}"
  done <<< "${_LBNGINX_ENV_SNAPSHOT:-}"
  local new_snapshot=""
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue ;; esac
    key="${line%%=*}"
    value="${line#*=}"
    if [ -z "${!key+x}" ]; then
      export "$key=$value"                       # no estaba definida
    elif [ -n "${_snap[$key]+x}" ] && [ "${!key}" = "${_snap[$key]}" ]; then
      export "$key=$value"                       # heredada de un .env anterior: refrescar
    fi                                           # si no, la fijó alguien explícitamente
    [ "${!key}" = "$value" ] && new_snapshot+="${key}=${value}"$'\n'
  done < "$ENV_FILE"
  export _LBNGINX_ENV_SNAPSHOT="$new_snapshot"
  export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-lbnginx}"
}

# Actualiza (o añade) KEY=VALUE en .env
set_env_var() {
  local key="$1" value="$2"
  ensure_env
  if grep -qE "^${key}=" "$ENV_FILE"; then
    # sed -i portable entre GNU y BSD
    sed -i.bak -E "s|^${key}=.*|${key}=${value}|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

# ---------------------------------------------------------------------------
# Docker / Compose
# ---------------------------------------------------------------------------
# COMPOSE_EXTRA_ARGS permite añadir archivos: COMPOSE_EXTRA_ARGS="-f docker-compose.yml -f compose.weighted.yml"
compose() {
  # Releer .env justo antes de cada llamada (solo en esta subshell): Compose interpola
  # con el entorno, que tiene prioridad sobre .env, así que debe llevar el valor vigente.
  # shellcheck disable=SC2086
  (cd "$ROOT_DIR" && load_env && docker compose ${COMPOSE_EXTRA_ARGS:-} "$@")
}

lb_exec() { compose exec -T lb "$@"; }
lb_get()  { lb_exec wget -qO- "$1"; }

# IDs de contenedores de un servicio (incluso si está en un profile no activo)
service_containers() {
  docker ps -q \
    --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME:-lbnginx}" \
    --filter "label=com.docker.compose.service=$1" \
    --filter "status=running"
}

# Nombres ordenados de los contenedores de un servicio
service_container_names() {
  docker ps --format '{{.Names}}' \
    --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME:-lbnginx}" \
    --filter "label=com.docker.compose.service=$1" | sort -V
}

backend_count() { service_containers backend | wc -l | tr -d ' '; }

healthy_count() {
  local ids
  ids=$(service_containers "$1")
  [ -z "$ids" ] && { echo 0; return; }
  # shellcheck disable=SC2086
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $ids | grep -c '^healthy$' || true
}

# Espera a que 'expected' contenedores del servicio estén healthy (timeout en s)
wait_healthy() {
  local service="$1" expected="${2:-1}" timeout="${3:-120}" waited=0 n
  while :; do
    n=$(healthy_count "$service")
    if [ "$n" -ge "$expected" ]; then ok "$service: $n/$expected healthy"; return 0; fi
    if [ "$waited" -ge "$timeout" ]; then die "$service: solo $n/$expected healthy tras ${timeout}s"; fi
    sleep 2; waited=$((waited + 2))
  done
}

# Política vigente según la configuración GENERADA dentro del contenedor
current_policy() {
  lb_exec sh -c "grep -o 'policies/[a-z_]*' /etc/nginx/generated/http.conf | head -1 | cut -d/ -f2" 2>/dev/null \
    | tr -d '[:space:]' || true
}

current_feature() {
  lb_exec sh -c "grep -o 'features/[a-z_]*' /etc/nginx/generated/http.conf | head -1 | cut -d/ -f2" 2>/dev/null \
    | tr -d '[:space:]' || true
}

stub_status_raw() { lb_get http://127.0.0.1:8080/stub_status; }

# ---------------------------------------------------------------------------
# Corridas y eventos
# ---------------------------------------------------------------------------
current_run_dir() {
  if [ -n "${RUN_DIR:-}" ]; then echo "$RUN_DIR"; return; fi
  [ -f "$CURRENT_RUN_FILE" ] || return 1
  echo "$RESULTS_DIR/$(cat "$CURRENT_RUN_FILE")"
}

# log_event <run_dir> <evento> <detalle>
log_event() {
  local dir="$1" event="$2" detail="${3:-}"
  mkdir -p "$dir"
  [ -f "$dir/events.csv" ] || echo "epoch,iso,event,detail" > "$dir/events.csv"
  printf '%s,%s,%s,"%s"\n' "$(date +%s.%N)" "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" "$event" "${detail//\"/\'}" >> "$dir/events.csv"
  log "evento: $event $detail"
}

# Anotación en Grafana (solo si está corriendo). Se envía desde el contenedor lb,
# que comparte la red frontend con grafana (sin curl en el host).
grafana_annotate() {
  local text="$1" tags="${2:-}"
  [ -n "$(service_containers grafana)" ] || return 0
  local auth tagjson
  auth=$(printf '%s:%s' "${GRAFANA_ADMIN_USER:-admin}" "${GRAFANA_ADMIN_PASSWORD:-cambiar-esto}" | base64 | tr -d '\n')
  tagjson=$(printf '%s' "$tags" | awk -F, '{for(i=1;i<=NF;i++){printf "%s\"%s\"", (i>1?",":""), $i}}')
  lb_exec wget -qO- --timeout=3 \
    --header="Content-Type: application/json" \
    --header="Authorization: Basic $auth" \
    --post-data="{\"text\":\"${text//\"/\'}\",\"tags\":[${tagjson}]}" \
    http://grafana:3000/api/annotations >/dev/null 2>&1 || warn "no se pudo anotar en Grafana"
}

# Devuelve el índice (1..N) de un backend a su nombre de contenedor
backend_name_by_index() {
  service_container_names backend | sed -n "${1}p"
}

# Hostname (= X-Backend-Node) de un contenedor
container_hostname() { docker inspect -f '{{.Config.Hostname}}' "$1"; }

cooldown() {
  local s="${1:-20}"
  log "enfriamiento ${s}s"
  sleep "$s"
}

# Mezcla aleatoriamente los argumentos (orden aleatorio de configuraciones, sección 8.2)
shuffle() { printf '%s\n' "$@" | awk 'BEGIN{srand()} {print rand() "\t" $0}' | sort -n | cut -f2-; }
