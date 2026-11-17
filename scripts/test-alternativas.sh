#!/usr/bin/env bash
# =============================================================================
# scripts/test-alternativas.sh — mediciones de la matriz 4.1 (tecnología de balanceo).
#
#   Levanta compose.alternativas.yml: NGINX, HAProxy, Traefik y Apache, cada uno con su
#   configuración MÍNIMA equivalente (alternativas/): proxy en :80 hacia las 3 réplicas,
#   round-robin, detección de fallos y reintentos.
#
#   C5 (facilidad de configuración): cuenta las líneas útiles (sin comentarios ni líneas en
#      blanco) de cada caso base y comprueba que funciona: 30 peticiones, 3 nodos, 0 fallos.
#      -> results/alternativas_c5.csv
#   C1 (desempeño): la misma carga (rampa.yml) contra cada alternativa, en orden aleatorio;
#      p99 de Artillery y CPU del contenedor del balanceador (docker_stats.csv).
#      -> corridas A05B_alt-<nombre>_...
#   LVS/IPVS solo se cuenta (alternativas/lvs-keepalived.conf): necesita el módulo ip_vs del
#   kernel del host y que el director sea la puerta de enlace de los backends.
# Variables: REPS=3  COOLDOWN=20  SCENARIO=rampa.yml
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

files="-f docker-compose.yml"
[ -f "$ROOT_DIR/docker-compose.override.yml" ] && files="$files -f docker-compose.override.yml"
export COMPOSE_EXTRA_ARGS="$files -f compose.alternativas.yml"
load_env

REPS="${REPS:-3}"; [ "${QUICK:-0}" = "1" ] && REPS=1
COOLDOWN="${COOLDOWN:-20}"
SCENARIO="${SCENARIO:-rampa.yml}"
ALTS="alt-nginx alt-haproxy alt-traefik alt-apache"

# Líneas útiles de configuración: sin comentarios (# o !) ni líneas en blanco
config_lines() {
  local total=0 f n
  for f in "$@"; do
    n=$(grep -cvE '^[[:space:]]*([#!]|$)' "$ROOT_DIR/alternativas/$f" || true)
    total=$((total + n))
  done
  echo "$total"
}

"$ROOT_DIR/scripts/set-policy.sh" round_robin
log "levantando las alternativas (compose.alternativas.yml)"
# shellcheck disable=SC2086
compose up -d --no-deps $ALTS >/dev/null
for a in $ALTS; do wait_healthy "$a" 1 120; done

mkdir -p "$RESULTS_DIR"
CSV="$RESULTS_DIR/alternativas_c5.csv"
echo "alternativa,archivos,lineas,nodos_distintos,fallos,verificado" > "$CSV"
for spec in "NGINX:alt-nginx:nginx.conf" "HAProxy:alt-haproxy:haproxy.cfg" \
            "Traefik:alt-traefik:traefik.yml traefik-dinamica.yml" "Apache:alt-apache:httpd.conf" \
            "LVS:-:lvs-keepalived.conf"; do
  name="${spec%%:*}"; rest="${spec#*:}"; svc="${rest%%:*}"; cfgs="${rest#*:}"
  # shellcheck disable=SC2086
  lines=$(config_lines $cfgs)
  if [ "$svc" = "-" ]; then
    echo "$name,${cfgs// /+},$lines,,,no ejecutado (requiere el módulo ip_vs del kernel del host)" >> "$CSV"
    continue
  fi
  out=$(compose exec -T lb sh -c "for i in \$(seq 1 30); do r=\$(wget -qO- --timeout=3 http://$svc/api/info 2>/dev/null); n=\$(printf '%s' \"\$r\" | sed -n 's/.*\"node\":\"\\([^\"]*\\)\".*/\\1/p'); echo \"\${n:-__FAIL__}\"; done")
  fails=$(printf '%s\n' "$out" | grep -c '^__FAIL__$' || true)
  distinct=$(printf '%s\n' "$out" | grep -v '^__FAIL__$' | sort -u | grep -c . || true)
  ok_flag="no"; [ "$fails" -eq 0 ] && [ "$distinct" -ge 3 ] && ok_flag="sí"
  echo "$name,${cfgs// /+},$lines,$distinct,$fails,$ok_flag" >> "$CSV"
  ok "C5 $name: $lines líneas · $distinct nodos · $fails fallos · verificado=$ok_flag"
done
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"

for rep in $(seq 1 "$REPS"); do
  # shellcheck disable=SC2086
  for a in $(shuffle $ALTS); do
    cooldown "$COOLDOWN"
    TARGET="http://$a" POLICY_OVERRIDE="$a" NOTES="matriz 4.1: $a con configuración mínima (alternativas/)" \
      "$ROOT_DIR/scripts/run-test.sh" A05B "$SCENARIO" "${a}_rep$rep"
  done
done

# shellcheck disable=SC2086
compose rm -sf $ALTS >/dev/null || true
ok "===== mediciones de la matriz 4.1 terminadas. Ahora: make analyze && make matrix ====="
