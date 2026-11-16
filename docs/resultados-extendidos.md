# Resultados de las pruebas extendidas (E-xx) y avanzadas (A-xx)

Todas las cifras provienen de `results/` (regla del proyecto). Las corridas se ejecutaron con el
flujo `pruebas.yml` en **GitHub Actions** (`ubuntu-latest`, 2 vCPU, 7,9 GB; NGINX 1.30.6; Artillery
2.0.34; backends con 0,5 CPU y 256 MB) el 16-nov-2026. Los resúmenes por corrida (`metadata.json`,
`resumen.json`, `distribucion_backend.csv`, `serie_1s.csv`, `events.csv`, `stub_status.csv`,
`docker_stats.csv`, `artillery.json`, figuras) están versionados en `results/ejemplos/lote-*-actions/`;
los logs JSON crudos de NGINX (hasta 130 MB por lote) quedan en los artefactos de Actions (90 días).

**Limitación transversal:** con 2 vCPU el generador de carga fue el cuello de botella en todas las
corridas (`bottleneck = artillery`, CPU media 63–69 %). Las comparaciones entre políticas son válidas
porque todas recibieron exactamente la misma carga (274 510 peticiones en `rampa.yml`), pero las
cifras de capacidad (E-02, E-13) miden el límite del generador, no del balanceador; por eso E-02 y
E-13 se repitieron con un endpoint que consume CPU (`/api/work?ms=20&cpu=3`).

## E-03 · Backends heterogéneos (3 rápidos + 1 lento con 150 ms y 0,25 CPU)

Fuente: `results/ejemplos/lote-E03-actions/` (ejecución 43958941819; `compose.weighted.yml`,
`rampa.yml`, 2 repeticiones por configuración, orden aleatorio);
figuras `docs/figuras/algoritmos_latencia_E03.png` y `algoritmos_distribucion_E03.png`.

| Configuración | Media (ms) ± desv. | p95 (ms) | p99 (ms) | % al backend lento | Jain (4 nodos) | Latencia media del lento |
|---|---|---|---|---|---|---|
| round_robin (1:1:1:1) | **58,2 ± 0,1** | 171 | 173 | 25,0 % (68 256 / 273 018) | 1,000 | 171,6 ms |
| round_robin ponderado 3:1 | 35,5 ± 0,0 | 171 | 172 | 10,0 % (27 302) | 0,893 | 170,8 ms |
| least_conn | **27,1 ± 0,0** | **23** | 171 | 4,5 % (12 170) | 0,816 | 170,8 ms |
| random_two (least_conn) | 27,9 ± 0,1 | 25,5 ± 2,1 | 171 | 4,9 % (13 425) | 0,823 | 170,9 ms |

Lectura: round-robin reparte por turnos e ignora que un nodo tarda 8 veces más, así que el 25 % de
las peticiones pagan 170 ms y la **media se duplica** (58 vs 27 ms) y el **p95 pasa de 23 a 171 ms**.
`least_conn` y `random_two` observan las conexiones activas: el nodo lento acumula conexiones y
recibe solo ~4,5–5 % del tráfico, lo que protege la media y el p95; el p99 sigue en 171 ms porque
ese ~5 % de peticiones sigue existiendo. El round-robin ponderado 3:1 es un término medio (10 % al
lento) y exige conocer de antemano la capacidad de cada nodo. Diferencia least_conn vs random_two:
0,8 ms en la media con desviaciones ≤ 0,1 ms → distinguible pero operativamente irrelevante.

Hipótesis "least_conn y random_two protegen la cola de latencia": **confirmada** (media y p95);
el p99 no, porque la cola la define el propio backend lento.

## E-07 · Modos de falla bajo carga constante (300 req/s, 180 s, falla en t = 60 s, reposición en t = 120 s)

Fuente: `results/ejemplos/lote-E07-actions/` (ejecución 43958990234; `constante.yml`, round_robin,
3 backends, `scripts/inject-fault.sh` sobre la réplica 1); figura `docs/figuras/resiliencia_E07_round_robin.png`
(última corrida) y `figuras/timeline.png` de cada corrida.

| Falla | Errores al cliente en los 30 s tras la falla | Errores en toda la corrida | p99 en esos 30 s | Reintentos (`upstream_addr` con coma) | Detección | Recuperación | Observación |
|---|---|---|---|---|---|---|---|
| `docker stop` (SIGTERM) | **0** | 0 | 22 ms | 1 | 0,0 s | 3,4 s tras `docker start` | apagado elegante: cierra el listener y termina lo en vuelo; NGINX ve "conexión rechazada" y reintenta |
| `docker kill` (SIGKILL) | **0** | 0 | 22 ms | 3 | 0,0 s | automática (`restart: unless-stopped`) | las 3 peticiones en vuelo se reintentan en otro backend |
| `docker pause` (cuelgue a nivel SO) | **9** (0,10 %) | 0,02 % | **10 021 ms** | 199 | 0,0 s | 5,0 s tras `unpause` | el kernel acepta la conexión pero nadie responde: cada petición afectada espera `proxy_read_timeout` = 10 s y luego se reintenta; 9 agotan los 3 intentos / 15 s |
| `/admin/crash` (exit 1) | **0** | 0 | 22 ms | 4 | — (vuelve con el mismo hostname) | automática, ~1 s (Docker lo reinicia) | 4 peticiones en vuelo reintentadas |
| `/admin/fault error500` | **3001** (33,3 %) | 13,3 % (6004 de 54 000) | 22 ms | **0** | no se detecta | al restaurar | NGINX **no reintenta** respuestas 500 (`proxy_next_upstream` sin `http_500`) ni las cuenta como fallo pasivo: 1 de 3 backends devuelve error y el cliente lo ve |
| `/admin/fault slow` (+2 s) | 0 | 0 | **2022 ms** | 0 | no se detecta | al restaurar | 2 s < `proxy_read_timeout` (10 s): el backend lento no es un "fallo" para NGINX; media 277 ms, p99 2022 ms durante 60 s |
| `/admin/fault hang` (HTTP sin respuesta) | **9** (0,10 %) | 0,02 % | **10 021 ms** | 199 | 0,0 s | al restaurar | idéntico a `pause`: lo detecta el timeout, no la detección pasiva |

Conclusiones de E-07:

1. **Caída** (conexión rechazada: stop, kill, crash) es el caso benigno: detección inmediata, 1–4
   reintentos, **0 errores** y p99 intacto. La detección pasiva (`max_fails`/`fail_timeout`) y
   `proxy_next_upstream` bastan.
2. **Cuelgue** (pause, hang) es el caso caro: cada petición que toca el backend colgado paga el
   `proxy_read_timeout` completo (10 s) antes del reintento; 199 reintentos y 9 errores en 60 s.
   La defensa es un `proxy_read_timeout` ajustado al endpoint legítimo más lento (E-08) y, en
   producción, checks activos (NGINX Plus) o un healthcheck externo que retire el nodo.
3. **Errores de aplicación** (error500) y **lentitud** (slow) son invisibles para NGINX OSS con la
   configuración por defecto: no son `error`/`timeout`, así que ni se reintentan ni cuentan para
   `max_fails`. Añadir `http_500` a `LB_NEXT_UPSTREAM` convierte el primer caso en 0 errores
   (a costa de reintentar peticiones no idempotentes solo si se habilita `non_idempotent`); el
   segundo solo lo resuelven `least_conn`/`random_two` (E-03) o un timeout más corto.
4. `docker kill` y `/admin/crash` no son "eliminar" el backend: `restart: unless-stopped` lo
   reinicia en ~1 s. Por eso M-03 usa `docker rm -f`.

## E-01 / E-02 · Escalabilidad con el endpoint de espera (`/api/work?ms=20`)

Fuente: `results/ejemplos/lote-E02-ms20-actions/` (ejecución 43958958299; `rampa.yml`, 2
repeticiones por N, orden aleatorio); figura `docs/figuras/escalabilidad_ms20.png`.

| N backends | Throughput tras calentamiento (req/s) | Media (ms) | p95 (ms) | p99 (ms) | Errores | CPU media backends (suma) | CPU media Artillery |
|---|---|---|---|---|---|---|---|
| 1 | 1137,5 ± 0,0 | 20,2 | 21 | 22 | 0 | 9,9 % | 65,7 % |
| 2 | 1137,4 ± 0,0 | 20,3 | 21 | 22 | 0 | 6,0 % | 65,3 % |
| 3 | 1137,4 ± 0,1 | 20,3 | 21 | 22 | 0 | 4,5 % | 64,4 % |
| 5 | 1137,4 ± 0,0 | 20,5 | 21 | 22 | 0 | 3,8 % | 63,5 % |
| 7 | 1137,4 ± 0,0 | 20,6 | 22 | 22,5 ± 0,7 | 0 | 3,7 % | 64,0 % |

Resultado honesto: **ninguna diferencia entre N = 1 y N = 7**. El endpoint `ms=20` solo espera
(temporizador asíncrono), así que un único backend con 0,5 CPU atiende 1137 req/s usando el 10 % de
CPU; la tasa la fija el escenario (150 VU/s × 10 peticiones / ~5,5 s) y el generador está al 65 %.
La eficiencia de escalado Throughput(N)/(N·Throughput(1)) cae como 1/N precisamente porque la carga no
crece con N. Esta corrida mide el **escenario**, no la capacidad: para medir escalabilidad hay que
saturar los backends, lo que se hace en la repetición con costo de CPU (sección siguiente).

## E-02 · Escalabilidad con costo de CPU (`/api/work?ms=20&cpu=3`)

> Pendiente: ejecución en curso (`pruebas.yml`, `work_path=/api/work?ms=20&cpu=3`, 2 repeticiones).
> Se incorporará aquí con `docs/figuras/escalabilidad.png`.

## E-13 · Punto de quiebre con el endpoint de espera

Fuente: `results/ejemplos/lote-E13-ms20-actions/` (ejecución 43958973688; `quiebre.yml`, rampa de 50 a
3000 llegadas/s en 300 s); figura `docs/figuras/quiebre_ms20.png`.

| N | Peticiones | Tasa media tras calentamiento (req/s) | Tasa máx. en 10 s con error < 1 % y p99 < 1 s | Errores | p99 | CPU Artillery / lb / backends |
|---|---|---|---|---|---|---|
| 1 | 457 500 | 1626 | 2650 req/s | **0** | 22 ms | 65 % / 15 % / 16 % |
| 3 | 457 500 | 1607 | 2444 req/s | **0** | 22 ms | 68 % / 18 % / 8 % |
| 5 | 457 500 | 1598 | 2395 req/s | **0** | 22 ms | 68 % / 18 % / 5 % |

El sistema **no se quebró**: 0 errores y p99 de 22 ms hasta el final de la rampa. Artillery, al 65–68 %
de un núcleo, solo llegó a emitir ~1600 req/s de media (pico de ~2650 en ventanas de 10 s) en lugar de
los 3000 VU/s nominales; el balanceador y un solo backend absorbieron todo. De nuevo, el punto de quiebre
observado es el del generador. La repetición con `cpu=3` (sección siguiente) sí satura los backends.

## E-13 · Punto de quiebre con costo de CPU

> Pendiente: ejecución en curso (`work_path=/api/work?ms=20&cpu=3`).

## E-05 · Trampa de ip_hash y afinidad L7

> Pendiente de la verificación de `hash … consistent` + `resolve` (ver `docs/hallazgos.md`); se
> completa con los datos de `results/ejemplos/lote-E05-actions/` tras esa verificación.

## E-04, E-09, E-10, E-11, E-14

> Pendientes: ejecuciones en curso en Actions.

## E-06, E-08, E-12, E-15 y A-01, A-02, A-05

> No ejecutadas todavía (disponibles con `make test-ext E=…`, `make feature F=…`, `make haproxy-up`).
