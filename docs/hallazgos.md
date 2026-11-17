# Hallazgos técnicos durante la implementación

Problemas reales encontrados al ejecutar el sistema, con su evidencia, causa y solución. Sirven para
la sección de discusión del informe y para la sustentación.

## H-1 · `hash … consistent` no da afinidad cuando el upstream usa `resolve`

**Síntoma.** En la primera ejecución de E-05 (`results/ejemplos/lote-E05-actions/`, ejecución
43958925688), las políticas `hash_client` (`hash $http_x_client_id consistent`) y `hash_remote_addr`
(`hash $remote_addr consistent`) repartieron como round-robin:

| Política (versión con `consistent`) | Jain (3 nodos) | % al backend más cargado | Clientes fieles a un backend |
|---|---|---|---|
| hash_client | 1,000 | 33,3 % | 0,13–0,19 % |
| hash_remote_addr | 1,000 | 33,3 % | 0,21 % |
| ip_hash (control) | 0,333 | 100 % | 100 % |

Con `hash_remote_addr` el resultado es imposible para un hash que funcione: todas las peticiones
venían de la misma IP (`172.18.0.3`) y aun así se repartieron 16 669 / 16 667 / 16 665 entre los tres
backends.

**Verificación aislada.** El paso "Afinidad de sesión por política" de la CI
(`scripts/check-affinity.sh`: 30 clientes lógicos × 5 peticiones, misma IP) lo confirma:

| Política | Clientes fieles a un backend | Backends distintos |
|---|---|---|
| round_robin | 0 % | 3 |
| ip_hash | 100 % | 1 |
| `hash $http_x_client_id consistent` | **0 %** | 3 |
| `hash $http_x_client_id` (simple) | **100 %** | 3 |
| `hash $remote_addr consistent` | **0 %** | 3 |

**Causa probable.** El método `consistent` (ketama) precalcula un anillo de puntos a partir de la
lista de servidores **al cargar la configuración**. Con `server backend:3000 resolve`, en ese momento
el nombre todavía no tiene direcciones (las aporta el resolver después), así que el anillo queda vacío y
el módulo recurre al reparto por turnos. El hash simple, en cambio, se calcula en cada petición sobre los
*peers* vigentes, por lo que sí funciona con `resolve`. `ip_hash` tampoco depende de un anillo
precalculado y funciona.

**Solución aplicada.** `hash_client` y `hash_remote_addr` usan ahora hash simple (afinidad 100 %
verificada). Se conserva `hash_client_consistent.conf` para reproducir el hallazgo.

**Costo medido (E-06).** Con hash simple, al retirar 1 de 5 réplicas cambió de backend el **84 %**
de 200 clientes fijos (teoría del hash por módulo: 80 %), frente al ≈ 20 % que remapearía un hash
consistente funcional (`scripts/check-remap.sh`, CI 43984410914).

**Consecuencia de diseño (matriz 4.3).** Elegir descubrimiento DNS con `resolve` tiene un costo no
previsto: renuncia al hash consistente. Con hash simple, al cambiar el número de réplicas se remapea la
mayoría de los clientes (no solo ~1/N). Si la afinidad estable ante escalado fuera un requisito, habría
que usar servidores estáticos con nombre (opción 1 de la matriz 4.3) o regenerar la configuración y
recargar (opción 3). La matriz se actualiza con este criterio.

## H-2 · `server.maxConnections = 0` rechazaba todas las conexiones del backend

En la primera ejecución real (CI), los tres backends quedaron `unhealthy` y el stack no arrancó. En
Node.js 24, `server.maxConnections = 0` significa "cero conexiones permitidas", no "sin límite". Se
eliminó la línea. Evidencia: ejecución de CI fallida y su corrección en el historial de git.

## H-3 · El healthcheck de Docker no gobierna el tráfico de NGINX

En M-03 la réplica repuesta empezó a recibir tráfico **antes** de que Docker la marcara `healthy`:
`resolve` la incorpora en cuanto el DNS de Docker devuelve su IP (≤ 5 s), sin consultar el
healthcheck. En este proyecto no causó errores porque el backend arranca en milisegundos, pero una
aplicación con arranque lento recibiría peticiones antes de estar lista. La detección pasiva
(`max_fails`) y los reintentos lo mitigan; la solución completa son checks activos (NGINX Plus) o un
readiness gate externo.

## H-4 · Errores 500 y lentitud son invisibles para la detección pasiva

E-07 (`results/ejemplos/lote-E07-actions/`): un backend que responde 500 produjo 3001 errores al
cliente en 30 s (33,3 %, uno de cada tres) sin ningún reintento, y uno que tarda 2 s elevó el p99 a
2022 ms sin ser marcado como caído. `proxy_next_upstream` por defecto solo cubre `error` y `timeout`
(más los códigos 502/503/504 que configuramos). Ver la discusión en `docs/resultados-extendidos.md`.

## H-5 · Con 2 vCPU el generador de carga es el cuello de botella

En todas las corridas de GitHub Actions Artillery consumió 43–114 % de CPU mientras NGINX no pasó del
18 % y los backends del 16 %. Las cifras de capacidad con el endpoint de espera (`ms=20`) miden al
generador; por eso E-02 y E-13 se repitieron con costo de CPU (`ms=20&cpu=3`).

## H-6 · La afinidad no puede basarse en la cookie de sesión de la aplicación

**Síntoma.** La primera versión de la política `sticky_cookie` hacía `hash $cookie_sid` (la cookie
de sesión que crea la tienda al iniciar sesión). En la prueba de la CI con sesiones en memoria
perdió la sesión en **4 de 5 compras**, igual que round-robin (ejecución de CI fallida del
17-nov-2026, paso "Sesiones en memoria sin y con afinidad").

**Causa.** El login llega **sin** cookie, así que NGINX lo envía a un nodo cualquiera y ese nodo crea
la sesión. Las peticiones siguientes llevan `sid`, pero `hash(sid)` apunta a un nodo que **no** tiene
por qué ser el que creó la sesión: la clave de afinidad no existía cuando se tomó la primera decisión.

**Solución aplicada.** La cookie de afinidad la emite **el balanceador**, no la aplicación: en la
primera respuesta NGINX añade `lbid=$request_id` (el mismo valor que usó para elegir el nodo) y desde
entonces hace `hash $cookie_lbid`, que siempre devuelve ese nodo. Es lo que hacen el *sticky cookie*
de NGINX Plus y la directiva `cookie` de HAProxy. Con el cambio, la CI completó **5 de 5 compras** con
sesiones en memoria.

**Lección.** La afinidad debe decidirse con una clave que exista **desde la primera petición** del
cliente: una cabecera propia (`X-Client-Id`), la IP o una cookie emitida por el balanceador.

## H-7 · HAProxy solo expande variables de entorno entre comillas dobles

`balance ${HAPROXY_BALANCE}` falló la validación (`haproxy -c`) con "balance only supports
'roundrobin', …": HAProxy no expande variables fuera de comillas dobles. Se corrigió a
`balance "${HAPROXY_BALANCE}"`. Lo detectó el paso de validación añadido a la CI antes de
ejecutar la comparativa A-05.

## H-8 · El 503 de una dependencia caída hace que NGINX descarte réplicas sanas

**Síntoma.** E-18 (PostgreSQL caído 30 s): el p99 durante la caída fue de 0 ms y casi no hubo
reintentos; al volver la base de datos, el servicio siguió fallando **6,3 s más**. E-19 (Redis caído
30 s): además de login y carrito, falló el **catálogo**, que no usa Redis (357 errores 5xx).

**Causa.** Cuando falla una dependencia, la aplicación responde `503`. Con
`proxy_next_upstream error timeout http_502 http_503 http_504`, NGINX cuenta cada 503 como un intento
fallido; tras `max_fails=3` en `fail_timeout=10s` marca la réplica como caída. Como **todas** las réplicas
dependen de la misma base de datos o del mismo Redis, todas acumulan fallos y NGINX responde
"no live upstreams" (502 inmediato, `upstream_addr = backend_pool`) incluso a rutas que funcionarían.
Al recuperarse la dependencia, las réplicas siguen excluidas hasta que vence el `fail_timeout`.

**Consecuencia.** La detección pasiva confunde "mi dependencia está caída" con "este backend está caído":
deshace la degradación parcial de la aplicación (E-19) y alarga la recuperación (E-18). Por el lado
bueno, evita una tormenta de reintentos contra la base de datos.

**Corrección medida y adoptada.** No incluir `http_503` en `proxy_next_upstream`
(`LB_NEXT_UPSTREAM="error timeout http_502 http_504"`, ahora el valor por defecto): las caídas de
proceso siguen detectándose por `error`/`timeout`, y el 503 de la aplicación llega al cliente sin que
NGINX castigue a la réplica. Resultado (`results/ejemplos/lote-E18B-actions/`, `lote-E19B-actions/`):

| | E-18 | E-18B | E-19 | E-19B |
|---|---|---|---|---|
| Peticiones respondidas con "no live upstreams" durante la caída | 99,9 % | **0 %** | 27,5 % | **0 %** |
| Errores del catálogo durante la caída | 100 % | 100 % | 27,8 % | **0 %** |
| Recuperación tras volver la dependencia | 6,3 s | **1,3 s** | 3,0 s | 2,8 s |
| Errores en toda la corrida | 23,2 % | **13,4 %** | 8,8 % | **3,3 %** |

Con PostgreSQL caído siguen fallando todas las peticiones (nada puede compensarlo), pero el servicio
vuelve en 1,3 s en lugar de 6,3 s. Con Redis caído el catálogo sigue funcionando: se conserva la
degradación parcial que hace la aplicación.

## H-9 · Los cambios de `.env` a mitad de un lote no llegaban a los scripts hijos

**Síntoma.** E-08 (timeouts × reintentos) dio resultados idénticos en sus cuatro configuraciones. Los
`metadata.json` lo delataron: las cuatro registraban `LB_READ_TIMEOUT=10s` y el mismo
`proxy_next_upstream`.

**Causa.** `load_env` exportaba el `.env` al iniciar el lote. Cuando `set-env.sh` lo modificaba, los
scripts hijos (por ejemplo `set-policy.sh`, que recrea NGINX) heredaban el valor viejo, y en Compose el
entorno tiene prioridad sobre el `.env`.

**Corrección.** `load_env` refresca desde el `.env` actual los valores heredados de una carga anterior y
respeta los fijados explícitamente; la función `compose` relee el `.env` antes de cada llamada. Además,
`metadata.json` registra ahora la configuración **efectiva** leída de NGINX (`nginx_effective`). Se
verificó que E-12, A-02 y E-16 no estaban afectadas: sus metadatos muestran la configuración aplicada
(`keepalive`, `feature`, `SESSION_STORE`). E-08, E-18B y E-19B se repitieron.

## H-10 · El tiempo de respuesta de Artillery no incluye la conexión

**Síntoma.** En A-03, HTTP y HTTPS dieron el mismo p95 (22 ms) aunque HTTPS hace un handshake TLS por
cada usuario. En A-04, el p99 apenas subió durante el failover, aunque la sonda propia dejó de recibir
respuestas durante ≈ 3,5 s.

**Causa.** `http.response_time` empieza cuando la conexión ya está abierta: no incluye DNS, TCP ni TLS.
Lo que pasa antes (el handshake, o los reintentos de SYN mientras la IP flotante cambia de dueño) solo
aparece en `vusers.session_length`, que mide toda la sesión del usuario virtual.

**Consecuencia.** `analysis/avanzadas.py` reporta la duración de la sesión junto al tiempo de respuesta
(A-03: +1,3 ms en la mediana con HTTPS; A-04: sesiones de hasta ≈ 4 s durante el failover) y la sonda
de A-04 usa una conexión nueva por petición. Al comparar protocolos o medir conmutaciones no basta con el
tiempo de respuesta.

## H-11 · Con preempción, la vuelta del balanceador principal provoca un segundo corte

**Síntoma.** En A-04, al volver `lb` después del kill, Artillery registró 8–11 errores `ECONNRESET`,
aunque los dos balanceadores estaban sanos.

**Causa.** VRRP por defecto es *preemptivo*: el nodo de más prioridad recupera la IP flotante en cuanto
vuelve. Las conexiones que estaban abiertas con `lb2` a través de la VIP llegan entonces a `lb`, que no las
conoce, y se cortan.

**Corrección medida y adoptada.** `nopreempt` en keepalived (`HA_PREEMPT=off`): la VIP se queda en `lb2` y
`lb` vuelve como respaldo. Resultado (`results/ejemplos/lote-A04-actions/`): errores al volver
9 ± 2 → **0**, con el mismo tiempo de failover (3,71 ± 0,12 s frente a 3,50 ± 0,11 s). Es el valor por
defecto de `compose.ha.yml`; `scripts/test-ha.sh` mide ambas variantes.
