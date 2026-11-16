# Resultados de las pruebas mínimas (M-00 … M-06)

Todas las cifras de este documento provienen de archivos en `results/` (regla del proyecto).
Hay dos fuentes:

1. **Corrida rápida en GitHub Actions** (`QUICK=1`, una repetición), versionada completa en
   [`results/ejemplos/lote-test-min-quick-actions/`](../results/ejemplos/lote-test-min-quick-actions/)
   (ejecución `43953413366` del flujo `pruebas.yml`, 16-nov-2026, 28 min).
2. **Corrida completa** (`REPS=3`) en GitHub Actions: pendiente de incorporar al terminar
   (resúmenes en `results/ejemplos/lote-test-min-reps3-actions/`).
3. **Corrida en la máquina del equipo** (WSL2 + Docker Desktop): pendiente; sustituirá o complementará
   las anteriores en el informe.

## Entorno de la corrida rápida

| Dato | Valor (de `metadata.json`) |
|---|---|
| Runner | GitHub Actions `ubuntu-latest`, kernel `7.0.0-1019-azure` |
| CPU / RAM | **2 vCPU** / 7931 MB |
| Docker / Compose | 29.4.2 / 5.1.3 |
| Imágenes | `nginx:1.30-alpine` (NGINX 1.30.6), `artilleryio/artillery:2.0.34`, backend `node:24-alpine` |
| Límites por backend | 0,50 CPU, 256 MB (`BACKEND_CPUS`, `BACKEND_MEMORY`) |
| Calentamiento descartado | 30 s |

**Limitación principal:** con 2 vCPU el generador de carga fue el cuello de botella en todas las
corridas (`bottleneck=artillery` en `resumen.json`: CPU media de Artillery 43–114 %, de NGINX 4–11 %,
de los backends 2–5 %). Los backends nunca se saturaron, así que las comparaciones de latencia entre
algoritmos miden sobre todo el costo fijo del endpoint (`/api/work?ms=20` → p50 = 20,0 ms).

## M-00 · Smoke de despliegue

Fuente: `lote_test-min_20261116-204757.log`, corrida `20261116-204805_M00_round_robin_3b`.

```
Peticiones por nodo (X-Backend-Node):
     10  a397ee21ae65
     10  525cff00d9fe
     10  2f4a34fa714b
  nodos distintos: 3 · fallos: 0
OK smoke superado (3 nodos, 0 fallos, política round_robin)
```

Criterio (3 nodos, 10/10/10, 0 errores, healthchecks healthy): **cumplido**.

## M-01 · Funcionamiento de cada algoritmo con `stub_status`

Fuente: `stub_status.csv` de cada corrida M-05 (sondeo cada 1 s durante `rampa.yml`).

| Política | Requests en la corrida (`stub_requests_total`) | Active connections máx. | Waiting máx. | accepts − handled | Corrida |
|---|---|---|---|---|---|
| round_robin | 274 838 | 45 | 33 | 0 | `20261116-204924_M05_round_robin_3b_rep1` |
| least_conn | 274 838 | 48 | 35 | 0 | `20261116-205934_M05_least_conn_3b_rep1` |
| ip_hash | 274 838 | 43 | 29 | 0 | `20261116-205428_M05_ip_hash_3b_rep1` |

`stub_status` es **global**: muestra la actividad del balanceador (conexiones activas, accepts/handled/
requests, reading/writing/waiting), no el reparto por backend; las tres políticas se ven idénticas
aquí. El reparto por backend sale del log JSON y de los contadores de Artillery (M-06). Las capturas de
pantalla (`docs/capturas/stub_status_<política>.png`) se toman en la demo con el stack local.

## M-02 · Reparto equitativo con round-robin (1000 peticiones secuenciales)

Fuente: `20261116-204854_M02_round_robin_3b_seq1000/conteo_por_nodo.txt` y `resumen.json`.

| Backend | Peticiones | % |
|---|---|---|
| 2f4a34fa714b | 334 | 33,4 |
| a397ee21ae65 | 333 | 33,3 |
| 525cff00d9fe | 333 | 33,3 |

Índice de Jain **1,000** (criterio > 0,99) · diferencia máxima entre backends **0,3 %** (criterio < 2 %) ·
0 fallos. Hipótesis "J ≈ 1 con backends homogéneos": **confirmada**.

## M-03 · Resiliencia: eliminar un backend en caliente

Fuente: `20261116-210440_M03_round_robin_3b_rm` y `20261116-210814_M03_least_conn_3b_rm`
(`resumen.json`, `serie_1s.csv`, `events.csv`); figuras `docs/figuras/resiliencia_M03_round_robin.png`
y `resiliencia_M03_least_conn.png`. Escenario `constante.yml` (100 VU/s × 3 peticiones = 300 req/s,
180 s); `docker rm -f` de la réplica 1 en t ≈ 60 s; `make scale N=3` en t ≈ 120 s.

| Política | Peticiones | Disponibilidad observada | Errores en los 30 s tras la falla | p99 en esos 30 s | Reintentos (`upstream_addr` con coma) | Detección | Reparto tras el calentamiento (log) |
|---|---|---|---|---|---|---|---|
| round_robin | 54 000 | **100,00 %** | **0** | 22,0 ms | 3 | 0,0 s | 18 231 / 18 231 / 2 868 (eliminado) / 5 670 (repuesto) |
| least_conn | 54 000 | **100,00 %** | **0** | 22,0 ms | 3 | 0,0 s | 18 235 / 18 227 / 2 863 (eliminado) / 5 675 (repuesto) |

Lectura: en el instante de la retirada había 3 peticiones en vuelo hacia ese backend; NGINX las
reintentó en otro backend (`proxy_next_upstream`) y el cliente no vio ningún error. El p99 no se movió
(22 ms antes, durante y después). La réplica repuesta recibió tráfico **antes** de que Docker la marcara
*healthy*: `resolve` la incorpora en cuanto el DNS la resuelve (≤ 5 s), sin consultar el healthcheck.
Por eso en esta corrida el tiempo de recuperación no pudo medirse (la réplica nueva ya tenía tráfico
cuando se registró `backend_restored`); los scripts ya registran también `backend_restore_start` para
medirlo en las siguientes corridas.

Hipótesis "errores visibles cero o solo peticiones en vuelo; p99 sube brevemente": **confirmada en la
primera parte y refutada en la segunda** (el p99 no subió: la carga era baja para los backends).
Criterio de éxito (disponibilidad ≥ 99,9 %, redistribución entre los restantes): **cumplido**.

## M-04 · 1000 usuarios concurrentes durante 60 s

Fuente: `20261116-211150_M04_round_robin_3b_rep1/resumen.json`, `serie_artillery_10s.csv`;
figura `docs/figuras/usuarios_activos_M04.png`.

| Métrica | Valor |
|---|---|
| vusers created / completed / failed | 1000 / 1000 / **0** |
| Usuarios activos máximos | **1000** |
| Meseta ≥ 900 usuarios activos | **60 s** (t = 10 s a 70 s) |
| Peticiones (todas HTTP 200) | 70 000 |
| Latencia Artillery p95 / p99 | 32,8 ms / 44,3 ms |
| Latencia NGINX (log) p99 | 23,0 ms |
| Umbral `ensure` p99 < 2000 ms | cumplido (Artillery exit 0) |
| CPU media artillery / lb / backend | 43 % / 9,7 % / 4,4 % |

Contraste con el modelo abierto (`20261116-211340_M04b_round_robin_3b`, 1000 llegadas/s × 60 s, una
petición cada una): 60 000 peticiones a 999 req/s, usuarios activos máximos **22**, p99 25,8 ms,
CPU de Artillery 114 %. Explica la ley de Little: con la misma "cifra 1000", L = λ·W da ~1000 usuarios
concurrentes cuando cada sesión dura ~70 s (M-04) y solo ~22 cuando dura ~22 ms (M-04b).

## M-05 · Latencia media y p99 por algoritmo (rampa.yml)

Fuente: `resumen_corridas.csv` (test_id = M05, **una repetición** en la corrida rápida);
figura `docs/figuras/algoritmos_latencia_M05.png`. Media ± desviación con 3 repeticiones: pendiente
de la corrida `REPS=3`.

| Política | Peticiones | Throughput tras calentamiento (log) | Media (log / Artillery) | p99 (log / Artillery) | Errores | Jain | % al backend más cargado |
|---|---|---|---|---|---|---|---|
| round_robin | 274 510 | 1137 req/s | 20,1 / 20,4 ms | 22,0 / 25,8 ms | 0 | **1,000** | 33,3 % |
| least_conn | 274 510 | 1138 req/s | 20,2 / 20,5 ms | 22,0 / 24,8 ms | 0 | **1,000** | 33,3 % |
| ip_hash | 274 510 | 1138 req/s | 20,1 / 20,4 ms | 22,0 / 23,8 ms | 0 | **0,333** | **100 %** |

Significancia (`significancia.txt`): con una sola repetición no se puede evaluar; las diferencias de p99
en el log (todas 22,0 ms) son nulas. Hipótesis "round_robin ≈ least_conn": **confirmada**. Hipótesis
"ip_hash peor por concentrar tráfico": **refutada en latencia** (un solo backend con 0,5 CPU bastó para
~1138 req/s de 20 ms de espera) pero **confirmada en distribución** (100 % a un backend, Jain 0,333).

## M-06 · Distribución real por backend desde los logs

Fuente: `distribucion_backend.csv` de cada corrida M-05; figura `docs/figuras/algoritmos_distribucion_M05.png`.

| Política | Backend | Peticiones (log, corrida completa) | % | Peticiones (Artillery) |
|---|---|---|---|---|
| round_robin | 3 réplicas | 91 503 / 91 504 / 91 503 | 33,33 / 33,33 / 33,33 | idénticas (latencia media por réplica 20,12–20,13 ms) |
| least_conn | 3 réplicas | 91 488 / 91 540 / 91 482 | 33,33 / 33,35 / 33,33 | idénticas (20,15–20,16 ms) |
| ip_hash | 1 réplica (2f4a34fa714b) | 274 510 | 100 | idéntica (20,10 ms) |

Diferencia log de NGINX vs contadores `backend.*` de Artillery: **0,00 %** en las 8 corridas con
Artillery (`diff_log_vs_artillery_pct`). Tasa de reintentos: 0 en todas salvo M-03 (3 reintentos
= las peticiones en vuelo al retirar el backend).

Sobre `ip_hash`: Artillery y NGINX comparten la red Docker `lbnginx_frontend` (`172.19.0.0/16`); todas
las peticiones llegan desde `172.19.0.3`, e `ip_hash` usa los tres primeros octetos, así que toda la
carga cae en un backend. No es un error del proyecto sino el hallazgo E-05: la afinidad por cliente
debe hacerse en L7 (`hash $http_x_client_id consistent`).

## Cuello de botella observado y limitaciones

- `bottleneck = artillery` en todas las corridas (CPU media 43–114 %); NGINX ≤ 11 %; backends ≤ 5 %.
- Artillery no emitió advertencias de CPU alta en `rampa.yml`; en `p04b-abierto.yml` (1000 llegadas/s)
  su CPU superó el 100 % de un núcleo.
- El runner tiene 2 vCPU: las cifras de throughput son un **límite del generador**, no del balanceador.
  Las pruebas en la máquina del equipo (más núcleos) deben repetir M-05 con `REPS=3` y E-02/E-13 para
  caracterizar la capacidad real.
