#!/usr/bin/env python3
"""
analysis/decision_matrix.py — matrices de decisión multicriterio (sección 4).

  Matriz 4.1  tecnología de balanceo: cada criterio tiene una ESCALA 1–5 explícita y
              cada celda su evidencia. C1 (desempeño) y C5 (facilidad) se calculan con
              datos medidos (corridas A05B y alternativas_c5.csv de
              scripts/test-alternativas.sh); el resto, con la documentación oficial.
              Incluye ANÁLISIS DE SENSIBILIDAD (cada peso ±5 y umbrales de cambio).
  Matriz 4.2  algoritmo recomendado: se llena SOLO con datos medidos que estén en
              results/resumen_comparativo.csv (o COMPARATIVO_CSV). Si no hay
              datos, la matriz queda marcada como pendiente.
  Matriz 4.3  estrategia de descubrimiento de backends (decisión de diseño).

Salida: Markdown en stdout y en docs/decision-matrix-generada.md.
Solo usa la biblioteca estándar (csv, json), por lo que también puede ejecutarse
con cualquier Python sin dependencias.
"""
from __future__ import annotations

import csv
import itertools
import math
import os
import sys
from pathlib import Path

RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", "/results"))
DOCS_DIR = Path(os.environ.get("DOCS_DIR", "/docs"))

# ---------------------------------------------------------------------------
# Matriz 4.1 — tecnología de balanceo
# ---------------------------------------------------------------------------
COMPARATIVO_CSV = os.environ.get("COMPARATIVO_CSV", "")

# (id, nombre, peso, cómo se mide, escala 1–5)
CRITERIA_41 = [
    ("C1", "Desempeño y eficiencia", 20,
     "Medido: misma carga (rampa.yml) contra el caso base mínimo de cada alternativa sobre las mismas 3 réplicas "
     "(corridas A05B, scripts/test-alternativas.sh); p99 de Artillery y CPU media del contenedor del balanceador",
     "5·(½·p99_mejor/p99 + ½·CPU_mejor/CPU), redondeado, mínimo 1"),
    ("C2", "Algoritmos de balanceo disponibles", 15,
     "Conteo de métodos en la documentación oficial de la versión libre",
     "5 ≥ 8 · 4 = 5–7 · 3 = 3–4 · 2 = 2 · 1 = 1"),
    ("C3", "Detección de fallos y tolerancia (versión libre)", 15,
     "Documentación oficial: checks activos, detección pasiva y reintentos en otro servidor",
     "5 = activos + pasivos + reintentos · 4 = dos de los tres · 3 = pasivos + reintentos · 2 = solo uno · 1 = ninguno"),
    ("C4", "Observabilidad", 10,
     "Documentación oficial: métricas por servidor de backend en la versión libre",
     "5 = por servidor en Prometheus nativo · 4 = por servidor parcial o vía exportador estándar · "
     "3 = por servidor solo en página/consola · 2 = solo globales · 1 = ninguna"),
    ("C5", "Facilidad de configuración", 10,
     "Medido: líneas útiles (sin comentarios ni blancos) del caso base mínimo equivalente (alternativas/), "
     "comprobado funcionando: 30 peticiones, 3 nodos, 0 fallos (alternativas_c5.csv)",
     "5 ≤ 10 · 4 = 11–20 · 3 = 21–30 · 2 = 31–40 · 1 > 40 líneas"),
    ("C6", "Integración con Docker / descubrimiento dinámico", 10,
     "Qué hay que hacer para que una réplica nueva reciba tráfico (en este proyecto: E-02/E-10 con `resolve`)",
     "5 = automático por la API/etiquetas de Docker · 4 = re-resolución DNS sin recargar · "
     "3 = lista estática + recarga sin cortar conexiones · 2 = lista estática + reinicio · 1 = alta manual con comandos"),
    ("C7", "Madurez, comunidad y documentación", 10,
     "Años desde la primera versión estable y versiones publicadas en los últimos 12 meses",
     "5 = ≥ 15 años y versiones recientes · 4 = ≥ 10 años, o ≥ 15 sin versiones recientes de la herramienta de usuario · "
     "3 = 5–9 años · 2 = < 5 años · 1 = sin mantenimiento"),
    ("C8", "Funciones L7 adicionales", 10,
     "Cuántas de 6 funciones trae la versión libre: servir estáticos, caché, TLS, limitación de tasa, "
     "reescritura/redirección, compresión",
     "5 = 6 · 4 = 5 · 3 = 4 · 2 = 2–3 · 1 = 0–1"),
]
ALTERNATIVES_41 = ["NGINX", "HAProxy", "Traefik", "Apache", "LVS"]
ALT_SERVICE = {"NGINX": "alt-nginx", "HAProxy": "alt-haproxy", "Traefik": "alt-traefik", "Apache": "alt-apache"}

# Puntuación y evidencia de los criterios que salen de la documentación (C2, C3, C4, C6, C7, C8).
# Fuentes: nginx.org ngx_http_upstream_module; docs.haproxy.org 3.2 (balance, check, observe);
# doc.traefik.io (load-balancing service, retry, metrics); httpd.apache.org 2.4 (mod_proxy_balancer,
# mod_proxy_hcheck, mod_proxy); ipvsadm(8).
EVIDENCE_41 = {
    "C2": {
        "NGINX": (4, "7: round-robin, least_conn, ip_hash, hash, hash consistent, random, random two (least_time es libre solo desde 1.31)"),
        "HAProxy": (5, "13: roundrobin, static-rr, leastconn, first, hash, source, uri, url_param, hdr, random, rdp-cookie, log-hash, sticky"),
        "Traefik": (3, "4: wrr, p2c, hrw, leasttime"),
        "Apache": (3, "4: byrequests, bytraffic, bybusyness, heartbeat"),
        "LVS": (5, "10: rr, wrr, lc, wlc, lblc, lblcr, dh, sh, sed, nq"),
    },
    "C3": {
        "NGINX": (3, "pasiva (max_fails/fail_timeout) + reintentos (proxy_next_upstream); checks activos solo en NGINX Plus"),
        "HAProxy": (5, "activos (check), pasivos (observe) y reintentos (retries + redispatch)"),
        "Traefik": (5, "activos (healthCheck), pasivos (passiveHealthCheck) y middleware retry"),
        "Apache": (5, "activos (mod_proxy_hcheck, ≥ 2.4.21), pasivos (worker en estado de error, retry) y maxattempts"),
        "LVS": (1, "ninguno propio: requiere keepalived o ldirectord"),
    },
    "C4": {
        "NGINX": (2, "stub_status es global; por servidor solo en logs (exporter oficial, métricas globales)"),
        "HAProxy": (5, "exportador Prometheus integrado con métricas por servidor"),
        "Traefik": (4, "Prometheus nativo; por servidor solo traefik_service_server_up (estado)"),
        "Apache": (3, "por miembro solo en balancer-manager (página HTML)"),
        "LVS": (4, "contadores por servidor real (ipvsadm --stats) y colector ipvs de node_exporter"),
    },
    "C6": {
        "NGINX": (4, "`resolve` (libre desde 1.27.3) re-resuelve el DNS de Docker sin recargar (medido en E-02/E-10)"),
        "HAProxy": (4, "server-template + resolvers re-resuelven el DNS"),
        "Traefik": (5, "proveedor Docker: descubre contenedores por etiquetas"),
        "Apache": (3, "BalancerMember estáticos; apachectl graceful recarga sin cortar"),
        "LVS": (1, "ipvsadm -a por cada servidor real"),
    },
    "C7": {
        "NGINX": (5, "desde 2004; versión estable 1.30 en 2026"),
        "HAProxy": (5, "desde 2001; 3.2 LTS con versiones en 2026"),
        "Traefik": (4, "desde 2015 (11 años); v3.7 en 2026"),
        "Apache": (5, "httpd desde 1995, mod_proxy_balancer desde 2.2 (2005); 2.4.6x en 2026"),
        "LVS": (4, "IPVS en el kernel desde 1998; ipvsadm sin versiones recientes"),
    },
    "C8": {
        "NGINX": (5, "6/6"),
        "HAProxy": (4, "5/6: no sirve archivos estáticos"),
        "Traefik": (3, "4/6: sin estáticos ni caché en la versión libre"),
        "Apache": (4, "5/6: sin limitación de tasa de peticiones nativa (mod_ratelimit limita ancho de banda)"),
        "LVS": (1, "0/6: balanceo de capa 4"),
    },
}
# Valores de respaldo si no hay mediciones (C1 y C5 de la versión anterior de la matriz)
FALLBACK_41 = {"C1": {"NGINX": 5, "HAProxy": 4, "Traefik": 4, "Apache": 3, "LVS": 5},
               "C5": {"NGINX": 4, "HAProxy": 3, "Traefik": 4, "Apache": 3, "LVS": 2}}
# LVS no se puede medir en contenedores (módulo ip_vs del kernel del host): C1 por diseño
LVS_C1 = (5, "no medido (IPVS vive en el kernel del host); 5 por diseño: reenvío en el kernel, sin proxy en espacio de usuario")


def c5_points(lines: int) -> int:
    return 5 if lines <= 10 else 4 if lines <= 20 else 3 if lines <= 30 else 2 if lines <= 40 else 1


def load_alt_measurements():
    """C1 y C5 medidos: corridas A05B (resumen.json) y alternativas_c5.csv bajo RESULTS_DIR."""
    import json
    perf = {}
    for meta in sorted(RESULTS_DIR.rglob("metadata.json")):
        run = meta.parent
        if "_A05B_" not in run.name or not (run / "resumen.json").exists():
            continue
        r = json.loads((run / "resumen.json").read_text(encoding="utf-8"))
        svc = r.get("policy", "")
        p99, cpu = to_float(r.get("art_lat_p99")), to_float(r.get(f"cpu_mean_{svc}"))
        if not math.isnan(p99) and not math.isnan(cpu) and cpu > 0:
            perf.setdefault(svc, []).append((p99, cpu, to_float(r.get("art_error_rate"))))
    c5 = {}
    csvs = sorted(RESULTS_DIR.rglob("alternativas_c5.csv"))
    if csvs:
        with open(csvs[-1], encoding="utf-8") as f:
            for row in csv.DictReader(f):
                c5[row["alternativa"]] = row
    return perf, c5


def build_scores_41():
    """Devuelve (scores por alternativa, evidencia por criterio y alternativa, notas)."""
    perf, c5 = load_alt_measurements()
    ev = {c[0]: {} for c in CRITERIA_41}
    notes = []
    # C1
    means = {}
    for alt, svc in ALT_SERVICE.items():
        vals = perf.get(svc, [])
        if vals:
            means[alt] = (sum(v[0] for v in vals) / len(vals), sum(v[1] for v in vals) / len(vals),
                          sum(v[2] for v in vals if not math.isnan(v[2])) / len(vals), len(vals))
    if len(means) == len(ALT_SERVICE):
        best_p99 = min(m[0] for m in means.values())
        best_cpu = min(m[1] for m in means.values())
        for alt, (p99, cpu, err, n) in means.items():
            pts = max(1, min(5, math.floor(5 * (0.5 * best_p99 / p99 + 0.5 * best_cpu / cpu) + 0.5)))
            ev["C1"][alt] = (pts, f"p99 {p99:.1f} ms · CPU {cpu:.1f} % · errores {100 * err:.2f} % (n = {n})")
        notes.append("C1 medido en las corridas A05B (scripts/test-alternativas.sh).")
    else:
        for alt in ALT_SERVICE:
            ev["C1"][alt] = (FALLBACK_41["C1"][alt], "sin corridas A05B: valor de respaldo")
        notes.append("C1 SIN mediciones A05B: se usan valores de respaldo.")
    ev["C1"]["LVS"] = LVS_C1
    # C5
    for alt in ALTERNATIVES_41:
        row = c5.get(alt)
        if row and row.get("lineas"):
            lines = int(row["lineas"])
            ver = row.get("verificado", "")
            how = "funciona: 3 nodos, 0 fallos" if ver == "sí" else ver
            ev["C5"][alt] = (c5_points(lines), f"{lines} líneas ({row['archivos']}); {how}")
        else:
            ev["C5"][alt] = (FALLBACK_41["C5"][alt], "sin alternativas_c5.csv: valor de respaldo")
    for cid, by_alt in EVIDENCE_41.items():
        ev[cid] = dict(by_alt)
    scores = {a: [ev[c[0]][a][0] for c in CRITERIA_41] for a in ALTERNATIVES_41}
    return scores, ev, notes


SCORES_41, EVIDENCE_TABLE_41, NOTES_41 = None, None, []

# ---------------------------------------------------------------------------
# Matriz 4.3 — descubrimiento de backends
# ---------------------------------------------------------------------------
# (nombre, peso, cómo se mide, escala)
CRITERIA_43 = [
    ("Escalar sin tocar la config", 30,
     "Pasos manuales para pasar de 3 a 5 réplicas (medido con `make scale N=5` en la CI y en E-10)",
     "5 = ninguno · 3 = un script automatizable + recarga · 1 = editar la configuración y recargar a mano"),
    ("Pesos/backup por servidor", 20,
     "¿Se puede dar `weight` o `backup` a una réplica concreta?",
     "5 = sí, por réplica · 2 = solo el mismo valor para todas · 1 = no"),
    ("Simplicidad", 20,
     "Piezas que hay que mantener además de la plantilla de NGINX",
     "5 = ninguna y no cambia al escalar · 4 = 1–3 directivas extra fijas · 3 = la lista se edita en cada cambio · "
     "2 = un componente externo (script o generador) · 1 = varios componentes"),
    ("Robustez ante cambios", 30,
     "Qué pasa si una réplica desaparece o un nombre no resuelve al arrancar",
     "5 = arranca y se adapta sola · 4 = arranca y se adapta, con limitaciones conocidas (H-1, H-3) · "
     "3 = no arranca si un nombre no resuelve (`host not found in upstream`) · 2 = depende de un proceso externo · 1 = requiere intervención"),
]
ALTERNATIVES_43 = ["Servidores estáticos con nombre", "DNS con resolve (elegida)", "Regenerar config + reload"]
SCORES_43 = {
    "Servidores estáticos con nombre": [1, 5, 3, 3],
    "DNS con resolve (elegida)":       [5, 2, 4, 4],
    "Regenerar config + reload":       [3, 5, 2, 2],
}

# ---------------------------------------------------------------------------
# Matriz 4.2 — algoritmo recomendado (con datos)
# ---------------------------------------------------------------------------
CRITERIA_42 = [
    # (nombre, peso, cómo se obtiene)
    ("Latencia p99, backends homogéneos", 20, "p99 (ms) en rampa.yml, media de repeticiones (M-05/ALG). Menor es mejor: 5·(mejor/valor), mín. 1"),
    ("Latencia p95, backends heterogéneos", 25, "p95 con un backend lento (E-03). Igual normalización. Se usa p95 y no p99: en E-03 el p99 lo fija el propio nodo lento (~5 % de las peticiones) y vale 171-173 ms con todas las políticas"),
    ("Equidad de la distribución", 15, "Índice de Jain J sobre peticiones por backend (M-06). 5·J"),
    ("Errores durante fallo de backend", 20, "% de respuestas no-2xx en la ventana de 30 s tras la falla (M-03/E-07). 5 si 0 %; 5·(1 − min(err,5 %)/5 %), mín. 1"),
    ("Afinidad de sesión", 10, "% de clientes que siempre caen en el mismo backend (log NGINX, client_id). 5·(%/100), mín. 1"),
    ("Simplicidad operativa", 10, "Líneas del archivo de la política (nginx/policies/, sin comentarios) y requisitos al cliente: "
     "5 = 0–1 directiva sin parámetros · 4 = 1 directiva con parámetros · 3 = necesita mapas o variables extra · "
     "2 = exige algo al cliente (cabecera propia) · 1 = componentes externos"),
]
# round_robin: 0 líneas · least_conn / ip_hash: 1 directiva sin parámetros · random_two: `random two least_conn;`
# hash_remote_addr: `hash $remote_addr;` · hash_client: `hash $http_x_client_id;` + el cliente debe enviar X-Client-Id
SIMPLICITY_42 = {"round_robin": 5, "least_conn": 5, "ip_hash": 5, "hash_client": 2, "hash_remote_addr": 4, "random_two": 4}
POLICIES_42 = ["round_robin", "least_conn", "ip_hash", "hash_client", "random_two"]


def score(weights: list[int], scores: list[int]) -> float:
    return sum(w * s for w, s in zip(weights, scores)) / 5.0


def ranking(weights, scores_by_alt):
    return sorted(scores_by_alt, key=lambda a: -score(weights, scores_by_alt[a]))


def overtaker(weights, scores_by_alt, leader):
    """Alternativa que SUPERA estrictamente al líder con estos pesos (un empate no cambia el líder)."""
    base = score(weights, scores_by_alt[leader])
    best = max((a for a in scores_by_alt if a != leader), key=lambda a: score(weights, scores_by_alt[a]))
    return best if score(weights, scores_by_alt[best]) > base + 1e-9 else leader


def sensitivity(criteria, scores_by_alt, delta=5):
    """Varía cada peso ±delta redistribuyendo proporcionalmente; devuelve los casos que cambian el orden."""
    base_w = [c[2] for c in criteria]
    base_rank = ranking(base_w, scores_by_alt)
    changes = []
    for i, c in enumerate(criteria):
        for sign in (+1, -1):
            w = list(base_w)
            new = max(0, w[i] + sign * delta)
            diff = new - w[i]
            others = [j for j in range(len(w)) if j != i]
            tot_others = sum(w[j] for j in others) or 1
            for j in others:
                w[j] = w[j] - diff * w[j] / tot_others
            w[i] = new
            new_leader = overtaker(w, scores_by_alt, base_rank[0])
            if new_leader != base_rank[0]:
                changes.append((c[0], sign * delta, new_leader, [round(x, 1) for x in w]))
    # Umbral: ¿cuánto debe pesar cada criterio para que cambie el líder?
    # Se busca en las dos direcciones desde el peso base: subiendo hasta 100 y bajando hasta 0.
    thresholds = []
    for i, c in enumerate(criteria):
        def leader_at(target):
            w = list(base_w)
            diff = target - w[i]
            others = [j for j in range(len(w)) if j != i]
            tot_others = sum(w[j] for j in others) or 1
            for j in others:
                w[j] = w[j] - diff * w[j] / tot_others
            w[i] = target
            return overtaker(w, scores_by_alt, base_rank[0])
        up = next(((t, leader_at(t)) for t in range(base_w[i] + 1, 101) if leader_at(t) != base_rank[0]), None)
        down = next(((t, leader_at(t)) for t in range(base_w[i] - 1, -1, -1) if leader_at(t) != base_rank[0]), None)
        if up or down:
            thresholds.append((c[0], up, down))
    return base_rank, changes, thresholds


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def fmt(v, nd=1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


# ---------------------------------------------------------------------------
def load_comparativo():
    p = Path(COMPARATIVO_CSV) if COMPARATIVO_CSV else RESULTS_DIR / "resumen_comparativo.csv"
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pick(rows, test_ids, policy, label_base=""):
    best = None
    for r in rows:
        if r.get("test_id") in test_ids and r.get("policy") == policy and (r.get("label_base") or "") == label_base:
            best = r
    return best


def matrix_42(rows):
    """Devuelve (tabla markdown, filas de datos, pendiente:bool)."""
    data = {}
    for pol in POLICIES_42:
        # Backends homogéneos con rampa.yml: M-05 (o ALG) y, para las políticas hash, E-05
        hom = pick(rows, {"M05", "ALG"}, pol) or pick(rows, {"E05"}, pol)
        het = pick(rows, {"E03"}, pol)
        fail = pick(rows, {"M03", "E07"}, pol, "rm") or pick(rows, {"M03"}, pol)
        data[pol] = {
            "p99_hom": to_float(hom["ng_lat_p99_ms_mean"]) if hom else float("nan"),
            "p99_het": to_float(het["ng_lat_p95_ms_mean"]) if het else float("nan"),
            "jain": to_float(hom["ng_jain_mean"]) if hom else float("nan"),
            "err_fail": to_float(fail.get("error_rate_30s_after_backend_removed_mean", "nan")) * 100 if fail else float("nan"),
            "affinity": to_float(hom.get("ng_affinity_pct_mean", "nan")) if hom else float("nan"),
            "simplicity": SIMPLICITY_42.get(pol, 3),
        }
    have_any = any(not math.isnan(d["p99_hom"]) for d in data.values())

    def norm_lower(values):
        valid = [v for v in values.values() if not math.isnan(v)]
        best = min(valid) if valid else float("nan")
        return {k: (max(1.0, min(5.0, 5 * best / v)) if (not math.isnan(v) and v > 0) else float("nan")) for k, v in values.items()}

    s_hom = norm_lower({k: d["p99_hom"] for k, d in data.items()})
    s_het = norm_lower({k: d["p99_het"] for k, d in data.items()})
    s_jain = {k: (5 * d["jain"] if not math.isnan(d["jain"]) else float("nan")) for k, d in data.items()}
    s_err = {k: (max(1.0, 5 * (1 - min(d["err_fail"], 5) / 5)) if not math.isnan(d["err_fail"]) else float("nan")) for k, d in data.items()}
    s_aff = {k: (max(1.0, 5 * d["affinity"] / 100) if not math.isnan(d["affinity"]) else float("nan")) for k, d in data.items()}
    weights = [c[1] for c in CRITERIA_42]
    rows_md = []
    totals = {}
    coverage = {}
    for pol in POLICIES_42:
        scores = [s_hom[pol], s_het[pol], s_jain[pol], s_err[pol], s_aff[pol], float(data[pol]["simplicity"])]
        # Criterios sin dato: se excluyen y se renormalizan los pesos (se indica en la tabla)
        pairs = [(w, s) for w, s in zip(weights, scores) if not math.isnan(s)]
        tot_w = sum(w for w, _ in pairs)
        total = (sum(w * s for w, s in pairs) / 5.0) * (100 / tot_w) if tot_w else float("nan")
        totals[pol] = total
        coverage[pol] = tot_w
        rows_md.append([pol] + [f"{fmt(s)} ({fmt(v)})" for s, v in zip(
            scores, [data[pol]["p99_hom"], data[pol]["p99_het"], data[pol]["jain"], data[pol]["err_fail"], data[pol]["affinity"], data[pol]["simplicity"]])]
            + [fmt(total), f"{tot_w}/100"])
    headers = ["Política"] + [f"{c[0]} ({c[1]})" for c in CRITERIA_42] + ["Puntaje /100", "Pesos con dato"]
    return md_table(headers, rows_md), totals, not have_any, coverage


def main() -> int:
    # Salida UTF-8 también en consolas con otra codificación (Windows)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    out = []
    out.append("# Matrices de decisión (generadas por analysis/decision_matrix.py)\n")
    out.append("Puntuación 1–5; pesos suman 100; puntaje = Σ(peso × puntuación) / 5 (sobre 100).\n")

    # 4.1
    global SCORES_41, EVIDENCE_TABLE_41, NOTES_41
    SCORES_41, EVIDENCE_TABLE_41, NOTES_41 = build_scores_41()
    w41 = [c[2] for c in CRITERIA_41]
    out.append("## Matriz 4.1 — tecnología de balanceo\n")
    out.append(md_table(["ID", "Criterio", "Peso", "Cómo se mide", "Escala 1–5"], [(c[0], c[1], c[2], c[3], c[4]) for c in CRITERIA_41]))
    out.append("\n**Evidencia de cada puntuación** (puntos: evidencia)\n")
    out.append(md_table(["Criterio"] + ALTERNATIVES_41,
                        [[c[0]] + [f"**{EVIDENCE_TABLE_41[c[0]][a][0]}** · {EVIDENCE_TABLE_41[c[0]][a][1]}" for a in ALTERNATIVES_41]
                         for c in CRITERIA_41]))
    if NOTES_41:
        out.append("\n" + " ".join(NOTES_41))
    out.append("")
    rows = []
    for i, c in enumerate(CRITERIA_41):
        rows.append([f"{c[0]} ({c[2]})"] + [SCORES_41[a][i] for a in ALTERNATIVES_41])
    rows.append(["**Puntaje /100**"] + [f"**{score(w41, SCORES_41[a]):.0f}**" for a in ALTERNATIVES_41])
    out.append(md_table(["Criterio (peso)"] + ALTERNATIVES_41, rows))
    base_rank, changes, thresholds = sensitivity(CRITERIA_41, SCORES_41)
    out.append("\n**Ranking base:** " + " > ".join(f"{a} ({score(w41, SCORES_41[a]):.0f})" for a in base_rank))
    out.append("\n**Análisis de sensibilidad (±5 en cada peso, redistribuido proporcionalmente):** "
               + ("el líder NO cambia en ningún caso; el ranking es estable." if not changes else
                  "el líder cambia en: " + "; ".join(f"{c} {d:+d} → {lead}" for c, d, lead, _ in changes)))
    out.append("\n**Umbrales de cambio de líder** (peso del criterio, redistribuyendo el resto, a partir del cual otra alternativa pasa al primer lugar):\n")
    fmt_t = lambda x: f"{x[0]} → {x[1]}" if x else "no cambia"  # noqa: E731
    out.append(md_table(["Criterio", "Peso base", "Subiendo el peso", "Bajando el peso"],
                        [(c, next(cc[2] for cc in CRITERIA_41 if cc[0] == c), fmt_t(up), fmt_t(down)) for c, up, down in thresholds])
               if thresholds else "Ningún criterio, dentro de 0–100, cambia el líder.")
    # Diferencia NGINX vs líder
    leader = base_rank[0]
    pos = base_rank.index("NGINX") + 1
    gap = score(w41, SCORES_41[leader]) - score(w41, SCORES_41["NGINX"])
    if leader == "NGINX":
        out.append(f"\nNGINX lidera con {score(w41, SCORES_41['NGINX']):.0f}/100.\n")
    else:
        out.append(f"\nNGINX obtiene {score(w41, SCORES_41['NGINX']):.0f}/100 ({pos}.º lugar, a {gap:.0f} puntos de {leader}). "
                   f"{leader} gana por criterios puramente de balanceo (checks activos y métricas por servidor en la versión libre) "
                   "y se reporta tal cual. NGINX se usa porque (1) es la tecnología asignada al proyecto, por lo que la matriz "
                   "valida la elección en lugar de hacerla; (2) empata con HAProxy en el desempeño medido (p99 y CPU, las mejores de las cuatro medidas) y es la más completa en funciones L7; "
                   "y (3) sus debilidades se mitigan en el diseño: detección pasiva + reintentos (C3), exporter + logs JSON + "
                   "/metrics por réplica (C4) y `resolve` (C6).\n")

    # 4.2
    out.append("## Matriz 4.2 — algoritmo de balanceo recomendado (con datos medidos)\n")
    out.append(md_table(["Criterio", "Peso", "Métrica, prueba de origen y normalización"], [(c[0], c[1], c[2]) for c in CRITERIA_42]))
    comp = load_comparativo()
    table, totals, pending, coverage = matrix_42(comp)
    if pending:
        out.append("\n> **PENDIENTE:** no hay datos en `results/resumen_comparativo.csv`. Ejecutar `make test-min` "
                   "(y `make test-ext E=E03`) y luego `make analyze && make matrix`. Las celdas muestran puntuación (valor medido).\n")
    out.append("\nCeldas: puntuación 1–5 (valor medido: p99 en ms, Jain, % errores, % afinidad). "
               "Los criterios sin dato se excluyen y los pesos restantes se renormalizan a 100 (columna 'Pesos con dato').\n")
    out.append(table)
    if not pending:
        # Solo compiten las políticas con al menos 70 de 100 puntos de peso medidos
        eligible = {k: v for k, v in totals.items() if not math.isnan(v) and coverage.get(k, 0) >= 70}
        if eligible:
            best = max(eligible, key=eligible.get)
            ranking_txt = " > ".join(f"{k} ({v:.1f})" for k, v in sorted(eligible.items(), key=lambda kv: -kv[1]))
            out.append(f"\n**Algoritmo recomendado según los datos:** `{best}` ({eligible[best]:.1f}/100). "
                       f"Ranking entre las políticas con al menos 70/100 de peso medido: {ranking_txt}. "
                       "Interpretar junto con `results/significancia.txt`: si la diferencia es menor que la desviación "
                       "observada, las alternativas se declaran no distinguibles.\n")
        skipped = [k for k in totals if k not in eligible]
        if skipped:
            out.append("Sin datos suficientes para competir (menos de 70/100 de peso medido): "
                       + ", ".join(f"`{k}`" for k in skipped) + ".\n")

    # 4.3
    out.append("## Matriz 4.3 — estrategia de descubrimiento de backends (decisión de diseño)\n")
    out.append(md_table(["Criterio", "Peso", "Cómo se mide", "Escala 1–5"], [(c[0], c[1], c[2], c[3]) for c in CRITERIA_43]))
    out.append("")
    w43 = [c[1] for c in CRITERIA_43]
    rows = []
    for i, c in enumerate(CRITERIA_43):
        rows.append([f"{c[0]} ({c[1]})"] + [SCORES_43[a][i] for a in ALTERNATIVES_43])
    rows.append(["**Puntaje /100**"] + [f"**{score(w43, SCORES_43[a]):.0f}**" for a in ALTERNATIVES_43])
    out.append(md_table(["Criterio (peso)"] + ALTERNATIVES_43, rows))
    out.append("\nDecisión: DNS con `resolve` para el stack principal; servidores estáticos con nombre solo para el "
               "experimento de pesos (`compose.weighted.yml`). Plan B si `resolve` fallara: generar `backend1…backendN` con un script.\n")

    text = "\n".join(out)
    print(text)
    try:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        (DOCS_DIR / "decision-matrix-generada.md").write_text(text, encoding="utf-8")
        print(f"\n[decision_matrix] escrito {DOCS_DIR / 'decision-matrix-generada.md'}", file=sys.stderr)
    except OSError as e:
        print(f"[decision_matrix] no se pudo escribir en {DOCS_DIR}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
