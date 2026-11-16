# Resultados de las pruebas mínimas (M-00 … M-06)

> **Estado: PENDIENTE DE EJECUCIÓN.** Este documento se completa únicamente con cifras que
> existan en `results/` (generadas por `make test-min` y `make analyze`). Las secciones indican de
> qué archivo sale cada valor. No se escribe ninguna cifra estimada.

Máquina de pruebas: ver `docs/entorno.md` y el campo `host` de `metadata.json`.
Lote ejecutado: `results/lote_test-min_<fecha>.log`.

## M-00 · Smoke de despliegue

- Comando: `make up && make smoke`
- Resultado: ___ nodos distintos, reparto __/__/__, __ fallos. (Pegar la salida.)
- Captura del navegador: `docs/capturas/navegador_round_robin.png`.

## M-01 · Funcionamiento de cada algoritmo con `stub_status`

| Política | Captura | Active connections (máx.) | Requests en la corrida | Waiting (máx.) | Corrida |
|---|---|---|---|---|---|
| round_robin | `docs/capturas/stub_status_round_robin.png` | `stub_active_max` | `stub_requests_total` | `stub_waiting_max` | `results/<…>_M05_round_robin_3b_rep1` |
| least_conn | `docs/capturas/stub_status_least_conn.png` | | | | |
| ip_hash | `docs/capturas/stub_status_ip_hash.png` | | | | |

Nota para la sustentación: `stub_status` es **global** (conexiones activas, accepts/handled/requests,
reading/writing/waiting); no muestra peticiones por backend. Por eso se acompaña de la distribución
por backend obtenida del log JSON y de los contadores `backend.*` de Artillery (M-06).

## M-02 · Reparto equitativo con round-robin (1000 peticiones secuenciales)

Fuente: `results/<…>_M02_round_robin_3b_seq1000/conteo_por_nodo.txt` y `resumen.json`.

| Backend | Peticiones | % |
|---|---|---|
| | | |

Índice de Jain: ___ (criterio: > 0,99). Diferencia máxima entre backends: ___ % (criterio: < 2 %).
Hipótesis "J ≈ 1 con backends homogéneos": confirmada / refutada.

## M-03 · Resiliencia: eliminar un backend en caliente

Fuente: `results/<…>_M03_<política>_3b_rm/resumen.json`, `serie_1s.csv`, `events.csv`;
figura `docs/figuras/resiliencia_<…>.png`.

| Política | Disponibilidad observada | Errores en los 30 s tras la falla | p99 en esos 30 s (ms) | Tiempo de detección (s) | Tiempo de recuperación (s) | Reintentos |
|---|---|---|---|---|---|---|
| round_robin | `ng_availability` | `errors_30s_after_backend_removed` | `p99_30s_after_backend_removed_ms` | `detect_s_backend_removed` | `recover_s_backend_restored` | `ng_retries` |
| least_conn | | | | | | |

Hipótesis "errores visibles cero o solo peticiones en vuelo; p99 sube brevemente": ___.
Criterio de éxito: disponibilidad ≥ 99,9 % y redistribución entre los backends restantes.

## M-04 · 1000 usuarios concurrentes durante 60 s

Fuente: `results/<…>_M04_<política>_3b_rep{1,2,3}/resumen.json` y `serie_artillery_10s.csv`;
figura `docs/figuras/usuarios_activos_<…>.png`.

| Rep. | vusers created / completed / failed | Usuarios activos máx. | Meseta ≥ 900 (s) | Peticiones | p95 (ms) | p99 (ms) | Códigos no-2xx | Artillery exit |
|---|---|---|---|---|---|---|---|---|
| 1 | | `vusers_active_max` | `vusers_plateau_s` | `art_requests` | `art_lat_p95` | `art_lat_p99` | `art_non2xx` | `artillery_exit` |
| 2 | | | | | | | | |
| 3 | | | | | | | | |

Contraste con el modelo abierto (`M04b`, 1000 llegadas/s × 60 s, una petición cada una): ___
peticiones, p99 ___ ms, usuarios activos máx. ___. Explicación (ley de Little): ___.

CPU durante la prueba (`docker_stats.csv`): backends ___ %, lb ___ %, artillery ___ % → cuello de botella: ___.

## M-05 · Latencia media y p99 por algoritmo (rampa.yml, 3 repeticiones)

Fuente: `results/resumen_comparativo.csv` (test_id = M05) y `results/significancia.txt`;
figura `docs/figuras/algoritmos_latencia_M05.png`.

| Política | Media (ms) ± desv. | p99 (ms) ± desv. | Throughput (req/s) | Errores (%) | Jain |
|---|---|---|---|---|---|
| round_robin | | | | | |
| least_conn | | | | | |
| ip_hash | | | | | |

Significancia práctica (`significancia.txt`): ___.
Hipótesis "round_robin ≈ least_conn; ip_hash peor por concentrar tráfico": ___.

## M-06 · Distribución real por backend desde los logs

Fuente: `results/<…>_M05_*/distribucion_backend.csv`; figura `docs/figuras/algoritmos_distribucion_M05.png`.

| Política | Backend | Peticiones (log) | % | Peticiones (Artillery) | Latencia media (ms) |
|---|---|---|---|---|---|
| | | | | | |

Diferencia log vs Artillery (`diff_log_vs_artillery_pct`): ___ %. Reintentos (`ng_retry_rate`): ___ %.

## Cuello de botella observado y limitaciones

- Quién saturó primero según `docker_stats.csv` (`bottleneck` en `resumen.json`): ___.
- Advertencias de CPU de Artillery: sí / no.
- Un solo host comparte CPU entre generador, balanceador y backends: ___.
