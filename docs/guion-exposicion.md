# Guion de la exposición (25 minutos)

Proyecto 2 · Balanceador de carga web con NGINX · Grupo 3
Presentan: **Fabio Jordan C.** (primera mitad) y **Juan David Morales** (segunda mitad).
Diapositivas: `slides/presentacion.pdf`. La demo en vivo tiene su propio guion: [`guion-demo.md`](guion-demo.md).

## Reparto del tiempo

| Minuto | Quién | Diapositivas | Bloque |
|---|---|---|---|
| 0:00 – 9:15 | **Fabio** | 1 – 10 | Apertura, requisitos, selección, diseño, metodología y pruebas mínimas |
| 9:15 – 17:45 | **Juan David** | 11 – 19 | Algoritmos, escalabilidad, fallas, matriz 4.2, tienda, mejoras, hallazgos y conclusiones |
| 17:45 – 23:45 | **Ambos** | 20 | Demo en vivo (Fabio pasos 1–4, Juan David pasos 5–8) |
| 23:45 – 25:00 | **Ambos** | 21 | Cierre y preguntas; diapositivas 22–24 solo si las piden |

Ritmo de referencia: unas 130 palabras por minuto. El texto es una guía para decirlo con sus palabras,
no para leerlo. Las cifras sí deben decirse tal cual: todas salen de `results/ejemplos/`.

---

## Parte 1 · Fabio Jordan C.

### Diapositiva 1 · Portada · 0:30 (0:00 – 0:30)

> Buenos días. Soy Fabio Jordan y él es Juan David Morales, del grupo 3. Nuestro proyecto es un
> balanceador de carga web con NGINX: un clúster contenedorizado con siete políticas de balanceo,
> una tienda con base de datos detrás y pruebas de carga reproducibles con Artillery. Yo presento la
> primera mitad, el diseño y las pruebas mínimas, y Juan David la segunda, las pruebas extendidas, la
> tienda y las conclusiones. Al final hacemos la demo en vivo.

### Diapositiva 2 · El proyecto en cifras · 1:00 (0:30 – 1:30)

> Antes de entrar en detalle, este es el resumen. Cumplimos los 25 requisitos del enunciado y cada uno
> tiene evidencia. Hicimos 195 corridas reales, organizadas en 36 lotes, y todas están en el repositorio.
> Algunos resultados: al retirar un backend con 300 peticiones por segundo hubo cero errores; sostuvimos
> mil usuarios concurrentes durante 60 segundos sin un solo fallo; con un backend lento, `least_conn`
> bajó el percentil 95 de 171 a 23 milisegundos; y con cinco réplicas el sistema atendió 4,6 veces más.
> En la tienda, con sesiones en Redis, el 100 % de las compras se completó. Y el propio balanceador
> deja de ser un punto único de falla: el respaldo toma el control en 3,5 segundos.

*Señalar:* la fila de abajo (−77 %, 100 %, 3,5 s); Juan David la explica después.

### Diapositiva 3 · Problema, objetivo y conceptos · 0:45 (1:30 – 2:15)

> El problema es conocido: un solo servidor web es un punto único de falla y tiene un techo de capacidad.
> La solución es un balanceador de capa 7, un proxy inverso que reparte las peticiones entre varios
> backends iguales. Nuestro objetivo fue construirlo con NGINX, todo en Docker Compose, y medir cómo se
> comporta. A la derecha están los conceptos del curso y dónde se ven: por ejemplo, el hash por una
> cabecera HTTP solo es posible en capa 7, y los backends no publican puertos, solo el proxy.

### Diapositiva 4 · Requisitos del enunciado → evidencia · 1:00 (2:15 – 3:15)

> Esta tabla toma los requisitos del catálogo, uno por uno, y muestra cómo se cumplen y dónde está la
> evidencia. NGINX con un `upstream` de tres backends, los tres algoritmos pedidos más cuatro adicionales,
> `stub_status`, timeouts y reintentos, Artillery con rampa, la comparación de algoritmos y las fallas
> de backends. Del lado de Docker: el `nginx.conf` montado como volumen, la red con nombre y los backends
> sin puertos, el `.env` con workers, puerto y política, Prometheus con Grafana y la recarga en caliente.
> Abajo, las cinco pruebas mínimas: todas cumplen y las vamos a ver en un momento.

### Diapositiva 5 · Selección de la tecnología: matriz 4.1 · 1:15 (3:15 – 4:30)

> Para elegir la tecnología seguimos un proceso estructurado. Comparamos NGINX, HAProxy, Traefik, Apache
> y LVS con ocho criterios con peso. Lo importante es que cada criterio dice cómo se mide y tiene una
> escala de 1 a 5 con umbrales que fijamos antes de puntuar. Dos criterios los medimos nosotros: para el
> desempeño montamos la configuración mínima de cada balanceador y les aplicamos la misma carga; para la
> facilidad contamos las líneas de esa configuración, comprobada funcionando. Los demás salen de la
> documentación oficial, por ejemplo el número de algoritmos de la versión libre.

*Señalar:* la tabla de la derecha: NGINX 35,7 ms y HAProxy 36,0 ms de p99, prácticamente iguales.

### Diapositiva 6 · Reflexión de la matriz y descubrimiento · 1:00 (4:30 – 5:30)

> Y aquí está la reflexión, que es honesta: la matriz no elige NGINX. HAProxy gana por 13 puntos, por
> criterios de balanceo puro: tiene checks activos y pasivos, más algoritmos y métricas por servidor en
> la versión libre. El resultado es estable: moviendo cualquier peso cinco puntos, no cambia. NGINX es un
> requisito del cliente, porque el enunciado lo asigna, así que la matriz valida la elección y nos dice
> qué compensar en el diseño. Sin esa restricción, recomendaríamos HAProxy. La segunda matriz decide
> cómo descubrir los backends: elegimos DNS con `resolve`, que permite escalar sin recargar NGINX.

### Diapositiva 7 · Arquitectura e implementación · 1:00 (5:30 – 6:30)

> La arquitectura tiene dos redes con nombre. En la red frontend solo el balanceador publica un puerto,
> el 8080. La red backend es interna: las réplicas, PostgreSQL y Redis no tienen salida al host ni a
> Internet. Toda la configuración de NGINX es externa: se monta en solo lectura y se genera desde
> plantillas con el `.env`. Este es el `upstream`: la política es un archivo que se incluye, y `resolve`
> hace que NGINX vuelva a preguntar al DNS de Docker cada cinco segundos. Cambiar de algoritmo es un
> comando, `make policy`, y escalar es `make scale`, sin reiniciar el balanceador.

### Diapositiva 8 · Metodología y observabilidad · 0:45 (6:30 – 7:15)

> Para que los resultados sean confiables, todo corre en contenedores, también Artillery y el análisis.
> Cada prueba se repite tres veces en orden aleatorio, descartamos los primeros 30 segundos y cada corrida
> guarda la configuración que NGINX tenía realmente. Si la diferencia entre dos algoritmos es menor que la
> desviación, decimos que no se distinguen. Y para ver el sistema en vivo tenemos Grafana, alimentado por
> `stub_status` y por las métricas de cada réplica.

### Diapositiva 9 · M-00 a M-02 y M-06: así reparte cada algoritmo · 1:00 (7:15 – 8:15)

> Primera prueba mínima: el reparto. Estas son tres visitas seguidas a la página `/nodo` con round-robin:
> cada una la atiende un nodo distinto, de otro color. Con carga, round-robin reparte exactamente 7 500
> respuestas a cada réplica, y lo mismo se ve en Grafana arriba a la derecha: tres líneas a 100 peticiones
> por segundo. Pero mire `ip_hash`, abajo: una sola réplica recibe las 300 peticiones. No es un error: la
> carga sale de una sola IP, y `ip_hash` decide por la red de origen. Además verificamos que el log de
> NGINX coincide al 100 % con lo que contó Artillery.

### Diapositiva 10 · M-03 y M-04: resiliencia y mil usuarios · 1:00 (8:15 – 9:15)

> Las otras dos pruebas mínimas. A la izquierda, eliminamos una réplica en caliente con 300 peticiones por
> segundo: la línea vertical es el momento de la falla. Disponibilidad del 100 %, cero errores: NGINX
> reintentó tres peticiones en otro backend y la latencia no se movió. A la derecha, mil usuarios
> concurrentes: diseñamos la prueba con la ley de Little, mil llegadas en diez segundos con sesiones de
> unos 70 segundos, y se ve la meseta de mil usuarios activos durante 60 segundos, sin fallos, en las tres
> repeticiones.
>
> **Relevo:** Ahora Juan David les cuenta cuándo importa el algoritmo y qué pasó con una aplicación real.

---

## Parte 2 · Juan David Morales

### Diapositiva 11 · M-05 y E-03: ¿cuándo importa el algoritmo? · 1:00 (9:15 – 10:15)

> Gracias. La pregunta clave del proyecto es cuándo importa el algoritmo. A la izquierda, la prueba mínima
> con backends iguales: round-robin, `least_conn` e `ip_hash` dan 20,3 milisegundos de media y 22 de p99.
> No se distinguen. A la derecha cambiamos una cosa: uno de los backends es lento. Ahí round-robin le sigue
> mandando un cuarto del tráfico y el p95 sube a 171 milisegundos. `least_conn` nota que ese backend
> acumula conexiones, le manda solo el 4,5 % y el p95 baja a 23 milisegundos. Conclusión: con backends
> iguales da igual; con capacidad distinta, `least_conn`.

### Diapositiva 12 · E-02 y E-13: escalabilidad y punto de quiebre · 0:50 (10:15 – 11:05)

> ¿Escala? Con una petición que consume tres milisegundos de CPU, una réplica atiende 170 peticiones por
> segundo y rechaza el 81 % de la carga. Con cinco réplicas atiende 783 y cero errores: 4,6 veces más, con
> una eficiencia entre 0,79 y 0,92. Con siete ya sobra capacidad. Y el punto de quiebre, la carga máxima
> con menos del 1 % de error, pasa de 185 a 875 peticiones por segundo de una a cinco réplicas.

### Diapositiva 13 · Fallas y operación en caliente · 1:00 (11:05 – 12:05)

> Probamos siete formas de fallar. Si un backend se cae, se detiene o se reinicia, cero errores: NGINX
> reintenta en otro. Si se cuelga, cada petición paga el timeout; y si responde 500, el 33 % falla, porque
> NGINX no reintenta un 500 por defecto. Con el timeout también hay que tener cuidado: con 3 segundos y
> reintentos, cero errores; con 10 segundos, el nodo colgado nunca se marca como caído. A la derecha, la
> operación en caliente: escalar, recargar la configuración y un pico de 16 veces la tasa, todo sin
> errores, y 15 minutos seguidos con 360 000 peticiones sin un fallo.

### Diapositiva 14 · Matriz 4.2: algoritmo recomendado · 0:50 (12:05 – 12:55)

> Con estos resultados llenamos la segunda matriz, que elige el algoritmo, y todos sus criterios están
> medidos. Gana `least_conn` con 92 sobre 100: empata con los demás cuando los backends son iguales y es
> el que mejor protege la latencia cuando uno se degrada. Es estable: solo si la afinidad de sesión pesara
> 27 o más, ganaría `hash_client`.

### Diapositiva 15 · TelemaShop: ¿sobrevive la sesión al balanceo? · 1:00 (12:55 – 13:55)

> El profesor nos recomendó probar con una aplicación real, con funcionalidades y base de datos. Hicimos
> TelemaShop: catálogo de 2000 productos, login, carrito y compra sobre PostgreSQL. La pregunta fue:
> ¿sobrevive la sesión al balanceo? Si la sesión vive en la memoria de cada réplica, con round-robin el
> 98 a 99 % de los recorridos pierde la sesión y solo un 20 % termina la compra. Con afinidad, por ejemplo
> la cookie que emite el propio balanceador, el 100 %. Y con las sesiones en Redis, el 100 % con cualquier
> algoritmo. Con estado, importa más dónde vive la sesión que el algoritmo.

### Diapositiva 16 · La base de datos compartida · 1:00 (13:55 – 14:55)

> Pero aparece un nuevo cuello de botella. Al pasar de una a cinco réplicas, la CPU de cada réplica baja,
> pero PostgreSQL sigue en 23 %: escalar backends no escala la base de datos. Lo que sí funcionó fue una
> microcaché de un segundo en NGINX, solo para el catálogo público: redujo la CPU de PostgreSQL un 77 %.
> Y encontramos un problema real: cuando caía una dependencia, la aplicación respondía 503 y NGINX lo
> interpretaba como réplica caída, así que descartaba réplicas sanas. Lo corregimos y la recuperación
> bajó de 6,3 a 1,3 segundos.

### Diapositiva 17 · Mejoras avanzadas · 1:15 (14:55 – 16:10)

> Implementamos y medimos las seis mejoras avanzadas. Limitación de tasa: un cliente abusivo recibió un
> 36 % de rechazos, justo lo que predice el límite, y los clientes normales ninguno. TLS 1.3 con HTTP/2:
> la latencia no cambia, el costo es CPU del balanceador. Alta disponibilidad: dos NGINX con keepalived y
> una IP flotante; al matar el activo, el respaldo responde en 3,5 segundos con 99,95 % de disponibilidad,
> y con `nopreempt` la vuelta del principal no corta ninguna conexión. La comparativa con HAProxy,
> Traefik y Apache alimentó la matriz. Y la integración continua prueba todo esto en cada cambio.

### Diapositiva 18 · Hallazgos · 0:50 (16:10 – 17:00)

> Estas son cosas que no estaban en el enunciado y que solo aparecieron al medir. Las más importantes: el
> hash consistente no mantiene la afinidad cuando NGINX resuelve los backends por DNS; la afinidad no puede
> basarse en la cookie de la aplicación, porque el login llega sin cookie; el 503 de una dependencia tumba
> réplicas sanas; y la conmutación con preempción corta las conexiones dos veces. Cada uno está documentado
> con su evidencia y su corrección.

### Diapositiva 19 · Conclusiones · 0:45 (17:00 – 17:45)

> Para cerrar: el balanceo aporta disponibilidad, cero errores al perder un backend, y capacidad casi
> lineal. Con backends iguales el algoritmo no importa; con capacidad distinta, `least_conn`, que es
> nuestra recomendación. En un servicio real importa más dónde vive la sesión: Redis con `least_conn`, o
> `sticky_cookie` si la sesión no puede salir de la réplica. La base de datos no escala sola, la
> microcaché sí la alivia, y con keepalived el balanceador deja de ser un punto único de falla.
> Ahora lo vemos funcionando.

---

## Demo en vivo · Diapositiva 20 · 6:00 (17:45 – 23:45)

Seguir [`guion-demo.md`](guion-demo.md). Fabio hace los pasos 1–4 (despliegue, reparto, tienda y
sesiones) y Juan David los pasos 5–8 (afinidad, carga con Grafana, falla y escalado).

## Cierre · Diapositiva 21 · (23:45 – 25:00)

> **Fabio:** Eso es todo. El repositorio tiene el código, la configuración, el informe, estas diapositivas
> y los resultados de todas las corridas. Con `make up` y `make smoke` se levanta y se verifica.
> **Juan David:** Quedamos atentos a sus preguntas.

---

## Preguntas probables y quién responde

| Pregunta | Responde | Respuesta corta |
|---|---|---|
| ¿Por qué usaron NGINX si la matriz eligió HAProxy? | Fabio | NGINX es requisito del enunciado; la matriz lo valida y muestra su costo. Empatan en desempeño y NGINX es más completo en L7; sus debilidades (sin checks activos, métricas globales) se compensan con reintentos, exporter, logs JSON y `/metrics` por réplica. Sin la restricción, HAProxy. |
| ¿Cómo midieron cada criterio de la matriz? | Fabio | Cada criterio tiene forma de medir y escala fijadas antes de puntuar (diapositiva 23). C1 y C5 se midieron con el caso base de cada alternativa; el resto, con la documentación oficial, citada celda por celda. |
| ¿Cómo escalan sin recargar NGINX? | Fabio | `server backend:3000 resolve` y `resolver 127.0.0.11 valid=5s`: NGINX re-resuelve el DNS de Docker, que devuelve las IP de todas las réplicas. |
| ¿NGINX revisa activamente si un backend está vivo? | Fabio | En la versión libre no; eso es de NGINX Plus. Usamos detección pasiva (`max_fails`, `fail_timeout`), reintentos (`proxy_next_upstream`) y los healthchecks de Docker. |
| ¿Por qué `stub_status` no muestra el reparto por backend? | Fabio | Es global por diseño. El reparto sale del log JSON (`$upstream_addr`), de `/metrics` de cada réplica y de los contadores de Artillery; los tres coinciden. |
| ¿Cómo garantizan mil usuarios concurrentes? | Fabio | Ley de Little: mil llegadas en 10 s con sesiones de ~70 s dan una meseta de ~1000 activos durante más de 60 s; la gráfica de usuarios activos lo confirma. |
| ¿Por qué `ip_hash` mandó todo a un solo backend? | Juan David | Usa solo los tres primeros octetos de la IP; toda la carga sale de una red. La afinidad útil es por usuario: `hash_client` (cabecera) o `sticky_cookie`. |
| ¿Por qué round-robin y `least_conn` dan lo mismo? | Juan David | Con backends y peticiones iguales las conexiones activas ya están equilibradas; la diferencia aparece cuando un backend tiene menos capacidad (E-03). |
| ¿Se reintenta un POST si falla el backend? | Juan David | No por defecto: NGINX no reenvía peticiones no idempotentes ya enviadas, para no duplicar compras. |
| ¿Qué pasa con un backend que responde 500? | Juan David | No se reintenta por defecto: el 33 % de las peticiones falló en E-07 (hallazgo H-4). Añadir `http_500` solo tendría sentido en rutas idempotentes. |
| ¿Por qué no hacer hash de la cookie de sesión de la tienda? | Juan David | El login llega sin cookie y cae en un nodo; después `hash(sid)` apunta a otro. La cookie de afinidad la debe emitir el balanceador (H-6). |
| ¿Escalar backends escala la base de datos? | Juan David | No: todas las réplicas comparten PostgreSQL (E-17). Por eso la microcaché (−77 % de CPU) y el pool de conexiones. |
| ¿Y si cae el balanceador? | Juan David | Con uno solo es punto único de falla. A-04: dos NGINX con keepalived e IP flotante, failover en 3,5 s, 99,95 % de disponibilidad; con `nopreempt` la vuelta no corta conexiones. |
| ¿Qué limita sus resultados? | Juan David | Las pruebas versionadas corrieron en GitHub Actions con 2 vCPU compartidas entre generador y servicio; lo medimos con `docker stats` y lo declaramos. La demo corre en nuestra máquina. |
