#!/bin/sh
# ha/vrrp-entry.sh — A-04: arranca keepalived dentro del espacio de red de un NGINX.
# Uso (entrypoint en compose.ha.yml): vrrp-entry.sh <MASTER|BACKUP> <prioridad> <ip_propia> <ip_par>
# keepalived se instala al arrancar en un contenedor alpine (nada en el host).
set -eu
STATE="$1"; PRIO="$2"; SELF="$3"; PEER="$4"; VIP="${VIP:-172.31.250.100}"

apk add --no-cache keepalived >/dev/null

# La interfaz de la red ha no tiene nombre fijo (eth0/eth1/eth2): se busca por la IP
IFACE=""
for _ in $(seq 1 30); do
  IFACE=$(ip -o -4 addr show | awk -v ip="$SELF" '$4 ~ "^"ip"/" {sub(/@.*/, "", $2); print $2; exit}')
  [ -n "$IFACE" ] && break
  sleep 1
done
[ -n "$IFACE" ] || { echo "vrrp-entry: no se encontró la interfaz con $SELF" >&2; exit 1; }

mkdir -p /etc/keepalived
sed -e "s/__STATE__/$STATE/g" -e "s/__PRIO__/$PRIO/g" -e "s/__IFACE__/$IFACE/g" \
    -e "s/__SELF__/$SELF/g" -e "s/__PEER__/$PEER/g" -e "s#__VIP__#$VIP#g" \
    /ha/keepalived.conf.tmpl > /etc/keepalived/keepalived.conf
echo "vrrp-entry: $STATE prioridad=$PRIO interfaz=$IFACE ip=$SELF par=$PEER vip=$VIP"
exec keepalived --dont-fork --log-console --log-detail -f /etc/keepalived/keepalived.conf
