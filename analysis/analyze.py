#!/usr/bin/env python3
"""
analysis/analyze.py — análisis de resultados (sección 7.10 y 8.3).

Recorre results/*/ (cada carpeta = una corrida creada por scripts/run-test.sh o
scripts/test-seq.sh) y produce, SIN inventar nada:

  por corrida (results/<corrida>/):
    resumen.json                 métricas de Artillery + del log de NGINX + derivadas
    distribucion_backend.csv     peticiones por backend (log) y contadores de Artillery
    serie_1s.csv                 por segundo: peticiones, errores, p99, reintentos (log NGINX)
    figuras/timeline.png         errores/s y p99/s con líneas verticales en los eventos
    figuras/distribucion.png     barras por backend

  globales (results/):
    resumen_corridas.csv         una fila por corrida
    resumen_comparativo.csv      media ± desviación por (test_id, policy, replicas, scenario, label_base)

  figuras comparativas (docs/figuras/):
    algoritmos_latencia.png      media y p99 por política (barras de error)
    algoritmos_distribucion.png  distribución por backend por política (apilado)
    escalabilidad.png            throughput y p95 vs. número de backends + eficiencia
    quiebre.png                  carga máxima sostenible por N (E-13)
    resiliencia_<corrida>.png    copia de los timelines de M-03/E-07/E-09/E-10/E-11
    recursos_<corrida>.png       CPU por contenedor (docker stats)

Variables: RESULTS_DIR (/results), DOCS_DIR (/docs), WARMUP_SECONDS (30), ONLY (prefijo de corrida)
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", "/results"))
DOCS_DIR = Path(os.environ.get("DOCS_DIR", "/docs"))
FIG_DIR = DOCS_DIR / "figuras"
WARMUP_DEFAULT = float(os.environ.get("WARMUP_SECONDS", "30"))
ONLY = os.environ.get("ONLY", "")

# Estilo consistente y legible en blanco y negro
plt.rcParams.update({
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
})
HATCHES = ["", "//", "..", "xx", "\\\\", "++", "oo"]
POLICY_ORDER = ["round_robin", "least_conn", "ip_hash", "hash_client", "hash_remote_addr", "random_two"]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    print(f"[analyze] {msg}", flush=True)


def jain(values) -> float:
    """Índice de equidad de Jain: J = (Σx)² / (n·Σx²). 1 = reparto perfecto, 1/n = todo en uno."""
    x = np.asarray([v for v in values if v is not None], dtype=float)
    if x.size == 0 or x.sum() == 0:
        return float("nan")
    return float(x.sum() ** 2 / (x.size * (x ** 2).sum()))


def cv(values) -> float:
    x = np.asarray(list(values), dtype=float)
    return float(x.std(ddof=0) / x.mean()) if x.size and x.mean() else float("nan")


def load_json(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        log(f"  no se pudo leer {path.name}: {e}")
        return None


def label_base(label: str) -> str:
    """Quita el sufijo de repetición (rep1, rep2…) para agrupar."""
    return re.sub(r"_?rep\d+$", "", label or "")


# ---------------------------------------------------------------------------
# Artillery
# ---------------------------------------------------------------------------
def parse_artillery(path: Path) -> dict:
    data = load_json(path)
    if not data or "aggregate" not in data:
        return {}
    agg = data["aggregate"]
    counters = agg.get("counters", {})
    summ = agg.get("summaries", {}).get("http.response_time", {})
    rates = agg.get("rates", {})
    codes = {k.split(".")[-1]: v for k, v in counters.items() if k.startswith("http.codes.")}
    errors = {k.split(".", 1)[-1]: v for k, v in counters.items() if k.startswith("errors.")}
    backend_counts = {k[len("backend."):]: v for k, v in counters.items() if k.startswith("backend.")}
    requests = counters.get("http.requests", 0)
    responses = counters.get("http.responses", 0)
    non2xx = sum(v for c, v in codes.items() if not c.startswith("2"))
    err_total = sum(errors.values())
    bad = non2xx + err_total
    out = {
        "art_requests": requests,
        "art_responses": responses,
        "art_rps": rates.get("http.request_rate"),
        "art_codes": codes,
        "art_errors": errors,
        "art_non2xx": non2xx,
        "art_transport_errors": err_total,
        "art_error_rate": (bad / requests) if requests else float("nan"),
        "art_lat_min": summ.get("min"),
        "art_lat_mean": summ.get("mean"),
        "art_lat_median": summ.get("median"),
        "art_lat_p95": summ.get("p95"),
        "art_lat_p99": summ.get("p99"),
        "art_lat_max": summ.get("max"),
        "art_vusers_created": counters.get("vusers.created", 0),
        "art_vusers_completed": counters.get("vusers.completed", 0),
        "art_vusers_failed": counters.get("vusers.failed", 0),
        "art_backend_counts": backend_counts,
        "art_affinity_changes": counters.get("afinidad.cambios_de_backend", 0),
        "art_retries": counters.get("lb.reintentos", 0),
        "art_jain": jain(backend_counts.values()) if backend_counts else float("nan"),
    }
    # Serie intermedia (cada 10 s): usuarios activos, rps, p99, errores
    rows = []
    created_cum = completed_cum = 0
    for it in data.get("intermediate", []):
        c = it.get("counters", {})
        s = it.get("summaries", {}).get("http.response_time", {})
        r = it.get("rates", {})
        created_cum += c.get("vusers.created", 0)
        completed_cum += c.get("vusers.completed", 0) + c.get("vusers.failed", 0)
        non2 = sum(v for k, v in c.items() if k.startswith("http.codes.") and not k.split(".")[-1].startswith("2"))
        errs = sum(v for k, v in c.items() if k.startswith("errors."))
        req = c.get("http.requests", 0)
        rows.append({
            "t_end": it.get("lastCounterAt") or it.get("period"),
            "requests": req,
            "rps": r.get("http.request_rate"),
            "p95": s.get("p95"),
            "p99": s.get("p99"),
            "mean": s.get("mean"),
            "non2xx": non2,
            "transport_errors": errs,
            "error_rate": ((non2 + errs) / req) if req else 0.0,
            "vusers_active": created_cum - completed_cum,
        })
    out["art_intermediate"] = pd.DataFrame(rows)
    return out


# ---------------------------------------------------------------------------
# Log JSON de NGINX
# ---------------------------------------------------------------------------
def parse_nginx_log(path: Path) -> pd.DataFrame:
    gz = path.with_suffix(path.suffix + ".gz")
    if not path.exists() and gz.exists():
        path = gz
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    recs = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not recs:
        return pd.DataFrame()
    df = pd.DataFrame(recs)
    df["msec"] = pd.to_numeric(df.get("msec"), errors="coerce")
    df["status"] = pd.to_numeric(df.get("status"), errors="coerce")
    df["request_time"] = pd.to_numeric(df.get("request_time"), errors="coerce")
    df["upstream_addr"] = df.get("upstream_addr", "").fillna("").astype(str)
    df["backend_node"] = df.get("backend_node", "").fillna("").astype(str)
    df.loc[df["backend_node"] == "", "backend_node"] = "sin_backend"
    df["retried"] = df["upstream_addr"].str.contains(",")
    # Último upstream (el que respondió)
    df["upstream_final"] = df["upstream_addr"].str.split(",").str[-1].str.strip()
    # upstream_response_time puede traer "0.012, 0.003" si hubo reintentos
    def last_float(v):
        try:
            return float(str(v).split(",")[-1].strip())
        except ValueError:
            return np.nan
    df["upstream_rt"] = df.get("upstream_response_time", np.nan).map(last_float)
    df = df.dropna(subset=["msec"]).sort_values("msec")
    df["t_rel"] = df["msec"] - df["msec"].iloc[0]
    df["sec"] = df["t_rel"].astype(int)
    df["is_error"] = (df["status"] >= 500) | (df["status"] == 499)
    return df


def nginx_metrics(df: pd.DataFrame, warmup: float, events: pd.DataFrame | None, replicas: int = 0) -> dict:
    if df.empty:
        return {}
    post = df[df["t_rel"] >= warmup] if (df["t_rel"].max() > warmup * 2) else df
    counts = post["backend_node"].value_counts()
    real = counts.drop("sin_backend", errors="ignore")
    # Jain sobre TODAS las réplicas: las que no recibieron tráfico cuentan como 0
    # (si no, ip_hash concentrando todo en un nodo daría J = 1).
    padded = list(real.values) + [0] * max(int(replicas) - len(real), 0)
    out = {
        "ng_requests": int(len(df)),
        "ng_requests_post_warmup": int(len(post)),
        "ng_duration_s": float(df["t_rel"].max()),
        "ng_rps_post_warmup": float(len(post) / max(post["t_rel"].max() - post["t_rel"].min(), 1e-9)),
        "ng_errors": int(post["is_error"].sum()),
        "ng_error_rate": float(post["is_error"].mean()),
        "ng_availability": float(1 - post["is_error"].mean()),
        "ng_retries": int(post["retried"].sum()),
        "ng_retry_rate": float(post["retried"].mean()),
        "ng_lat_mean_ms": float(post["request_time"].mean() * 1000),
        "ng_lat_p50_ms": float(post["request_time"].quantile(0.50) * 1000),
        "ng_lat_p95_ms": float(post["request_time"].quantile(0.95) * 1000),
        "ng_lat_p99_ms": float(post["request_time"].quantile(0.99) * 1000),
        "ng_lat_max_ms": float(post["request_time"].max() * 1000),
        "ng_backend_counts": {k: int(v) for k, v in counts.items()},
        "ng_backend_counts_all": {k: int(v) for k, v in df["backend_node"].value_counts().items()},
        "ng_backends": int(len(real)),
        "ng_jain": jain(padded),
        "ng_cv": cv(padded),
        "ng_max_share": float(real.max() / real.sum()) if len(real) and real.sum() else float("nan"),
        "ng_status_counts": {int(k): int(v) for k, v in post["status"].value_counts().items()},
        "ng_lat_by_backend_ms": {
            k: float(v) for k, v in (post.groupby("backend_node")["request_time"].mean() * 1000).items()
        },
    }
    # Afinidad: % de clientes (client_id) que siempre cayeron en el mismo backend
    if "client_id" in post.columns:
        cid = post[post["client_id"].fillna("") != ""]
        if len(cid):
            g = cid.groupby("client_id")["backend_node"]
            per_client = g.nunique()[g.size() >= 2]   # con 1 petición la afinidad es trivial
            if len(per_client):
                out["ng_affinity_pct"] = float((per_client == 1).mean() * 100)
                out["ng_clients"] = int(len(per_client))
    # Tiempos de detección / recuperación respecto a los eventos de falla
    if events is not None and not events.empty:
        t0_abs = df["msec"].iloc[0]
        ev_times = sorted(float(e) - t0_abs for e in events["epoch"].dropna())
        for _, ev in events.iterrows():
            name = str(ev["event"])
            detail = str(ev.get("detail", ""))
            t_ev = float(ev["epoch"]) - t0_abs
            # La ventana de análisis de una falla termina en el siguiente evento (p. ej. la
            # reposición) o a los 60 s, lo que ocurra antes
            t_next = min([t for t in ev_times if t > t_ev + 0.5] + [t_ev + 60])
            m = re.search(r"node=(\S+)", detail)
            node = m.group(1) if m else None
            if name in ("backend_removed", "backend_stopped", "backend_killed", "backend_paused", "backend_crashed") or name.startswith("fault_"):
                if node and node in df["backend_node"].values:
                    # Detección: última respuesta correcta del nodo caído dentro de los 60 s
                    # posteriores a la falla (antes de cualquier reposición)
                    served_after = df[(df["backend_node"] == node) & (df["t_rel"] > t_ev) & (df["t_rel"] < t_next) & (~df["is_error"])]
                    last_ok = served_after["t_rel"].max() if len(served_after) else t_ev
                    out[f"detect_s_{name}"] = float(max(last_ok - t_ev, 0))
                win = df[(df["t_rel"] >= t_ev) & (df["t_rel"] < t_ev + 30)]
                if len(win):
                    out[f"errors_30s_after_{name}"] = int(win["is_error"].sum())
                    out[f"error_rate_30s_after_{name}"] = float(win["is_error"].mean())
                    out[f"p99_30s_after_{name}_ms"] = float(win["request_time"].quantile(0.99) * 1000)
            if name in ("backend_restore_start", "scale_start", "backend_started", "backend_unpaused"):
                # Recuperación: desde que EMPIEZA la reposición hasta la primera respuesta de un nodo nuevo
                # (scale.sh registra 'backend_restored' al terminar los healthchecks, pero NGINX ya
                # envía tráfico a la réplica nueva en cuanto el DNS la resuelve).
                # Primer nodo "nuevo" (que no aparecía justo antes del evento) y tiempo hasta recibir tráfico
                before_nodes = set(df[(df["t_rel"] < t_ev) & (df["t_rel"] > t_ev - 20)]["backend_node"])
                after = df[df["t_rel"] > t_ev]
                new = after[~after["backend_node"].isin(before_nodes) & (after["backend_node"] != "sin_backend")]
                if len(new):
                    out[f"recover_s_{name}"] = float(new["t_rel"].iloc[0] - t_ev)
    return out


def per_second_series(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("sec")
    s = pd.DataFrame({
        "requests": g.size(),
        "errors": g["is_error"].sum(),
        "retries": g["retried"].sum(),
        "p50_ms": g["request_time"].quantile(0.50) * 1000,
        "p99_ms": g["request_time"].quantile(0.99) * 1000,
        "mean_ms": g["request_time"].mean() * 1000,
        "backends": g["backend_node"].nunique(),
    }).reset_index()
    return s


# ---------------------------------------------------------------------------
# Otros archivos de la corrida
# ---------------------------------------------------------------------------
def read_events(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["epoch", "iso", "event", "detail"])
    try:
        ev = pd.read_csv(path)
        ev["epoch"] = pd.to_numeric(ev["epoch"], errors="coerce")  # segundos (float), como $msec de NGINX
        return ev
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=["epoch", "iso", "event", "detail"])


def read_stub_status(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        st = pd.read_csv(path)
    except Exception:  # noqa: BLE001
        return {}
    if st.empty or "requests" not in st:
        return {}
    d = {
        "stub_samples": int(len(st)),
        "stub_requests_total": int(st["requests"].max() - st["requests"].min()),
        "stub_accepts_total": int(st["accepts"].max() - st["accepts"].min()),
        "stub_unhandled": int((st["accepts"] - st["handled"]).max()),
        "stub_active_max": int(st["active"].max()),
        "stub_active_mean": float(st["active"].mean()),
        "stub_writing_max": int(st["writing"].max()),
        "stub_waiting_max": int(st["waiting"].max()),
    }
    return d


def read_docker_stats(path: Path) -> tuple[dict, pd.DataFrame]:
    if not path.exists():
        return {}, pd.DataFrame()
    try:
        ds = pd.read_csv(path)
    except Exception:  # noqa: BLE001
        return {}, pd.DataFrame()
    if ds.empty or "cpu_perc" not in ds:
        return {}, pd.DataFrame()
    ds["cpu"] = pd.to_numeric(ds["cpu_perc"].astype(str).str.rstrip("%"), errors="coerce")
    ds["mem_mb"] = ds["mem_usage"].astype(str).str.split("/").str[0].map(_to_mb)
    ds["role"] = ds["name"].astype(str).map(_role)
    by_role = ds.groupby("role")["cpu"].agg(["mean", "max"])
    out = {}
    for role, r in by_role.iterrows():
        out[f"cpu_mean_{role}"] = float(r["mean"])
        out[f"cpu_max_{role}"] = float(r["max"])
    mem = ds.groupby("role")["mem_mb"].max()
    for role, v in mem.items():
        out[f"mem_max_mb_{role}"] = float(v)
    if len(by_role):
        out["bottleneck"] = str(by_role["mean"].idxmax())
    return out, ds


def _to_mb(s: str) -> float:
    s = str(s).strip()
    m = re.match(r"([\d.]+)\s*([KMGT]?i?B)", s)
    if not m:
        return np.nan
    v, u = float(m.group(1)), m.group(2)
    return v * {"B": 1 / 1e6, "KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "TiB": 1024 ** 2,
                "KB": 1 / 1000, "MB": 1, "GB": 1000, "TB": 1e6}.get(u, 1)


def _role(name: str) -> str:
    n = name.lower()
    for key in ("backend-slow", "backend", "artillery", "haproxy", "lb", "prometheus", "grafana", "exporter", "pushgateway", "cadvisor"):
        if key in n:
            return key
    return "otro"


# ---------------------------------------------------------------------------
# Figuras por corrida
# ---------------------------------------------------------------------------
def fig_timeline(run: Path, serie: pd.DataFrame, events: pd.DataFrame, t0_abs: float, title: str) -> Path | None:
    if serie.empty:
        return None
    fig, ax1 = plt.subplots(figsize=(10, 4.2))
    ax1.plot(serie["sec"], serie["p99_ms"], color="black", lw=1.2, label="p99 (ms)")
    ax1.plot(serie["sec"], serie["p50_ms"], color="gray", lw=0.9, ls="--", label="p50 (ms)")
    ax1.set_xlabel("segundos desde el inicio de la corrida")
    ax1.set_ylabel("latencia (ms)")
    ax2 = ax1.twinx()
    ax2.bar(serie["sec"], serie["errors"], width=1.0, color="tab:red", alpha=0.55, label="errores/s (5xx, 499)")
    ax2.bar(serie["sec"], serie["retries"], width=1.0, color="tab:orange", alpha=0.45, label="reintentos/s")
    ax2.set_ylabel("errores y reintentos por segundo")
    ax2.spines["right"].set_visible(True)
    if events is not None and not events.empty:
        for _, ev in events.iterrows():
            name = str(ev["event"])
            if name in ("artillery_start", "artillery_end"):
                continue
            t = float(ev["epoch"]) - t0_abs
            ax1.axvline(t, color="tab:blue", ls=":", lw=1.2)
            ax1.text(t, ax1.get_ylim()[1] * 0.98, name, rotation=90, va="top", ha="right", fontsize=7, color="tab:blue")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7, ncol=2)
    ax1.set_title(title, fontsize=9)
    fig.tight_layout()
    out = run / "figuras" / "timeline.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
    return out


def fig_distribution(run: Path, ng_counts: dict, art_counts: dict, title: str) -> Path | None:
    nodes = sorted(set(ng_counts) | set(art_counts), key=lambda n: (-ng_counts.get(n, 0), n))
    nodes = [n for n in nodes if n != "sin_backend"] + (["sin_backend"] if "sin_backend" in nodes else [])
    if not nodes:
        return None
    fig, ax = plt.subplots(figsize=(7, 3.6))
    x = np.arange(len(nodes))
    w = 0.38
    ax.bar(x - w / 2, [ng_counts.get(n, 0) for n in nodes], w, color="#444", label="log NGINX")
    ax.bar(x + w / 2, [art_counts.get(n, 0) for n in nodes], w, color="#bbb", hatch="//", label="contadores Artillery")
    ax.set_xticks(x)
    ax.set_xticklabels([n[:12] for n in nodes], rotation=30, ha="right")
    ax.set_ylabel("peticiones")
    ax.set_title(title, fontsize=9)
    ax.legend(fontsize=7)
    fig.tight_layout()
    out = run / "figuras" / "distribucion.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
    return out


def fig_resources(run: Path, ds: pd.DataFrame, title: str) -> Path | None:
    if ds.empty:
        return None
    fig, ax = plt.subplots(figsize=(9, 3.6))
    t0 = ds["epoch"].min()
    for i, (role, g) in enumerate(ds.groupby("role")):
        agg = g.groupby("epoch")["cpu"].sum()
        ax.plot(agg.index - t0, agg.values, lw=1.2, label=f"{role} (suma)", ls=["-", "--", ":", "-."][i % 4])
    ax.set_xlabel("segundos")
    ax.set_ylabel("CPU % (docker stats)")
    ax.set_title(title, fontsize=9)
    ax.legend(fontsize=7, ncol=3)
    fig.tight_layout()
    out = run / "figuras" / "recursos.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
    return out


def fig_vusers(run: Path, inter: pd.DataFrame, title: str) -> Path | None:
    if inter is None or inter.empty or "vusers_active" not in inter:
        return None
    fig, ax = plt.subplots(figsize=(8, 3.4))
    t = np.arange(len(inter)) * 10
    ax.step(t, inter["vusers_active"], where="post", color="black", label="usuarios activos (≈ creados − terminados)")
    ax.set_xlabel("segundos (periodos de 10 s de Artillery)")
    ax.set_ylabel("usuarios virtuales activos")
    ax.set_title(title, fontsize=9)
    ax.legend(fontsize=7)
    fig.tight_layout()
    out = run / "figuras" / "usuarios_activos.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Corrida
# ---------------------------------------------------------------------------
def analyze_run(run: Path) -> dict | None:
    meta = load_json(run / "metadata.json") or {}
    if not meta:
        return None
    warmup = float(meta.get("warmup_seconds", WARMUP_DEFAULT))
    test_id = meta.get("test_id", "?")
    policy = meta.get("policy", "?")
    replicas = meta.get("replicas", 0)
    label = meta.get("label", "")
    scenario = meta.get("scenario", "")
    title = f"{run.name} · {scenario} · {policy} · {replicas} backends"

    row = {
        "run": run.name,
        "test_id": test_id,
        "scenario": scenario,
        "policy": policy,
        "replicas": replicas,
        "label": label,
        "label_base": label_base(label),
        "feature": meta.get("feature", ""),
        "keepalive": meta.get("upstream_keepalive", ""),
        "target": meta.get("target", ""),
        "notes": meta.get("notes", ""),
        "started_at": meta.get("started_at", ""),
        "artillery_exit": meta.get("artillery_exit_code", ""),
    }

    # M-02 secuencial
    if (run / "secuencial.csv").exists():
        seq = pd.read_csv(run / "secuencial.csv", header=None, names=["t", "node", "ok"])
        counts = seq["node"].value_counts()
        real = counts.drop("__FAIL__", errors="ignore")
        padded = list(real.values) + [0] * max(int(replicas or 0) - len(real), 0)
        row.update({
            "ng_requests": int(len(seq)),
            "ng_errors": int((seq["ok"] == 0).sum()),
            "ng_error_rate": float((seq["ok"] == 0).mean()),
            "ng_backends": int(len(real)),
            "ng_jain": jain(padded),
            "ng_cv": cv(padded),
            "ng_max_share": float(real.max() / real.sum()) if real.sum() else float("nan"),
            "ng_backend_counts": {k: int(v) for k, v in real.items()},
        })
        if len(real) > 1:
            row["seq_max_diff_pct"] = float((real.max() - real.min()) / real.mean() * 100)
        fig_distribution(run, row["ng_backend_counts"], {}, title)
        (run / "resumen.json").write_text(json.dumps(row, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return row

    art = parse_artillery(run / "artillery.json")
    events = read_events(run / "events.csv")
    df = parse_nginx_log(run / "nginx_access.jsonl")
    ng = nginx_metrics(df, warmup, events, int(replicas or 0))
    stub = read_stub_status(run / "stub_status.csv")
    res, ds = read_docker_stats(run / "docker_stats.csv")

    inter = art.pop("art_intermediate", pd.DataFrame())
    row.update({k: v for k, v in art.items() if not isinstance(v, (dict, pd.DataFrame))})
    row.update({k: v for k, v in ng.items() if not isinstance(v, dict)})
    row.update(stub)
    row.update(res)

    # Comparación log NGINX vs contadores Artillery (deben coincidir, M-06)
    ng_counts = ng.get("ng_backend_counts", {})            # tras el calentamiento (para Jain)
    ng_counts_all = ng.get("ng_backend_counts_all", {})    # corrida completa (comparable con Artillery)
    art_counts = art.get("art_backend_counts", {})
    if ng_counts_all and art_counts:
        common = set(ng_counts_all) | set(art_counts)
        diff = sum(abs(ng_counts_all.get(n, 0) - art_counts.get(n, 0)) for n in common)
        row["diff_log_vs_artillery"] = int(diff)
        row["diff_log_vs_artillery_pct"] = float(diff / max(sum(ng_counts_all.values()), 1) * 100)
    dist = pd.DataFrame({
        "backend": sorted(set(ng_counts_all) | set(art_counts)),
    })
    dist["nginx_log"] = dist["backend"].map(lambda n: ng_counts_all.get(n, 0))
    dist["nginx_log_post_warmup"] = dist["backend"].map(lambda n: ng_counts.get(n, 0))
    dist["artillery"] = dist["backend"].map(lambda n: art_counts.get(n, 0))
    total = max(dist["nginx_log"].sum(), 1)
    dist["pct_log"] = dist["nginx_log"] / total * 100
    dist["lat_mean_ms"] = dist["backend"].map(lambda n: ng.get("ng_lat_by_backend_ms", {}).get(n, np.nan))
    dist.to_csv(run / "distribucion_backend.csv", index=False)

    serie = per_second_series(df)
    if not serie.empty:
        serie.to_csv(run / "serie_1s.csv", index=False)
    if not inter.empty:
        inter.to_csv(run / "serie_artillery_10s.csv", index=False)
        # Punto de quiebre (E-13): mayor tasa con error < 1 % y p99 < 1000 ms
        okp = inter[(inter["error_rate"] < 0.01) & (inter["p99"].fillna(1e9) < 1000)]
        row["break_max_rps_ok"] = float(okp["rps"].max()) if len(okp) and okp["rps"].notna().any() else float("nan")
        row["break_first_fail_rps"] = float(inter[~inter.index.isin(okp.index)]["rps"].min()) if len(inter) > len(okp) else float("nan")
        row["vusers_active_max"] = int(inter["vusers_active"].max())
        plateau = inter[inter["vusers_active"] >= 0.9 * inter["vusers_active"].max()]
        row["vusers_plateau_s"] = int(len(plateau) * 10)

    t0_abs = float(df["msec"].iloc[0]) if not df.empty else float(meta.get("start_epoch", 0))
    fig_timeline(run, serie, events, t0_abs, title)
    fig_distribution(run, ng_counts_all, art_counts, title)
    fig_resources(run, ds, title)
    fig_vusers(run, inter, title)

    # Resumen por corrida
    full = dict(row)
    full["ng_backend_counts"] = ng_counts
    full["ng_backend_counts_all"] = ng_counts_all
    full["art_backend_counts"] = art_counts
    full["art_codes"] = art.get("art_codes", {})
    full["art_errors"] = art.get("art_errors", {})
    full["ng_status_counts"] = ng.get("ng_status_counts", {})
    full["ng_lat_by_backend_ms"] = ng.get("ng_lat_by_backend_ms", {})
    (run / "resumen.json").write_text(json.dumps(full, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return row


# ---------------------------------------------------------------------------
# Figuras comparativas
# ---------------------------------------------------------------------------
def fig_algoritmos(comp: pd.DataFrame, runs: pd.DataFrame) -> None:
    sel = comp[comp["test_id"].isin(["M05", "ALG", "E03", "E04", "E05", "E12"])]
    if sel.empty:
        return
    for tid, g in sel.groupby("test_id"):
        g = g.copy()
        g["order"] = g["policy"].map(lambda p: POLICY_ORDER.index(p) if p in POLICY_ORDER else 99)
        g["cfg"] = g["policy"] + np.where(g["label_base"].astype(str) != "", " [" + g["label_base"].astype(str) + "]", "")
        g = g.sort_values(["order", "cfg"])
        fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
        x = np.arange(len(g))
        for ax, col, name in ((axes[0], "ng_lat_mean_ms", "latencia media (ms)"), (axes[1], "ng_lat_p99_ms", "latencia p99 (ms)")):
            ax.bar(x, g[f"{col}_mean"], yerr=g[f"{col}_std"].fillna(0), capsize=4,
                   color=["#333", "#777", "#aaa", "#ccc", "#eee", "#999"][: len(g)] * 3, edgecolor="black")
            ax.set_xticks(x)
            ax.set_xticklabels(g["cfg"], rotation=25, ha="right")
            ax.set_ylabel(name)
            ax.set_title(f"{tid}: {name} (media ± desv., n={int(g['n'].max())})", fontsize=9)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"algoritmos_latencia_{tid}.png")
        plt.close(fig)

        # Distribución apilada por política (promedio de reparto % por backend ordenado)
        rr = runs[runs["test_id"] == tid]
        fig, ax = plt.subplots(figsize=(8, 3.6))
        cfgs = list(g["cfg"])
        for i, cfg in enumerate(cfgs):
            pol = g.iloc[i]["policy"]
            lb = g.iloc[i]["label_base"]
            sub = rr[(rr["policy"] == pol) & (rr["label_base"] == lb)]
            shares = []
            for _, r in sub.iterrows():
                counts = r.get("_ng_counts") or {}
                counts = {k: v for k, v in counts.items() if k != "sin_backend"}
                tot = sum(counts.values()) or 1
                shares.append(sorted([v / tot * 100 for v in counts.values()], reverse=True))
            if not shares:
                continue
            n = max(len(s) for s in shares)
            mean_share = np.array([np.mean([s[j] if j < len(s) else 0 for s in shares]) for j in range(n)])
            bottom = 0
            for j, v in enumerate(mean_share):
                ax.bar(i, v, bottom=bottom, color=plt.cm.Greys(0.25 + 0.6 * j / max(n - 1, 1)), edgecolor="black", hatch=HATCHES[j % len(HATCHES)])
                bottom += v
        ax.set_xticks(range(len(cfgs)))
        ax.set_xticklabels(cfgs, rotation=25, ha="right")
        ax.set_ylabel("% de peticiones por backend (apilado)")
        ax.set_title(f"{tid}: distribución por backend (log NGINX, Jain medio = " +
                     ", ".join(f"{p}:{j:.2f}" for p, j in zip(g["policy"], g["ng_jain_mean"])) + ")", fontsize=8)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"algoritmos_distribucion_{tid}.png")
        plt.close(fig)


def fig_escalabilidad(comp: pd.DataFrame) -> None:
    sel = comp[comp["test_id"].isin(["E01", "E02"])].sort_values("replicas")
    if sel.empty or sel["replicas"].nunique() < 2:
        return
    base = sel[sel["replicas"] == sel["replicas"].min()]
    base_tp = float(base["ng_rps_post_warmup_mean"].iloc[0]) if len(base) else np.nan
    base_n = int(sel["replicas"].min())
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    axes[0].errorbar(sel["replicas"], sel["ng_rps_post_warmup_mean"], yerr=sel["ng_rps_post_warmup_std"].fillna(0), marker="o", color="black", capsize=3)
    axes[0].set_xlabel("backends (N)"); axes[0].set_ylabel("throughput (req/s)"); axes[0].set_title("Throughput vs N", fontsize=9)
    axes[1].errorbar(sel["replicas"], sel["ng_lat_p95_ms_mean"], yerr=sel["ng_lat_p95_ms_std"].fillna(0), marker="s", color="black", capsize=3, label="p95")
    axes[1].errorbar(sel["replicas"], sel["ng_lat_p99_ms_mean"], yerr=sel["ng_lat_p99_ms_std"].fillna(0), marker="^", color="gray", capsize=3, label="p99")
    axes[1].set_xlabel("backends (N)"); axes[1].set_ylabel("latencia (ms)"); axes[1].set_title("p95 / p99 vs N", fontsize=9); axes[1].legend(fontsize=7)
    eff = sel["ng_rps_post_warmup_mean"] / (sel["replicas"] / base_n * base_tp)
    axes[2].plot(sel["replicas"], eff, marker="d", color="black")
    axes[2].axhline(1.0, ls="--", color="gray"); axes[2].set_ylim(0, 1.3)
    axes[2].set_xlabel("backends (N)"); axes[2].set_ylabel("eficiencia de escalado"); axes[2].set_title("Throughput(N) / (N·Throughput(1))", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "escalabilidad.png")
    plt.close(fig)


def fig_quiebre(runs: pd.DataFrame) -> None:
    sel = runs[(runs["test_id"] == "E13") & runs["break_max_rps_ok"].notna()].sort_values("replicas")
    if sel.empty:
        return
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.bar(sel["replicas"].astype(str), sel["break_max_rps_ok"], color="#555", edgecolor="black")
    ax.set_xlabel("backends (N)"); ax.set_ylabel("carga máx. con error < 1 % y p99 < 1 s (req/s)")
    ax.set_title("E-13: punto de quiebre por número de backends", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "quiebre.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    if not RESULTS_DIR.exists():
        log(f"no existe {RESULTS_DIR}")
        return 1
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    runs = sorted(p for p in RESULTS_DIR.glob("*/") if (p / "metadata.json").exists())
    runs += sorted(p for p in (RESULTS_DIR / "ejemplos").glob("*/") if (p / "metadata.json").exists())
    if ONLY:
        runs = [r for r in runs if r.name.startswith(ONLY)]
    if not runs:
        log("no hay corridas con metadata.json en results/ (ejecuta make test-smoke o make test-min)")
        return 0
    rows = []
    for run in runs:
        log(f"corrida {run.name}")
        try:
            row = analyze_run(run)
        except Exception as e:  # noqa: BLE001
            log(f"  ERROR analizando {run.name}: {e!r}")
            continue
        if row:
            r = load_json(run / "resumen.json") or {}
            row["_ng_counts"] = r.get("ng_backend_counts", {})
            rows.append(row)
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    out_cols = [c for c in df.columns if not c.startswith("_")]
    df[out_cols].to_csv(RESULTS_DIR / "resumen_corridas.csv", index=False)
    log(f"resumen_corridas.csv: {len(df)} corridas")

    num_cols = [c for c in df.columns if df[c].dtype.kind in "fi" and c not in ("replicas",)]
    keys = ["test_id", "scenario", "policy", "replicas", "label_base"]
    agg = df.groupby(keys, dropna=False)[num_cols].agg(["mean", "std"])
    agg.columns = [f"{a}_{b}" for a, b in agg.columns]
    agg["n"] = df.groupby(keys, dropna=False).size()
    comp = agg.reset_index()
    comp.to_csv(RESULTS_DIR / "resumen_comparativo.csv", index=False)
    log(f"resumen_comparativo.csv: {len(comp)} configuraciones")

    # Significancia práctica: diferencia menor que la desviación observada -> "no distinguible"
    notes = []
    comparables = comp[comp["test_id"].isin(["M05", "ALG", "E03", "E04", "E05", "E12"])]
    for (tid, reps), g in comparables.groupby(["test_id", "replicas"]):
        if len(g) < 2 or "ng_lat_p99_ms_mean" not in g:
            continue
        g = g.sort_values("ng_lat_p99_ms_mean")
        best, second = g.iloc[0], g.iloc[1]
        gap = float(second["ng_lat_p99_ms_mean"] - best["ng_lat_p99_ms_mean"])
        sds = [float(x) for x in (best.get("ng_lat_p99_ms_std"), second.get("ng_lat_p99_ms_std")) if x is not None and not np.isnan(float(x))]
        if not sds:
            notes.append(f"{tid} ({reps} backends): una sola repetición por configuración; no se puede evaluar la significancia (REPS>=2)")
            continue
        sd = max(sds)
        verdict = "NO distinguible (diferencia < desviación)" if gap < sd else "distinguible"
        cfg = lambda r: r["policy"] + (f" [{r['label_base']}]" if str(r.get("label_base") or "") else "")  # noqa: E731
        notes.append(f"{tid} ({reps} backends): mejor p99 {cfg(best)} ({best['ng_lat_p99_ms_mean']:.1f} ms) vs {cfg(second)} "
                     f"({second['ng_lat_p99_ms_mean']:.1f} ms): diferencia {gap:.1f} ms, desv. máx. {sd:.1f} ms -> {verdict}")
    (RESULTS_DIR / "significancia.txt").write_text("\n".join(notes) + "\n", encoding="utf-8")
    for n in notes:
        log(n)

    fig_algoritmos(comp, df)
    fig_escalabilidad(comp)
    fig_quiebre(df)
    # Copias de timelines y recursos de pruebas de fallo/operación a docs/figuras
    for run in runs:
        tid = (load_json(run / "metadata.json") or {}).get("test_id", "")
        if tid in ("M03", "E06", "E07", "E08", "E09", "E10", "E11", "E14", "E15"):
            src = run / "figuras" / "timeline.png"
            if src.exists():
                shutil.copy(src, FIG_DIR / f"resiliencia_{run.name}.png")
                pol = (load_json(run / "metadata.json") or {}).get("policy", "")
                shutil.copy(src, FIG_DIR / f"resiliencia_{tid}_{pol}.png")
                if tid == "M03":
                    shutil.copy(src, FIG_DIR / "resiliencia_M03.png")
        if tid in ("M04", "M04b"):
            src = run / "figuras" / "usuarios_activos.png"
            if src.exists():
                shutil.copy(src, FIG_DIR / f"usuarios_activos_{run.name}.png")
                shutil.copy(src, FIG_DIR / f"usuarios_activos_{tid}.png")
    log(f"figuras comparativas en {FIG_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
