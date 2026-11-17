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
| **Comparación consolidada** de todas las políticas en todos los escenarios | Una tabla por métrica, ganador por escenario y mapa de calor | `analysis/compare_all.py`, [`comparacion-algoritmos.md`](comparacion-algoritmos.md) |
| **Readiness** (`/ready`) separado de liveness (`/health`) | Distingue "el proceso vive" de "puede atender" (base de datos y sesiones) | `backend/server.js` |
| **Métricas de la aplicación** en Prometheus/Grafana | Sesiones perdidas, pedidos por réplica, pool de conexiones y tiempo de consulta | `tienda_*` en `/metrics`, dashboard |
| **CI con la tienda** | Humo de compra completa y verificación de sesiones con y sin afinidad en cada push | `.github/workflows/ci.yml` |
| Pruebas en GitHub Actions bajo demanda | Resultados reales sin depender de una máquina con Docker | `.github/workflows/pruebas.yml` |
| Compilación automática de informe, diapositivas y diagrama | Entregables siempre sincronizados con el código | `.github/workflows/documentos.yml` |

## Propuestas (trabajo futuro, en orden de valor)

1. **Alta disponibilidad del balanceador** (A-04): dos NGINX con keepalived (VRRP) e IP flotante; hoy
   NGINX es un punto único de falla.
2. **Health checks activos**: NGINX OSS solo detecta fallos de forma pasiva. Opciones: el módulo de
   terceros `nginx_upstream_check_module`, HAProxy (que ya los trae) o un agente externo que retire
   réplicas no listas (`/ready`) del DNS.
3. **Reintentos seguros para errores de aplicación**: añadir `http_500` a `proxy_next_upstream` solo en
   rutas idempotentes (`GET`), con un `location` separado para la API de escritura.
4. **Alta disponibilidad de los datos**: réplica de lectura de PostgreSQL (o PgBouncer para el pool
   de conexiones) y Redis Sentinel; E-18 y E-19 muestran que son los nuevos puntos únicos de falla.
5. **TLS y HTTP/2** en el balanceador (A-03), con certificados de prueba generados en contenedor.
6. **Limitación de tasa por usuario** (A-01) medida con la tienda: proteger `/api/login` contra
   fuerza bruta y `/api/orders` contra abuso.
7. **Orquestación con Kubernetes**: Service + Ingress NGINX, para comparar el descubrimiento por DNS
   de Docker con el de Kubernetes.
