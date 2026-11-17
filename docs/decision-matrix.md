# Alternativas de solución y matrices de decisión multicriterio

El 30 % de la nota (criterio 2 de la rúbrica) depende de un **proceso estructurado de
evaluación y selección** con matrices multicriterio, donde cada criterio dice **cómo se mide**.
Se usan tres matrices. En todas: puntuación de 1 a 5, pesos que suman 100,
puntaje final = Σ(peso × puntuación) / 5 (sobre 100).

- La matriz **4.1** (tecnología) define para cada criterio **cómo se mide y una escala 1–5 con
  umbrales**. C1 (desempeño) y C5 (facilidad) se **midieron** con el caso base mínimo de cada
  alternativa (`alternativas/`, `scripts/test-alternativas.sh`); el resto sale de la documentación
  oficial, citada celda por celda.
- La matriz **4.2** (algoritmo) se llena **exclusivamente con resultados medidos** por
  `analysis/decision_matrix.py`; también la simplicidad, que se mide en líneas de la política.
- La matriz **4.3** (descubrimiento de backends) es una decisión de diseño con forma de medir y escala
  por criterio, revisada después del hallazgo H-1.

`make matrix` regenera [`decision-matrix-generada.md`](decision-matrix-generada.md) con la
sensibilidad de 4.1 y la 4.2 con datos; este archivo explica el razonamiento.

---

## Matriz 4.1 — tecnología de balanceo

Alternativas (todas mencionadas o relacionadas con la presentación del curso): **NGINX** (open
source), **HAProxy**, **Traefik**, **Apache HTTP Server** con `mod_proxy_balancer` y **Linux Virtual
Server (LVS/IPVS)**.

### Criterios, pesos, forma de medir y escala

| ID | Criterio | Peso | Cómo se mide | Escala 1–5 |
|---|---|---|---|---|
| C1 | Desempeño y eficiencia | 20 | **Medido.** Misma carga (`rampa.yml`, ~983 req/s) contra el caso base mínimo de cada alternativa sobre las mismas 3 réplicas, 3 repeticiones en orden aleatorio (corridas A05B). p99 de Artillery y CPU media del contenedor del balanceador. | 5·(½·p99_mejor/p99 + ½·CPU_mejor/CPU), redondeado, mínimo 1 |
| C2 | Algoritmos disponibles | 15 | Conteo de métodos en la documentación oficial de la versión libre | 5 ≥ 8 · 4 = 5–7 · 3 = 3–4 · 2 = 2 · 1 = 1 |
| C3 | Detección de fallos (versión libre) | 15 | Documentación oficial: checks activos, detección pasiva y reintentos en otro servidor | 5 = los tres · 4 = dos de los tres · 3 = pasivos + reintentos · 2 = solo uno · 1 = ninguno |
| C4 | Observabilidad | 10 | Documentación oficial: métricas por servidor de backend en la versión libre | 5 = por servidor en Prometheus nativo · 4 = por servidor parcial o vía exportador estándar · 3 = por servidor solo en página/consola · 2 = solo globales · 1 = ninguna |
| C5 | Facilidad de configuración | 10 | **Medido.** Líneas útiles (sin comentarios ni blancos) del caso base mínimo equivalente en `alternativas/`: proxy en :80 a 3 réplicas, round-robin, detección de fallos y reintentos. Cada uno se comprobó funcionando: 30 peticiones, 3 nodos, 0 fallos. | 5 ≤ 10 · 4 = 11–20 · 3 = 21–30 · 2 = 31–40 · 1 > 40 líneas |
| C6 | Docker / descubrimiento dinámico | 10 | Qué hay que hacer para que una réplica nueva reciba tráfico | 5 = automático por la API/etiquetas de Docker · 4 = re-resolución DNS sin recargar · 3 = lista estática + recarga sin cortar · 2 = lista estática + reinicio · 1 = alta manual con comandos |
| C7 | Madurez y documentación | 10 | Años desde la primera versión estable y versiones en los últimos 12 meses | 5 = ≥ 15 años y versiones recientes · 4 = ≥ 10 años, o ≥ 15 sin versiones recientes de la herramienta de usuario · 3 = 5–9 años · 2 = < 5 años · 1 = sin mantenimiento |
| C8 | Funciones L7 adicionales | 10 | Cuántas de 6 trae la versión libre: estáticos, caché, TLS, limitación de tasa, reescritura, compresión | 5 = 6 · 4 = 5 · 3 = 4 · 2 = 2–3 · 1 = 0–1 |

Las escalas se fijaron antes de puntuar y se aplican igual a las cinco alternativas. Fuentes de la
documentación: nginx.org (`ngx_http_upstream_module`), docs.haproxy.org 3.2 (`balance`, `check`,
`observe`), doc.traefik.io (servicio de balanceo, `retry`, métricas), httpd.apache.org 2.4
(`mod_proxy_balancer`, `mod_proxy_hcheck`, `mod_proxy`) e `ipvsadm(8)`.

### Mediciones de C1 y C5

Fuente: `results/ejemplos/lote-A05B-actions/` (3 repeticiones por alternativa, 0 errores en todas) y
`alternativas_c5.csv` del mismo lote.

| Alternativa | p99 | CPU del balanceador | C1 | Líneas del caso base | ¿Funciona? | C5 |
|---|---|---|---|---|---|---|
| NGINX 1.30 | 35,7 ms | 9,9 % | **5** | 20 | sí (3 nodos, 0 fallos) | **4** |
| HAProxy 3.2 | 36,0 ms | 10,9 % | **5** | 18 | sí | **4** |
| Apache 2.4.68 | 38,0 ms | 19,6 % | **4** | 23 | sí | **3** |
| Traefik 3.7.16 | 41,2 ms | 28,1 % | **3** | 27 | sí | **3** |
| LVS (keepalived) | no medido | — | 5† | 33 | no ejecutado | **2** |

† LVS no se puede medir en contenedores: IPVS vive en el kernel del host (módulo `ip_vs`) y el modo
NAT exige que el director sea la puerta de enlace de los backends. Se le asigna 5 por diseño (reenvío en
el kernel, sin proxy en espacio de usuario) y se declara como valor no medido.

Con reutilización de conexiones hacia los backends en las cuatro alternativas, **NGINX y HAProxy
quedan prácticamente empatados** (p99 35,7 frente a 36,0 ms). La diferencia de A-05 (p99 32,5 frente
a 40,5 ms y el doble de CPU) se debía a la opción `http-server-close` de aquella configuración de
HAProxy, como ya advertía su salvedad.

### Puntuación con evidencia

| Criterio (peso) | NGINX | HAProxy | Traefik | Apache | LVS |
|---|---|---|---|---|---|
| C1 (20) | **5** · p99 35,7 ms, CPU 9,9 % | **5** · p99 36,0 ms, CPU 10,9 % | **3** · p99 41,2 ms, CPU 28,1 % | **4** · p99 38,0 ms, CPU 19,6 % | **5†** · por diseño |
| C2 (15) | **4** · 7 métodos | **5** · 13 | **3** · 4 (wrr, p2c, hrw, leasttime) | **3** · 4 (byrequests, bytraffic, bybusyness, heartbeat) | **5** · 10 |
| C3 (15) | **3** · pasiva + reintentos; activos solo en Plus | **5** · activos, pasivos (`observe`) y reintentos | **5** · `healthCheck`, `passiveHealthCheck` y `retry` | **5** · `mod_proxy_hcheck`, estado de error y `maxattempts` | **1** · ninguno propio (keepalived) |
| C4 (10) | **2** · `stub_status` global | **5** · Prometheus por servidor | **4** · por servidor solo `server_up` | **3** · `balancer-manager` (HTML) | **4** · `ipvsadm --stats`, colector ipvs |
| C5 (10) | **4** · 20 líneas | **4** · 18 | **3** · 27 | **3** · 23 | **2** · 33 |
| C6 (10) | **4** · `resolve` | **4** · `server-template` + `resolvers` | **5** · proveedor Docker | **3** · estáticos + `graceful` | **1** · `ipvsadm -a` por réplica |
| C7 (10) | **5** · desde 2004 | **5** · desde 2001 | **4** · desde 2015 | **5** · desde 1995 | **4** · IPVS desde 1998, `ipvsadm` sin versiones recientes |
| C8 (10) | **5** · 6/6 | **4** · 5/6 (sin estáticos) | **3** · 4/6 | **4** · 5/6 (sin límite de peticiones) | **1** · 0/6 |
| **Puntaje /100** | **81** | **94** | **74** | **76** | **62** |

La versión regenerada, con la evidencia completa, está en
[`decision-matrix-generada.md`](decision-matrix-generada.md).

### Análisis de sensibilidad

Cada peso se varía ±5 puntos (redistribuyendo proporcionalmente en los demás). Un empate no cuenta
como cambio de líder. Calculado por `decision_matrix.py`:

- **Ranking:** HAProxy (94) > NGINX (81) > Apache (76) > Traefik (74) > LVS (62).
- **±5 en los pesos:** el líder no cambia en ningún caso.
- **Umbrales:** Traefik pasaría al primer lugar si C6 (descubrimiento) pesara **56** o más; NGINX, si
  C8 (funciones L7) pesara **46** o más. Ningún otro criterio, entre 0 y 100, cambia el líder.

### Reflexión

La matriz, aplicada con criterios medibles, **no elige NGINX**: HAProxy gana por 13 puntos gracias a
criterios puramente de balanceo (checks activos y pasivos, más algoritmos y métricas por servidor en la
versión libre), y la ventaja es robusta. Se reporta tal cual. Con las primeras puntuaciones la ventaja
era de 3 puntos; al medir C1 y C5 y aplicar escalas explícitas creció, porque varias puntuaciones
iniciales favorecían a NGINX sin evidencia (por ejemplo C1, que se había dado por bueno con una
configuración de HAProxy que no reutilizaba conexiones).

En este proyecto la tecnología es un **requisito del cliente** (el enunciado asigna NGINX), así que la
matriz no decide: **valida** la elección y señala sus costos. NGINX queda segundo, empata con HAProxy en
el desempeño medido y es la más completa en funciones L7 (la microcaché redujo un 77 % la CPU de
PostgreSQL en A-02). Sus debilidades se mitigan en el diseño: detección pasiva + reintentos (C3, medido
en M-03 y E-07), exporter + logs JSON + `/metrics` por réplica (C4) y `resolve` (C6). Para un servicio
nuevo sin esa restricción, la recomendación sería HAProxy.

---

## Matriz 4.2 — algoritmo de balanceo recomendado (se llena con datos)

Responde a "¿qué algoritmo recomendamos para este tipo de servicio?". Los valores salen de las
pruebas; la normalización convierte cada métrica a la escala 1–5.

| Criterio | Peso | Métrica y prueba de origen | Normalización a 1–5 |
|---|---|---|---|
| Latencia p99, backends homogéneos | 20 | p99 (ms) en `rampa.yml`, media de 3 repeticiones (M-05) — `ng_lat_p99_ms_mean` del log de NGINX tras 30 s de calentamiento | Menor es mejor: 5 × (mejor / valor), mínimo 1 |
| Latencia p95, backends heterogéneos | 25 | p95 con un backend lento (E-03, `compose.weighted.yml`) | Igual que la anterior |
| Equidad de la distribución | 15 | Índice de Jain J = (Σxᵢ)² / (n·Σxᵢ²) sobre peticiones por backend (M-06); réplicas sin tráfico cuentan como 0 | 5 × J (J ∈ [1/n, 1]) |
| Errores durante fallo de backend | 20 | % de respuestas no-2xx en los 30 s siguientes a la falla (M-03 / E-07, `error_rate_30s_after_backend_removed`) | 5 si 0 %; 5 × (1 − min(err, 5 %)/5 %), mínimo 1 |
| Afinidad de sesión | 10 | % de clientes (`client_id`) que siempre cayeron en el mismo backend (`ng_affinity_pct`; también `afinidad.cambios_de_backend` de Artillery) | 5 × (% / 100), mínimo 1 |
| Simplicidad operativa | 10 | Líneas del archivo de la política en `nginx/policies/` (sin comentarios) y requisitos al cliente | 5 = 0–1 directiva sin parámetros (round_robin, least_conn, ip_hash) · 4 = 1 directiva con parámetros (random_two, hash_remote_addr) · 3 = mapas o variables extra · 2 = exige algo al cliente (hash_client: cabecera `X-Client-Id`) · 1 = componentes externos |

Alternativas: `round_robin`, `least_conn`, `ip_hash`, `hash_client` (hash por `X-Client-Id`; hash
simple, ver hallazgo H-1) y `random_two`.

**Dos ajustes metodológicos hechos al ver los datos** (se declaran, no se ocultan):

1. El criterio heterogéneo usa **p95** en lugar de p99. En E-03 el p99 vale 171–173 ms con todas las
   políticas porque lo fija el propio nodo lento (≈ 5 % de las peticiones aun con `least_conn`), así que
   no discrimina; el p95 sí (23 ms con `least_conn` frente a 171 ms con `round_robin`).
2. Para recomendar un algoritmo se exige que tenga **al menos 70 de 100 puntos de peso medidos**. Sin esta
   regla, una política con un solo criterio medido podía ganar con pesos renormalizados.

**Hipótesis a confirmar o refutar con datos:** con backends homogéneos las diferencias son
pequeñas (no distinguibles frente a la desviación); con backends heterogéneos `least_conn` y
`random_two` reducen la cola de latencia; `ip_hash` concentra la carga cuando los clientes comparten
red `/24` (E-05), por lo que su equidad será mínima y su afinidad máxima.

> La tabla con valores se genera con `make analyze && make matrix` y queda en
> [`decision-matrix-generada.md`](decision-matrix-generada.md). Los criterios sin dato se excluyen
> y los pesos restantes se renormalizan; el documento indica qué pesos tienen dato.

### Resultado con datos medidos

Fuente: `results/ejemplos/matriz-4.2/resumen_comparativo_combinado.csv`, que une los lotes de GitHub
Actions test-min (REPS=3), ALG, E-03 (dos ejecuciones), E-05 y M-03 por política. Las cinco políticas
tienen **100/100 de peso medido**. Celdas: puntuación 1–5 (valor medido).

| Política | p99 homogéneos (20) | p95 un backend lento (25) | Jain (15) | Errores al caer un backend (20) | Afinidad (10) | Simplicidad (10) | **Puntaje /100** |
|---|---|---|---|---|---|---|---|
| **least_conn** | 5,0 (22 ms) | **5,0 (23 ms)** | 5,0 (1,00) | 5,0 (0 %) | 1,0 (0,3 %) | 5 | **92,0** |
| random_two | 5,0 (22 ms) | 4,5 (25,5 ms) | 5,0 (1,00) | 5,0 (0 %) | 1,0 (0 %) | 4 | 87,5 |
| hash_client | 5,0 (22 ms) | 1,0 (171 ms) | 5,0 (1,00) | 5,0 (0 %) | **5,0 (100 %)** | 2 | 74,0 |
| round_robin | 4,9 (22,5 ms) | 1,0 (171 ms) | 5,0 (1,00) | 5,0 (0 %) | 1,0 (0,1 %) | 5 | 71,6 |
| ip_hash | 4,8 (23 ms) | 1,0 (113,5 ms) | 1,7 (0,33) | 5,0 (0 %) | 5,0 (100 %) | 5 | 69,2 |

**Recomendación: `least_conn`.** Iguala a las demás con backends homogéneos y es la que mejor protege la
latencia cuando un backend se degrada.

**Análisis de sensibilidad** (cada peso ±5, redistribuido proporcionalmente): el líder **no cambia en
ningún caso**. Umbrales de cambio de líder: `hash_client` pasaría al primer lugar si la **afinidad de
sesión pesara 27/100 o más** (hoy 10), o si el criterio de backends heterogéneos bajara a 3. Ningún otro
criterio, dentro de 0–100, cambia el líder.

**Contraste con las hipótesis:** homogéneos no distinguibles (confirmada); `least_conn` y `random_two`
protegen la cola con heterogeneidad de capacidad (confirmada en p95, no en p99); `ip_hash` concentra la
carga de una /24 (confirmada: Jain 0,33, y con un backend lento su resultado depende de a qué nodo cae la
/24). Resultado no previsto: `hash_client` sin datos heterogéneos llegó a liderar (94,7) solo porque los
pesos se renormalizaban; medir ese criterio lo bajó a 74,0. Por eso se exige ≥ 70/100 de peso medido.

---

## Matriz 4.3 — estrategia de descubrimiento de backends (decisión de diseño)

| Criterio | Peso | Cómo se mide | Escala 1–5 |
|---|---|---|---|
| Escalar sin tocar la config | 30 | Pasos manuales para pasar de 3 a 5 réplicas (con `resolve`: `make scale N=5` en la CI y en E-10) | 5 = ninguno · 3 = un script automatizable + recarga · 1 = editar la configuración y recargar a mano |
| Pesos/backup por servidor | 20 | ¿Se puede dar `weight` o `backup` a una réplica concreta? | 5 = sí, por réplica · 2 = solo el mismo valor para todas · 1 = no |
| Simplicidad | 20 | Piezas que hay que mantener además de la plantilla de NGINX | 5 = ninguna y no cambia al escalar · 4 = 1–3 directivas extra fijas · 3 = la lista se edita en cada cambio · 2 = un componente externo · 1 = varios |
| Robustez ante cambios | 30 | Qué pasa si una réplica desaparece o un nombre no resuelve al arrancar | 5 = arranca y se adapta sola · 4 = arranca y se adapta, con limitaciones conocidas (H-1, H-3) · 3 = no arranca si un nombre no resuelve (`host not found in upstream`) · 2 = depende de un proceso externo · 1 = requiere intervención |

| Criterio (peso) | Servidores estáticos con nombre | DNS con `resolve` (elegida) | Regenerar config + reload |
|---|---|---|---|
| Escalar sin tocar la config (30) | 1: editar y recargar | 5: automático vía DNS de Docker | 3: script externo + recarga |
| Pesos/backup por servidor (20) | 5: `weight` y `backup` por línea | 2: mismos parámetros para todas las réplicas | 5 |
| Simplicidad (20) | 3: la lista se edita en cada cambio | 4: `zone` + `resolver` fijos | 2: script o generador externo |
| Robustez ante cambios (30) | 3: no arranca si un nombre no resuelve | 4: arranca aunque no resuelva; H-1 y H-3 | 2: depende del script |
| **Puntaje /100** | **56** | **78** | **58** |

**Decisión:** DNS con `resolve` para el stack principal; servidores estáticos con nombre solo para
el experimento de pesos y heterogeneidad (`compose.weighted.yml`, que monta una plantilla con dos
grupos `backend` y `backend-slow` con `weight`). Si `resolve` presentara problemas en la versión
usada, el plan B documentado es generar `backend1…backendN` con un script y recargar.

### Revisión tras el hallazgo H-1 (hash consistente + `resolve`)

Las pruebas revelaron un costo que la matriz original no contemplaba: con `resolve`, `hash … consistent`
no mantiene la afinidad (H-1 en [`hallazgos.md`](hallazgos.md)). Se añade el criterio
**C5 · Compatibilidad con hash consistente** (estáticos 5, `resolve` 1, regenerar + reload 5) con peso
*x* tomado proporcionalmente de los demás:

| Peso de C5 | Estáticos | DNS con `resolve` | Regenerar + reload | Gana |
|---|---|---|---|---|
| 0 (matriz original) | 56 | **78** | 58 | `resolve` |
| 10 | 60 | **72** | 62 | `resolve` |
| 20 | 65 | 66 | 66 | empate `resolve` / regenerar |
| 25 | 67 | 64 | **69** | regenerar + reload |

**Umbral:** si la afinidad estable ante escalado pesa **20 o más** sobre 100, conviene regenerar la
configuración y recargar (o servidores estáticos) en lugar de `resolve`. En este proyecto ningún requisito
del enunciado (R-01 … R-25) exige afinidad de sesión, y el escalado sin recarga (E-10: 0 errores al pasar
de 3 a 6 réplicas) sí es un objetivo, por lo que **se mantiene `resolve`** con hash simple para
`hash_client`. La reflexión queda registrada como lección de diseño para servicios con estado.
