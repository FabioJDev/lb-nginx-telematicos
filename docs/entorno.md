# Entorno y versiones

## Imágenes (todas con versión fijada; nunca `:latest`)

Verificadas en Docker Hub el 16 de noviembre de 2026 (`.env.example`).

| Servicio | Imagen | Notas |
|---|---|---|
| lb | `nginx:1.30-alpine` | Rama estable vigente. `resolve` en `upstream` existe en NGINX OSS desde 1.27.3 (estable ≥ 1.28). |
| backend | `lbnginx-backend:local` (build de `node:24-alpine`) | Node.js 24 LTS; dependencias fijadas en `package-lock.json`: `pg` 8.23.1 y `redis` 4.7.0 (tienda). |
| postgres | `postgres:17-alpine` | Base de datos de la tienda, compartida por todas las réplicas; sin puertos al host. |
| redis | `redis:7.4-alpine` | Sesiones compartidas (`SESSION_STORE=redis`); sin puertos al host. |
| artillery | `artilleryio/artillery:2.0.34` | `artillery report` fue retirado en 2.0.22: no se usa. |
| nginx-exporter | `nginx/nginx-prometheus-exporter:1.5.3` | Lee `http://lb:8080/stub_status`. |
| prometheus | `prom/prometheus:v3.16.0` | `dns_sd_configs` descubre todas las réplicas. |
| pushgateway | `prom/pushgateway:v1.11.5` | Recibe `publish-metrics` de Artillery (opcional). |
| grafana | `grafana/grafana:12.4.15` | Dashboard y datasource aprovisionados desde el repo. |
| cadvisor | `gcr.io/cadvisor/cadvisor:v0.52.1` | Profile aparte; puede no arrancar en Docker Desktop. |
| haproxy | `haproxy:3.2-alpine` | Solo para la comparativa A-05. |
| navegador | `mcr.microsoft.com/playwright:v1.49.1-noble` | Chromium sin interfaz para `make capturas` (`compose.capturas.yml`). |
| analysis | `lbnginx-analysis:local` (build de `python:3.12-slim`) | pandas 2.2.3, matplotlib 3.9.2. |
| (docs) | `texlive/texlive:TL2024-historic`, `marpteam/marp-cli:v4.5.1`, `minlag/mermaid-cli:11.4.2`, `koalaman/shellcheck:v0.10.0` | Solo se usan bajo demanda (`make informe`, `make slides`, …). |

## Host de pruebas

### Host donde se midieron los resultados del repositorio

Todas las corridas de `results/ejemplos/` se ejecutaron en runners `ubuntu-latest` de GitHub Actions
(`.github/workflows/pruebas.yml`). Valores tomados del campo `host` de sus `metadata.json`:

| Dato | Valor |
|---|---|
| CPU visibles | 2 (todas las corridas) |
| Memoria | 7 931 MB (148 corridas), 7 930 MB (14) y 7 775 MB (1) |
| Kernel | `7.0.0-1019-azure` (162 corridas) y `7.0.0-1016-aws` (1) |
| Docker Engine | 29.4.2 |
| Docker Compose | 5.1.3 |

Dos corridas de M-02 (`seq1000`) no registran `host`: usan un camino del script que no escribe ese campo.
Con 2 CPU, el generador de carga, el balanceador, los backends y la base de datos compiten por el mismo
procesador; esa limitación se declara en el informe y en los resultados.

### Máquina del equipo (para repetir las pruebas)

> Completar si se repiten las pruebas en el portátil del equipo (los valores también quedan en
> `metadata.json` de cada corrida, campo `host`).

| Dato | Valor |
|---|---|
| Sistema operativo | Windows 11 + WSL2 (distribución: ______) |
| Docker Desktop / Engine | `docker version` → ______ |
| Docker Compose | `docker compose version` → ______ (requiere v2.20+; `--scale` + `deploy.replicas`) |
| CPU (núcleos visibles en WSL) | `nproc` → ______ |
| Memoria asignada a WSL | `free -m` → ______ (ajustar en `%UserProfile%\.wslconfig`) |
| Equipo conectado a la corriente durante las pruebas | sí / no |

## Requisitos mínimos comprobados

- Docker Engine 24+ con Compose v2.20+ (sintaxis `name:`, `profiles`, `deploy.replicas`).
- El repositorio clonado **dentro** del sistema de archivos de WSL (`~/proyectos/...`), no en `/mnt/c/...`:
  los bind mounts son mucho más rápidos y los cambios se propagan al watcher.
- `make` dentro de WSL (`sudo apt install make`) o usar los comandos equivalentes del README.

## Nota sobre la máquina en la que se generó este repositorio

El repositorio se construyó en un equipo **sin Docker ni WSL instalados**, por lo que todo lo que
hay en `results/ejemplos/` proviene de ejecuciones reales en GitHub Actions (host descrito arriba). Lo que se
validó estáticamente al construirlo: sintaxis de `server.js` y `processor.js` (`node --check`),
sintaxis de todos los scripts (`bash -n`), YAML/JSON de compose, Artillery, Prometheus y Grafana,
y el pipeline `analyze.py` + `decision_matrix.py` con datos sintéticos que **no** se incluyen en el repo.

La **primera ejecución real** del stack fue la integración continua de GitHub Actions
(`.github/workflows/ci.yml`, ejecución verde del 16 de noviembre de 2026 en `ubuntu-latest`):
`docker compose config` de los cuatro archivos, shellcheck, build del backend, `nginx -t`,
backends sin puertos, smoke 10/10/10 con round-robin, cambio a `least_conn`, escalado 3 → 5 con las
réplicas nuevas recibiendo tráfico sin recargar NGINX (`resolve`), escenario `smoke.yml` de Artillery con
contadores `backend.*` y `make analyze`. Los artefactos de esa corrida quedan en la pestaña *Actions*
(artefacto `results-ci`); las pruebas de carga se ejecutan con el workflow `pruebas.yml`, un lote por ejecución.
