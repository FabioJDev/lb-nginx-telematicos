# Guion de presentación y sustentación (máximo 20 minutos)

| Min. | Bloque | Contenido | Diapositivas |
|---|---|---|---|
| 0–1 | Apertura | Problema (punto único de falla, techo de capacidad) y objetivo en una diapositiva | 1–2 |
| 1–3 | Conceptos | Proxy inverso, L4 vs L7, algoritmos (con un dibujo, no texto) | 3–4 |
| 3–5 | Selección de la alternativa | Matriz multicriterio 4.1, cómo se midió cada criterio, sensibilidad y reflexión (HAProxy > NGINX en balanceo puro) | 5–6 |
| 5–7 | Arquitectura | Diagrama, dos redes, decisiones clave (`resolve`, config externa, política = archivo) y cumplimiento R-01…R-25 | 7–8 |
| 7–12 | **Demo en vivo** | Ver guion abajo | 9 |
| 12–15 | Resultados | 3–4 gráficas: algoritmos (M-05), trampa de ip_hash (E-05), resiliencia (M-03), escalabilidad (E-02) | 10–13 |
| 15–16 | Conclusiones | Recomendación de algoritmo con datos (matriz 4.2) y limitaciones | 14 |
| 16–20 | Preguntas | Sustentación | — |

## Guion de la demo (ensayar y grabar un video de respaldo)

Antes de empezar: `make up && make monitoring-up` ya ejecutados; Grafana abierto en el dashboard;
una terminal con `make logs-lb` en segundo plano; `.env` con `LB_POLICY=round_robin`.

1. `docker compose ps` → los backends, PostgreSQL y Redis **no** muestran `0.0.0.0:`.
2. Navegador en <http://localhost:8080/nodo>: recargar 3–4 veces → cambia el nodo y el color (round-robin).
3. **La tienda** en <http://localhost:8080>: buscar "Router", iniciar sesión (`usuario1` / `clave123`),
   agregar 2 productos y comprar. El panel "Diagnóstico del balanceo" muestra que cada petición la
   atendió una réplica distinta y que el carrito se conserva (sesiones en Redis).
4. **Romper las sesiones a propósito:** `make sesiones S=memory` (round-robin activo) → en la tienda,
   iniciar sesión y agregar al carrito → aviso "Sesión perdida: la réplica X no conoce tu sesión".
   `make policy P=sticky_cookie` → recargar, iniciar sesión otra vez → el carrito se conserva porque
   NGINX fija al cliente con su cookie `lbid`. `make sesiones S=redis` para volver.
5. `make smoke` → 10/10/10.
4. Lanzar carga: `scripts/run-test.sh DEMO constante.yml &` → en Grafana se ve la distribución por réplica.
5. `make policy P=ip_hash` → en Grafana todo el tráfico cae en **un** backend; explicar la `/24`.
   `make policy P=hash_client` → se reparte de nuevo y cada cliente mantiene su backend.
6. Durante la carga: `scripts/inject-fault.sh rm 1` → el tráfico se redistribuye; en Grafana la anotación
   roja y la tasa de error cercana a cero; `make status` muestra 2 réplicas.
7. `make scale N=5` → las réplicas nuevas aparecen en Grafana **sin reiniciar NGINX** (resolve).
8. (Si hay tiempo) editar `nginx/policies/round_robin.conf` y mostrar `[watcher] … recargado` en los logs.

Nota: con los pasos 3 y 4 la demo pasa de 5 a ~7 minutos; si falta tiempo, omitir el paso 8.

## Preguntas probables del jurado

| Pregunta | Respuesta corta |
|---|---|
| ¿Qué pasa con las sesiones de usuario si el balanceador reparte por turnos? | Si viven en la memoria de cada réplica, se pierden (E-16 lo mide); la solución es afinidad (`hash_client`, `sticky_cookie`) o un almacén compartido (Redis), que es lo recomendado. |
| ¿Por qué no hacer hash de la cookie de sesión de la aplicación? | El login llega sin cookie y cae en un nodo cualquiera; luego `hash(sid)` apunta a otro. La cookie de afinidad debe emitirla el balanceador (hallazgo H-6). |
| ¿Escalar backends escala la base de datos? | No: todas las réplicas comparten PostgreSQL (E-17); por eso la caché (A-02) y el pool de conexiones importan. |
| ¿Qué hace el balanceador si cae la base de datos? | Nada puede hacer: todas las réplicas fallan igual; los reintentos de `proxy_next_upstream` multiplican la carga (E-18). |

| Pregunta | Respuesta corta |
|---|---|
| ¿Por qué ip_hash mandó todo a un solo backend? | Usa los tres primeros octetos IPv4; los clientes de la prueba comparten la `/24` de Docker. Solución L7: hash por cabecera (`hash_client`) o cookie. |
| ¿NGINX revisa activamente si un backend está vivo? | En la versión libre no (checks activos son de NGINX Plus); usamos detección pasiva `max_fails`/`fail_timeout` + reintentos `proxy_next_upstream`, y healthchecks de Docker. |
| ¿Por qué round-robin y least_conn dan casi lo mismo? | Con backends y peticiones homogéneos las conexiones activas están balanceadas; la diferencia aparece con heterogeneidad (E-03/E-04). |
| ¿Se reintenta un POST si falla el backend? | No por defecto: NGINX no reenvía peticiones no idempotentes ya enviadas, para evitar efectos duplicados (`proxy_next_upstream non_idempotent` lo cambiaría). |
| ¿Qué limita sus resultados? | Un solo host comparte CPU entre generador, balanceador y backends; lo medimos con `docker stats` y lo reportamos. |
| ¿Cómo garantizan 1000 usuarios concurrentes con Artillery? | Ley de Little: 1000 llegadas en 10 s con sesiones de ~70 s → meseta de ~1000 activos durante más de 60 s (gráfica de usuarios activos). |
| ¿Y si cae el balanceador? | Es un punto único de falla; la solución es un par activo/pasivo con IP flotante (keepalived/VRRP), trabajo futuro (A-04). |
| ¿Por qué `stub_status` no muestra el reparto por backend? | Es global por diseño; el reparto se obtiene del log JSON (`$upstream_addr`, `X-Backend-Node`), de `/metrics` por réplica y de los contadores de Artillery. |
| ¿Qué pasa con un backend que responde 500? | No se reintenta por defecto (`proxy_next_upstream` solo cubre error/timeout/502/503/504); E-08 muestra el efecto de añadir `http_500`. |
| ¿Cómo escalan sin recargar NGINX? | `server backend:3000 resolve` + `resolver 127.0.0.11 valid=5s`: NGINX re-resuelve el DNS de Docker, que devuelve todas las IPs de las réplicas. |
