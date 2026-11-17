# Matrices de decisión (generadas por analysis/decision_matrix.py)

Puntuación 1–5; pesos suman 100; puntaje = Σ(peso × puntuación) / 5 (sobre 100).

## Matriz 4.1 — tecnología de balanceo

| ID | Criterio | Peso | Cómo se mide | Escala 1–5 |
|---|---|---|---|---|
| C1 | Desempeño y eficiencia | 20 | Medido: misma carga (rampa.yml) contra el caso base mínimo de cada alternativa sobre las mismas 3 réplicas (corridas A05B, scripts/test-alternativas.sh); p99 de Artillery y CPU media del contenedor del balanceador | 5·(½·p99_mejor/p99 + ½·CPU_mejor/CPU), redondeado, mínimo 1 |
| C2 | Algoritmos de balanceo disponibles | 15 | Conteo de métodos en la documentación oficial de la versión libre | 5 ≥ 8 · 4 = 5–7 · 3 = 3–4 · 2 = 2 · 1 = 1 |
| C3 | Detección de fallos y tolerancia (versión libre) | 15 | Documentación oficial: checks activos, detección pasiva y reintentos en otro servidor | 5 = activos + pasivos + reintentos · 4 = dos de los tres · 3 = pasivos + reintentos · 2 = solo uno · 1 = ninguno |
| C4 | Observabilidad | 10 | Documentación oficial: métricas por servidor de backend en la versión libre | 5 = por servidor en Prometheus nativo · 4 = por servidor parcial o vía exportador estándar · 3 = por servidor solo en página/consola · 2 = solo globales · 1 = ninguna |
| C5 | Facilidad de configuración | 10 | Medido: líneas útiles (sin comentarios ni blancos) del caso base mínimo equivalente (alternativas/), comprobado funcionando: 30 peticiones, 3 nodos, 0 fallos (alternativas_c5.csv) | 5 ≤ 10 · 4 = 11–20 · 3 = 21–30 · 2 = 31–40 · 1 > 40 líneas |
| C6 | Integración con Docker / descubrimiento dinámico | 10 | Qué hay que hacer para que una réplica nueva reciba tráfico (en este proyecto: E-02/E-10 con `resolve`) | 5 = automático por la API/etiquetas de Docker · 4 = re-resolución DNS sin recargar · 3 = lista estática + recarga sin cortar conexiones · 2 = lista estática + reinicio · 1 = alta manual con comandos |
| C7 | Madurez, comunidad y documentación | 10 | Años desde la primera versión estable y versiones publicadas en los últimos 12 meses | 5 = ≥ 15 años y versiones recientes · 4 = ≥ 10 años, o ≥ 15 sin versiones recientes de la herramienta de usuario · 3 = 5–9 años · 2 = < 5 años · 1 = sin mantenimiento |
| C8 | Funciones L7 adicionales | 10 | Cuántas de 6 funciones trae la versión libre: servir estáticos, caché, TLS, limitación de tasa, reescritura/redirección, compresión | 5 = 6 · 4 = 5 · 3 = 4 · 2 = 2–3 · 1 = 0–1 |

**Evidencia de cada puntuación** (puntos: evidencia)

| Criterio | NGINX | HAProxy | Traefik | Apache | LVS |
|---|---|---|---|---|---|
| C1 | **5** · p99 35.7 ms · CPU 9.9 % · errores 0.00 % (n = 3) | **5** · p99 36.0 ms · CPU 10.9 % · errores 0.00 % (n = 3) | **3** · p99 41.2 ms · CPU 28.1 % · errores 0.00 % (n = 3) | **4** · p99 38.0 ms · CPU 19.6 % · errores 0.00 % (n = 3) | **5** · no medido (IPVS vive en el kernel del host); 5 por diseño: reenvío en el kernel, sin proxy en espacio de usuario |
| C2 | **4** · 7: round-robin, least_conn, ip_hash, hash, hash consistent, random, random two (least_time es libre solo desde 1.31) | **5** · 13: roundrobin, static-rr, leastconn, first, hash, source, uri, url_param, hdr, random, rdp-cookie, log-hash, sticky | **3** · 4: wrr, p2c, hrw, leasttime | **3** · 4: byrequests, bytraffic, bybusyness, heartbeat | **5** · 10: rr, wrr, lc, wlc, lblc, lblcr, dh, sh, sed, nq |
| C3 | **3** · pasiva (max_fails/fail_timeout) + reintentos (proxy_next_upstream); checks activos solo en NGINX Plus | **5** · activos (check), pasivos (observe) y reintentos (retries + redispatch) | **5** · activos (healthCheck), pasivos (passiveHealthCheck) y middleware retry | **5** · activos (mod_proxy_hcheck, ≥ 2.4.21), pasivos (worker en estado de error, retry) y maxattempts | **1** · ninguno propio: requiere keepalived o ldirectord |
| C4 | **2** · stub_status es global; por servidor solo en logs (exporter oficial, métricas globales) | **5** · exportador Prometheus integrado con métricas por servidor | **4** · Prometheus nativo; por servidor solo traefik_service_server_up (estado) | **3** · por miembro solo en balancer-manager (página HTML) | **4** · contadores por servidor real (ipvsadm --stats) y colector ipvs de node_exporter |
| C5 | **4** · 20 líneas (nginx.conf); funciona: 3 nodos, 0 fallos | **4** · 18 líneas (haproxy.cfg); funciona: 3 nodos, 0 fallos | **3** · 27 líneas (traefik.yml+traefik-dinamica.yml); funciona: 3 nodos, 0 fallos | **3** · 23 líneas (httpd.conf); funciona: 3 nodos, 0 fallos | **2** · 33 líneas (lvs-keepalived.conf); no ejecutado (requiere el módulo ip_vs del kernel del host) |
| C6 | **4** · `resolve` (libre desde 1.27.3) re-resuelve el DNS de Docker sin recargar (medido en E-02/E-10) | **4** · server-template + resolvers re-resuelven el DNS | **5** · proveedor Docker: descubre contenedores por etiquetas | **3** · BalancerMember estáticos; apachectl graceful recarga sin cortar | **1** · ipvsadm -a por cada servidor real |
| C7 | **5** · desde 2004; versión estable 1.30 en 2026 | **5** · desde 2001; 3.2 LTS con versiones en 2026 | **4** · desde 2015 (11 años); v3.7 en 2026 | **5** · httpd desde 1995, mod_proxy_balancer desde 2.2 (2005); 2.4.6x en 2026 | **4** · IPVS en el kernel desde 1998; ipvsadm sin versiones recientes |
| C8 | **5** · 6/6 | **4** · 5/6: no sirve archivos estáticos | **3** · 4/6: sin estáticos ni caché en la versión libre | **4** · 5/6: sin limitación de tasa de peticiones nativa (mod_ratelimit limita ancho de banda) | **1** · 0/6: balanceo de capa 4 |

C1 medido en las corridas A05B (scripts/test-alternativas.sh).

| Criterio (peso) | NGINX | HAProxy | Traefik | Apache | LVS |
|---|---|---|---|---|---|
| C1 (20) | 5 | 5 | 3 | 4 | 5 |
| C2 (15) | 4 | 5 | 3 | 3 | 5 |
| C3 (15) | 3 | 5 | 5 | 5 | 1 |
| C4 (10) | 2 | 5 | 4 | 3 | 4 |
| C5 (10) | 4 | 4 | 3 | 3 | 2 |
| C6 (10) | 4 | 4 | 5 | 3 | 1 |
| C7 (10) | 5 | 5 | 4 | 5 | 4 |
| C8 (10) | 5 | 4 | 3 | 4 | 1 |
| **Puntaje /100** | **81** | **94** | **74** | **76** | **62** |

**Ranking base:** HAProxy (94) > NGINX (81) > Apache (76) > Traefik (74) > LVS (62)

**Análisis de sensibilidad (±5 en cada peso, redistribuido proporcionalmente):** el líder NO cambia en ningún caso; el ranking es estable.

**Umbrales de cambio de líder** (peso del criterio, redistribuyendo el resto, a partir del cual otra alternativa pasa al primer lugar):

| Criterio | Peso base | Subiendo el peso | Bajando el peso |
|---|---|---|---|
| C1 | 20 | 100 → NGINX | no cambia |
| C5 | 10 | 100 → NGINX | no cambia |
| C6 | 10 | 56 → Traefik | no cambia |
| C7 | 10 | 100 → NGINX | no cambia |
| C8 | 10 | 46 → NGINX | no cambia |

NGINX obtiene 81/100 (2.º lugar, a 13 puntos de HAProxy). HAProxy gana por criterios puramente de balanceo (checks activos y métricas por servidor en la versión libre) y se reporta tal cual. NGINX se usa porque (1) es la tecnología asignada al proyecto, por lo que la matriz valida la elección en lugar de hacerla; (2) es la mejor alternativa en funciones L7 y desempeño medido; y (3) sus debilidades se mitigan en el diseño: detección pasiva + reintentos (C3), exporter + logs JSON + /metrics por réplica (C4) y `resolve` (C6).

## Matriz 4.2 — algoritmo de balanceo recomendado (con datos medidos)

| Criterio | Peso | Métrica, prueba de origen y normalización |
|---|---|---|
| Latencia p99, backends homogéneos | 20 | p99 (ms) en rampa.yml, media de repeticiones (M-05/ALG). Menor es mejor: 5·(mejor/valor), mín. 1 |
| Latencia p95, backends heterogéneos | 25 | p95 con un backend lento (E-03). Igual normalización. Se usa p95 y no p99: en E-03 el p99 lo fija el propio nodo lento (~5 % de las peticiones) y vale 171-173 ms con todas las políticas |
| Equidad de la distribución | 15 | Índice de Jain J sobre peticiones por backend (M-06). 5·J |
| Errores durante fallo de backend | 20 | % de respuestas no-2xx en la ventana de 30 s tras la falla (M-03/E-07). 5 si 0 %; 5·(1 − min(err,5 %)/5 %), mín. 1 |
| Afinidad de sesión | 10 | % de clientes que siempre caen en el mismo backend (log NGINX, client_id). 5·(%/100), mín. 1 |
| Simplicidad operativa | 10 | Líneas del archivo de la política (nginx/policies/, sin comentarios) y requisitos al cliente: 5 = 0–1 directiva sin parámetros · 4 = 1 directiva con parámetros · 3 = necesita mapas o variables extra · 2 = exige algo al cliente (cabecera propia) · 1 = componentes externos |

Celdas: puntuación 1–5 (valor medido: p99 en ms, Jain, % errores, % afinidad). Los criterios sin dato se excluyen y los pesos restantes se renormalizan a 100 (columna 'Pesos con dato').

| Política | Latencia p99, backends homogéneos (20) | Latencia p95, backends heterogéneos (25) | Equidad de la distribución (15) | Errores durante fallo de backend (20) | Afinidad de sesión (10) | Simplicidad operativa (10) | Puntaje /100 | Pesos con dato |
|---|---|---|---|---|---|---|---|---|
| round_robin | 4.9 (22.5) | 1.0 (171.0) | 5.0 (1.0) | 5.0 (0.0) | 1.0 (0.1) | 5.0 (5) | 71.6 | 100/100 |
| least_conn | 5.0 (22.0) | 5.0 (23.0) | 5.0 (1.0) | 5.0 (0.0) | 1.0 (0.3) | 5.0 (5) | 92.0 | 100/100 |
| ip_hash | 4.8 (23.0) | 1.0 (113.5) | 1.7 (0.3) | 5.0 (0.0) | 5.0 (100.0) | 5.0 (5) | 69.2 | 100/100 |
| hash_client | 5.0 (22.0) | 1.0 (171.0) | 5.0 (1.0) | 5.0 (0.0) | 5.0 (100.0) | 2.0 (2) | 74.0 | 100/100 |
| random_two | 5.0 (22.0) | 4.5 (25.5) | 5.0 (1.0) | 5.0 (0.0) | 1.0 (0.0) | 4.0 (4) | 87.5 | 100/100 |

**Algoritmo recomendado según los datos:** `least_conn` (92.0/100). Ranking entre las políticas con al menos 70/100 de peso medido: least_conn (92.0) > random_two (87.5) > hash_client (74.0) > round_robin (71.6) > ip_hash (69.2). Interpretar junto con `results/significancia.txt`: si la diferencia es menor que la desviación observada, las alternativas se declaran no distinguibles.

## Matriz 4.3 — estrategia de descubrimiento de backends (decisión de diseño)

| Criterio | Peso | Cómo se mide | Escala 1–5 |
|---|---|---|---|
| Escalar sin tocar la config | 30 | Pasos manuales para pasar de 3 a 5 réplicas (medido con `make scale N=5` en la CI y en E-10) | 5 = ninguno · 3 = un script automatizable + recarga · 1 = editar la configuración y recargar a mano |
| Pesos/backup por servidor | 20 | ¿Se puede dar `weight` o `backup` a una réplica concreta? | 5 = sí, por réplica · 2 = solo el mismo valor para todas · 1 = no |
| Simplicidad | 20 | Piezas que hay que mantener además de la plantilla de NGINX | 5 = ninguna y no cambia al escalar · 4 = 1–3 directivas extra fijas · 3 = la lista se edita en cada cambio · 2 = un componente externo (script o generador) · 1 = varios componentes |
| Robustez ante cambios | 30 | Qué pasa si una réplica desaparece o un nombre no resuelve al arrancar | 5 = arranca y se adapta sola · 4 = arranca y se adapta, con limitaciones conocidas (H-1, H-3) · 3 = no arranca si un nombre no resuelve (`host not found in upstream`) · 2 = depende de un proceso externo · 1 = requiere intervención |

| Criterio (peso) | Servidores estáticos con nombre | DNS con resolve (elegida) | Regenerar config + reload |
|---|---|---|---|
| Escalar sin tocar la config (30) | 1 | 5 | 3 |
| Pesos/backup por servidor (20) | 5 | 2 | 5 |
| Simplicidad (20) | 3 | 4 | 2 |
| Robustez ante cambios (30) | 3 | 4 | 2 |
| **Puntaje /100** | **56** | **78** | **58** |

Decisión: DNS con `resolve` para el stack principal; servidores estáticos con nombre solo para el experimento de pesos (`compose.weighted.yml`). Plan B si `resolve` fallara: generar `backend1…backendN` con un script.
