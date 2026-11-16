#!/usr/bin/env bash
# scripts/log-event.sh — registra un evento (con marca de tiempo) en events.csv de
# la corrida en curso y lo anota en Grafana si está levantado.
# Uso: scripts/log-event.sh <evento> [detalle]   (RUN_DIR opcional en el entorno)
source "$(dirname "$0")/lib.sh"
load_env
dir=$(current_run_dir) || die "no hay corrida en curso (results/.current_run)"
log_event "$dir" "${1:?evento}" "${2:-}"
grafana_annotate "${1}: ${2:-}" "evento,${1}"
