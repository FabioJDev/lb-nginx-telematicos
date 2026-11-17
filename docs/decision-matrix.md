# Alternativas de solución y matrices de decisión multicriterio

El 30 % de la nota (criterio 2 de la rúbrica) depende de un **proceso estructurado de
evaluación y selección** con matrices multicriterio, donde cada criterio dice **cómo se mide**.
Se usan tres matrices. En todas: puntuación de 1 a 5, pesos que suman 100,
puntaje final = Σ(peso × puntuación) / 5 (sobre 100).

- La matriz **4.1** (tecnología) usa puntuaciones justificadas con documentación oficial y, si se
  ejecuta A-05, con datos medidos de HAProxy en el mismo escenario.
- La matriz **4.2** (algoritmo) se llena **exclusivamente con resultados medidos** por
  `analysis/decision_matrix.py` a partir de `results/resumen_comparativo.csv`.
- La matriz **4.3** (descubrimiento de backends) es una decisión de diseño.

`make matrix` regenera [`decision-matrix-generada.md`](decision-matrix-generada.md) con la
sensibilidad de 4.1 y la 4.2 con datos; este archivo explica el razonamiento.

---

## Matriz 4.1 — tecnología de balanceo

Alternativas (todas mencionadas o relacionadas con la presentación del curso): **NGINX** (open
source), **HAProxy**, **Traefik**, **Apache HTTP Server** con `mod_proxy_balancer` y **Linux Virtual
Server (LVS/IPVS)**.

### Criterios, pesos y forma de medir

| ID | Criterio | Peso | Cómo se mide / justifica |
|---|---|---|---|
| C1 | Desempeño y eficiencia | 20 | Throughput y latencia p99 en el mismo escenario y hardware (A-05: `TARGET=http://haproxy scripts/run-test.sh A05 rampa.yml`) o benchmarks publicados; consumo de CPU/RAM con `docker stats`. |
| C2 | Algoritmos de balanceo disponibles | 15 | Conteo de algoritmos en la documentación de la versión libre (round-robin, ponderado, menos conexiones, hash, afinidad…). |
| C3 | Detección de fallos y tolerancia (versión libre) | 15 | Checks activos vs. pasivos, reintentos configurables, `backup`. 5 = checks activos + reintentos; 3 = solo pasivos + reintentos; 1 = sin reintentos. |
| C4 | Observabilidad | 10 | Métricas por backend sin módulos de pago; endpoint Prometheus nativo o vía exporter. |
| C5 | Facilidad de configuración | 10 | Líneas de configuración del caso base + curva de aprendizaje del equipo (encuesta interna 1–5). |
| C6 | Integración con Docker / descubrimiento dinámico | 10 | ¿Detecta réplicas nuevas sin reiniciar? (DNS re-resolvable, etiquetas, API). |
| C7 | Madurez, comunidad y documentación | 10 | Años en producción, frecuencia de versiones, calidad de la documentación oficial. |
| C8 | Funciones L7 adicionales | 10 | Servir estáticos, caché, TLS, limitación de tasa, reescrituras, en la versión libre. |

### Puntuación (propuesta inicial, validada por el equipo con documentación oficial)

| Criterio (peso) | NGINX | HAProxy | Traefik | Apache | LVS |
|---|---|---|---|---|---|
| C1 (20) | 5 | 5 | 4 | 3 | 5 |
| C2 (15) | 4 | 5 | 3\* | 4 | 5 |
| C3 (15) | 3 | 5 | 4 | 4 | 1 |
| C4 (10) | 2 | 5 | 5 | 3 | 2 |
| C5 (10) | 4 | 3 | 4 | 3 | 2 |
| C6 (10) | 4 | 4 | 5 | 2 | 1 |
| C7 (10) | 5 | 4 | 4 | 4 | 3 |
| C8 (10) | 5 | 3 | 3 | 4 | 1 |
| **Puntaje /100** | **81** | **88** | **79** | **68** | **56** |

\* Verificar en la documentación vigente de Traefik los algoritmos disponibles en la versión instalada.

Justificación resumida por celda (NGINX): C3 = 3 porque NGINX OSS solo tiene detección **pasiva**
(`max_fails`/`fail_timeout`) + reintentos (`proxy_next_upstream`); los checks activos son de NGINX
Plus. C4 = 2 porque `stub_status` es global (no hay métricas por backend sin módulos de pago); se
mitiga con logs JSON por petición y el exporter. C6 = 4 porque `resolve` (OSS ≥ 1.27.3) re-resuelve
el DNS de Docker sin recargar. C8 = 5: servidor web, caché, TLS, `limit_req`, reescrituras.

### Análisis de sensibilidad

Cada peso se varía ±5 puntos (redistribuyendo proporcionalmente en los demás) y se verifica si
cambia el orden. Calculado por `decision_matrix.py`:

- **Ranking base:** HAProxy (88) > NGINX (81) > Traefik (79) > Apache (68) > LVS (56).
- **±5 en cualquier peso: el líder no cambia; el ranking es estable.**
- Umbral de cambio de líder: NGINX pasaría al primer lugar si C8 (funciones L7) pesara ≥ 24, C5
  (facilidad) ≥ 34 o C7 (madurez) ≥ 34; Traefik lideraría si C6 (descubrimiento dinámico) pesara ≥ 38.
  C1, C2, C3 y C4 no cambian el líder dentro de 0–100.

### Reflexión (debe aparecer en el informe)

HAProxy obtiene un puntaje superior a NGINX en criterios puramente de balanceo (checks activos y
métricas por backend en la versión libre). No se oculta: mostrarlo es la "reflexión coherente" que
pide la rúbrica. La selección de NGINX se justifica por: (1) es la **restricción del proyecto
asignado** (requisito del cliente); (2) queda en el **grupo líder** de la matriz, a 7 puntos y con
ranking estable; (3) aporta funciones L7 completas (servidor web, caché, TLS, limitación de tasa) en
un solo componente; y (4) sus debilidades **se mitigan en el diseño**: detección pasiva + reintentos
para C3, exporter + logs JSON enriquecidos + `/metrics` por réplica para C4, y `resolve` para C6.
Si se ejecuta A-05 (`compose.haproxy.yml`), C1 se respalda con datos medidos y la comparación queda
documentada en `results/`.

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
| Simplicidad operativa | 10 | Cualitativo: directivas extra, requisitos (p. ej. cabecera `X-Client-Id`) | Juicio del equipo: round_robin 5, least_conn 5, ip_hash 4, hash_remote_addr 4, random_two 4, hash_client 3 |

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
| hash_client | 5,0 (22 ms) | 1,0 (171 ms) | 5,0 (1,00) | 5,0 (0 %) | **5,0 (100 %)** | 3 | 76,0 |
| round_robin | 4,9 (22,5 ms) | 1,0 (171 ms) | 5,0 (1,00) | 5,0 (0 %) | 1,0 (0,1 %) | 5 | 71,6 |
| ip_hash | 4,8 (23 ms) | 1,0 (113,5 ms) | 1,7 (0,33) | 5,0 (0 %) | 5,0 (100 %) | 4 | 67,2 |

**Recomendación: `least_conn`.** Iguala a las demás con backends homogéneos y es la que mejor protege la
latencia cuando un backend se degrada.

**Análisis de sensibilidad** (cada peso ±5, redistribuido proporcionalmente): el líder **no cambia en
ningún caso**. Umbrales de cambio de líder: `hash_client` pasaría al primer lugar si la **afinidad de
sesión pesara 26/100 o más** (hoy 10), o si el criterio de backends heterogéneos pesara 0. Ningún otro
criterio, dentro de 0–100, cambia el líder.

**Contraste con las hipótesis:** homogéneos no distinguibles (confirmada); `least_conn` y `random_two`
protegen la cola con heterogeneidad de capacidad (confirmada en p95, no en p99); `ip_hash` concentra la
carga de una /24 (confirmada: Jain 0,33, y con un backend lento su resultado depende de a qué nodo cae la
/24). Resultado no previsto: `hash_client` sin datos heterogéneos llegó a liderar (94,7) solo porque los
pesos se renormalizaban; medir ese criterio lo bajó a 76,0. Por eso se exige ≥ 70/100 de peso medido.

---

## Matriz 4.3 — estrategia de descubrimiento de backends (decisión de diseño)

| Criterio (peso) | Servidores estáticos con nombre | DNS con `resolve` (elegida) | Regenerar config + reload |
|---|---|---|---|
| Escalar sin tocar la config (30) | 1: hay que editar y recargar | 5: automático vía DNS de Docker | 3: script externo |
| Pesos/backup por servidor (20) | 5: `weight` y `backup` por línea | 2: mismos parámetros para todas las réplicas | 5 |
| Simplicidad (20) | 4 | 4: requiere `zone` + `resolver` | 2: piezas extra |
| Robustez ante cambios (30) | 3 | 4: arranca aunque no resuelva | 3: depende del script |
| **Puntaje /100** | **60** | **78** | **64** |

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
| 0 (matriz original) | 60 | **78** | 64 | `resolve` |
| 10 | 64 | **72** | 68 | `resolve` |
| 15 | 66 | 69 | **69** | empate |
| 20 | 68 | 66 | **71** | regenerar + reload |

**Umbral:** si la afinidad estable ante escalado pesa **15 o más** sobre 100, conviene regenerar la
configuración y recargar (o servidores estáticos) en lugar de `resolve`. En este proyecto ningún requisito
del enunciado (R-01 … R-25) exige afinidad de sesión, y el escalado sin recarga (E-10: 0 errores al pasar
de 3 a 6 réplicas) sí es un objetivo, por lo que **se mantiene `resolve`** con hash simple para
`hash_client`. La reflexión queda registrada como lección de diseño para servicios con estado.
