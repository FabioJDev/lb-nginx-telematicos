#!/usr/bin/env python3
"""
analysis/decision_matrix.py — matrices de decisión multicriterio (sección 4).

  Matriz 4.1  tecnología de balanceo: puntuaciones propuestas + ANÁLISIS DE
              SENSIBILIDAD (cada peso ±5 redistribuido proporcionalmente en los
              demás; se reporta si cambia el orden).
  Matriz 4.2  algoritmo recomendado: se llena SOLO con datos medidos que estén en
              results/resumen_comparativo.csv (generado por analyze.py). Si no hay
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
CRITERIA_41 = [
    ("C1", "Desempeño y eficiencia", 20, "Throughput y p99 en el mismo escenario/hardware (A-05) o benchmarks publicados; CPU/RAM con docker stats"),
    ("C2", "Algoritmos de balanceo disponibles", 15, "Conteo en la documentación de la versión libre (RR, ponderado, least-conn, hash, afinidad…)"),
    ("C3", "Detección de fallos y tolerancia (versión libre)", 15, "5 = checks activos + reintentos; 3 = solo pasivos + reintentos; 1 = sin reintentos"),
    ("C4", "Observabilidad", 10, "Métricas por backend sin módulos de pago; endpoint Prometheus nativo o vía exporter"),
    ("C5", "Facilidad de configuración", 10, "Líneas de configuración del caso base + curva de aprendizaje (encuesta interna 1-5)"),
    ("C6", "Integración con Docker / descubrimiento dinámico", 10, "¿Detecta réplicas nuevas sin reiniciar? (DNS re-resolvable, etiquetas, API)"),
    ("C7", "Madurez, comunidad y documentación", 10, "Años en producción, frecuencia de versiones, calidad de la documentación oficial"),
    ("C8", "Funciones L7 adicionales", 10, "Estáticos, caché, TLS, limitación de tasa, reescrituras en la versión libre"),
]
ALTERNATIVES_41 = ["NGINX", "HAProxy", "Traefik", "Apache", "LVS"]
SCORES_41 = {
    #        C1 C2 C3 C4 C5 C6 C7 C8
    "NGINX":   [5, 4, 3, 2, 4, 4, 5, 5],
    # C1 HAProxy = 4 con datos de A-05 (results/ejemplos/lote-A05-actions): con la misma carga, p99 +25 %
    # y el doble de CPU que NGINX, con la configuración usada (sin keepalive hacia los backends).
    "HAProxy": [4, 5, 5, 5, 3, 4, 4, 3],
    "Traefik": [4, 3, 4, 5, 4, 5, 4, 3],
    "Apache":  [3, 4, 4, 3, 3, 2, 4, 4],
    "LVS":     [5, 5, 1, 2, 2, 1, 3, 1],
}

# ---------------------------------------------------------------------------
# Matriz 4.3 — descubrimiento de backends
# ---------------------------------------------------------------------------
CRITERIA_43 = [
    ("Escalar sin tocar la config", 30), ("Pesos/backup por servidor", 20),
    ("Simplicidad", 20), ("Robustez ante cambios", 30),
]
ALTERNATIVES_43 = ["Servidores estáticos con nombre", "DNS con resolve (elegida)", "Regenerar config + reload"]
SCORES_43 = {
    "Servidores estáticos con nombre": [1, 5, 4, 3],
    "DNS con resolve (elegida)":       [5, 2, 4, 4],
    "Regenerar config + reload":       [3, 5, 2, 3],
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
    ("Simplicidad operativa", 10, "Cualitativo (juicio del equipo): directivas extra y requisitos del cliente"),
]
SIMPLICITY_42 = {"round_robin": 5, "least_conn": 5, "ip_hash": 4, "hash_client": 3, "hash_remote_addr": 4, "random_two": 4}
POLICIES_42 = ["round_robin", "least_conn", "ip_hash", "hash_client", "random_two"]


def score(weights: list[int], scores: list[int]) -> float:
    return sum(w * s for w, s in zip(weights, scores)) / 5.0


def ranking(weights, scores_by_alt):
    return sorted(scores_by_alt, key=lambda a: -score(weights, scores_by_alt[a]))


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
            rank = ranking(w, scores_by_alt)
            if rank[0] != base_rank[0]:
                changes.append((c[0], sign * delta, rank[0], [round(x, 1) for x in w]))
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
            return ranking(w, scores_by_alt)[0]
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
    p = RESULTS_DIR / "resumen_comparativo.csv"
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
    w41 = [c[2] for c in CRITERIA_41]
    out.append("## Matriz 4.1 — tecnología de balanceo\n")
    out.append(md_table(["ID", "Criterio", "Peso", "Cómo se mide / justifica"], [(c[0], c[1], c[2], c[3]) for c in CRITERIA_41]))
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
    out.append(f"\nNGINX obtiene {score(w41, SCORES_41['NGINX']):.0f}/100 frente a {score(w41, SCORES_41[leader]):.0f}/100 de {leader}. "
               "Si HAProxy lidera en criterios puramente de balanceo (checks activos y métricas por backend en la versión libre), "
               "se reporta con honestidad: NGINX se selecciona porque (1) es la restricción del proyecto asignado, "
               "(2) queda en el grupo líder, (3) aporta funciones L7 completas en un solo componente y (4) sus debilidades se mitigan "
               "en el diseño (detección pasiva + reintentos, exporter + logs JSON, `resolve`).\n")

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
