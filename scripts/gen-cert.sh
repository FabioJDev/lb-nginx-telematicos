#!/usr/bin/env bash
# scripts/gen-cert.sh — A-03: genera un certificado AUTOFIRMADO para el balanceador
# dentro de un contenedor (nada se instala en el host). Válido para los nombres
# lb y localhost; sirve solo para pruebas.
#   nginx/certs/lb.crt  nginx/certs/lb.key   (ignorados por git)
# Uso: scripts/gen-cert.sh [--force]
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
load_env

CERT_DIR="$ROOT_DIR/nginx/certs"
mkdir -p "$CERT_DIR"
if [ -s "$CERT_DIR/lb.crt" ] && [ -s "$CERT_DIR/lb.key" ] && [ "${1:-}" != "--force" ]; then
  ok "ya existe nginx/certs/lb.crt (usa --force para regenerarlo)"
  exit 0
fi
docker run --rm -v "$CERT_DIR:/out" "${OPENSSL_IMAGE:-alpine:3.22}" sh -c '
  apk add --no-cache openssl >/dev/null &&
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 -sha256 \
    -subj "/CN=lb/O=Servicios Telematicos 2026-02" \
    -addext "subjectAltName=DNS:lb,DNS:localhost,IP:127.0.0.1" \
    -keyout /out/lb.key -out /out/lb.crt 2>/dev/null &&
  chmod 644 /out/lb.crt && chmod 600 /out/lb.key &&
  openssl x509 -in /out/lb.crt -noout -subject -enddate'
ok "certificado generado en nginx/certs/"
