# Resultados de las pruebas extendidas (E-xx)

Todas las cifras provienen de `results/` (regla del proyecto). Las corridas se ejecutaron con el
flujo `pruebas.yml` en **GitHub Actions** (`ubuntu-latest`, 2 vCPU, 7,9 GB; NGINX 1.30.6; Artillery
2.0.34; backends con 0,5 CPU y 256 MB) el 16-nov-2026. Los resúmenes por corrida están versionados en
`results/ejemplos/lote-*-actions/` (sin los logs JSON crudos de NGINX, que quedan 90 días en los
artefactos de Actions).

**Limitación transversal:** con 2 vCPU el generador de carga es el cuello de botella cuando el endpoint
solo espera (`/api/work?ms=20`). Por eso las pruebas de capacidad (E-02, E-13) se hicieron dos veces:
con ese endpoint y con uno que consume 3 ms de CPU por petición (`/api/work?ms=20&cpu=3`), que sí
satura los backends (≈ 166 req/s por réplica con 0,5 CPU).

Índice: [E-02 escalabilidad](#e-01--e-02--escalabilidad-horizontal) · [E-13 quiebre](#e-13--punto-de-quiebre) ·
[E-03 heterogéneos](#e-03--backends-heterogéneos) · [E-04 costo variable](#e-04--peticiones-de-costo-variable) ·
[E-05 afinidad](#e-05--trampa-de-ip_hash-y-afinidad-l7) · [E-06 remapeo](#e-06--remapeo-al-retirar-un-nodo) ·
[E-07 modos de falla](#e-07--modos-de-falla-bajo-carga) · [E-09 falla total](#e-09--falla-múltiple-y-total) ·
[E-10 escalado en caliente](#e-10--escalado-en-caliente-bajo-carga) · [E-11 recarga](#e-11--recarga-de-configuración-bajo-carga) ·
[E-14 pico](#e-14--pico-súbito) · [pendientes](#pruebas-no-ejecutadas)

## E-01 / E-02 · Escalabilidad horizontal

### Con costo de CPU (`/api/work?ms=20&cpu=3`) — resultado principal

Fuente: `results/ejemplos/lote-E02-cpu3-actions/` (ejecución 43969174214; `rampa.yml`, 2 repeticiones
por N, orden aleatorio); figura `docs/figuras/escalabilidad.png`.

| N backends | Goodput (req/s correctas) | Atendidas (incl. errores) | Tasa de error | Media (ms) | p95 (ms) | p99 (ms) | CPU máx. por backend |
|---|---|---|---|---|---|---|---|
| 1 (E-01, sin balanceo efectivo) | **170,5 ± 0,0** | 920 ± 28 | **81,5 %** | 1822 | 2003 | 4040 | 52,5 % (límite 50 %) |
| 2 | **270,9 ± 41,0** | 735 ± 81 | 62,6 % | 389 | 2001 | 4160 | 52,7 % |
| 3 | **471,6 ± 137,7** | 803 ± 22 | 41,0 % ± 18,8 | 474 | 2894 | 4258 | 52,1 % |
| 5 | **783,3 ± 6,7** | 783 ± 7 | **0 %** | 155 | 292 | 533 | 34,6 % |
| 7 | **751,3 ± 6,0** | 751 ± 6 | **0 %** | 88 | 188 | 345 | 25,8 % |

Lectura:

- Con 1 backend el clúster entrega **170 req/s correctas**, que coincide con la capacidad teórica de una
  réplica (0,5 CPU / 3 ms ≈ 166 req/s). El resto de la carga se rechaza o agota los timeouts: 81,5 % de error.
- El goodput crece casi linealmente: 170 → 271 → 472 → 783 req/s. La **eficiencia de escalado**
  Goodput(N) / (N · Goodput(1)) es 0,79 (N = 2), 0,92 (N = 3) y 0,92 (N = 5).
- Con **5 backends** el sistema atiende **toda** la carga ofrecida sin errores; con 7 la latencia sigue
  bajando (p99 533 → 345 ms) pero el goodput ya no sube porque la carga del escenario es la que manda
  (eficiencia 0,63: hay capacidad sobrante).
- N = 3 tiene mucha variación entre repeticiones (error 41 % ± 19): está justo en el borde de la
  saturación, donde pequeñas diferencias de planificación del runner cambian el resultado.

**Conclusión:** para este escenario (pico de ~1137 req/s con 3 ms de CPU cada una) hacen falta **5
réplicas**; la regla de dimensionamiento es N ≥ carga pico × costo de CPU / CPU por réplica
(1137 × 3 ms / 0,5 ≈ 6,8 réplicas al 100 %; 5 bastan porque la rampa solo sostiene el pico 120 s).

### Con el endpoint de espera (`/api/work?ms=20`)

Fuente: `results/ejemplos/lote-E02-ms20-actions/` (ejecución 43958958299); figura `docs/figuras/escalabilidad_ms20.png`.

| N | Goodput (req/s) | Media (ms) | p95 (ms) | p99 (ms) | Errores | CPU media backends | CPU media Artillery |
|---|---|---|---|---|---|---|---|
| 1 | 1137,5 | 20,2 | 21 | 22 | 0 | 9,9 % | 65,7 % |
| 2 | 1137,4 | 20,3 | 21 | 22 | 0 | 6,0 % | 65,3 % |
| 3 | 1137,4 | 20,3 | 21 | 22 | 0 | 4,5 % | 64,4 % |
| 5 | 1137,4 | 20,5 | 21 | 22 | 0 | 3,8 % | 63,5 % |
| 7 | 1137,4 | 20,6 | 22 | 22,5 | 0 | 3,7 % | 64,0 % |

Sin diferencia entre 1 y 7 backends: la espera de 20 ms no consume CPU, así que una sola réplica atiende
toda la carga al 10 % de CPU. Este resultado es el motivo de la repetición con costo de CPU.

## E-13 · Punto de quiebre

### Con costo de CPU (`cpu=3`) — resultado principal

Fuente: `results/ejemplos/lote-E13-cpu3-actions/` (ejecución 43969188688; `quiebre.yml`, rampa de 50 a
3000 llegadas/s en 300 s, sin umbral `ensure`); figura `docs/figuras/quiebre.png`.

| N | Peticiones | Goodput medio (req/s) | Tasa de error | Carga máx. con error < 1 % y p99 < 1 s (ventanas de 10 s) | Primera ventana que falla | p99 global |
|---|---|---|---|---|---|---|
| 1 | 416 371 | 165,8 | 87,3 % | **91–185 req/s** | 185 req/s | 4253 ms |
| 3 | 457 500 | 305,6 | 80,3 % | **582 req/s** | 670 req/s | 6116 ms |
| 5 | 457 500 | 833,1 | **0 %** | **875 req/s** | 820 req/s (por p99 > 1 s) | 3540 ms |

El punto de quiebre escala con el número de réplicas: ~185 → ~600 → ~850 req/s. Con 5 réplicas no hubo
errores, pero el p99 superó 1 s a partir de ~820 req/s: el sistema se degrada por latencia antes que por
errores. Con 1 y 3 réplicas los errores son 502/504 por `proxy_connect_timeout`/`proxy_read_timeout`
(colas de conexiones en backends saturados).

### Con el endpoint de espera (`ms=20`)

Fuente: `results/ejemplos/lote-E13-ms20-actions/` (ejecución 43958973688); figura `docs/figuras/quiebre_ms20.png`.
Con N = 1, 3 y 5 hubo **0 errores** y p99 de 22 ms hasta el final: Artillery solo pudo emitir ~1600 req/s
de media (pico ~2650 en 10 s) en lugar de las 3000 llegadas/s nominales. El quiebre observado es el del
generador, no el del balanceador.

## E-03 · Backends heterogéneos

Fuente: `results/ejemplos/lote-E03-actions/` (ejecución 43958941819; `compose.weighted.yml`: 3 réplicas
rápidas + 1 lenta con 150 ms de latencia y 0,25 CPU; `rampa.yml`, 2 repeticiones, orden aleatorio);
figuras `docs/figuras/algoritmos_latencia_E03.png` y `algoritmos_distribucion_E03.png`.

| Configuración | Media (ms) | p95 (ms) | p99 (ms) | % al backend lento | Jain (4 nodos) |
|---|---|---|---|---|---|
| round_robin (1:1:1:1) | **58,2 ± 0,1** | 171 | 173 | 25,0 % | 1,000 |
| round_robin ponderado 3:1 | 35,5 ± 0,0 | 171 | 172 | 10,0 % | 0,893 |
| least_conn | **27,1 ± 0,0** | **23** | 171 | **4,5 %** | 0,816 |
| random_two (least_conn) | 27,9 ± 0,1 | 25,5 ± 2,1 | 171 | 4,9 % | 0,823 |

Round-robin reparte por turnos e ignora que un nodo es 8 veces más lento: el 25 % de las peticiones paga
170 ms, la **media se duplica** (58 vs 27 ms) y el **p95 pasa de 23 a 171 ms**. `least_conn` y
`random_two` ven que el nodo lento acumula conexiones y le envían solo 4,5–4,9 % del tráfico. El p99 no
mejora porque ese ~5 % sigue existiendo. El round-robin ponderado es un término medio que exige conocer
de antemano la capacidad de cada nodo. Diferencia least_conn vs random_two: 0,8 ms en la media.

Hipótesis "least_conn y random_two protegen la cola de latencia": **confirmada en media y p95**; el p99
lo fija el propio backend lento.

## E-04 · Peticiones de costo variable

Fuente: `results/ejemplos/lote-E04-actions/` (ejecución 43969202574; `WORK_PATH=/api/mixed`: 90 % de
peticiones de 5 ms y 10 % de 300 ms; 2 repeticiones); figura `docs/figuras/algoritmos_latencia_E04.png`.

| Política | Media (ms) | p95 (ms) | p99 (ms) | Jain |
|---|---|---|---|---|
| round_robin | 34,8 / 34,7 | 300 | 301 | 1,000 |
| least_conn | 34,9 / 34,7 | 300 | 301 | 1,000 |
| random_two | 34,8 / 34,6 | 300 | 301 | 1,000 |

**No distinguibles** (`significancia.txt`). Hipótesis "least_conn mejora frente a colas largas":
**refutada en este escenario**. Las peticiones lentas solo esperan un temporizador y no ocupan CPU, así
que un backend con varias peticiones lentas en curso atiende las rápidas igual de rápido: no hay cola
real. La ventaja de `least_conn` aparece cuando el costo es de **capacidad** (E-03: un nodo con menos
CPU), no cuando es de espera.

## E-05 · Trampa de ip_hash y afinidad L7

### Primera ejecución: `hash … consistent` (hallazgo H-1)

Fuente: `results/ejemplos/lote-E05-consistent-actions/` (ejecución 43958925688); figura
`docs/figuras/algoritmos_distribucion_E05_consistent.png`.

| Política | Jain | % al backend más cargado | Clientes fieles a un backend |
|---|---|---|---|
| ip_hash | 0,333 | 100 % | 100 % |
| `hash $http_x_client_id consistent` | 1,000 | 33,3 % | 0,13–0,19 % |
| `hash $remote_addr consistent` | 1,000 | 33,3 % | 0,21 % |

El hash consistente no mantuvo la afinidad: con `server … resolve` reparte como round-robin
(ver `docs/hallazgos.md`, H-1). Las políticas se cambiaron a hash simple.

### Segunda ejecución: hash simple

> Ejecución 43982116149 en curso; se completa al terminar.

## E-06 · Remapeo al retirar un nodo

> Medición determinista con `scripts/check-remap.sh` (200 clientes fijos, 5 → 4 réplicas) en la CI;
> se completa al terminar la ejecución.

## E-07 · Modos de falla bajo carga

Fuente: `results/ejemplos/lote-E07-actions/` (ejecución 43958990234; `constante.yml`, 300 req/s,
round_robin, 3 backends; falla en t ≈ 60 s, reposición en t ≈ 120 s); figuras
`docs/figuras/resiliencia_*_E07_*.png`.

| Falla | Errores en los 30 s tras la falla | p99 en esos 30 s | Reintentos | Recuperación | Mecanismo |
|---|---|---|---|---|---|
| `docker stop` (SIGTERM) | **0** | 22 ms | 1 | 3,4 s tras `start` | conexión rechazada → reintento inmediato |
| `docker kill` (SIGKILL) | **0** | 22 ms | 3 | automática (`restart`) | 3 peticiones en vuelo reintentadas |
| `/admin/crash` (exit 1) | **0** | 22 ms | 4 | automática, ~1 s | 4 peticiones en vuelo reintentadas |
| `docker pause` (cuelgue) | **9** (0,10 %) | **10 021 ms** | 199 | 5,0 s tras `unpause` | cada petición espera `proxy_read_timeout` = 10 s antes de reintentar |
| `/admin/fault hang` | **9** (0,10 %) | **10 021 ms** | 199 | al restaurar | igual que `pause` |
| `/admin/fault slow` (+2 s) | 0 | **2022 ms** | 0 | al restaurar | 2 s < timeout: NGINX no lo considera fallo |
| `/admin/fault error500` | **3001** (33,3 %) | 22 ms | **0** | al restaurar | NGINX no reintenta 500 ni lo cuenta como fallo |

1. **Caída** (stop, kill, crash): detección inmediata, **0 errores**, p99 intacto.
2. **Cuelgue** (pause, hang): el caso caro; cada petición afectada paga 10 s. Lo mitiga un
   `proxy_read_timeout` ajustado al endpoint legítimo más lento.
3. **Error de aplicación** y **lentitud** son invisibles para la detección pasiva de NGINX OSS con la
   configuración por defecto (hallazgo H-4).

## E-09 · Falla múltiple y total

Fuente: `results/ejemplos/lote-E09-actions/` (ejecución 43969216892; `constante.yml`, 300 req/s;
eventos: retirar una réplica cada 30 s hasta 0, reponer 3); figura `docs/figuras/resiliencia_E09_round_robin.png`.

| Fase | Backends | Errores | p99 |
|---|---|---|---|
| inicio | 3 | 0 | 24 ms |
| retirar el 1.º | 2 | **0** (3 reintentos) | 23 ms |
| retirar el 2.º | 1 | **0** (3 reintentos) | 23–39 ms |
| retirar el 3.º (sin backends) | 0 | **100 %** durante 30 s (2806 errores, página de mantenimiento 502) | 2001 ms |
| reponer 3 (`scale 3`) | 3 | primeras respuestas correctas **0,84 s** después de iniciar la reposición | 23 ms |

Degradación limpia: con 1 de 3 backends el servicio siguió sin errores (300 req/s caben en una réplica);
sin ninguno, NGINX respondió la página de mantenimiento; al reponer, el tráfico volvió en menos de 1 s.
Errores totales de la corrida: 7,0 % (todos en la ventana sin backends).

## E-10 · Escalado en caliente bajo carga

Fuente: `results/ejemplos/lote-E10-actions/` (ejecución 43969231394; `constante.yml`; escalar 3 → 6 y
luego 6 → 2); figura `docs/figuras/resiliencia_E10_round_robin.png`.

- **3 → 6:** las 3 réplicas nuevas recibieron tráfico **sin recargar NGINX** (`resolve`), 0 errores, p99 ≤ 28 ms.
- **6 → 2 (scale-in):** **1 error** y 10 reintentos en 54 000 peticiones; un pico de p99 de 1900 ms en
  esa ventana de 10 s (peticiones que estaban en las réplicas eliminadas y fueron reintentadas).

## E-11 · Recarga de configuración bajo carga

Fuente: `results/ejemplos/lote-E11-actions/` (ejecución 43969246596; `constante.yml`; cambio de política
round_robin → least_conn → round_robin con `nginx -s reload` en t = 60 s y 120 s).

**0 errores** en 54 000 peticiones y p99 entre 22 y 29 ms durante toda la corrida: la recarga de NGINX
es elegante (los workers viejos terminan sus conexiones mientras los nuevos aceptan las nuevas).

## E-14 · Pico súbito

Fuente: `results/ejemplos/lote-E14-actions/` (ejecución 43969261690; `spike.yml`: 50 → 800 → 50 VU/s,
pico de 20 s); figura `docs/figuras/resiliencia_E14_round_robin.png`.

El pico multiplicó la tasa por 16 (de 150 a ~2400 req/s durante 20 s). Resultado: **0 errores** y p99
máximo de **31 ms** en la ventana del pico, 22–24 ms antes y después. Con el endpoint de espera el
sistema absorbe la ráfaga sin cola.

## Pruebas no ejecutadas

- **E-08** (matriz timeouts × reintentos bajo `hang`), **E-12** (keepalive on/off), **E-15** (soak 15 min):
  disponibles con `make test-ext E=E08|E12|E15`.
- **A-01** (limitación de tasa), **A-02** (microcaché), **A-05** (HAProxy): disponibles con
  `make feature F=…` y `make haproxy-up`.
