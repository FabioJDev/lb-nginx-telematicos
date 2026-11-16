#!/usr/bin/env bash
# scripts/test-seq.sh — M-02: N peticiones SECUENCIALES a través del balanceador
# y conteo por backend. Con round_robin y backends homogéneos se espera reparto
# exacto (diferencia < 2 % y Jain > 0,99).
# Uso: scripts/test-seq.sh [N=1000] [ruta=/api/info]
source "$(dirname "$0")/lib.sh"
load_env

N="${1:-1000}"; PATH_URL="${2:-/api/info}"
[ -n "$(service_containers lb)" ] || die "lb no está corriendo"

POLICY=$(current_policy); REPLICAS=$(backend_count)
RUN_NAME="$(date +%Y%m%d-%H%M%S)_M02_${POLICY}_${REPLICAS}b_seq${N}"
RUN_DIR="$RESULTS_DIR/$RUN_NAME"; mkdir -p "$RUN_DIR"
log "M-02: $N peticiones secuenciales · política=$POLICY · réplicas=$REPLICAS"

compose exec -T lb sh -s "$N" "$PATH_URL" < "$ROOT_DIR/scripts/in-container/seq-loop.sh" > "$RUN_DIR/secuencial.csv"

echo "Peticiones por nodo:"
cut -d, -f2 "$RUN_DIR/secuencial.csv" | sort | uniq -c | sort -rn | tee "$RUN_DIR/conteo_por_nodo.txt" | awk '{printf "  %5d  %s\n", $1, $2}'

# Índice de Jain J = (Σx)² / (n·Σx²) calculado con awk (sin Python en el host)
jain=$(cut -d, -f2 "$RUN_DIR/secuencial.csv" | grep -v __FAIL__ | sort | uniq -c \
  | awk '{s+=$1; s2+=$1*$1; n++} END { if (n>0 && s2>0) printf "%.4f", (s*s)/(n*s2); else print "0" }')
fails=$(grep -c ',__FAIL__,' "$RUN_DIR/secuencial.csv" || true)
cat > "$RUN_DIR/metadata.json" <<EOF
{ "run_name": "$RUN_NAME", "test_id": "M02", "scenario": "secuencial", "policy": "$POLICY",
  "replicas": $REPLICAS, "requests": $N, "path": "$PATH_URL", "jain": $jain, "failed": $fails,
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)" }
EOF
echo "  índice de Jain: $jain · fallos: $fails"
ok "guardado en results/$RUN_NAME"
