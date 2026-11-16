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
