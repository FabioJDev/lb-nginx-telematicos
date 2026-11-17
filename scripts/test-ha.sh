#!/usr/bin/env bash
# =============================================================================
# scripts/test-ha.sh — A-04: conmutación por falla del balanceador (keepalived + VIP).
#
#   Levanta compose.ha.yml (lb + lb2 con keepalived, VIP 172.31.250.100) y, contra la
#   VIP, corre constante.yml (100 VU/s, 180 s) más una sonda cada 100 ms:
#     t = 60 s   docker kill del NGINX activo (lb)          -> evento lb_killed
#                (failover: lb2 debe tomar la VIP)
#     t = 120 s  se levanta de nuevo lb y su keepalived      -> evento lb_restored
#   Dos configuraciones de keepalived (HA_VARIANTS="on off"):
#     preempt on  (comportamiento por defecto de VRRP): lb, con más prioridad, recupera
#                 la VIP al volver -> las conexiones abiertas en lb2 se cortan otra vez.
#     preempt off (nopreempt): la VIP se queda en lb2 -> no hay segundo corte.
#   Resultados extra en la corrida: vip_probe.csv, ha_hosts.csv y keepalived.log.
# Variables: REPS=2  T_FAULT=60  T_RESTORE=120  POLICY=round_robin  HA_VARIANTS="on off"
# =============================================================================
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

files="-f docker-compose.yml"
[ -f "$ROOT_DIR/docker-compose.override.yml" ] && files="$files -f docker-compose.override.yml"
export COMPOSE_EXTRA_ARGS="$files -f compose.ha.yml"
load_env

REPS="${REPS:-2}"; [ "${QUICK:-0}" = "1" ] && REPS=1
T_FAULT="${T_FAULT:-60}"; T_RESTORE="${T_RESTORE:-120}"
VIP="172.31.250.100"
mkdir -p "$ROOT_DIR/logs/nginx-lb2"

vip_owner() { # imprime vrrp1 / vrrp2 / ninguno según quién tenga la VIP
  local s
  for s in vrrp1 vrrp2; do
    if compose exec -T "$s" ip -4 addr show 2>/dev/null | grep -q "$VIP/"; then echo "$s"; return; fi
  done
  echo ninguno
}

wait_vip_on() { # wait_vip_on <vrrp1|vrrp2> <segundos>
  for _ in $(seq 1 "$2"); do [ "$(vip_owner)" = "$1" ] && return 0; sleep 1; done
  return 1
}

# Deja la VIP en lb antes de cada repetición (con nopreempt puede haber quedado en lb2)
vip_to_lb() {
  # Primero solo vrrp1: con nopreempt, el primero que arranca se queda con la VIP
  compose stop vrrp2 >/dev/null 2>&1 || true
  compose up -d --no-deps --force-recreate vrrp1 >/dev/null
  wait_vip_on vrrp1 60 || die "la VIP no quedó en lb"
  compose up -d --no-deps --force-recreate vrrp2 >/dev/null
  sleep 10   # vrrp2 instala keepalived y entra como BACKUP al recibir los anuncios de vrrp1
  [ "$(vip_owner)" = "vrrp1" ] || die "la VIP se movió al arrancar vrrp2"
}

log "levantando el par de balanceadores (compose.ha.yml)"
compose up -d >/dev/null
wait_healthy lb 1 90
wait_healthy lb2 1 90
"$ROOT_DIR/scripts/set-policy.sh" "${POLICY:-round_robin}"

for pre in ${HA_VARIANTS:-on off}; do
  export HA_PREEMPT="$pre"
  for rep in $(seq 1 "$REPS"); do
    vip_to_lb
    ok "VIP $VIP en lb · preempt=$pre · repetición $rep"
    cooldown "${COOLDOWN:-20}"
    # Sonda de la VIP: arranca ANTES de la carga y se espera a que responda, para que
    # cubra el kill (en una corrida previa arrancó tarde y no vio el failover)
    PROBE_TMP=$(mktemp)
    compose --profile loadtest run --rm --no-deps -T --entrypoint node artillery \
      /scripts/lib/vip-probe.js "http://$VIP/api/info" 200 100 1000 > "$PROBE_TMP" 2>/dev/null &
    PROBE_PID=$!
    for _ in $(seq 1 90); do [ "$(wc -l < "$PROBE_TMP")" -gt 10 ] && break; sleep 1; done
    [ "$(wc -l < "$PROBE_TMP")" -gt 10 ] || die "la sonda de la VIP no arrancó"

    before=$(cat "$CURRENT_RUN_FILE" 2>/dev/null || true)
    TARGET="http://$VIP" NOTES="A-04 VIP=$VIP preempt=$pre; kill del NGINX activo en t=${T_FAULT}s, retorno en t=${T_RESTORE}s" \
      "$ROOT_DIR/scripts/run-test.sh" A04 constante.yml "ha-preempt-${pre}_rep$rep" &
    RUN_PID=$!
    for _ in $(seq 1 60); do
      cur=$(cat "$CURRENT_RUN_FILE" 2>/dev/null || true)
      if [ -n "$cur" ] && [ "$cur" != "$before" ] && grep -q artillery_start "$RESULTS_DIR/$cur/events.csv" 2>/dev/null; then break; fi
      sleep 1
    done
    RUN_DIR="$RESULTS_DIR/$(cat "$CURRENT_RUN_FILE")"
    t_start=$(awk -F, '/artillery_start/ {print $1}' "$RUN_DIR/events.csv" | head -1)
    sleep_until() {
      local d
      d=$(awk -v a="$t_start" -v t="$1" -v n="$(date +%s.%N)" 'BEGIN{d=a+t-n; printf "%.2f", (d>0?d:0)}')
      sleep "$d"
    }

    # Mapa hostname -> servicio (X-LB-Host es el hostname del contenedor)
    {
      echo "hostname,servicio"
      for s in lb lb2; do
        c=$(service_containers "$s" | head -1)
        echo "$(container_hostname "$c"),$s"
      done
    } > "$RUN_DIR/ha_hosts.csv"

    sleep_until "$T_FAULT"
    log_event "$RUN_DIR" lb_killed "docker kill del NGINX activo (lb); dueño de la VIP: $(vip_owner)"
    docker kill "$(service_containers lb | head -1)" >/dev/null
    if wait_vip_on vrrp2 30; then
      log_event "$RUN_DIR" vip_moved "la VIP pasó a lb2"
    else
      log_event "$RUN_DIR" vip_not_moved "la VIP no pasó a lb2 en 30 s"
    fi

    sleep_until "$T_RESTORE"
    log_event "$RUN_DIR" lb_restore_start "docker compose up lb + keepalived (preempt=$pre)"
    compose up -d --no-deps lb >/dev/null
    wait_healthy lb 1 60
    compose up -d --no-deps --force-recreate vrrp1 >/dev/null
    if [ "$pre" = "on" ]; then
      if wait_vip_on vrrp1 60; then
        log_event "$RUN_DIR" lb_restored "lb recuperó la VIP (preempción por prioridad)"
      else
        log_event "$RUN_DIR" lb_restored "lb volvió sin recuperar la VIP en 60 s"
      fi
    else
      sleep 5
      log_event "$RUN_DIR" lb_restored "lb volvió como BACKUP (nopreempt); dueño de la VIP: $(vip_owner)"
    fi

    wait "$RUN_PID" || true
    wait "$PROBE_PID" || true
    mv "$PROBE_TMP" "$RUN_DIR/vip_probe.csv"
    { echo "# keepalived (vrrp1, vrrp2) durante la corrida"; compose logs --no-color --since 10m vrrp1 vrrp2 2>/dev/null | grep -iE 'state|vip|transition|entering|fault|vrrp-entry' | tail -60; } > "$RUN_DIR/keepalived.log" || true
    ok "A-04 preempt=$pre repetición $rep: $RUN_DIR"
  done
done
vip_to_lb

ok "===== A-04 terminado. Ahora: make analyze ====="
