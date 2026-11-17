#!/usr/bin/env bash
# =============================================================================
# scripts/test-tls.sh — A-03: costo de la terminación TLS (+ HTTP/2) en NGINX.
#
#   1. Genera el certificado autofirmado (contenedor) y activa LB_TLS=on con
#      compose.tls.yml (el puerto 80 sigue disponible).
#   2. Comprueba con curl (contenedor) que HTTPS negocia HTTP/2 por ALPN.
#   3. Misma carga (constante.yml, 100 VU/s, 180 s) por http://lb y https://lb, en
#      orden aleatorio. Cada usuario virtual abre su propia conexión, así que con
#      HTTPS cada uno paga un handshake TLS: es el caso costoso y realista.
#   Mide latencia (media, p95, p99) y CPU del balanceador (docker_stats.csv).
#   4. Deja LB_TLS=off.
# Variables: REPS=2  COOLDOWN=20  POLICY=round_robin
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

files="-f docker-compose.yml"
[ -f "$ROOT_DIR/docker-compose.override.yml" ] && files="$files -f docker-compose.override.yml"
export COMPOSE_EXTRA_ARGS="$files -f compose.tls.yml"
load_env

REPS="${REPS:-2}"; [ "${QUICK:-0}" = "1" ] && REPS=1
COOLDOWN="${COOLDOWN:-20}"
CURL_IMAGE="${CURL_IMAGE:-curlimages/curl:8.11.1}"

"$ROOT_DIR/scripts/gen-cert.sh"
"$ROOT_DIR/scripts/set-env.sh" LB_TLS on --recreate-lb
"$ROOT_DIR/scripts/set-policy.sh" "${POLICY:-round_robin}"

# Evidencia de HTTP/2 + TLS: versión negociada, protocolo TLS y cabeceras
mkdir -p "$RESULTS_DIR"
EVID="$RESULTS_DIR/A03_tls_http2.txt"
{
  echo "# A-03: negociación TLS/HTTP2 contra https://lb (curl en contenedor, $(date -u +%FT%TZ))"
  docker run --rm --network "${COMPOSE_PROJECT_NAME:-lbnginx}_frontend" "$CURL_IMAGE" \
    -sk --http2 -o /dev/null \
    -w 'http_version=%{http_version} ssl_verify_result=%{ssl_verify_result} time_connect=%{time_connect} time_appconnect=%{time_appconnect} time_total=%{time_total}\n' \
    https://lb/api/info
  docker run --rm --network "${COMPOSE_PROJECT_NAME:-lbnginx}_frontend" "$CURL_IMAGE" \
    -skv --http2 -o /dev/null https://lb/api/info 2>&1 | grep -E 'SSL connection using|ALPN|^< HTTP/|^< x-lb' || true
} | tee "$EVID"
grep -q 'http_version=2' "$EVID" || die "HTTPS no negoció HTTP/2 (ver $EVID)"
ok "HTTPS negocia HTTP/2: $EVID"

for rep in $(seq 1 "$REPS"); do
  for proto in $(shuffle http https); do
    cooldown "$COOLDOWN"
    TARGET="$proto://lb" NOTES="A-03 protocolo=$proto LB_TLS=on" \
      "$ROOT_DIR/scripts/run-test.sh" A03 constante.yml "proto-${proto}_rep$rep" -- --insecure
  done
done

"$ROOT_DIR/scripts/set-env.sh" LB_TLS off --recreate-lb
ok "===== A-03 terminado. Ahora: make analyze ====="
