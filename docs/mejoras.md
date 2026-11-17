# Mejoras del proyecto: implementadas y propuestas

## Implementadas (más allá del enunciado)

| Mejora | Qué aporta | Dónde |
|---|---|---|
| **Aplicación con estado** (tienda con PostgreSQL y Redis) | Recomendación del profesor: probar el balanceador con funcionalidades reales, sesiones y base de datos | [`docs/tienda.md`](tienda.md), `backend/tienda.js` |
| **Sesiones en memoria vs Redis** (E-16) | Muestra por qué el balanceo sin afinidad rompe las sesiones locales y cómo lo resuelven la afinidad o un almacén compartido | `scripts/test-tienda.sh` |
| **Afinidad por cookie del balanceador** (`sticky_cookie`) | Equivalente libre del *sticky cookie* de NGINX Plus; corrige el error de hacer hash de la cookie de la aplicación (H-6) | `nginx/policies/sticky_cookie.conf` |
| **Dependencias compartidas como punto único de falla** (E-17, E-18, E-19) | El balanceador reparte réplicas, pero la base de datos y Redis siguen siendo únicas | `scripts/test-extendidas.sh` |
| **Microcaché segura** (A-02) | Cachea solo el catálogo público durante 1 s; nunca carrito ni sesión | `nginx/extras/features/microcache/` |
| **Comparativa con HAProxy** (A-05) | Datos medidos para el criterio de desempeño de la matriz 4.1 | `scripts/test-haproxy.sh` |
| **Limitación de tasa por cliente** (A-01) | Corta en el balanceador el exceso de un cliente abusivo sin afectar a los demás (35,9 % de 429 al abusivo, 0 a los normales) | `nginx/extras/features/ratelimit/`, `scripts/test-ratelimit.sh` |
| **TLS 1.3 + HTTP/2** (A-03) | Terminación TLS en NGINX con certificado generado en contenedor; costo medido en CPU | `compose.tls.yml`, `scripts/test-tls.sh` |
| **Alta disponibilidad del balanceador** (A-04) | Dos NGINX con keepalived e IP flotante; failover de 3,5 s y `nopreempt` para no cortar dos veces (H-11) | `compose.ha.yml`, `ha/`, `scripts/test-ha.sh` |
| **Capturas de evidencia automáticas** | `stub_status`, Grafana y `/nodo` capturados con un navegador sin interfaz bajo carga | `compose.capturas.yml`, `scripts/capturas.sh` |
| **Comparación consolidada** de todas las políticas en todos los escenarios | Una tabla por métrica, ganador por escenario y mapa de calor | `analysis/compare_all.py`, [`comparacion-algoritmos.md`](comparacion-algoritmos.md) |
| **Readiness** (`/ready`) separado de liveness (`/health`) | Distingue "el proceso vive" de "puede atender" (base de datos y sesiones) | `backend/server.js` |
| **Métricas de la aplicación** en Prometheus/Grafana | Sesiones perdidas, pedidos por réplica, pool de conexiones y tiempo de consulta | `tienda_*` en `/metrics`, dashboard |
| **CI con la tienda** | Humo de compra completa y verificación de sesiones con y sin afinidad en cada push | `.github/workflows/ci.yml` |
| Pruebas en GitHub Actions bajo demanda | Resultados reales sin depender de una máquina con Docker | `.github/workflows/pruebas.yml` |
| Compilación automática de informe, diapositivas y diagrama | Entregables siempre sincronizados con el código | `.github/workflows/documentos.yml` |

## Propuestas (trabajo futuro, en orden de valor)

1. **Alta disponibilidad del balanceador fuera de Docker** (A-04 ya medido dentro de Docker con
   `compose.ha.yml`): llevar la IP flotante a la red física o a un balanceador de nube, y sincronizar el
   estado de afinidad (cookie `lbid`) entre los dos NGINX.
2. **Health checks activos**: NGINX OSS solo detecta fallos de forma pasiva. Opciones: el módulo de
   terceros `nginx_upstream_check_module`, HAProxy (que ya los trae) o un agente externo que retire
   réplicas no listas (`/ready`) del DNS.
3. **Reintentos seguros para errores de aplicación**: añadir `http_500` a `proxy_next_upstream` solo en
   rutas idempotentes (`GET`), con un `location` separado para la API de escritura.
4. **Alta disponibilidad de los datos**: réplica de lectura de PostgreSQL (o PgBouncer para el pool
   de conexiones) y Redis Sentinel; E-18 y E-19 muestran que son los nuevos puntos únicos de falla.
5. **TLS de extremo a extremo**: A-03 termina TLS en NGINX; faltaría TLS hacia los backends
   (`proxy_ssl_*`) y certificados de una CA (ACME/Let's Encrypt) en lugar del autofirmado.
6. **Limitación de tasa por ruta** (A-01 ya medido por cliente): límites distintos para `/api/login`
   (fuerza bruta) y `/api/orders` (abuso), con la clave de cliente firmada para que no se pueda rotar.
7. **Orquestación con Kubernetes**: Service + Ingress NGINX, para comparar el descubrimiento por DNS
   de Docker con el de Kubernetes.
