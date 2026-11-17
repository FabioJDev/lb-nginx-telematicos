# Guion de la demo en vivo (6 minutos)

Corresponde a la diapositiva 20 de [`slides/presentacion.pdf`](../slides/presentacion.pdf). El guion de
la exposición está en [`guion-exposicion.md`](guion-exposicion.md).

- **Fabio Jordan C.:** pasos 1–4 (despliegue, reparto, tienda y sesiones) · unos 3 minutos.
- **Juan David Morales:** pasos 5–8 (afinidad, carga con Grafana, falla y escalado) · unos 3 minutos.

Todos los resultados esperados de abajo salen de un ensayo real en el portátil del equipo (Docker
Desktop + Ubuntu en WSL, 17-nov-2026). Los nombres de los nodos cambian en cada despliegue: lo que
importa son los conteos.

---

## Antes de la sustentación (15 minutos antes)

En la terminal de **Ubuntu (WSL)**:

```bash
cd ~/proyectos/lb-nginx-telematicos
```

```bash
make up && make monitoring-up
```

```bash
make sesiones S=redis && make policy P=round_robin && make scale N=3
```

```bash
make smoke
```

`make smoke` debe terminar con `smoke superado (3 nodos, 0 fallos, política round_robin)`.

```bash
make test-smoke
```

Esto deja descargada la imagen de Artillery, para que la carga del paso 6 arranque al instante.

**Ventanas preparadas:**
1. Dos terminales de Ubuntu en `~/proyectos/lb-nginx-telematicos`, con letra grande.
2. Navegador, pestaña 1: <http://localhost:8080/nodo>
3. Navegador, pestaña 2: <http://localhost:8080> (la tienda)
4. Navegador, pestaña 3: Grafana en <http://localhost:3001> (el puerto es `GRAFANA_PORT` del `.env`;
   en su máquina es 3001). Usuario `admin`, contraseña `GRAFANA_ADMIN_PASSWORD` del `.env`
   (`cambiar-esto` si no la cambiaron). Abrir el dashboard **Balanceador NGINX**, rango **Last 5
   minutes**, actualización **5s**, y bajar hasta la fila **Backends (una serie por réplica)**.
5. El video de respaldo abierto y en pausa, por si algo falla.

---

## Parte de Fabio

### Paso 1 · Despliegue y redes (0:30)

```bash
make ps
```

**Se ve:** `lb` con `0.0.0.0:8080->80/tcp`; los tres `backend`, `postgres` y `redis` solo con su
puerto interno (`3000/tcp`, `5432/tcp`, `6379/tcp`), sin `0.0.0.0`.

> Todo el sistema son contenedores. Fíjense que solo el balanceador publica un puerto al host; las
> réplicas, PostgreSQL y Redis están en una red interna y no se pueden alcanzar desde fuera.

### Paso 2 · Reparto (0:40)

```bash
make smoke
```

**Se ve:** `10 / 10 / 10` en tres nodos distintos y `smoke superado (3 nodos, 0 fallos, política round_robin)`.
Ignorar la tabla de contenedores que aparece al final.

Luego, en la pestaña 1 (`/nodo`), recargar tres o cuatro veces.

**Se ve:** cada recarga muestra otro nodo y otro color, y abajo «Balanceador: política=round_robin».

> Treinta peticiones, diez a cada réplica: eso es round-robin. Y en el navegador, cada recarga la
> atiende otro nodo.

### Paso 3 · La tienda (1:00)

Pestaña 2 (la tienda):
1. Buscar `Router`.
2. Iniciar sesión con `usuario1` / `clave123`.
3. Agregar dos productos al carrito y comprar.
4. Señalar el panel **Diagnóstico del balanceo**, a la derecha.

**Se ve:** la compra se completa; en el panel, las últimas peticiones las atienden nodos distintos.

> Esta es TelemaShop. Cada petición la atiende una réplica distinta, como muestra el panel, y aun así la
> sesión y el carrito se conservan, porque las sesiones viven en Redis, compartido por todas.

### Paso 4 · Romper las sesiones a propósito (1:00)

```bash
make sesiones S=memory
```

Tarda unos 13 s (recrea las réplicas). Mientras tanto:

> Ahora movemos las sesiones a la memoria de cada réplica, como haría una aplicación sin Redis.

En la tienda: recargar, iniciar sesión otra vez y agregar un producto.

**Se ve:** el aviso **«Sesión perdida»**: la petición cayó en una réplica que no conoce la sesión. En el
ensayo, de seis consultas seguidas solo dos encontraron la sesión.

> Con sesiones locales y round-robin, la sesión se pierde. La solución es la afinidad: que el
> balanceador fije cada cliente a una réplica.

```bash
make policy P=sticky_cookie
```

Tarda unos 8 s. En la tienda: recargar, iniciar sesión y agregar productos.

**Se ve:** el carrito se conserva en todas las peticiones (en el ensayo, seis de seis).

> NGINX emite su propia cookie y con ella manda siempre al mismo cliente a la misma réplica. Le paso la
> palabra a Juan David.

---

## Parte de Juan David

### Paso 5 · Afinidad por IP vs por usuario (1:00)

```bash
make policy P=ip_hash && make smoke
```

**Se ve:** `30` peticiones en **un solo** nodo (`nodos distintos: 1`).

> Con `ip_hash` todas van a la misma réplica: todas salen de la misma red, y `ip_hash` decide por la
> red de origen. Detrás de un NAT, todos los usuarios caerían en el mismo servidor.

```bash
make policy P=hash_client && make smoke
```

**Se ve:** las 30 peticiones repartidas en los tres nodos (en el ensayo, 14 / 11 / 5).

> Con `hash_client` la afinidad es por usuario, con una cabecera: cada cliente va siempre a la misma
> réplica, pero los clientes se reparten.

```bash
make policy P=round_robin
```

### Paso 6 · Carga constante y Grafana (0:30)

En la segunda terminal:

```bash
scripts/run-test.sh DEMO constante.yml
```

Dura 3 minutos: 100 usuarios por segundo, unas 300 peticiones por segundo. Cambiar a Grafana.

**Se ve:** en **Peticiones/s por réplica**, tres líneas que suben y se quedan juntas, a unas 100 req/s cada una.

> Esta es la carga en vivo: las tres réplicas reciben lo mismo.

### Paso 7 · Retirar un backend en caliente (0:45)

En la primera terminal, con la carga corriendo:

```bash
scripts/inject-fault.sh rm 1
```

**Se ve:** `OK rm aplicado a lbnginx-backend-1 … en 1.41 s`. En Grafana, una línea cae a cero, las otras
dos suben a unas 150 req/s; si los scripts llegan a la API de Grafana, aparece además una anotación del evento.

> Acabamos de eliminar una réplica con el sistema bajo carga. El tráfico se redistribuye solo y los
> usuarios no ven errores: NGINX reintenta en otra réplica.

### Paso 8 · Escalar sin reiniciar NGINX (0:45)

```bash
make scale N=5
```

Tarda unos 17 s. **Se ve:** la lista de réplicas con sus IP; en Grafana aparecen líneas nuevas que
empiezan a recibir tráfico. Para confirmarlo:

```bash
make smoke
```

**Se ve:** `nodos distintos: 5 · fallos: 0`.

> Pasamos a cinco réplicas y reciben tráfico sin reiniciar ni recargar NGINX: el balanceador vuelve a
> preguntar al DNS de Docker cada cinco segundos.

**Cierre de la demo (si la carga ya terminó):** la segunda terminal muestra el resumen de Artillery. En
el ensayo, con la réplica eliminada y el escalado en medio: **54 000 peticiones, todas con respuesta 200,
cero errores**.

> Con una réplica menos y dos más en plena carga: 54 000 peticiones y ninguna falló.

---

## Plan B por paso

| Si falla… | Hacer |
|---|---|
| Algo no responde al empezar | `make down && make up`, esperar `make smoke` y seguir. Si no hay tiempo, pasar al video. |
| El navegador no carga la tienda | Mostrar lo mismo por terminal: `curl -s localhost:8080/api/info` varias veces (cambia `node`). |
| No aparece «Sesión perdida» al primer intento | Agregar otro producto o recargar: con tres réplicas, una de cada tres peticiones acierta por azar. |
| Grafana no muestra datos | Revisar el rango (Last 5 minutes) y la actualización (5s); si sigue vacío, mostrar `make status` (stub_status y réplicas activas). |
| La carga tarda en arrancar | Seguir con el paso 7 igual; Artillery empieza en segundos si se ejecutó `make test-smoke` antes. |
| `make policy` se demora | Es normal: recrea el balanceador (unos 8 s). No cambiar de política con la carga corriendo: corta conexiones. |
| Cualquier falla seria | Poner el video de respaldo desde el mismo paso. |

## Después de la demo (dejar todo como estaba)

```bash
make scale N=3 && make sesiones S=redis && make policy P=round_robin
```
