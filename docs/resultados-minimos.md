# Resultados de las pruebas mínimas (M-00 … M-06)

Todas las cifras provienen de archivos en `results/` (regla del proyecto).

| Lote | Repeticiones | Carpeta | Ejecución de Actions |
|---|---|---|---|
| **test-min completo (fuente principal)** | **3** | [`results/ejemplos/lote-test-min-reps3-actions/`](../results/ejemplos/lote-test-min-reps3-actions/) | 43958910350 |
| test-min rápido (validación del lote) | 1 | [`results/ejemplos/lote-test-min-quick-actions/`](../results/ejemplos/lote-test-min-quick-actions/) | 43953413366 |

Ambos dieron resultados coincidentes. Pendiente: repetir en la máquina del equipo (WSL2 + Docker
Desktop) para el informe final; esas corridas complementarán estas.

## Entorno

| Dato | Valor (de `metadata.json`) |
|---|---|
| Runner | GitHub Actions `ubuntu-latest`, kernel `7.0.0-1019-azure` |
| CPU / RAM | **2 vCPU** / 7931 MB |
| Docker / Compose | 29.4.2 / 5.1.3 |
| Imágenes | `nginx:1.30-alpine` (NGINX 1.30.6), `artilleryio/artillery:2.0.34`, backend `node:24-alpine` |
| Backends | 3 réplicas, 0,50 CPU y 256 MB cada una; endpoint `/api/work?ms=20` (espera 20 ms sin consumir CPU) |
| Metodología | 30 s de calentamiento descartados, orden aleatorio de políticas, 20 s de enfriamiento, `lb` recreado al cambiar de política |

**Limitación principal:** con 2 vCPU el generador de carga fue el cuello de botella (`bottleneck =
artillery`; CPU media de Artillery 55–105 %, NGINX ≤ 14 %, backends ≤ 7 %). Los backends nunca se
saturaron con este endpoint, así que las pruebas mínimas miden **corrección y resiliencia**, no
capacidad. La capacidad se mide en E-02/E-13 con un endpoint que consume CPU
(`docs/resultados-extendidos.md`).

## M-00 · Smoke de despliegue

Fuente: `lote_test-min_*.log` de ambos lotes.

```
Peticiones por nodo (X-Backend-Node):
     10  a397ee21ae65
     10  525cff00d9fe
     10  2f4a34fa714b
  nodos distintos: 3 · fallos: 0
OK smoke superado (3 nodos, 0 fallos, política round_robin)
```

Criterio (3 nodos, 10/10/10, 0 errores, healthchecks healthy): **cumplido** en los dos lotes.

## M-01 · Funcionamiento de cada algoritmo con `stub_status`

Fuente: `stub_status.csv` de cada corrida M-05 (sondeo cada 1 s durante `rampa.yml`).

| Política | Requests por corrida (`stub_requests_total`) | Active connections máx. (3 reps) | Waiting máx. (3 reps) | accepts − handled |
|---|---|---|---|---|
| round_robin | 274 838 | 61 / 63 / 62 | 48 / 44 / 41 | 0 |
| least_conn | 274 839 / 274 839 / 274 838 | 70 / 71 / 68 | 51 / 58 / 40 | 0 |
| ip_hash | 274 839 / 274 838 / 274 838 | 59 / 70 / 62 | 37 / 56 / 46 | 0 |

`stub_status` es **global**: muestra actividad del balanceador, no reparto por backend, y por eso las
tres políticas se ven casi idénticas. `accepts − handled = 0` confirma que NGINX no rechazó ninguna
conexión (no se agotaron `worker_connections` ni descriptores). El reparto por backend sale del log JSON
y de los contadores de Artillery (M-06). Las capturas de pantalla se toman en la demo local.

## M-02 · Reparto equitativo con round-robin (1000 peticiones secuenciales)

Fuente: `*_M02_round_robin_3b_seq1000/conteo_por_nodo.txt` (ambos lotes).

| Backend | Peticiones | % |
|---|---|---|
| nodo 1 | 334 | 33,4 |
| nodo 2 | 333 | 33,3 |
| nodo 3 | 333 | 33,3 |

Índice de Jain **1,000** (criterio > 0,99) · diferencia máxima **0,3 %** (criterio < 2 %) · 0 fallos.
Hipótesis "J ≈ 1 con backends homogéneos": **confirmada**.

## M-03 · Resiliencia: eliminar un backend en caliente

Fuente: `*_M03_round_robin_3b_rm` y `*_M03_least_conn_3b_rm` (`resumen.json`, `serie_1s.csv`,
`events.csv`); figuras `docs/figuras/resiliencia_M03_round_robin.png` y `resiliencia_M03_least_conn.png`.
Escenario `constante.yml` (300 req/s, 180 s); `docker rm -f` de una réplica en t ≈ 60 s; reposición
con `make scale N=3` en t ≈ 120 s. Resultados idénticos en los dos lotes.

| Política | Peticiones | Disponibilidad observada | Errores en los 30 s tras la falla | p99 en esos 30 s | Reintentos | Reparto (log, tras calentamiento) |
|---|---|---|---|---|---|---|
| round_robin | 54 000 | **100,000 %** | **0** | 22 ms | 3 | 18 217 / 18 216 / 2 770 (retirado) / 5 796 (repuesto) |
| least_conn | 54 000 | **100,000 %** | **0** | 22 ms | 3 | 18 235 / 18 205 / 2 768 (retirado) / 5 791 (repuesto) |

Lectura: en el instante de la retirada había 3 peticiones en vuelo hacia ese backend; NGINX las
reintentó en otro (`proxy_next_upstream`) y el cliente no vio ningún error. El p99 no se movió. La
réplica repuesta recibió tráfico **antes** de que Docker la marcara *healthy* (hallazgo H-3 en
`docs/hallazgos.md`): `resolve` la incorpora en cuanto el DNS de Docker la resuelve.

Hipótesis "errores visibles cero o solo peticiones en vuelo; p99 sube brevemente": **confirmada en la
primera parte, refutada en la segunda** (el p99 no subió porque los backends tenían holgura).
Criterio (disponibilidad ≥ 99,9 % y redistribución entre los restantes): **cumplido**.

## M-04 · 1000 usuarios concurrentes durante 60 s

Fuente: `*_M04_round_robin_3b_rep{1,2,3}/resumen.json` y `serie_artillery_10s.csv`;
figura `docs/figuras/usuarios_activos_M04.png`.

| Rep. | vusers creados / completados / fallidos | Activos máx. | Meseta de 1000 activos | Peticiones (HTTP 200) | Artillery p95 / p99 | NGINX p99 | CPU Artillery / lb / backends |
|---|---|---|---|---|---|---|---|
| 1 | 1000 / 1000 / **0** | 1000 | **60 s** | 70 000 | 47,0 / 74,4 ms | 23 ms | 56 % / 13 % / 5 % |
| 2 | 1000 / 1000 / **0** | 1000 | **60 s** | 70 000 | 43,4 / 76,0 ms | 24 ms | 55 % / 14 % / 5 % |
| 3 | 1000 / 1000 / **0** | 1000 | **60 s** | 70 000 | 40,0 / 63,4 ms | 22 ms | 58 % / 13 % / 5 % |

Umbral `ensure` (p99 < 2000 ms): cumplido en las 3 (exit 0). La diferencia entre el p99 de Artillery
(63–76 ms) y el de NGINX (22–24 ms) es tiempo pasado **en el cliente** (cola de eventos de Node.js con
1000 usuarios simultáneos en 2 vCPU), no en el balanceador.

Contraste con el modelo abierto (`*_M04b_round_robin_3b`, 1000 llegadas/s × 60 s, una petición cada
una): 60 000 peticiones sin fallos, usuarios activos máximos **23**, p99 29,1 ms. Ley de Little:
con la misma "cifra 1000", L = λ·W da ~1000 concurrentes cuando cada sesión dura ~70 s (M-04) y ~23
cuando dura ~23 ms (M-04b).

## M-05 · Latencia media y p99 por algoritmo (rampa.yml, 3 repeticiones, orden aleatorio)

Fuente: `resumen_comparativo.csv` y `significancia.txt` del lote completo;
figura `docs/figuras/algoritmos_latencia_M05.png`.

| Política | Peticiones por rep. | Goodput (req/s) | Media NGINX (ms) | p99 NGINX (ms) | p99 Artillery (ms) | Errores | Jain |
|---|---|---|---|---|---|---|---|
| round_robin | 274 510 | 1137,2 ± 0,1 | **20,30 ± 0,02** | **22,0 ± 0,0** | 35,0 ± 1,1 | 0 | 1,000 |
| least_conn | 274 510 | 1137,2 ± 0,1 | **20,35 ± 0,01** | **22,0 ± 0,0** | 35,5 ± 1,2 | 0 | 1,000 |
| ip_hash | 274 510 | 1137,3 ± 0,1 | **20,33 ± 0,02** | **22,3 ± 0,6** | 34,6 ± 0,4 | 0 | **0,333** |

Significancia práctica (`significancia.txt`): la diferencia de p99 entre la mejor y la segunda política
es 0,0 ms → **NO distinguibles**. Hipótesis "round_robin ≈ least_conn": **confirmada**. Hipótesis
"ip_hash peor por concentrar tráfico": **refutada en latencia** (un solo backend con 0,5 CPU basta para
1137 req/s de una espera de 20 ms) y **confirmada en distribución** (100 % a un backend).

## M-06 · Distribución real por backend desde los logs

Fuente: `distribucion_backend.csv` de cada corrida M-05; figura `docs/figuras/algoritmos_distribucion_M05.png`.

| Política (rep. 1) | Peticiones por backend (log de NGINX, corrida completa) | % | Contadores de Artillery |
|---|---|---|---|
| round_robin | 91 504 / 91 503 / 91 503 | 33,33 / 33,33 / 33,33 | idénticos |
| least_conn | 91 519 / 91 473 / 91 518 | 33,34 / 33,32 / 33,34 | idénticos |
| ip_hash | 274 510 / 0 / 0 | 100 / 0 / 0 | idénticos |

Diferencia log de NGINX vs contadores `backend.*` de Artillery: **0,00 %** en todas las corridas
(`diff_log_vs_artillery_pct`). Tasa de reintentos: 0 en M-05; 3 en cada M-03.

Sobre `ip_hash`: Artillery llega desde una sola IP de la red `lbnginx_frontend`, e `ip_hash` usa los tres
primeros octetos de IPv4, así que toda la carga cae en un backend. Es el hallazgo esperado de E-05,
no un error: la afinidad por cliente debe hacerse en L7 (`hash $http_x_client_id`).

## Resumen de cumplimiento

| Prueba | Criterio | Resultado |
|---|---|---|
| M-00 | 3 nodos, reparto 10/10/10, 0 errores | cumplido |
| M-01 | captura de `stub_status` por algoritmo | `stub_status.csv` por corrida; capturas de pantalla en la demo |
| M-02 | Jain > 0,99 y diferencia < 2 % | 1,000 y 0,3 % |
| M-03 | disponibilidad ≥ 99,9 % | 100 %, 0 errores, 3 reintentos |
| M-04 | 1000 concurrentes 60 s, `vusers.failed = 0`, p99 < 2 s | 3/3 repeticiones: meseta de 1000 durante 60 s, 0 fallidos, p99 ≤ 76 ms |
| M-05 | media y p99 por algoritmo con media ± desv. | no distinguibles (p99 22 ms) |
| M-06 | distribución real desde los logs | coincide al 100 % con Artillery; ip_hash 100 % a un nodo |
