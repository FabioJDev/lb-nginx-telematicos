#!/usr/bin/env bash
# scripts/scale.sh — escala los backends SIN recrear los existentes y espera a que
# todos estén healthy. Gracias a 'resolve' en el upstream, NGINX descubre las
# réplicas nuevas por DNS sin recargar (E-10).
#
# Uso: scripts/scale.sh <N>
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

N="${1:?número de réplicas}"
load_env
[[ "$N" =~ ^[0-9]+$ ]] && [ "$N" -ge 0 ] || die "N debe ser un entero >= 0"

before=$(backend_count)
log "escalando backend: $before -> $N réplicas"
compose up -d --no-deps --no-recreate --scale "backend=$N" backend >/dev/null
if [ "$N" -gt 0 ]; then
  wait_healthy backend "$N" 120
fi
after=$(backend_count)
ok "backends activos: $after"
echo "Réplicas (nombre -> hostname/IP):"
for id in $(service_containers backend); do
  docker inspect -f '  {{.Name}} -> {{.Config.Hostname}} {{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$id" | sed 's#^  /#  #'
done
