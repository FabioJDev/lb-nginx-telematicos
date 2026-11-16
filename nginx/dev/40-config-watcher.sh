#!/bin/sh
# nginx/dev/40-config-watcher.sh — recarga en caliente (SOLO desarrollo, R-19).
#
# El entrypoint oficial de la imagen nginx ejecuta los *.sh de /docker-entrypoint.d/
# antes de lanzar nginx. Este script deja un bucle en segundo plano que sondea por
# checksum (no inotify, porque los eventos de archivos no siempre cruzan
# Windows -> WSL2 -> contenedor). Cuando detecta un cambio:
#   1. vuelve a procesar las plantillas con envsubst (script 20 del entrypoint),
#   2. valida la configuración con `nginx -t`,
#   3. si es válida, `nginx -s reload` (recarga elegante, sin cortar conexiones);
#      si no, conserva la configuración anterior y lo informa en el log.
#
# Requiere bit ejecutable en git:  git update-index --chmod=+x nginx/dev/40-config-watcher.sh

set -u
INTERVAL="${CONFIG_WATCH_INTERVAL:-2}"
WATCH_PATHS="/etc/nginx/nginx.conf /etc/nginx/templates /etc/nginx/policies /etc/nginx/extras"

checksum() {
  # shellcheck disable=SC2086
  find $WATCH_PATHS -type f 2>/dev/null | sort | xargs md5sum 2>/dev/null | md5sum
}

echo "[watcher] recarga en caliente activa (intervalo ${INTERVAL}s) sobre: $WATCH_PATHS"

(
  last="$(checksum)"
  # Esperar a que nginx esté arriba antes de intentar recargas
  sleep 3
  while sleep "$INTERVAL"; do
    now="$(checksum)"
    [ "$now" = "$last" ] && continue
    last="$now"
    echo "[watcher] cambio detectado -> regenerando plantillas"
    if [ -x /docker-entrypoint.d/20-envsubst-on-templates.sh ]; then
      /docker-entrypoint.d/20-envsubst-on-templates.sh >/dev/null 2>&1
    fi
    if nginx -t 2>/tmp/nginx-t.log; then
      if nginx -s reload; then
        echo "[watcher] configuración válida: nginx recargado (policy=$(grep -ho 'policies/[a-z_]*' /etc/nginx/generated/http.conf | head -1 | cut -d/ -f2))"
      else
        echo "[watcher] ERROR: nginx -s reload falló"
      fi
    else
      echo "[watcher] configuración INVÁLIDA: se conserva la anterior"
      sed 's/^/[watcher]   /' /tmp/nginx-t.log
    fi
  done
) &
