#!/usr/bin/env bash
# scripts/capturas.sh — capturas de pantalla REALES de la evidencia, tomadas con un
# navegador sin interfaz mientras el sistema atiende carga:
#
#   M-00        docs/capturas/nodo_<i>.png      la página /nodo cambia de color (nodo)
#               docs/capturas/tienda.png        la tienda web servida a través del LB
#   M-01 / R-21 docs/capturas/stub_status_<política>.png (+ .txt con el texto crudo)
#               docs/capturas/distribucion_<política>.txt (respuestas por backend, Artillery)
#   R-18        docs/capturas/grafana_<política>.png (dashboard durante la carga)
#
# Requiere el stack base levantado. Levanta monitoring y el navegador con
# compose.capturas.yml. Uso: scripts/capturas.sh   (POLICIES="..." LOAD_SECONDS=75)
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

POLICIES="${POLICIES:-round_robin least_conn ip_hash hash_client hash_remote_addr random_two sticky_cookie}"
LOAD_SECONDS="${LOAD_SECONDS:-75}"
SHOT_AFTER="${SHOT_AFTER:-50}"
PW_VERSION="${PW_VERSION:-1.64.1}"
OUT="$ROOT_DIR/docs/capturas"

files="-f docker-compose.yml"
[ -f "$ROOT_DIR/docker-compose.override.yml" ] && files="$files -f docker-compose.override.yml"
export COMPOSE_EXTRA_ARGS="$files -f compose.capturas.yml"
export COMPOSE_PROFILES="monitoring,capturas"
load_env
mkdir -p "$OUT"

# shot <url> <archivo> <ancho,alto> [espera_ms]
shot() {
  compose exec -T navegador npx -y "playwright@$PW_VERSION" screenshot \
    --viewport-size="$3" --wait-for-timeout="${4:-1500}" "$1" "/out/$2" >/dev/null \
    || die "no se pudo capturar $1"
  ok "captura: docs/capturas/$2"
}

# http_ok <url>: el navegador alcanza la URL (usa el Node de la imagen de Playwright)
http_ok() {
  compose exec -T navegador node -e \
    "fetch('$1').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" >/dev/null 2>&1
}

log "levantando monitoring y navegador (compose.capturas.yml)"
compose up -d >/dev/null
wait_healthy lb 1 60
for _ in $(seq 1 60); do http_ok http://grafana:3000/api/health && break; sleep 2; done
http_ok http://grafana:3000/api/health || die "Grafana no responde"
# Precalentar la interfaz de Grafana sin carga: con 2 CPU y la carga en marcha, el
# paquete JavaScript puede no terminar de arrancar y Grafana muestra su página de error.
GRAFANA_URL="http://grafana:3000/d/lbnginx?orgId=1&kiosk&from=now-100s&to=now"
compose exec -T navegador npx -y "playwright@$PW_VERSION" screenshot   --wait-for-timeout=15000 "$GRAFANA_URL" /tmp/precalentar.png >/dev/null 2>&1 || true

# ---- M-00: el color de /nodo cambia en cada petición nueva (round_robin) --------
scripts/set-policy.sh round_robin
for i in 1 2 3; do
  shot "http://lb/nodo" "nodo_$i.png" "900,420" 800
done
shot "http://lb/" "tienda.png" "1400,900" 3000

# ---- M-01 / R-21 / R-18: por algoritmo, bajo carga constante --------------------
overrides="{\"config\":{\"phases\":[{\"name\":\"capturas\",\"duration\":$LOAD_SECONDS,\"arrivalRate\":100}]}}"
tmp=$(mktemp -d)
for p in $POLICIES; do
  scripts/set-policy.sh "$p"
  log "carga de ${LOAD_SECONDS} s con $p (capturas a los ${SHOT_AFTER} s)"
  compose --profile loadtest run --rm -T artillery run --overrides "$overrides" \
    /scripts/scenarios/constante.yml > "$tmp/artillery_$p.log" 2>&1 &
  art_pid=$!
  sleep "$SHOT_AFTER"
  stub_status_raw > "$OUT/stub_status_$p.txt"
  shot "http://lb:8080/stub_status" "stub_status_$p.png" "560,200" 300
  wait "$art_pid" || warn "Artillery terminó con error en $p (ver distribución)"
  # Grafana se captura al terminar la carga; los últimos 100 s cubren solo esta corrida
  shot "$GRAFANA_URL" "grafana_$p.png" "1600,2200" 15000
  {
    echo "# Respuestas por backend con $p (Artillery, ${LOAD_SECONDS} s a 100 VU/s, 3 peticiones por VU)"
    awk '/Summary report/ {s=1} s && /backend\./' "$tmp/artillery_$p.log" | sed -E 's/\.{2,}/ /; s/^ +//'
  } > "$OUT/distribucion_$p.txt"
  ok "distribución: docs/capturas/distribucion_$p.txt"
  cooldown 10
done
rm -rf "${tmp:?}"

{
  echo "# Capturas de evidencia"
  echo
  echo "Generadas por \`scripts/capturas.sh\` el $(date -u '+%Y-%m-%d %H:%M UTC') en $(uname -n)"
  echo "($(nproc) CPU), con un navegador Chromium sin interfaz (Playwright $PW_VERSION) en la red"
  echo "frontend. Cada política atiende ${LOAD_SECONDS} s de carga constante (\`constante.yml\`, 100 VU/s)"
  echo "y \`stub_status\` se captura a los ${SHOT_AFTER} s; Grafana, al terminar la carga (últimos 100 s: solo esa política)."
  echo
  echo "| Evidencia | Archivos |"
  echo "|---|---|"
  echo "| M-00: la página \`/nodo\` cambia de color en cada petición (round_robin) | \`nodo_1.png\`, \`nodo_2.png\`, \`nodo_3.png\` |"
  echo "| Tienda web a través del balanceador | \`tienda.png\` |"
  for p in $POLICIES; do
    echo "| M-01 / R-21 / R-18: \`$p\` | \`stub_status_$p.png\` (\`.txt\`), \`distribucion_$p.txt\`, \`grafana_$p.png\` |"
  done
  echo
  echo "\`stub_status\` es global: muestra la actividad del balanceador, no el reparto. El reparto por"
  echo "backend de cada política está en \`distribucion_<política>.txt\` (contadores \`backend.<nodo>\` de"
  echo "Artillery) y, con repeticiones, en \`docs/resultados-minimos.md\`."
} > "$OUT/README.md"
ok "índice: docs/capturas/README.md"
