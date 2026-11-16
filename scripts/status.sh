#!/usr/bin/env bash
# scripts/status.sh — estado del balanceador: stub_status, política vigente,
# réplicas activas con IP y últimos reintentos registrados en el log.
source "$(dirname "$0")/lib.sh"
load_env

[ -n "$(service_containers lb)" ] || die "lb no está corriendo"

echo "=== Política / feature / keepalive (configuración generada) ==="
echo "  política : $(current_policy)"
echo "  feature  : $(current_feature)"
echo "  keepalive: $(lb_exec sh -c "grep -o 'keepalive/[a-z]*' /etc/nginx/generated/http.conf | head -1 | cut -d/ -f2")"
echo
echo "=== stub_status (http://lb:8080/stub_status) ==="
stub_status_raw | sed 's/^/  /'
echo
echo "=== Backends activos ==="
for id in $(service_containers backend); do
  docker inspect -f '  {{.Name}}  hostname={{.Config.Hostname}}  ip={{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}  health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$id" | sed 's#  /#  #'
done
echo
echo "=== Resolución DNS de 'backend' vista desde lb ==="
lb_exec sh -c "nslookup backend 127.0.0.11 2>/dev/null | awk '/^Address/ && !/127.0.0.11/ {print \"  \" \$0}'" || true
echo
echo "=== Últimas 5 líneas del log JSON ==="
lb_exec sh -c 'tail -5 /var/log/nginx/access.json 2>/dev/null' | sed 's/^/  /' || true
