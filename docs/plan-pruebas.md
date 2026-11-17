# Plan de pruebas

Cada prueba indica objetivo, hipótesis, procedimiento (comando), métricas, criterio de éxito y
evidencia. Las hipótesis son predicciones a contrastar: si los datos las refutan, se reporta tal cual
y se explica (eso también suma en la rúbrica). Toda cifra sale de `results/`.

## Metodología (sección 8 de la especificación)

| Tipo | Variables |
|---|---|
| Independientes | política de balanceo; número de backends; tipo y momento de la falla; timeouts y reintentos; keepalive; perfil de carga |
| Dependientes | latencia (media, mediana, p95, p99, máx.); throughput; tasa de error y códigos; distribución por backend (Jain, CV); reintentos; tiempo de detección y recuperación; CPU/RAM por contenedor; `stub_status` |
| Controladas | hardware y recursos de Docker; `BACKEND_CPUS=0.50`, `BACKEND_MEMORY=256M`; versiones de imágenes; escenario y endpoint; portátil conectado; aplicaciones pesadas cerradas |

Reglas: calentamiento de 30 s descartado; ≥ 3 repeticiones (2 si la prueba dura > 5 min);
orden aleatorio; 20 s de enfriamiento; `lb` recreado al cambiar de política; significancia práctica
(diferencia < desviación ⇒ "no distinguible"); registrar el cuello de botella con `docker_stats.csv`.

## Pruebas mínimas (prioridad A)

| ID | Prueba | Comando | Hipótesis | Éxito | Evidencia |
|---|---|---|---|---|---|
| M-00 | Smoke de despliegue | `make up && make smoke` | 3 nodos, 10/10/10, 0 errores | healthchecks healthy, 3 nodos | salida en README, captura navegador |
| M-01 | Cada algoritmo con `stub_status` | `make test-min` (captura `stub_status.csv` por corrida) + `make capturas` (capturas de `stub_status` y Grafana bajo carga, con navegador sin interfaz) | `stub_status` es global: muestra actividad, no reparto; el reparto sale de logs/Artillery | una captura por algoritmo + tabla de distribución | `docs/capturas/stub_status_<política>.png`, `stub_status.csv` |
| M-02 | Reparto equitativo con round-robin | `make test-seq` | J ≈ 1 con backends homogéneos | diferencia < 2 %, J > 0,99 | `results/*_M02_*/conteo_por_nodo.txt` |
| M-03 | Resiliencia: eliminar un backend en caliente | `make test-resiliencia P=round_robin` (y `least_conn`) | gracias a `proxy_next_upstream` los errores visibles son cero o solo peticiones en vuelo; p99 sube brevemente | disponibilidad ≥ 99,9 %; redistribución entre los restantes | `docs/figuras/resiliencia_*.png`, `resumen.json` (`detect_s_*`, `recover_s_*`) |
| M-04 | 1000 usuarios concurrentes 60 s | `make test-min` (M04 ×3 + M04b) | meseta de ~1000 VU activos (Little); `vusers.failed = 0`; p99 < 2000 ms | `ensure` cumplido | `docs/figuras/usuarios_activos_*.png`, `resumen.json` |
| M-05 | Media y p99: round_robin vs least_conn vs ip_hash | `make test-min` (rampa ×3 por política, orden aleatorio) | round_robin ≈ least_conn; ip_hash peor por concentrar tráfico | tabla media ± desv. | `docs/figuras/algoritmos_latencia_M05.png`, `resumen_comparativo.csv`, `significancia.txt` |
| M-06 | Distribución real desde los logs | `make analyze` sobre M-05 | log NGINX y contadores de Artillery coinciden | `diff_log_vs_artillery` ≈ 0 | `distribucion_backend.csv`, `docs/figuras/algoritmos_distribucion_M05.png` |

## Pruebas extendidas (prioridad B)

| ID | Prueba | Comando | Qué demuestra |
|---|---|---|---|
| E-01 | Línea base sin balanceo efectivo (1 backend) | `make test-escalabilidad` (N=1) | punto de partida para cuantificar la ganancia |
| E-02 | Escalabilidad horizontal N = 1, 2, 3, 5, 7 | `make test-escalabilidad` | curva throughput/p95 vs N, eficiencia de escalado, saturación del host (`docs/figuras/escalabilidad.png`) |
| E-03 | Backends heterogéneos (uno lento) | `make test-ext E=E03` | dónde difieren los algoritmos: least_conn y random_two protegen la cola; round-robin ponderado 3:1 |
| E-04 | Costo variable (`/api/mixed`) | `make test-ext E=E04` | colas largas en round_robin vs least_conn |
| E-05 | Trampa de ip_hash vs afinidad L7 | `make test-ext E=E05` | ip_hash concentra 100 % (misma /24); hash_client reparte y mantiene afinidad (≈ 0 cambios de backend) |
| E-06 | Hash consistente al quitar un nodo (5 → 4) | `make test-ext E=E06` | consistente remapea ~1/N de los clientes; ip_hash casi todos |
| E-07 | Modos de falla bajo carga | `make test-ext E=E07` | tabla falla → errores, p99, detección, recuperación; caída (conexión rechazada) vs cuelgue (timeout); `error500` no se reintenta por defecto |
| E-08 | Timeouts × reintentos bajo `hang` | `make test-ext E=E08` | compromiso latencia/errores; justifica 2s/10s/3 reintentos |
| E-09 | Falla múltiple y total | `make test-ext E=E09` | degradación gradual, página de mantenimiento (502), recuperación automática |
| E-10 | Escalado en caliente 3 → 6 → 2 | `make test-ext E=E10` | réplicas nuevas reciben tráfico sin recargar (`resolve`); errores en scale-in |
| E-11 | Recarga de configuración bajo carga | `make test-ext E=E11` | `nginx -s reload` elegante, sin errores |
| E-12 | Keepalive hacia upstream on/off | `make test-ext E=E12` | impacto de reutilizar conexiones en latencia y CPU |
| E-13 | Punto de quiebre N = 1, 3, 5 | `make test-quiebre` | carga máxima con error < 1 % y p99 < 1 s (`docs/figuras/quiebre.png`); limitación del generador |
| E-14 | Pico súbito | `make test-ext E=E14` | ráfaga 50 → 800 VU/s y tiempo de normalización |
| E-15 | Resistencia 15 min | `make test-ext E=E15` | estabilidad de latencia y memoria |

## Mejoras avanzadas implementadas (prioridad C)

| ID | Mejora | Cómo probarla |
|---|---|---|
| A-01 | Limitación de tasa (`limit_req`/`limit_conn` por `X-Client-Id`) | `make feature F=ratelimit` + `docker compose run --rm artillery run /scripts/scenarios/spike.yml` → contar `http.codes.429` |
| A-02 | Microcaché de 1 s | `make feature F=microcache` + rampa con `WORK_PATH=/api/info` → `cache.HIT` vs `cache.MISS` en Artillery, throughput |
| A-05 | Comparativa con HAProxy | `make haproxy-up` + `TARGET=http://haproxy scripts/run-test.sh A05 rampa.yml` (roundrobin/leastconn/source) → datos para C1 de la matriz 4.1 |
| A-06 | Integración continua | `.github/workflows/ci.yml` |
| A-03 / A-04 | TLS + HTTP/2; alta disponibilidad del balanceador (keepalived/VRRP) | documentadas como trabajo futuro |

## Matriz de corridas y tiempo estimado

| Bloque | Corridas | Duración aprox. |
|---|---|---|
| M-00 a M-06 (`make test-min`) | 3 políticas × 3 reps (rampa 4,5 min) + 3 reps M-04 + M-04b + 2 resiliencia + smoke | ≈ 1 h |
| E-02 + E-13 | 5 valores de N × 2 reps + quiebre × 3 | ≈ 1 h |
| E-03 a E-06 | 4 políticas × 2 reps × 2 escenarios | ≈ 1 h |
| E-07 a E-11 | ≈ 12 corridas de 3 min | ≈ 45 min |
| E-12, E-14, E-15 | ≈ 6 corridas | ≈ 40 min |
