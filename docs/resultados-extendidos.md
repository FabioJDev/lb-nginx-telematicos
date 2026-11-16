# Resultados de las pruebas extendidas (E-xx) y avanzadas (A-xx)

> **Estado: PENDIENTE DE EJECUCIÓN.** Se completa solo con cifras de `results/`
> (`make test-escalabilidad`, `make test-quiebre`, `make test-ext E=…`, `make analyze`).

## E-01 / E-02 · Línea base y escalabilidad horizontal

Fuente: `results/resumen_comparativo.csv` (E01, E02); figura `docs/figuras/escalabilidad.png`.

| N backends | Throughput (req/s) ± desv. | p95 (ms) | p99 (ms) | Errores (%) | Eficiencia Throughput(N)/(N·T(1)) | CPU backends / lb / artillery (%) |
|---|---|---|---|---|---|---|
| 1 | | | | | 1,00 | |
| 2 | | | | | | |
| 3 | | | | | | |
| 5 | | | | | | |
| 7 | | | | | | |

¿Dónde se satura el host? ___

## E-03 · Backends heterogéneos (uno lento: 150 ms, 0,25 CPU)

Fuente: `resumen_comparativo.csv` (E03); figura `docs/figuras/algoritmos_latencia_E03.png`.

| Configuración | p99 (ms) ± desv. | Media (ms) | % al backend lento | Jain |
|---|---|---|---|---|
| round_robin (1:1) | | | | |
| least_conn | | | | |
| random_two | | | | |
| round_robin ponderado 3:1 | | | | |

Hipótesis "least_conn y random_two protegen la cola de latencia": ___.

## E-04 · Peticiones de costo variable (`/api/mixed`)

| Política | p99 (ms) | Media (ms) | Jain |
|---|---|---|---|
| round_robin | | | |
| least_conn | | | |
| random_two | | | |

## E-05 · Trampa de ip_hash y afinidad L7

| Política | % al backend más cargado (`ng_max_share`) | Jain | Afinidad (% clientes en un solo backend) | Cambios de backend (Artillery) |
|---|---|---|---|---|
| ip_hash | | | | |
| hash_client | | | | |
| hash_remote_addr | | | | |

Explicación: ip_hash usa los tres primeros octetos IPv4; el contenedor de Artillery y NGINX comparten la
`/24` de Docker → ___.

## E-06 · Hash consistente al quitar un nodo (5 → 4)

| Política | % de clientes que cambiaron de backend tras la retirada | Esperado |
|---|---|---|
| hash_client (consistente) | | ≈ 1/5 = 20 % |
| ip_hash | | la mayoría |

## E-07 · Modos de falla bajo carga constante

Fuente: `results/<…>_E07_round_robin_3b_<acción>/resumen.json`; figuras `docs/figuras/resiliencia_*E07*.png`.

| Falla | Errores al cliente (30 s) | p99 (30 s, ms) | Detección (s) | Recuperación (s) | Reintentos | Observación |
|---|---|---|---|---|---|---|
| stop (SIGTERM) | | | | | | apagado elegante |
| kill (SIGKILL) | | | | | | restart automático |
| pause | | | | | | timeout, no rechazo |
| crash (exit 1) | | | | | | restart automático |
| fault:error500 | | | | | | 500 no se reintenta por defecto |
| fault:slow | | | | | | |
| fault:hang | | | | | | proxy_read_timeout |

## E-08 · Timeouts × reintentos bajo `hang`

| read_timeout | next_upstream | Errores (%) | p99 (ms) | Conclusión |
|---|---|---|---|---|
| 3 s | on | | | |
| 3 s | off | | | |
| 10 s | on | | | |
| 10 s | off | | | |

## E-09 · Falla múltiple y total

Secuencia (events.csv): 3 → 2 → 1 → 0 backends → scale 3. Errores por fase, página de mantenimiento
(502) observada: ___, recuperación automática: ___.

## E-10 · Escalado en caliente (3 → 6 → 2)

Tiempo hasta que las réplicas nuevas reciben tráfico (`recover_s_scaled`): ___ s (sin recargar NGINX).
Errores en el scale-in: ___.

## E-11 · Recarga de configuración bajo carga

Errores alrededor de `nginx -s reload`: ___ (esperado: 0).

## E-12 · Keepalive hacia upstream

| keepalive | p99 (ms) | Media (ms) | CPU lb (%) | CPU backends (%) |
|---|---|---|---|---|
| on | | | | |
| off | | | | |

## E-13 · Punto de quiebre

Fuente: `resumen.json` (`break_max_rps_ok`, `break_first_fail_rps`); figura `docs/figuras/quiebre.png`.

| N | Carga máx. con error < 1 % y p99 < 1 s (req/s) | Primera tasa que falla | Cuello de botella |
|---|---|---|---|
| 1 | | | |
| 3 | | | |
| 5 | | | |

## E-14 · Pico súbito / E-15 · Resistencia

- E-14: p99 durante el pico ___ ms; tiempo hasta volver a la base ___ s.
- E-15: p99 primeros 5 min ___ ms vs últimos 5 min ___ ms; memoria lb/backends inicio → fin ___.

## A-01 / A-02 / A-05

- A-01 ratelimit: respuestas 429 en `spike.yml`: ___.
- A-02 microcaché: HIT ___ / MISS ___; throughput con vs sin caché ___.
- A-05 HAProxy: p99 y throughput en `rampa.yml` (roundrobin / leastconn / source) vs NGINX: ___ → C1 de la matriz 4.1.
