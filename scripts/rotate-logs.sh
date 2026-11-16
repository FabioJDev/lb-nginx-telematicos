#!/usr/bin/env bash
# scripts/rotate-logs.sh — rotación manual del log JSON del balanceador para no
# llenar el disco: renombra access.json con marca de tiempo y pide a NGINX que
# reabra los archivos (nginx -s reopen), sin cortar el servicio.
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env
stamp=$(date +%Y%m%d-%H%M%S)
lb_exec sh -c "cd /var/log/nginx && [ -f access.json ] && mv access.json access-$stamp.json && [ -f error.log ] && mv error.log error-$stamp.log; nginx -s reopen"
ok "logs rotados: logs/nginx/access-$stamp.json"
ls -la "$ROOT_DIR/logs/nginx" | sed 's/^/  /'
