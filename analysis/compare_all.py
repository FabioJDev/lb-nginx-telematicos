#!/usr/bin/env python3
"""
analysis/compare_all.py — COMPARACIÓN CONSOLIDADA de todas las políticas de balanceo
en todos los escenarios probados.

Une todos los `resumen_comparativo.csv` que encuentra bajo RESULTS_DIR (incluidos los
lotes versionados en results/ejemplos/), elige para cada configuración el lote con más
repeticiones y produce:

  docs/comparacion-algoritmos.md         tablas política × escenario por métrica,
                                         ganador por escenario y ranking global
  docs/figuras/comparacion_latencia.png  p95 por escenario y política
  docs/figuras/comparacion_mapa.png      mapa de calor normalizado (1 = mejor del escenario)
  docs/figuras/comparacion_tienda.png    tienda: sesiones perdidas y pedidos completados
  results/comparacion_algoritmos.csv     tabla larga (escenario, política, métrica, media, desv., n)

Variables: RESULTS_DIR (/results), DOCS_DIR (/docs),
           EXCLUDE ("quick,consistent"): subcadenas de rutas de lotes que se ignoran
           (la corrida rápida de validación y E-05 antes de corregir el hash).
Todas las cifras salen de results/: este script no inventa ni rellena valores.
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

warnings.simplefilter("ignore", pd.errors.PerformanceWarning)

RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", "/results"))
DOCS_DIR = Path(os.environ.get("DOCS_DIR", "/docs"))
FIG_DIR = DOCS_DIR / "figuras"
EXCLUDE = [x for x in os.environ.get("EXCLUDE", "quick,consistent").split(",") if x]

POLICIES = ["round_robin", "least_conn", "random_two", "ip_hash", "hash_client", "sticky_cookie"]

# Escenarios: (clave, título, test_ids, filtro de label_base, descripción)
SCENARIOS = [
    ("homog", "Homogéneo", ["M05", "ALG"], lambda lb: lb == "", "3 réplicas iguales, rampa 5→150 VU/s, espera de 20 ms (M-05, ALG)"),
    ("heter", "1 backend lento", ["E03"], lambda lb: lb == "", "3 rápidas + 1 lenta (150 ms, 0,25 CPU), rampa (E-03)"),
    ("mixto", "Costo variable", ["E04"], lambda lb: lb == "", "90 % de 5 ms y 10 % de 300 ms de espera (E-04)"),
    ("afin", "Afinidad", ["E05", "ALG"], lambda lb: lb == "", "misma IP, cliente lógico por X-Client-Id (E-05 y ALG)"),
    ("falla", "Caída de un backend", ["M03"], lambda lb: lb == "rm", "docker rm -f de 1 de 3 réplicas bajo 300 req/s (M-03)"),
    ("t_mem", "Tienda, sesiones en memoria", ["E16"], lambda lb: lb == "ses-memory", "compra completa con sesión en la réplica (E-16)"),
    ("t_redis", "Tienda, sesiones en Redis", ["E16"], lambda lb: lb == "ses-redis", "compra completa con sesión compartida (E-16)"),
]

# Métricas: (columna base, título, unidad, menor_es_mejor, decimales)
METRICS = [
    ("ng_lat_mean_ms", "Latencia media en NGINX", "ms", True, 1),
    ("ng_lat_p95_ms", "Latencia p95 en NGINX", "ms", True, 1),
    ("ng_lat_p99_ms", "Latencia p99 en NGINX", "ms", True, 1),
    ("ng_goodput_rps", "Goodput (respuestas correctas/s)", "req/s", False, 0),
    ("ng_error_rate", "Tasa de error (5xx) en NGINX", "%", True, 3),
    ("ng_jain", "Índice de Jain (equidad)", "", False, 3),
    ("ng_max_share", "Fracción al backend más cargado", "%", True, 1),
    ("ng_affinity_pct", "Clientes fieles a un backend", "%", False, 1),
    ("ng_retries", "Reintentos (proxy_next_upstream)", "", True, 0),
    ("t_sesion_perdida_pct", "Recorridos con sesión perdida", "%", True, 1),
    ("t_pedido_ok_pct", "Recorridos con pedido completado", "%", False, 1),
    ("ep_p95_pedido", "p95 de la compra (POST /api/orders, Artillery)", "ms", True, 0),
]
PCT_SCALE = {"ng_error_rate": 100.0, "ng_max_share": 100.0}


def log(msg: str) -> None:
    print(f"[compare] {msg}", flush=True)


def load() -> pd.DataFrame:
    frames = []
    for p in sorted(RESULTS_DIR.rglob("resumen_comparativo.csv")):
        rel = str(p.relative_to(RESULTS_DIR)).replace("\\", "/")
        if any(x in rel for x in EXCLUDE):
            log(f"ignorado: {rel}")
            continue
        try:
            df = pd.read_csv(p)
        except Exception as e:  # noqa: BLE001
            log(f"no se pudo leer {rel}: {e}")
            continue
        df["_source"] = rel
        frames.append(df)
        log(f"leído: {rel} ({len(df)} configuraciones)")
    if not frames:
        return pd.DataFrame()
    all_ = pd.concat(frames, ignore_index=True, sort=False).copy()
    all_["label_base"] = all_["label_base"].fillna("").astype(str)
    # Una fila por configuración: la de más repeticiones (n); a igualdad, la última leída
    all_["_order"] = range(len(all_))
    all_ = all_.sort_values(["n", "_order"]).drop_duplicates(
        ["test_id", "scenario", "policy", "replicas", "label_base"], keep="last")
    return all_


def value(row: pd.Series, col: str):
    m, s = row.get(f"{col}_mean"), row.get(f"{col}_std")
    if m is None or (isinstance(m, float) and np.isnan(m)):
        return None, None
    k = PCT_SCALE.get(col, 1.0)
    return float(m) * k, (float(s) * k if s is not None and not (isinstance(s, float) and np.isnan(s)) else 0.0)


def build_long(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, title, tids, filt, desc in SCENARIOS:
        sel = df[df["test_id"].isin(tids) & df["label_base"].map(filt)]
        # Homogéneo: preferir M05 (3 reps) frente a ALG para las políticas que están en ambos
        for pol in POLICIES:
            r = sel[sel["policy"] == pol]
            if r.empty:
                continue
            r = r.sort_values(["n", "test_id"], ascending=[False, False]).iloc[0]
            for col, mtitle, unit, lower, nd in METRICS:
                m, s = value(r, col)
                if m is None:
                    continue
                rows.append(dict(scenario=key, scenario_title=title, policy=pol, metric=col, metric_title=mtitle,
                                 unit=unit, lower_is_better=lower, mean=m, std=s, n=int(r.get("n", 1)),
                                 test_id=r["test_id"], source=r["_source"]))
    return pd.DataFrame(rows)


def fmt(m, s, nd):
    if m is None or np.isnan(m):
        return "—"
    if s and s > 0 and nd >= 0:
        return f"{m:.{nd}f} ± {s:.{nd}f}".replace(".", ",")
    return f"{m:.{nd}f}".replace(".", ",")


def table_for_metric(long: pd.DataFrame, col: str, nd: int, lower: bool) -> str | None:
    sub = long[long["metric"] == col]
    if sub.empty:
        return None
    scen = [s for s in SCENARIOS if s[0] in set(sub["scenario"])]
    head = "| Política | " + " | ".join(s[1] for s in scen) + " |"
    sep = "|---|" + "---|" * len(scen)
    lines = [head, sep]
    best = {}
    for key, *_ in scen:
        g = sub[sub["scenario"] == key]
        if len(g) >= 2:
            best[key] = g["mean"].min() if lower else g["mean"].max()
    for pol in POLICIES:
        cells = []
        if sub[sub["policy"] == pol].empty:
            continue
        for key, *_ in scen:
            r = sub[(sub["scenario"] == key) & (sub["policy"] == pol)]
            if r.empty:
                cells.append("—")
                continue
            m, s = float(r["mean"].iloc[0]), float(r["std"].iloc[0])
            c = fmt(m, s, nd)
            if key in best and abs(m - best[key]) <= max(1e-9, abs(best[key]) * 1e-9):
                c = f"**{c}**"
            cells.append(c)
        lines.append(f"| `{pol}` | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def winners(long: pd.DataFrame) -> list[str]:
    """Ganador por escenario con su métrica principal y si es distinguible frente al segundo."""
    main_metric = {"homog": "ng_lat_p99_ms", "heter": "ng_lat_p95_ms", "mixto": "ng_lat_p99_ms", "afin": "ng_affinity_pct",
                   "falla": "ng_error_rate", "t_mem": "t_sesion_perdida_pct", "t_redis": "ng_lat_p95_ms"}
    out = []
    for key, title, *_ in SCENARIOS:
        col = main_metric[key]
        g = long[(long["scenario"] == key) & (long["metric"] == col)]
        if len(g) < 2:
            continue
        lower = bool(g["lower_is_better"].iloc[0])
        g = g.sort_values("mean", ascending=lower)
        b, s2 = g.iloc[0], g.iloc[1]
        gap = abs(s2["mean"] - b["mean"])
        sd = max(b["std"], s2["std"])
        ties = g[(g["mean"] - b["mean"]).abs() <= max(sd, 1e-9)]["policy"].tolist()
        unit = b["unit"]
        if len(ties) > 1:
            verdict = "empate (diferencia ≤ desviación): " + ", ".join(f"`{p}`" for p in ties)
        else:
            verdict = f"`{b['policy']}` ({b['mean']:.1f} {unit} vs {s2['mean']:.1f} {unit} de `{s2['policy']}`)".replace(".", ",")
        out.append(f"| {title} | {b['metric_title']} | {verdict} |")
    return out


def fig_latency(long: pd.DataFrame) -> None:
    sub = long[long["metric"] == "ng_lat_p95_ms"]
    scen = [s for s in SCENARIOS if s[0] in set(sub["scenario"])]
    if not scen:
        return
    fig, ax = plt.subplots(figsize=(11, 4))
    pols = [p for p in POLICIES if p in set(sub["policy"])]
    w = 0.8 / max(len(pols), 1)
    x = np.arange(len(scen))
    greys = plt.cm.Greys(np.linspace(0.3, 0.9, len(pols)))
    hatches = ["", "//", "..", "xx", "\\\\", "++"]
    for i, pol in enumerate(pols):
        vals, errs = [], []
        for key, *_ in scen:
            r = sub[(sub["scenario"] == key) & (sub["policy"] == pol)]
            vals.append(float(r["mean"].iloc[0]) if len(r) else np.nan)
            errs.append(float(r["std"].iloc[0]) if len(r) else 0)
        ax.bar(x + (i - (len(pols) - 1) / 2) * w, vals, w, yerr=errs, capsize=2, color=greys[i],
               edgecolor="black", hatch=hatches[i % len(hatches)], label=pol)
    ax.set_xticks(x)
    ax.set_xticklabels([s[1] for s in scen], rotation=15, ha="right")
    ax.set_ylabel("p95 en NGINX (ms, escala log)")
    ax.set_yscale("log")
    ax.set_title("Latencia p95 por escenario y política (todas las corridas de results/)", fontsize=9)
    ax.legend(fontsize=7, ncol=3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "comparacion_latencia.png", dpi=200)
    plt.close(fig)


def fig_heatmap(long: pd.DataFrame) -> None:
    """Puntuación normalizada por escenario (1 = mejor política del escenario en su métrica principal)."""
    spec = [("homog", "ng_lat_p99_ms"), ("heter", "ng_lat_p95_ms"), ("mixto", "ng_lat_p99_ms"), ("afin", "ng_jain"),
            ("afin", "ng_affinity_pct"), ("falla", "ng_error_rate"), ("t_mem", "t_pedido_ok_pct"), ("t_redis", "t_pedido_ok_pct")]
    cols, mat = [], []
    pols = [p for p in POLICIES if p in set(long["policy"])]
    for key, metric in spec:
        g = long[(long["scenario"] == key) & (long["metric"] == metric)]
        if len(g) < 2:
            continue
        lower = bool(g["lower_is_better"].iloc[0])
        vals = {r["policy"]: float(r["mean"]) for _, r in g.iterrows()}
        bestv = min(vals.values()) if lower else max(vals.values())
        eps = 1e-3 * max(abs(v) for v in vals.values()) + 1e-9   # evita dividir por 0 (p. ej. 0 errores)
        colv = []
        for p in pols:
            v = vals.get(p)
            if v is None:
                colv.append(np.nan)
            elif lower:
                colv.append(min(1.0, (bestv + eps) / (v + eps)))
            else:
                colv.append(v / bestv if bestv else np.nan)
        title = next(s[1] for s in SCENARIOS if s[0] == key)
        mt = next(m[1] for m in METRICS if m[0] == metric)
        cols.append(f"{title}\n{mt.split(' (')[0]}")
        mat.append(colv)
    if not cols:
        return
    arr = np.array(mat).T
    fig, ax = plt.subplots(figsize=(1.6 * len(cols) + 2, 0.55 * len(pols) + 1.6))
    im = ax.imshow(arr, cmap="Greys", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols, fontsize=7, rotation=30, ha="right")
    ax.set_yticks(range(len(pols)))
    ax.set_yticklabels(pols, fontsize=8)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            v = arr[i, j]
            ax.text(j, i, "—" if np.isnan(v) else f"{v:.2f}", ha="center", va="center", fontsize=7,
                    color="white" if (not np.isnan(v) and v > 0.6) else "black")
    fig.colorbar(im, ax=ax, fraction=0.03, label="1 = mejor del escenario")
    ax.set_title("Comparación normalizada de políticas (más oscuro = mejor)", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "comparacion_mapa.png", dpi=200)
    plt.close(fig)


def fig_tienda(long: pd.DataFrame) -> None:
    sub = long[long["scenario"].isin(["t_mem", "t_redis"]) & long["metric"].isin(["t_sesion_perdida_pct", "t_pedido_ok_pct"])]
    if sub.empty:
        return
    pols = [p for p in POLICIES if p in set(sub["policy"])]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, metric, title in ((axes[0], "t_sesion_perdida_pct", "Recorridos con sesión perdida (%)"),
                              (axes[1], "t_pedido_ok_pct", "Recorridos con pedido completado (%)")):
        x = np.arange(len(pols))
        for i, (key, lab, color, hatch) in enumerate((("t_mem", "sesiones en memoria", "#444", ""), ("t_redis", "sesiones en Redis", "#bbb", "//"))):
            vals, errs = [], []
            for p in pols:
                r = sub[(sub["scenario"] == key) & (sub["policy"] == p) & (sub["metric"] == metric)]
                vals.append(float(r["mean"].iloc[0]) if len(r) else np.nan)
                errs.append(float(r["std"].iloc[0]) if len(r) else 0)
            ax.bar(x + (i - 0.5) * 0.38, vals, 0.38, yerr=errs, capsize=3, color=color, hatch=hatch, edgecolor="black", label=lab)
        ax.set_xticks(x)
        ax.set_xticklabels(pols, rotation=25, ha="right")
        ax.set_ylim(0, 105)
        ax.set_title(title, fontsize=9)
    axes[0].legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "comparacion_tienda.png", dpi=200)
    plt.close(fig)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    df = load()
    if df.empty:
        log("no hay resumen_comparativo.csv en results/ (ejecutar make analyze)")
        return 0
    long = build_long(df)
    if long.empty:
        log("ningún lote corresponde a los escenarios comparados")
        return 0
    long.to_csv(RESULTS_DIR / "comparacion_algoritmos.csv", index=False, lineterminator="\n")

    md = ["# Comparación de todas las políticas de balanceo en todos los escenarios", "",
          "Generado por `analysis/compare_all.py` (`make compare`) a partir de los `resumen_comparativo.csv` de "
          "`results/` y `results/ejemplos/`. Para cada configuración se toma el lote con más repeticiones; "
          "valores = media ± desviación entre repeticiones. **En negrita, el mejor valor del escenario** "
          "(empates incluidos). `—` = combinación no medida.", "",
          "## Escenarios", "", "| Escenario | Qué se probó | Lotes |", "|---|---|---|"]
    for key, title, tids, _f, desc in SCENARIOS:
        srcs = sorted(set(long[long["scenario"] == key]["source"].map(lambda s: s.split("/")[-2] if "/" in s else s)))
        if srcs:
            md.append(f"| {title} | {desc} | {', '.join('`' + s + '`' for s in srcs)} |")
    md += ["", "## Ganador por escenario", "",
           "| Escenario | Métrica principal | Mejor política |", "|---|---|---|"] + winners(long)
    for col, title, unit, lower, nd in METRICS:
        t = table_for_metric(long, col, nd, lower)
        if t:
            md += ["", f"## {title}" + (f" ({unit})" if unit else ""),
                   "", ("Menor es mejor." if lower else "Mayor es mejor."), "", t]
    md += ["", "## Figuras", "",
           "![p95 por escenario](figuras/comparacion_latencia.png)", "",
           "![Mapa normalizado](figuras/comparacion_mapa.png)", "",
           "![Tienda: sesiones y pedidos](figuras/comparacion_tienda.png)", ""]
    (DOCS_DIR / "comparacion-algoritmos.md").write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    for fn in (fig_latency, fig_heatmap, fig_tienda):
        try:
            fn(long)
        except Exception as e:  # noqa: BLE001
            log(f"figura {fn.__name__} omitida: {e!r}")
    log(f"{len(long)} valores · escenarios: {sorted(set(long['scenario']))}")
    log(f"escrito {DOCS_DIR / 'comparacion-algoritmos.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
