# Balanceador de carga web con NGINX

**Servicios Telemáticos 2026-02 · Proyecto final 2 · Grupo 3 (Lista 1)**
Integrantes: Fabio Jordan C. · Juan David Morales

Clúster web con balanceo de carga de capa 7 basado en **NGINX** (`upstream`), totalmente
contenedorizado con **Docker Compose**: N backends escalables descubiertos por DNS,
seis políticas de balanceo intercambiables desde `.env`, detección pasiva de fallos con
reintentos, métricas en tiempo real (`stub_status` → Prometheus → Grafana), pruebas de
carga reproducibles con **Artillery** y un contenedor de análisis que convierte cada corrida
en tablas y gráficas. Nada se instala en el host.

> Especificación completa del proyecto: [`docs/especificacion.pdf`](docs/especificacion.pdf) ·
> Enunciado del curso: [`docs/enunciado/`](docs/enunciado/) ·
> Matrices de decisión: [`docs/decision-matrix.md`](docs/decision-matrix.md) ·
> Plan de pruebas: [`docs/plan-pruebas.md`](docs/plan-pruebas.md)

---

## Contenido

1. [Arquitectura](#1-arquitectura)
2. [Requisitos previos](#2-requisitos-previos)
3. [Despliegue paso a paso](#3-despliegue-paso-a-paso)
4. [Variables de entorno](#4-variables-de-entorno)
5. [Operación: políticas, escalado, recarga en caliente, monitoreo](#5-operación)
6. [Pruebas de carga y resiliencia](#6-pruebas-de-carga-y-resiliencia)
7. [Análisis de resultados y matrices de decisión](#7-análisis-de-resultados-y-matrices-de-decisión)
8. [Resultados](#8-resultados)
9. [Cumplimiento de requisitos R-01 … R-25](#9-cumplimiento-de-requisitos)
10. [Seguridad y buenas prácticas](#10-seguridad-y-buenas-prácticas)
11. [Solución de problemas](#11-solución-de-problemas)
12. [Versiones, estructura del repositorio y créditos](#12-versiones-estructura-y-créditos)

---

## 1. Arquitectura

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

Más diagramas (camino de una petición con reintento, flujo de una corrida) en
[`docs/diagramas/arquitectura.md`](docs/diagramas/arquitectura.md).

### Servicios

| Servicio | Imagen | Redes | Puerto en el host | Profile | Función |
|---|---|---|---|---|---|
| `lb` | `nginx:1.30-alpine` | frontend, backend | `LB_PUBLIC_PORT`→80 (`127.0.0.1:LB_STATUS_PORT`→8080 solo con el override) | — | Balanceador L7 y `stub_status` |
| `backend` | build `./backend` (`node:24-alpine`) | backend | **ninguno** | — | App de prueba instrumentada; N réplicas |
| `artillery` | `artilleryio/artillery:2.0.34` | frontend | ninguno | `loadtest` | Generador de carga (`docker compose run`) |
| `nginx-exporter` | `nginx/nginx-prometheus-exporter:1.5.3` | backend | ninguno | `monitoring` | `stub_status` → Prometheus |
| `prometheus` | `prom/prometheus:v3.16.0` | backend, frontend | 9090 | `monitoring` | Series de tiempo |
| `pushgateway` | `prom/pushgateway:v1.11.5` | backend, frontend | ninguno | `monitoring` | Métricas de Artillery |
| `grafana` | `grafana/grafana:12.4.15` | frontend | 3000 | `monitoring` | Dashboard aprovisionado |
| `cadvisor` | `gcr.io/cadvisor/cadvisor:v0.52.1` | backend | ninguno | `cadvisor` | CPU/RAM por contenedor (opcional) |
| `analysis` | build `./analysis` (`python:3.12-slim`) | ninguna | ninguno | `tools` | Tablas CSV, gráficas PNG, matrices |
| `haproxy` | `haproxy:3.2-alpine` | frontend, backend | `HAPROXY_PUBLIC_PORT`, `127.0.0.1:8404` | (compose.haproxy.yml) | Comparativa A-05 |

### Decisiones de diseño clave

- **Backend escalable con DNS dinámico.** Un solo servicio `backend` con `deploy.replicas` y
  `docker compose up --scale backend=N`. El `upstream` usa `server backend:3000 resolve` +
  `zone` + `resolver 127.0.0.11 valid=5s`: NGINX re-resuelve el nombre cada 5 s y las réplicas
  nuevas reciben tráfico **sin recargar**. (`resolve` está en NGINX OSS desde 1.27.3.)
- **Configuración 100 % externa.** La imagen oficial no se modifica: `nginx.conf`, plantillas,
  políticas, extras y la página de mantenimiento se montan `:ro`. Las plantillas se procesan
  con el `envsubst` del entrypoint oficial (`NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx/generated`, un tmpfs)
  y el filtro `NGINX_ENVSUBST_FILTER=^(NGINX_|LB_)` garantiza que `$remote_addr` y demás variables
  de NGINX queden intactas.
- **Política = un archivo.** `nginx/policies/<política>.conf` se incluye en el `upstream`
  (antes de `keepalive`, como exige la documentación). Cambiar de política es cambiar `LB_POLICY`.
- **Dos redes con nombre.** `lbnginx_frontend` (publica el puerto) y `lbnginx_backend`
  (`internal: true`): los backends no tienen salida al host ni a Internet **por diseño**, no solo
  por omitir `ports`.
- **Backend propio e instrumentado.** Identifica el nodo (`X-Backend-Node`), simula latencia y CPU,
  acepta inyección de fallos (`/admin/fault`, `/admin/crash`) y expone `/metrics`. Sin esto no se
  pueden diferenciar los algoritmos.
- **Observabilidad por capas.** `stub_status` (global) · log JSON con `$upstream_addr` y el nodo
  (por petición) · Prometheus/Grafana (series) · contadores de Artillery por backend.
- **Reproducibilidad.** Cada corrida queda en `results/<fecha>_<id>_<política>_<N>b/` con
  metadatos, JSON de Artillery, la porción exacta del log de NGINX, sondeo de `stub_status`,
  `docker stats` y eventos con marca de tiempo.

## 2. Requisitos previos

- **Docker Desktop** (Windows/macOS) o Docker Engine 24+ con **Compose v2.20+**. Nada más.
- Windows 11: habilitar WSL2, clonar el repositorio **dentro** de WSL (`~/proyectos/…`, no `/mnt/c/…`)
  y ejecutar los comandos desde la terminal de WSL. Asignar CPU/RAM suficientes a WSL
  (`%UserProfile%\.wslconfig`) y conectar el portátil a la corriente durante las pruebas.
- `make` (en WSL: `sudo apt install make`). Todos los objetivos tienen su equivalente sin `make` más abajo.

## 3. Despliegue paso a paso

```bash
git clone <url-del-repositorio> lb-nginx-telematicos
cd lb-nginx-telematicos
cp .env.example .env          # ajustar puertos/política si hace falta
make up                       # construye el backend, levanta lb + 3 backends, espera healthchecks
make smoke                    # 30 peticiones: debe repartir entre 3 nodos sin errores
```

Abrir <http://localhost:8080> y recargar: cada recarga cambia de nodo (y de color) con round-robin.

Equivalentes sin `make`:

```bash
docker compose up -d --build            # make up   (aplica docker-compose.override.yml)
docker compose -f docker-compose.yml up -d --build   # make up-clean (sin override)
scripts/smoke.sh 30                     # make smoke
docker compose exec lb nginx -t         # make nginx-test
docker compose down                     # make down
```

Salida esperada de `make smoke` (ejemplo de formato; las cifras reales se toman de la corrida):

```
[10:21:03] smoke: 30 peticiones a /api/info · política=round_robin · feature=none · backends activos=3

Peticiones por nodo (X-Backend-Node):
     10  3f2a9c1d0e4b
     10  7b61e0f9a2c3
     10  c4d8a1b2e5f6
  nodos distintos: 3 · fallos: 0

[10:21:06] OK smoke superado (3 nodos, 0 fallos, política round_robin)
SERVICE   NAME                  STATUS                 PORTS
backend   lbnginx-backend-1     Up 40 seconds (healthy)  3000/tcp
backend   lbnginx-backend-2     Up 40 seconds (healthy)  3000/tcp
backend   lbnginx-backend-3     Up 40 seconds (healthy)  3000/tcp
lb        lbnginx-lb-1          Up 35 seconds (healthy)  0.0.0.0:8080->80/tcp, 127.0.0.1:8081->8080/tcp
```

Los backends muestran `3000/tcp` **sin** `0.0.0.0:` porque solo usan `expose` (R-16).

## 4. Variables de entorno

Archivo `.env` (plantilla en [`.env.example`](.env.example)). Las más relevantes:

| Variable | Por defecto | Descripción |
|---|---|---|
| `NGINX_IMAGE` | `nginx:1.30-alpine` | Imagen del balanceador (≥ 1.28 para `resolve`). |
| `LB_PUBLIC_PORT` | `8080` | Puerto público del balanceador en el host. |
| `LB_STATUS_PORT` | `8081` | `stub_status` en `127.0.0.1` (solo con el override de desarrollo). |
| `NGINX_WORKER_PROCESSES` / `NGINX_WORKER_CONNECTIONS` | `auto` / `4096` | Workers y conexiones por worker. |
| `LB_POLICY` | `round_robin` | `round_robin` · `least_conn` · `ip_hash` · `hash_client` · `hash_remote_addr` · `random_two`. |
| `LB_FEATURE` | `none` | Función L7 extra: `ratelimit` (A-01) o `microcache` (A-02). |
| `LB_UPSTREAM_KEEPALIVE` | `on` | `keepalive 64` hacia los backends (E-12). |
| `LB_MAX_FAILS` / `LB_FAIL_TIMEOUT` | `3` / `10s` | Detección pasiva: tras 3 fallos en 10 s el backend se marca caído 10 s. |
| `LB_CONNECT_TIMEOUT` / `LB_SEND_TIMEOUT` / `LB_READ_TIMEOUT` | `2s` / `10s` / `10s` | Timeouts hacia el upstream. |
| `LB_NEXT_UPSTREAM` | `error timeout http_502 http_503 http_504` | Condiciones de reintento (`off` lo desactiva; E-08 añade `http_500`). |
| `LB_NEXT_UPSTREAM_TRIES` / `LB_NEXT_UPSTREAM_TIMEOUT` | `3` / `15s` | Límite de reintentos. |
| `BACKEND_REPLICAS` | `3` | Réplicas al hacer `make up`. |
| `BACKEND_CPUS` / `BACKEND_MEMORY` | `0.50` / `256M` | Límites por réplica (los backends se saturan antes que el host). |
| `BACKEND_BASE_DELAY_MS` | `0` | Latencia artificial en todas las réplicas. |
| `SLOW_BACKEND_DELAY_MS` / `SLOW_BACKEND_CPUS` / `LB_WEIGHT_FAST` / `LB_WEIGHT_SLOW` | `150` / `0.25` / `1` / `1` | Backend lento y pesos (`compose.weighted.yml`, E-03). |
| `ARTILLERY_IMAGE` / `WORK_PATH` / `PUBLISH_METRICS` / `WARMUP_SECONDS` | `…:2.0.34` / `/api/work?ms=20` / `0` / `30` | Generador de carga, endpoint, publicación a Prometheus, calentamiento descartado. |
| `PROMETHEUS_PORT` / `GRAFANA_PORT` / `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | `9090` / `3000` / `admin` / `cambiar-esto` | Monitoreo. |
| `HAPROXY_IMAGE` / `HAPROXY_PUBLIC_PORT` / `HAPROXY_STATS_PORT` / `HAPROXY_BALANCE` | `haproxy:3.2-alpine` / `8090` / `8404` / `roundrobin` | Comparativa A-05. |

## 5. Operación

### Cambiar la política de balanceo (R-08)

```bash
make policy P=least_conn      # valida nginx/policies/least_conn.conf, actualiza .env y recrea SOLO lb
make policy P=ip_hash
make policy P=hash_client     # afinidad L7 por cabecera X-Client-Id (hash consistente)
make status                   # política vigente, stub_status, réplicas con IP
```

| Política | Cómo decide | Cuándo conviene | Advertencia |
|---|---|---|---|
| `round_robin` | Turnos (ponderables con `weight`) | Backends homogéneos | Ignora la carga real |
| `least_conn` | Menos conexiones activas | Costo variable / heterogéneos | Con peticiones cortas ≈ round-robin |
| `ip_hash` | Hash de la IP (solo 3 octetos en IPv4) | Afinidad simple | Toda una `/24` cae en un backend (E-05) |
| `hash_client` | `hash $http_x_client_id consistent` | Afinidad por cliente lógico (L7) | El cliente debe enviar la cabecera |
| `hash_remote_addr` | `hash $remote_addr consistent` | Afinidad por IP completa | Un solo contenedor = una sola IP |
| `random_two` | `random two least_conn` | Muchos backends, buena cola de latencia | Comparar contra least_conn |

### Escalar backends (R-14 / E-10)

```bash
make scale N=5     # docker compose up -d --scale backend=5 --no-recreate; espera healthchecks
make scale N=7
make smoke         # las réplicas nuevas reciben tráfico sin recargar NGINX (resolve)
```

### Recarga en caliente (R-19, solo desarrollo)

`docker-compose.override.yml` monta `nginx/dev/40-config-watcher.sh`, que cada 2 s compara un
checksum de `nginx.conf`, plantillas, políticas y extras; si cambian, regenera las plantillas,
ejecuta `nginx -t` y, si es válida, `nginx -s reload` **sin reiniciar el contenedor** (si es
inválida, conserva la anterior). Demostración:

```bash
make logs-lb &                                  # ver los mensajes [watcher]
echo "least_conn;" >> nginx/policies/round_robin.conf   # (y luego revertir con git checkout)
# [watcher] cambio detectado -> regenerando plantillas
# [watcher] configuración válida: nginx recargado (policy=round_robin)
make reload                                     # recarga manual: nginx -t && nginx -s reload
```

Despliegue "limpio" sin override: `make up-clean` (`docker compose -f docker-compose.yml up -d`).

### Funciones L7 adicionales (A-01 / A-02)

```bash
make feature F=ratelimit    # limit_req 50 r/s por X-Client-Id (o IP), ráfaga 100, respuesta 429
make feature F=microcache   # proxy_cache de 1 s; cabecera X-Cache-Status HIT/MISS
make feature F=none
make keepalive K=off        # sin keepalive hacia upstream (E-12)
```

### Monitoreo (R-18)

```bash
make monitoring-up      # exporter + Prometheus + Pushgateway + Grafana
# Grafana:    http://localhost:3000  (admin / GRAFANA_ADMIN_PASSWORD)  dashboard "Balanceador NGINX"
# Prometheus: http://localhost:9090  (targets: nginx, backends vía DNS, pushgateway, cadvisor, haproxy)
make cadvisor-up        # opcional: CPU/RAM por contenedor
curl -s http://127.0.0.1:8081/stub_status      # stub_status desde el host (solo con override)
```

El dashboard aprovisionado (`monitoring/grafana/dashboards/lbnginx.json`) tiene paneles de
NGINX (conexiones, req/s, accepted/handled), por réplica (req/s, en vuelo, latencia media y p95,
errores, modo de falla, RSS), Artillery (p95/p99, códigos, contadores por backend), cAdvisor y HAProxy.
Los scripts crean **anotaciones** (inicio/fin de prueba, fallas, escalados) visibles en todos los paneles.

### Comparativa con HAProxy (A-05)

```bash
make haproxy-up                                  # HAProxy en :8090 con los mismos backends; stats en :8404/stats
TARGET=http://haproxy scripts/run-test.sh A05 rampa.yml haproxy
HAPROXY_BALANCE=leastconn make haproxy-up        # roundrobin | leastconn | source
```

## 6. Pruebas de carga y resiliencia

Todas las pruebas usan `scripts/run-test.sh <id> <escenario> [etiqueta]`, que deja cada corrida en
`results/<AAAAMMDD-HHMMSS>_<id>_<política>_<N>b[_etiqueta]/`:

| Archivo | Contenido |
|---|---|
| `metadata.json` | commit, política, réplicas, variables `LB_*`, imágenes, versión de Docker, CPU/RAM del host, horas |
| `artillery.json` / `artillery.log` | salida `--output` de Artillery (aggregate + series de 10 s) y consola |
| `nginx_access.jsonl` | **solo** las líneas del log JSON de NGINX de esta corrida (offset) |
| `stub_status.csv` | sondeo de `stub_status` cada 1 s |
| `docker_stats.csv` | `docker stats` cada 2 s (quién satura primero) |
| `events.csv` | eventos con marca de tiempo: inicio/fin, fallas, escalados, recargas |

### Escenarios de Artillery (`artillery/scenarios/`)

| Escenario | Perfil | Uso |
|---|---|---|
| `smoke.yml` | 1 VU/s · 10 s | Verificación rápida (M-00) |
| `rampa.yml` | 5 → 150 VU/s con rampa, sostenido 120 s (270 s) | R-11, comparación de algoritmos (M-05, E-03, E-04, E-05, E-12), escalabilidad (E-02) |
| `p04-1000-usuarios.yml` | 1000 VU en 10 s, cada uno ~70 s | **M-04 / R-23: 1000 usuarios concurrentes ≥ 60 s** (ley de Little) |
| `p04b-abierto.yml` | 1000 llegadas/s · 60 s, 1 petición | Contraste modelo abierto vs concurrencia |
| `constante.yml` | 100 VU/s · 180 s | Pruebas de fallo y operación en caliente (M-03, E-06…E-11) |
| `quiebre.yml` | 50 → 3000 VU/s en 300 s | E-13: punto de quiebre |
| `spike.yml` | 50 → 800 (20 s) → 50 VU/s | E-14 |
| `soak.yml` | 80 VU/s · 15 min | E-15 |

**1000 usuarios concurrentes con Artillery.** Artillery es un modelo abierto (llegadas/s). Por la
ley de Little, L = λ·W: 1000 llegadas en 10 s con sesiones de ~70 s (70 peticiones con `think: 1`)
producen una meseta de ~1000 usuarios activos durante más de 60 s. `make analyze` dibuja la curva
de usuarios activos (`figuras/usuarios_activos.png`).

### Lotes

```bash
make test-min            # M-00 … M-06 (REPS=3; QUICK=1 para una repetición) ≈ 1 h
make test-algoritmos     # 5 políticas × REPS, orden aleatorio, rampa.yml
make test-resiliencia P=round_robin     # M-03: rm de un backend en t=60 s, reposición en t=120 s
make test-escalabilidad  # E-01/E-02: N = 1, 2, 3, 5, 7
make test-quiebre        # E-13: N = 1, 3, 5
make test-ext E=E03      # E03 E04 E05 E06 E07 E08 E09 E10 E11 E12 E14 E15 | all
make test-all            # todo lo anterior (varias horas)
```

Metodología (sección 8 de la especificación): límites de CPU en los backends, 30 s de calentamiento
descartados, ≥ 3 repeticiones con **orden aleatorio**, 20 s de enfriamiento, `lb` recreado al cambiar
de política, y criterio de significancia práctica: si la diferencia entre dos configuraciones es
menor que la desviación estándar observada se reporta como *no distinguible* (`results/significancia.txt`).

### Inyección de fallos manual

```bash
scripts/inject-fault.sh rm 1            # elimina la réplica 1 (no vuelve sola; reponer con make scale)
scripts/inject-fault.sh stop 1          # SIGTERM: apagado elegante
scripts/inject-fault.sh kill 1          # SIGKILL: Docker la reinicia (restart: unless-stopped)
scripts/inject-fault.sh pause 1         # cuelgue: conexiones aceptadas, nunca respondidas (timeout)
scripts/inject-fault.sh fault:hang 1    # el backend no responde HTTP (proxy_read_timeout)
scripts/inject-fault.sh fault:error500 1   # responde 500 (NO se reintenta salvo LB_NEXT_UPSTREAM con http_500)
scripts/inject-fault.sh restore 1
```

## 7. Análisis de resultados y matrices de decisión

```bash
make analyze     # contenedor analysis: por corrida resumen.json, serie_1s.csv, figuras/; global resumen_corridas.csv,
                 # resumen_comparativo.csv (media ± desv.), significancia.txt y docs/figuras/*.png
make matrix      # docs/decision-matrix-generada.md: matriz 4.1 + sensibilidad, 4.2 CON DATOS, 4.3
make fix-perms   # si los archivos quedaron como root
```

Métricas derivadas (sección 8.3): índice de Jain J = (Σxᵢ)² / (n·Σxᵢ²) sobre peticiones por backend
(las réplicas sin tráfico cuentan como 0), disponibilidad observada, tiempo de detección (última
respuesta correcta del nodo caído tras la falla) y de recuperación (primera respuesta de la réplica
repuesta), tasa de reintentos (`upstream_addr` con coma), eficiencia de escalado
Throughput(N)/(N·Throughput(1)) y concurrencia por Little.

Las tres matrices multicriterio (tecnología, algoritmo con datos, descubrimiento de backends), con la
forma de medir cada criterio y el análisis de sensibilidad, están en
[`docs/decision-matrix.md`](docs/decision-matrix.md).

## 8. Resultados

> **Regla:** ninguna cifra de este README, del informe o de las diapositivas existe sin un archivo
> de origen en `results/`. Este repositorio se construyó en una máquina sin Docker; las corridas las
> ejecuta el equipo en la máquina de pruebas y luego se completan
> [`docs/resultados-minimos.md`](docs/resultados-minimos.md) y
> [`docs/resultados-extendidos.md`](docs/resultados-extendidos.md) y se copian las corridas de
> referencia a [`results/ejemplos/`](results/ejemplos/).

Evidencia esperada por prueba mínima (se rellena con `make analyze`):

| Prueba | Evidencia |
|---|---|
| M-00 smoke | salida de `make smoke` + captura del navegador cambiando de color |
| M-01 stub_status por algoritmo | `docs/capturas/stub_status_<política>.png` + `stub_status.csv` de cada corrida M-05 |
| M-02 reparto con round-robin | `results/*_M02_*/conteo_por_nodo.txt` (J > 0,99, diferencia < 2 %) |
| M-03 resiliencia | `docs/figuras/resiliencia_*.png` (errores/s y p99/s con líneas en t = 60 s y 120 s) |
| M-04 1000 usuarios · 60 s | `docs/figuras/usuarios_activos_*.png` + `resumen.json` (vusers.failed, p99 < 2000 ms) |
| M-05 media/p99 por algoritmo | `docs/figuras/algoritmos_latencia_M05.png` + `results/resumen_comparativo.csv` |
| M-06 distribución real (logs) | `docs/figuras/algoritmos_distribucion_M05.png` + `distribucion_backend.csv` (log vs Artillery) |

## 9. Cumplimiento de requisitos

| ID | Requisito | Cómo se cumple | Evidencia |
|---|---|---|---|
| R-01 | Todo en Docker/Compose, nada en el host | Todos los servicios, incluidos Artillery y el análisis, son contenedores; el Makefile solo invoca `docker` | `make ps`; este README |
| R-02 | README con instrucciones, diagramas y despliegue paso a paso | Este documento | — |
| R-03 | Informe IEEE ≤ 7 páginas | Plantilla IEEEtran, `make informe` | [`docs/informe/informe.tex`](docs/informe/informe.tex) |
| R-04 | Diapositivas en el repositorio | Marp, `make slides` | [`slides/presentacion.md`](slides/presentacion.md) |
| R-05 | Repositorio con configuración y aprovisionamiento | Estructura de la sección 12 | este repositorio |
| R-06 | Presentación ≤ 20 min | Guion cronometrado | [`docs/guion-demo.md`](docs/guion-demo.md) |
| R-07 | NGINX con `upstream` hacia ≥ 3 backends | `upstream backend_pool` + servicio `backend` con 3 réplicas | [`nginx/templates/http.conf.template`](nginx/templates/http.conf.template), `make smoke` |
| R-08 | round-robin, least_conn e ip_hash | Un archivo por política, `make policy P=…` | [`nginx/policies/`](nginx/policies/), resultados M-05 |
| R-09 | `stub_status` | Servidor interno :8080 restringido a redes privadas | [`http.conf.template`](nginx/templates/http.conf.template), `make status` |
| R-10 | Timeouts y reintentos | `proxy_*_timeout`, `proxy_next_upstream`, `max_fails`, `fail_timeout` desde `.env` | M-03, E-07, E-08 |
| R-11 | Rampa progresiva en Artillery | `rampa.yml` (calentamiento → rampa → sostenido → descenso) | [`artillery/scenarios/rampa.yml`](artillery/scenarios/rampa.yml) |
| R-12 | Comparar algoritmos | Mismo escenario, 3 repeticiones, orden aleatorio | `results/resumen_comparativo.csv`, `docs/figuras/algoritmos_*` |
| R-13 | Fallo de backends durante la prueba | Inyección automatizada bajo carga (rm/stop/kill/pause/500/slow/hang) | `docs/figuras/resiliencia_*` |
| R-14 | Compose con NGINX, ≥ 3 backends y Artillery | Servicios `lb`, `backend` (replicas 3), `artillery` (profile) | [`docker-compose.yml`](docker-compose.yml) |
| R-15 | `nginx.conf` como volumen, no en la imagen | Bind mounts `:ro`; imagen oficial sin Dockerfile | `docker inspect lbnginx-lb-1 --format '{{json .Mounts}}'` |
| R-16 | Red con nombre; backends sin puertos | `lbnginx_frontend`, `lbnginx_backend` (`internal: true`); solo `expose` | `docker network inspect lbnginx_backend`, `make ps` |
| R-17 | `.env` para workers, puerto y política | `NGINX_WORKER_PROCESSES`, `LB_PUBLIC_PORT`, `LB_POLICY` (+ timeouts, réplicas…) | [`.env.example`](.env.example) |
| R-18 | Prometheus + exporter (valorado) | Profile `monitoring` con exporter, Prometheus, Pushgateway, Grafana | [`monitoring/`](monitoring/), `docs/capturas/` |
| R-19 | Override con recarga en caliente | Watcher por checksum → `nginx -t && nginx -s reload` | [`docker-compose.override.yml`](docker-compose.override.yml), [`nginx/dev/40-config-watcher.sh`](nginx/dev/40-config-watcher.sh) |
| R-20 | README con diagrama, comandos y resultados esperados | Secciones 1, 3, 8 | — |
| R-21 | Cada algoritmo con capturas de `stub_status` | M-01 (stub_status.csv por corrida + capturas) | `docs/capturas/stub_status_<política>.png` |
| R-22 | Resiliencia al eliminar un backend en caliente | M-03 (`make test-resiliencia`) | `docs/figuras/resiliencia_*.png` |
| R-23 | 1000 usuarios concurrentes 60 s | M-04 (`p04-1000-usuarios.yml`, ley de Little) | `docs/figuras/usuarios_activos_*.png` |
| R-24 | Latencia media y p99 por algoritmo | M-05 (media ± desviación, 3 repeticiones) | `docs/figuras/algoritmos_latencia_M05.png` |
| R-25 | Distribución real por backend desde los logs | M-06 (`nginx_access.jsonl` → Jain, CV, reintentos; contrastado con Artillery) | `distribucion_backend.csv`, `docs/figuras/algoritmos_distribucion_M05.png` |

## 10. Seguridad y buenas prácticas

- Backends sin puertos publicados y en red `internal: true`; `stub_status` y `/admin/*` solo en redes internas.
- `server_tokens off`; configuración montada `:ro`; backend como usuario no root (`USER node`).
- Versiones de imágenes fijadas; `.env` fuera de git; contraseña de Grafana en `.env`.
- Healthchecks en todos los servicios y `depends_on: condition: service_healthy`.
- Límites de CPU/memoria en backends; `ulimits.nofile` elevado en NGINX y Artillery; rotación de logs (`make rotate-logs`).
- CI (`.github/workflows/ci.yml`): `compose config`, shellcheck, build, `nginx -t`, smoke, cambio de política y escalado.

## 11. Solución de problemas

| Síntoma | Causa / solución |
|---|---|
| `bind: address already in use` al hacer `make up` | Cambiar `LB_PUBLIC_PORT` (o `GRAFANA_PORT`, `PROMETHEUS_PORT`) en `.env`. |
| `/bin/sh^M: bad interpreter` o el watcher no arranca | Finales CRLF: `git add --renormalize . && git checkout -- .` y `make check-eol`. El watcher necesita bit ejecutable: `git update-index --chmod=+x nginx/dev/40-config-watcher.sh`. |
| `nginx: [emerg] host not found in upstream "backend"` | `resolve` requiere `zone` + `resolver`; NGINX ≥ 1.27.3. Comprobar `NGINX_IMAGE`. Plan B: generar `backend1…N` estáticos. |
| El watcher no detecta cambios en `nginx.conf` | Un bind mount de un solo archivo conserva el inodo: algunos editores guardan creando otro archivo. Usar `make reload` o editar plantillas/políticas (montadas como directorio). |
| Todo el tráfico va a un solo backend | Política `ip_hash`/`hash_remote_addr` con clientes en la misma `/24` (E-05): es el comportamiento esperado; usar `hash_client`. |
| Artillery avisa "high CPU" | El generador de carga es el cuello de botella (`docker_stats.csv`). Reducir la tasa o reportarlo como limitación. |
| Archivos de `results/` como root | `make fix-perms`. |
| Pruebas lentas o ruidosas en Windows | Repositorio dentro de WSL (no `/mnt/c`), portátil conectado, más CPU/RAM en `.wslconfig`, cerrar aplicaciones pesadas. |
| cAdvisor no arranca en Docker Desktop | Es opcional (profile `cadvisor`); `docker_stats.csv` cubre el uso de CPU. |

## 12. Versiones, estructura y créditos

Versiones de imágenes: ver tabla de la sección 1 y [`docs/entorno.md`](docs/entorno.md).

```
lb-nginx-telematicos/
├── CLAUDE.md  README.md  Makefile  .env.example  .gitignore  .gitattributes  .editorconfig
├── docker-compose.yml            # stack base + profiles monitoring / cadvisor / loadtest / tools
├── docker-compose.override.yml   # SOLO desarrollo: recarga en caliente + stub_status en 127.0.0.1
├── compose.weighted.yml          # backend lento + pesos (E-03)
├── compose.haproxy.yml           # comparativa HAProxy (A-05)
├── backend/                      # Dockerfile (node:24-alpine) + server.js (sin dependencias)
├── nginx/
│   ├── nginx.conf                # montado :ro
│   ├── templates/                # main, events, http, upstream_servers (envsubst)
│   ├── policies/                 # round_robin, least_conn, ip_hash, hash_client, hash_remote_addr, random_two
│   ├── extras/                   # keepalive on/off · features none/ratelimit/microcache
│   ├── html/maintenance.html     # 502/503/504
│   ├── dev/40-config-watcher.sh  # recarga en caliente (solo override)
│   ├── weighted/                 # plantilla de servidores con pesos
│   └── haproxy/haproxy.cfg
├── artillery/                    # lib/processor.js · scenarios/*.yml · config/publish-prometheus.yml
├── monitoring/                   # prometheus.yml · grafana (datasource + dashboard aprovisionados)
├── scripts/                      # run-test.sh, smoke.sh, set-policy.sh, scale.sh, inject-fault.sh, test-*.sh, in-container/
├── analysis/                     # Dockerfile (python:3.12-slim), analyze.py, decision_matrix.py
├── results/                      # una carpeta por corrida (ignorada salvo ejemplos/)
├── logs/nginx/                   # access.json / error.log del balanceador (volumen)
├── docs/                         # especificación, enunciado, matrices, plan de pruebas, informe IEEE, capturas, figuras
├── slides/                       # presentacion.md (Marp) + outline.md
└── .github/workflows/ci.yml      # integración continua (A-06)
```

Créditos: documentación de NGINX (`ngx_http_upstream_module`, `ngx_http_stub_status_module`), imagen
oficial de NGINX (plantillas con envsubst), Artillery, nginx-prometheus-exporter, Prometheus, Grafana,
HAProxy; Little (1961), Jain et al. (1984), Mitzenmacher (2001), Karger et al. (1997). Referencias
completas en `docs/informe/referencias.bib`.
