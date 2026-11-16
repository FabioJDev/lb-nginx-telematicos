# Diagramas de arquitectura

Fuente de los diagramas (Mermaid). Para exportar a PNG sin instalar nada en el host:

```bash
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD/docs/diagramas:/data" minlag/mermaid-cli:11.4.2 -i arquitectura.mmd -o arquitectura.png -b white -s 2
```

## 1. Arquitectura lógica, redes y flujos

```mermaid
flowchart LR
    subgraph HOST["Host (Windows 11 + WSL2 + Docker Desktop)"]
        direction LR
        CLI[("curl / navegador<br/>localhost:8080")]
        subgraph FRONT["red lbnginx_frontend (bridge)"]
            ART["artillery<br/>(profile loadtest)"]
            GRAF["grafana :3000<br/>(profile monitoring)"]
        end
        subgraph LBN["lb — NGINX 1.30 (en ambas redes)"]
            NGX["upstream backend_pool<br/>policy include · resolve · keepalive<br/>:80 público · :8080 stub_status"]
        end
        subgraph BACK["red lbnginx_backend (internal: true — sin host ni Internet)"]
            B1["backend réplica 1<br/>node:24-alpine :3000"]
            B2["backend réplica 2"]
            B3["backend réplica N<br/>(--scale backend=N)"]
            EXP["nginx-prometheus-exporter"]
            PROM["prometheus :9090"]
            PUSH["pushgateway"]
        end
    end
    CLI -- "HTTP :8080→80" --> NGX
    ART -- "HTTP http://lb" --> NGX
    NGX -- "proxy_pass (DNS 'backend' → N IPs)" --> B1 & B2 & B3
    EXP -. "scrape lb:8080/stub_status" .-> NGX
    PROM -. "scrape" .-> EXP
    PROM -. "dns_sd backend:3000/metrics" .-> B1 & B2 & B3
    ART -. "publish-metrics (opcional)" .-> PUSH
    PROM -. "scrape" .-> PUSH
    GRAF -. "PromQL" .-> PROM
```

## 2. Camino de una petición y detección pasiva de fallos

```mermaid
sequenceDiagram
    participant C as Cliente (Artillery)
    participant N as NGINX (lb)
    participant A as backend A
    participant B as backend B
    C->>N: GET /api/work?ms=20 (X-Client-Id)
    N->>A: proxy_pass (keepalive, connect_timeout 2s, read_timeout 10s)
    A--xN: conexión rechazada / timeout (backend caído)
    Note over N: fail #1 de max_fails=3 en fail_timeout=10s<br/>proxy_next_upstream → reintento
    N->>B: misma petición (tries ≤ 3, ≤ 15s en total)
    B-->>N: 200 OK · X-Backend-Node: B
    N-->>C: 200 OK · X-Upstream-Addr: "A:3000, B:3000" (reintento visible)
    Note over N: log JSON: upstream_addr con coma → retried=1
```

## 3. Flujo de una corrida de prueba (`scripts/run-test.sh`)

```mermaid
flowchart TD
    S([make test-… / run-test.sh id escenario]) --> M[Crea results/&lt;fecha&gt;_id_política_Nb/<br/>metadata.json]
    M --> O[Anota offset de /var/log/nginx/access.json]
    O --> C1[Colector stub_status 1 s<br/>dentro de lb]
    O --> C2[Colector docker stats 2 s]
    O --> A[docker compose run artillery<br/>--output artillery.json]
    A --> E[events.csv: artillery_start/end<br/>+ fallas / escalados de otros scripts]
    E --> L[Extrae solo las líneas nuevas del log<br/>→ nginx_access.jsonl]
    L --> AN[make analyze → resumen.json, serie_1s.csv,<br/>figuras/*.png, resumen_comparativo.csv]
```
