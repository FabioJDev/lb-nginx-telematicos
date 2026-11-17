---
marp: true
theme: default
paginate: true
size: 16:9
header: "Servicios Telemáticos 2026-02 · Proyecto 2 · Grupo 3"
footer: "Balanceador de carga web con NGINX"
style: |
  section { font-size: 26px; }
  h1 { color: #009639; }
  h2 { color: #1f2937; }
  table { font-size: 20px; }
  .small { font-size: 18px; }
  .todo { color: #b91c1c; font-weight: bold; }
---

<!-- _class: lead -->
<!-- _paginate: false -->

# Balanceador de carga web con NGINX

### Clúster web contenedorizado, seis políticas de balanceo y pruebas de carga reproducibles con Artillery

**Fabio Jordan C. · Juan David Morales**
Servicios Telemáticos 2026-02 · Proyecto final 2 · Grupo 3 (Lista 1)

---

## Problema y objetivo

- Un único servidor web = **punto único de falla** + **techo de capacidad**: si cae, el servicio cae; si la demanda lo supera, la latencia crece hasta fallar.
- Un **balanceador L7** (proxy inverso) reparte las peticiones entre N backends equivalentes → escalado horizontal + tolerancia a fallos.

**Objetivo:** diseñar, implementar y evaluar experimentalmente un clúster web con balanceo NGINX, totalmente en Docker Compose, comparando algoritmos y caracterizando desempeño y resiliencia con Artillery.

---

## Conceptos del curso

| Concepto | En el proyecto |
|---|---|
| Sin balanceo vs con balanceo | E-01 (1 backend) vs 3, 5, 7 backends (E-02) |
| Balanceo L4 vs L7 | NGINX decide por cabeceras: `hash $http_x_client_id` es imposible en L4 |
| Proxy directo vs inverso | El cliente solo conoce al balanceador; backends sin puertos publicados |
| Round Robin, Leastconn, Source | `round_robin`, `least_conn`, `ip_hash` + `hash consistent`, `random two` |
| Alta disponibilidad y health checks | `max_fails`/`fail_timeout`, `proxy_next_upstream`, healthchecks Docker |
| Pruebas de carga con Artillery | usuarios concurrentes soportados y punto de quiebre (E-13) |

---

## Algoritmos de balanceo

| Política | Cómo decide | Advertencia |
|---|---|---|
| `round_robin` | turnos (ponderables) | ignora la carga real |
| `least_conn` | menos conexiones activas | ≈ RR con peticiones cortas |
| `ip_hash` | hash de la IP (**solo /24 en IPv4**) | toda una /24 → un backend |
| `hash_client` | hash **consistente** de `X-Client-Id` | el cliente debe enviar la cabecera |
| `random_two` | 2 al azar, el de menos conexiones | comparar con least_conn |

---

## Alternativas: matriz multicriterio 4.1

<div class="small">

| Criterio (peso) · cómo se mide | NGINX | HAProxy | Traefik | Apache | LVS |
|---|---|---|---|---|---|
| C1 Desempeño (20) · throughput/p99 mismo escenario, `docker stats` | 5 | 5 | 4 | 3 | 5 |
| C2 Algoritmos (15) · conteo en docs versión libre | 4 | 5 | 3 | 4 | 5 |
| C3 Detección de fallos (15) · activos+reintentos=5, pasivos=3 | 3 | 5 | 4 | 4 | 1 |
| C4 Observabilidad (10) · métricas por backend sin pago | 2 | 5 | 5 | 3 | 2 |
| C5 Facilidad (10) · líneas de config + encuesta | 4 | 3 | 4 | 3 | 2 |
| C6 Docker/descubrimiento (10) · réplicas nuevas sin reinicio | 4 | 4 | 5 | 2 | 1 |
| C7 Madurez (10) · años, releases, docs | 5 | 4 | 4 | 4 | 3 |
| C8 Funciones L7 (10) · estáticos, caché, TLS, rate limit | 5 | 3 | 3 | 4 | 1 |
| **Puntaje /100** | **81** | **88** | **79** | **68** | **56** |

</div>

---

## Sensibilidad y reflexión

- ±5 en cualquier peso: **el ranking no cambia**. NGINX lideraría solo si C8 ≥ 24, C5 ≥ 34 o C7 ≥ 34; Traefik si C6 ≥ 38.
- **HAProxy supera a NGINX** en balanceo puro (checks activos, métricas por backend). Lo decimos.
- NGINX se selecciona porque:
  1. es la restricción del proyecto asignado (requisito del cliente);
  2. queda en el grupo líder (−7 puntos, ranking estable);
  3. funciones L7 completas en un solo componente;
  4. las debilidades se **mitigan en el diseño**: detección pasiva + reintentos (C3), exporter + logs JSON + `/metrics` por réplica (C4), `resolve` (C6).
- Matriz 4.3 (descubrimiento): DNS con `resolve` 78 > regenerar+reload 64 > estáticos 60.

---

## Arquitectura

![h:420](../docs/diagramas/arquitectura.png)

<div class="small">Dos redes con nombre: <code>lbnginx_frontend</code> (publica :8080) y <code>lbnginx_backend</code> (<code>internal: true</code>). Config NGINX 100 % externa (volúmenes :ro + envsubst). Política = un archivo. Backend instrumentado (X-Backend-Node, fallos, /metrics).</div>

---

## Cumplimiento de requisitos (resumen)

<div class="small">

| Bloque | Requisitos | Evidencia |
|---|---|---|
| Infraestructura | R-07 upstream ≥ 3 · R-08 RR/least_conn/ip_hash · R-09 stub_status · R-10 timeouts/reintentos | `nginx/templates/http.conf.template`, `nginx/policies/` |
| Pruebas | R-11 rampa · R-12 comparación · R-13 fallos durante la prueba | `artillery/scenarios/`, `scripts/test-*.sh` |
| Docker | R-14 compose · R-15 nginx.conf volumen · R-16 redes/sin puertos · R-17 .env · R-18 Prometheus · R-19 override hot-reload · R-20 README | `docker-compose*.yml`, `monitoring/`, `README.md` |
| Mínimas | R-21 stub_status por algoritmo · R-22 resiliencia · R-23 1000 usuarios · R-24 media/p99 · R-25 logs | `results/`, `docs/figuras/` |

Más allá: 6 políticas, inyección de 7 modos de falla, escalado en caliente sin reload, Grafana aprovisionado, análisis automático, rate limiting, microcaché, comparativa HAProxy, CI.

</div>

---

## Demo en vivo (5 min)

1. `docker compose ps` → backends sin `0.0.0.0:`
2. Navegador `localhost:8080`: recargar → cambia nodo y color
3. Carga constante + Grafana: distribución por réplica en vivo
4. `make policy P=ip_hash` → todo a un backend (la /24) · `P=hash_client` → se reparte
5. `scripts/inject-fault.sh rm 1` → redistribución, error ≈ 0
6. `make scale N=5` → réplicas nuevas **sin reiniciar NGINX**

---

## Resultados: pruebas mínimas (3 repeticiones, GitHub Actions 2 vCPU)

| Prueba | Resultado medido |
|---|---|
| M-00 / M-02 reparto | 10/10/10 · 1000 secuenciales: 334/333/333, **Jain 1,000** |
| M-03 retirar un backend bajo 300 req/s | **100 % disponibilidad**, 0 errores, 3 reintentos, p99 22 ms estable |
| M-04 1000 usuarios concurrentes | 3/3 reps: **meseta de 1000 activos 60 s**, 0 fallidos, p99 ≤ 76 ms |
| M-05 round_robin vs least_conn vs ip_hash | media 20,30 / 20,35 / 20,33 ms · p99 22 ms → **no distinguibles** |
| M-06 logs vs Artillery | coincidencia **100 %**; ip_hash: **100 % a un solo backend** |

<div class="small">Fuente: results/ejemplos/lote-test-min-reps3-actions · el generador (Artillery) fue el cuello de botella: NGINX ≤ 14 % CPU.</div>

---

## Resultados: algoritmos y la trampa de ip_hash

![h:300](../docs/figuras/algoritmos_distribucion_M05.png)

- Homogéneos y peticiones baratas: **round-robin ≈ least_conn** (hipótesis confirmada).
- `ip_hash` usa la /24 → toda la carga de Artillery en un nodo. Afinidad correcta: **L7** con `hash $http_x_client_id`.

---

## Resultados: backends heterogéneos (E-03)

3 réplicas rápidas + 1 lenta (150 ms, 0,25 CPU):

| Política | Media | p95 | % al lento |
|---|---|---|---|
| round_robin | 58,2 ms | **171 ms** | 25 % |
| round_robin 3:1 | 35,5 ms | 171 ms | 10 % |
| **least_conn** | **27,1 ms** | **23 ms** | **4,5 %** |
| random_two | 27,9 ms | 25,5 ms | 4,9 % |

`least_conn` ve que el lento acumula conexiones y lo evita. Con peticiones que solo **esperan** (E-04) no hay diferencia: un temporizador no forma cola.

---

## Resultados: resiliencia (M-03 / E-07 / E-09)

![h:250](../docs/figuras/resiliencia_M03_round_robin.png)

<div class="small">

| Falla | Errores (30 s) | p99 |
|---|---|---|
| stop / kill / crash | **0** | 22 ms |
| pause / hang | 9 (0,1 %) | **10 s** (= proxy_read_timeout) |
| responde 500 | **3001 (33 %)** — NGINX no reintenta 500 | 22 ms |
| sin backends (E-09) | página de mantenimiento 30 s → recupera en **0,84 s** | — |

</div>

---

## Resultados: escalabilidad y punto de quiebre (E-02 / E-13)

![h:260](../docs/figuras/escalabilidad.png)

<div class="small">

Endpoint con 3 ms de CPU: goodput **170 → 271 → 472 → 783 req/s** para N = 1, 2, 3, 5 (error 81 % → 0 %), eficiencia 0,79–0,92. Quiebre (error < 1 %, p99 < 1 s): ~185 / 582 / 875 req/s con 1 / 3 / 5 réplicas.

</div>

---

## Hallazgos (lo que no estaba en el enunciado)

1. **`hash … consistent` + `resolve` no da afinidad** en NGINX 1.30.6 (0 % de clientes fieles). Hash simple: 100 %, pero al pasar de 5 a 4 réplicas **remapea al 84 %** de los clientes (E-06).
2. **Errores 500 y lentitud son invisibles** para la detección pasiva de NGINX OSS.
3. **`resolve` envía tráfico antes del healthcheck** de Docker.
4. `server.maxConnections = 0` en Node 24 = **cero** conexiones (lo detectó la CI).

→ Matriz 4.3: si la afinidad estable pesara ≥ 15/100, convendría regenerar la configuración en lugar de `resolve`.

---

## Matriz 4.2 y conclusiones

- **Algoritmo recomendado (con datos):** <span class="todo">___ (docs/decision-matrix-generada.md)</span>
- Homogéneos: no importa el algoritmo. Heterogéneos en **capacidad**: `least_conn` (p95 171 → 23 ms).
- Afinidad: en L7 con `hash $http_x_client_id`, sabiendo que escalar remapea la mayoría de las sesiones.
- Resiliencia: caídas sin errores; cuelgues cuestan el timeout; 500 requiere `proxy_next_upstream http_500`.
- Limitación: 2 vCPU → generador como cuello de botella; capacidad medida con costo de CPU.
- Trabajo futuro: HA del balanceador (keepalived/VRRP), health checks activos, TLS/HTTP2, Kubernetes.

---

<!-- _class: lead -->

# ¿Preguntas?

Repositorio: `lb-nginx-telematicos` · `make up && make smoke`
Referencias: NGINX docs (upstream, stub_status), Artillery docs, Little (1961), Jain (1984), Mitzenmacher (2001), Karger (1997)
