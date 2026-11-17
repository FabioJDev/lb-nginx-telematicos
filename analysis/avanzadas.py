#!/usr/bin/env python3
"""
analysis/avanzadas.py — resumen de las mejoras avanzadas medidas:

  A-01  limitación de tasa: 429 del cliente abusivo vs clientes normales, peticiones
        que llegan a los backends y latencia de los normales (LB_FEATURE none/ratelimit).
  A-03  TLS + HTTP/2: latencia y CPU del balanceador por http:// y https://.
  A-04  alta disponibilidad: errores y tiempos de conmutación (failover al matar el
        NGINX activo y failback al volver), medidos con la sonda vip_probe.csv.

Lee las corridas (metadata.json + resumen.json de analyze.py) bajo RESULTS_DIR, de forma
recursiva, y escribe RESULTS_DIR/avanzadas.md y avanzadas.csv. No inventa nada: si una
prueba no tiene corridas, su sección lo dice.

Uso (contenedor analysis): python avanzadas.py      Variables: RESULTS_DIR (/results)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", "/results"))
NO_BACKEND = {"", "-", "sin_backend", "nan", "None"}


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def runs(test_id: str) -> list[tuple[Path, dict]]:
    out = []
    for meta in sorted(RESULTS_DIR.rglob("metadata.json")):
        run = meta.parent
        if f"_{test_id}_" not in run.name:
            continue
        r = load(run / "resumen.json")
        if r:
            out.append((run, r))
    return out


def label_of(run: Path, r: dict) -> str:
    return re.sub(r"_?rep\d+$", "", r.get("label") or run.name.split("_", 4)[-1])


def fmt(v, nd=1, suf=""):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if nd == 0:
        return f"{int(round(float(v))):,}".replace(",", " ") + suf
    return f"{v:,.{nd}f}".replace(",", " ").replace(".", ",") + suf


def pm(series: pd.Series, nd=1, suf="") -> str:
    s = series.dropna()
    if s.empty:
        return "—"
    if len(s) == 1:
        return fmt(float(s.iloc[0]), nd, suf)
    return f"{fmt(float(s.mean()), nd)} ± {fmt(float(s.std()), nd)}{suf}"


def backend_requests(r: dict) -> int:
    c = r.get("ng_backend_counts_all") or {}
    return int(sum(v for k, v in c.items() if str(k) not in NO_BACKEND))


# ---------------------------------------------------------------------------
# A-01
# ---------------------------------------------------------------------------
def a01() -> tuple[str, list[dict]]:
    rows = []
    for run, r in runs("A01"):
        lab = label_of(run, r)
        feat = "ratelimit" if "ratelimit-ratelimit" in lab else "none"
        ab_tot = sum(v for k, v in r.items() if k.startswith("ep_abusivo_c"))
        no_tot = sum(v for k, v in r.items() if k.startswith("ep_normal_c"))
        rows.append({
            "prueba": "A01", "corrida": run.name, "config": feat,
            "abusivo_total": ab_tot, "abusivo_429": r.get("ep_abusivo_c429", 0),
            "normal_total": no_tot, "normal_429": r.get("ep_normal_c429", 0),
            "normal_200": r.get("ep_normal_c200", 0),
            "abusivo_429_pct": 100.0 * r.get("ep_abusivo_c429", 0) / ab_tot if ab_tot else float("nan"),
            "normal_429_pct": 100.0 * r.get("ep_normal_c429", 0) / no_tot if no_tot else float("nan"),
            "backend_reqs": backend_requests(r),
            "normal_p95_ms": r.get("ep_p95_normal"),
            "errores_transporte": r.get("art_transport_errors", 0),
            "cpu_lb": r.get("cpu_mean_lb"),
        })
    if not rows:
        return "## A-01 · Limitación de tasa\n\nSin corridas A01 en results/.\n", rows
    df = pd.DataFrame(rows)
    md = ["## A-01 · Limitación de tasa por cliente", "",
          "Escenario `ratelimit.yml`: 120 llegadas/s durante 90 s; ≈ 2/3 de un mismo cliente "
          "(`X-Client-Id: cliente-abusivo`) y ≈ 1/3 de clientes distintos. Límite: 50 req/s por "
          "cliente, ráfaga 100 (`nginx/extras/features/ratelimit/`).", "",
          f"Corridas: {len(df)} ({', '.join(f'{k}: {v}' for k, v in df['config'].value_counts().items())}). "
          "Valores: media ± desviación entre repeticiones.", "",
          "| Configuración | Peticiones del abusivo | 429 al abusivo | Peticiones normales | 429 a normales | p95 normales | Peticiones que llegan a los backends |",
          "|---|---|---|---|---|---|---|"]
    for feat in ("none", "ratelimit"):
        g = df[df["config"] == feat]
        if g.empty:
            continue
        md.append(f"| `LB_FEATURE={feat}` | {pm(g['abusivo_total'], 0)} | {pm(g['abusivo_429'], 0)} ({pm(g['abusivo_429_pct'], 1, ' %')}) "
                  f"| {pm(g['normal_total'], 0)} | {pm(g['normal_429'], 0)} ({pm(g['normal_429_pct'], 1, ' %')}) "
                  f"| {pm(g['normal_p95_ms'], 1, ' ms')} | {pm(g['backend_reqs'], 0)} |")
    md.append("")
    return "\n".join(md), rows


# ---------------------------------------------------------------------------
# A-03
# ---------------------------------------------------------------------------
def a03() -> tuple[str, list[dict]]:
    rows = []
    for run, r in runs("A03"):
        lab = label_of(run, r)
        proto = "https" if "proto-https" in lab else "http"
        sess = ((load(run / "artillery.json") or {}).get("aggregate", {}).get("summaries", {})
                .get("vusers.session_length", {}))
        rows.append({
            "sesion_mediana_ms": sess.get("median"), "sesion_p95_ms": sess.get("p95"),
            "prueba": "A03", "corrida": run.name, "config": proto,
            "lat_media_ms": r.get("art_lat_mean"), "lat_p95_ms": r.get("art_lat_p95"), "lat_p99_ms": r.get("art_lat_p99"),
            "nginx_p99_ms": r.get("ng_lat_p99_ms"),
            "cpu_lb_media": r.get("cpu_mean_lb"), "cpu_lb_max": r.get("cpu_max_lb"),
            "error_rate_pct": 100.0 * (r.get("art_error_rate") or 0),
            "peticiones": r.get("art_requests"),
        })
    md = ["## A-03 · TLS + HTTP/2 en el balanceador", ""]
    evid = RESULTS_DIR / "A03_tls_http2.txt"
    if not evid.exists():
        evid = next(iter(sorted(RESULTS_DIR.rglob("A03_tls_http2.txt"))), None)
    if evid and evid.exists():
        md += ["Negociación comprobada con curl (contenedor):", "", "```",
               *[ln for ln in evid.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")], "```", ""]
    if not rows:
        md.append("Sin corridas A03 en results/.")
        return "\n".join(md) + "\n", rows
    df = pd.DataFrame(rows)
    md += ["Misma carga (`constante.yml`, 100 usuarios/s, 3 peticiones por usuario, 180 s) por `http://lb` y "
           "`https://lb`. Cada usuario virtual abre su propia conexión: con HTTPS cada uno paga un handshake TLS. "
           "El tiempo de respuesta de Artillery empieza con la conexión ya abierta; la duración de la sesión "
           "(`vusers.session_length`) sí incluye conexión y handshake.", "",
           "| Protocolo | Respuesta p95 | Respuesta p99 | Sesión completa (mediana) | Sesión completa (p95) | CPU media del balanceador | CPU máx. del balanceador | Errores |",
           "|---|---|---|---|---|---|---|---|"]
    for proto in ("http", "https"):
        g = df[df["config"] == proto]
        if g.empty:
            continue
        md.append(f"| {proto} | {pm(g['lat_p95_ms'], 1, ' ms')} | {pm(g['lat_p99_ms'], 1, ' ms')} "
                  f"| {pm(g['sesion_mediana_ms'], 1, ' ms')} | {pm(g['sesion_p95_ms'], 1, ' ms')} "
                  f"| {pm(g['cpu_lb_media'], 1, ' %')} | {pm(g['cpu_lb_max'], 1, ' %')} | {pm(g['error_rate_pct'], 2, ' %')} |")
    md.append("")
    return "\n".join(md), rows


# ---------------------------------------------------------------------------
# A-04
# ---------------------------------------------------------------------------
def probe_stats(run: Path) -> dict:
    p, ev, hosts = run / "vip_probe.csv", run / "events.csv", run / "ha_hosts.csv"
    if not (p.exists() and ev.exists()):
        return {}
    try:
        pr = pd.read_csv(p, dtype={"status": str, "lb_host": str})
        events = pd.read_csv(ev)
    except (OSError, ValueError, pd.errors.ParserError):
        return {}
    if pr.empty:
        return {}
    hmap = {}
    if hosts.exists():
        h = pd.read_csv(hosts, dtype=str)
        hmap = dict(zip(h["hostname"], h["servicio"]))
    pr["svc"] = pr["lb_host"].map(hmap).fillna(pr["lb_host"].fillna(""))
    pr["ok"] = pr["status"] == "200"

    def ev_ms(name):
        e = events[events["event"] == name]
        return float(e["epoch"].iloc[0]) * 1000 if not e.empty else None

    t_kill, t_rest, t_back = ev_ms("lb_killed"), ev_ms("lb_restore_start"), ev_ms("lb_restored")
    out = {"sondas": int(len(pr)), "sondas_fallidas": int((~pr["ok"]).sum())}
    if t_kill and pr["epoch_ms"].min() > t_kill:
        # La sonda arrancó después del kill: el failover no quedó medido por la sonda
        out["sonda_tardia"] = True
        out["failover_ms"] = float("nan")
        out["failover_fallidas"] = float("nan")
    elif t_kill:
        before = pr[pr["epoch_ms"] < t_kill]
        out["svc_antes"] = before[before["ok"]]["svc"].mode().iloc[0] if before["ok"].any() else ""
        win = pr[(pr["epoch_ms"] >= t_kill) & ((pr["epoch_ms"] < t_rest) if t_rest else True)]
        first_lb2 = win[win["ok"] & (win["svc"] == "lb2")]
        out["failover_ms"] = float(first_lb2["epoch_ms"].iloc[0] - t_kill) if not first_lb2.empty else float("nan")
        out["failover_fallidas"] = int((~win["ok"]).sum())
        if not first_lb2.empty:
            out["failover_hueco_ms"] = float(
                first_lb2["epoch_ms"].iloc[0] - (win[~win["ok"]]["epoch_ms"].min() if (~win["ok"]).any() else first_lb2["epoch_ms"].iloc[0]))
    if t_rest:
        after = pr[pr["epoch_ms"] >= t_rest]
        out["failback_fallidas"] = int((~after["ok"]).sum())
        back = after[after["ok"] & (after["svc"] == "lb")]
        out["failback_ms"] = float(back["epoch_ms"].iloc[0] - t_rest) if not back.empty else float("nan")
        out["svc_final"] = after[after["ok"]]["svc"].iloc[-1] if after["ok"].any() else ""
    if t_back and t_rest:
        out["restauracion_s"] = (t_back - t_rest) / 1000
    return out


def art_phases(run: Path) -> dict:
    """Errores de Artillery y duración máxima de sesión en las ventanas de 10 s que
    contienen el failover (kill) y el failback (vuelta de lb)."""
    art, ev = load(run / "artillery.json") or {}, run / "events.csv"
    if not art or not ev.exists():
        return {}
    events = pd.read_csv(ev)

    def ev_ms(name):
        e = events[events["event"] == name]
        return float(e["epoch"].iloc[0]) * 1000 if not e.empty else None

    t_kill, t_rest, t_back = ev_ms("lb_killed"), ev_ms("lb_restore_start"), ev_ms("lb_restored")
    out = {"art_err_failover": 0, "art_err_failback": 0, "sesion_max_failover_ms": float("nan"),
           "sesion_max_failback_ms": float("nan")}
    # Intervalos de cada fase: failover = 20 s desde el kill; vuelta = desde que se levanta lb
    # hasta 10 s después de que lb queda listo (con preempción, ahí recupera la VIP)
    spans = {}
    if t_kill:
        spans["failover"] = (t_kill, t_kill + 20000)
    if t_rest:
        spans["failback"] = (t_rest, (t_back or t_rest) + 10000)
    for it in art.get("intermediate", []):
        p0 = float(it.get("period") or 0)
        errs = sum(v for k, v in it.get("counters", {}).items() if k.startswith("errors."))
        smax = it.get("summaries", {}).get("vusers.session_length", {}).get("max")
        for key, (a, b) in spans.items():
            # ventana de 10 s de Artillery que se solapa con la fase
            if p0 < b and p0 + 10000 > a:
                out[f"art_err_{key}"] += errs
                if smax is not None:
                    cur = out[f"sesion_max_{key}_ms"]
                    out[f"sesion_max_{key}_ms"] = smax if pd.isna(cur) else max(cur, smax)
    return out


def a04() -> tuple[str, list[dict]]:
    rows = []
    for run, r in runs("A04"):
        lab = label_of(run, r)
        variant = "off" if "preempt-off" in lab else "on"
        ps = probe_stats(run)
        ph = art_phases(run)
        req = r.get("art_requests") or 0
        bad = (r.get("art_non2xx") or 0) + (r.get("art_transport_errors") or 0)
        rows.append({
            "prueba": "A04", "corrida": run.name, "config": f"preempt-{variant}",
            "peticiones": req, "fallidas": bad,
            "disponibilidad_pct": 100.0 * (1 - bad / req) if req else float("nan"),
            "errores_transporte": r.get("art_transport_errors", 0),
            "tipos_error": " · ".join(f"{k} {v}" for k, v in sorted((r.get("art_errors") or {}).items())),
            "p99_ms": r.get("art_lat_p99"), "max_ms": r.get("art_lat_max"),
            "cpu_lb": r.get("cpu_mean_lb"), "cpu_lb2": r.get("cpu_mean_lb2"),
            **ps, **ph,
        })
    if not rows:
        return "## A-04 · Alta disponibilidad del balanceador\n\nSin corridas A04 en results/.\n", rows
    df = pd.DataFrame(rows)
    md = ["## A-04 · Alta disponibilidad del balanceador (keepalived + IP flotante)", "",
          "Carga `constante.yml` (100 usuarios/s, 180 s) contra la VIP `172.31.250.100`; `docker kill` del NGINX "
          "activo en t = 60 s y vuelta en t = 120 s. Sonda propia cada 100 ms (conexión nueva, timeout 1 s) que "
          "registra qué NGINX respondió (`X-LB-Host`). `preempt-on`: lb recupera la VIP al volver (defecto de VRRP); "
          "`preempt-off`: `nopreempt`, la VIP se queda en lb2.", "",
          "### Por configuración (media ± desviación)", "",
          "| Configuración | Corridas | Disponibilidad | Failover (1.ª respuesta de lb2) | Errores en el failover | Sesión más larga en el failover | Errores en la vuelta de lb | Atendía al final |",
          "|---|---|---|---|---|---|---|---|"]
    for cfg in ("preempt-on", "preempt-off"):
        g = df[df["config"] == cfg]
        if g.empty:
            continue
        final = ", ".join(sorted(set(str(v) for v in g.get("svc_final", pd.Series(dtype=str)).dropna())))
        md.append(f"| `{cfg}` | {len(g)} | {pm(g['disponibilidad_pct'], 2, ' %')} | {pm(g['failover_ms'] / 1000, 2, ' s')} "
                  f"| {pm(g['art_err_failover'], 0)} | {pm(g['sesion_max_failover_ms'] / 1000, 2, ' s')} "
                  f"| {pm(g['art_err_failback'], 0)} | {final or '—'} |")
    md += ["", "### Por corrida", "",
           "| Corrida | Peticiones | Fallidas (tipo) | Disponibilidad | Failover | Sondas fallidas (failover / vuelta) | Errores Artillery (failover / vuelta) |",
           "|---|---|---|---|---|---|---|"]
    for _, x in df.iterrows():
        md.append(f"| `{x['corrida']}` | {fmt(x['peticiones'], 0)} | {fmt(x['fallidas'], 0)} ({x['tipos_error'] or '—'}) "
                  f"| {fmt(x['disponibilidad_pct'], 2, ' %')} | {fmt((x.get('failover_ms') or float('nan')) / 1000, 2, ' s')} "
                  f"| {fmt(x.get('failover_fallidas'), 0)} / {fmt(x.get('failback_fallidas'), 0)} "
                  f"| {fmt(x.get('art_err_failover'), 0)} / {fmt(x.get('art_err_failback'), 0)} |")
    if "sonda_tardia" in df and df["sonda_tardia"].fillna(False).any():
        tard = ", ".join(f"`{c}`" for c in df[df["sonda_tardia"].fillna(False)]["corrida"])
        md += ["", f"En {tard} la sonda arrancó después del kill: su failover no quedó medido por la sonda "
                   "(«—») y no entra en las medias de failover; los errores de Artillery sí cuentan."]
    md.append("")
    return "\n".join(md), rows


def main() -> int:
    parts, allrows = [], []
    for fn in (a01, a03, a04):
        md, rows = fn()
        parts.append(md)
        allrows += rows
    head = ("# Mejoras avanzadas medidas (A-01, A-03, A-04)\n\n"
            "Generado por `analysis/avanzadas.py` a partir de las corridas de `results/`.\n\n")
    (RESULTS_DIR / "avanzadas.md").write_text(head + "\n".join(parts), encoding="utf-8", newline="\n")
    if allrows:
        pd.DataFrame(allrows).to_csv(RESULTS_DIR / "avanzadas.csv", index=False, lineterminator="\n")
    print(head + "\n".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
