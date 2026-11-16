#!/usr/bin/env bash
# scripts/wait-healthy.sh — espera a que <servicio> tenga <N> contenedores healthy.
# Uso: scripts/wait-healthy.sh <servicio> [N=1] [timeout_s=120]
source "$(dirname "$0")/lib.sh"
load_env
wait_healthy "${1:?servicio}" "${2:-1}" "${3:-120}"
