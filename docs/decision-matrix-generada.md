# Matrices de decisión (generadas por analysis/decision_matrix.py)

Puntuación 1–5; pesos suman 100; puntaje = Σ(peso × puntuación) / 5 (sobre 100).

## Matriz 4.1 — tecnología de balanceo

| ID | Criterio | Peso | Cómo se mide / justifica |
|---|---|---|---|
| C1 | Desempeño y eficiencia | 20 | Throughput y p99 en el mismo escenario/hardware (A-05) o benchmarks publicados; CPU/RAM con docker stats |
| C2 | Algoritmos de balanceo disponibles | 15 | Conteo en la documentación de la versión libre (RR, ponderado, least-conn, hash, afinidad…) |
| C3 | Detección de fallos y tolerancia (versión libre) | 15 | 5 = checks activos + reintentos; 3 = solo pasivos + reintentos; 1 = sin reintentos |
| C4 | Observabilidad | 10 | Métricas por backend sin módulos de pago; endpoint Prometheus nativo o vía exporter |
| C5 | Facilidad de configuración | 10 | Líneas de configuración del caso base + curva de aprendizaje (encuesta interna 1-5) |
| C6 | Integración con Docker / descubrimiento dinámico | 10 | ¿Detecta réplicas nuevas sin reiniciar? (DNS re-resolvable, etiquetas, API) |
| C7 | Madurez, comunidad y documentación | 10 | Años en producción, frecuencia de versiones, calidad de la documentación oficial |
| C8 | Funciones L7 adicionales | 10 | Estáticos, caché, TLS, limitación de tasa, reescrituras en la versión libre |

| Criterio (peso) | NGINX | HAProxy | Traefik | Apache | LVS |
|---|---|---|---|---|---|
| C1 (20) | 5 | 5 | 4 | 3 | 5 |
| C2 (15) | 4 | 5 | 3 | 4 | 5 |
| C3 (15) | 3 | 5 | 4 | 4 | 1 |
| C4 (10) | 2 | 5 | 5 | 3 | 2 |
| C5 (10) | 4 | 3 | 4 | 3 | 2 |
| C6 (10) | 4 | 4 | 5 | 2 | 1 |
| C7 (10) | 5 | 4 | 4 | 4 | 3 |
| C8 (10) | 5 | 3 | 3 | 4 | 1 |
| **Puntaje /100** | **81** | **88** | **79** | **68** | **56** |

**Ranking base:** HAProxy (88) > NGINX (81) > Traefik (79) > Apache (68) > LVS (56)

**Análisis de sensibilidad (±5 en cada peso, redistribuido proporcionalmente):** el líder NO cambia en ningún caso; el ranking es estable.

**Umbral de cambio de líder** (peso mínimo del criterio para que otra alternativa pase al primer lugar):

| Criterio | Peso base | Cambia el líder cuando el peso alcanza | Nuevo líder |
|---|---|---|---|
| C1 | 20 | 100 | NGINX |
| C5 | 10 | 34 | NGINX |
| C6 | 10 | 38 | Traefik |
| C7 | 10 | 34 | NGINX |
| C8 | 10 | 24 | NGINX |

NGINX obtiene 81/100 frente a 88/100 de HAProxy. Si HAProxy lidera en criterios puramente de balanceo (checks activos y métricas por backend en la versión libre), se reporta con honestidad: NGINX se selecciona porque (1) es la restricción del proyecto asignado, (2) queda en el grupo líder, (3) aporta funciones L7 completas en un solo componente y (4) sus debilidades se mitigan en el diseño (detección pasiva + reintentos, exporter + logs JSON, `resolve`).

## Matriz 4.2 — algoritmo de balanceo recomendado (con datos medidos)

| Criterio | Peso | Métrica, prueba de origen y normalización |
|---|---|---|
| Latencia p99, backends homogéneos | 20 | p99 (ms) en rampa.yml, media de repeticiones (M-05/ALG). Menor es mejor: 5·(mejor/valor), mín. 1 |
| Latencia p99, backends heterogéneos | 25 | p99 con un backend lento (E-03). Igual normalización |
| Equidad de la distribución | 15 | Índice de Jain J sobre peticiones por backend (M-06). 5·J |
| Errores durante fallo de backend | 20 | % de respuestas no-2xx en la ventana de 30 s tras la falla (M-03/E-07). 5 si 0 %; 5·(1 − min(err,5 %)/5 %), mín. 1 |
| Afinidad de sesión | 10 | % de clientes que siempre caen en el mismo backend (log NGINX, client_id). 5·(%/100), mín. 1 |
| Simplicidad operativa | 10 | Cualitativo (juicio del equipo): directivas extra y requisitos del cliente |

> **PENDIENTE:** no hay datos en `results/resumen_comparativo.csv`. Ejecutar `make test-min` (y `make test-ext E=E03`) y luego `make analyze && make matrix`. Las celdas muestran puntuación (valor medido).


Celdas: puntuación 1–5 (valor medido: p99 en ms, Jain, % errores, % afinidad). Los criterios sin dato se excluyen y los pesos restantes se renormalizan a 100 (columna 'Pesos con dato').

| Política | Latencia p99, backends homogéneos (20) | Latencia p99, backends heterogéneos (25) | Equidad de la distribución (15) | Errores durante fallo de backend (20) | Afinidad de sesión (10) | Simplicidad operativa (10) | Puntaje /100 | Pesos con dato |
|---|---|---|---|---|---|---|---|---|
| round_robin | — (—) | — (—) | — (—) | — (—) | — (—) | 5.0 (5) | 100.0 | 10/100 |
| least_conn | — (—) | — (—) | — (—) | — (—) | — (—) | 5.0 (5) | 100.0 | 10/100 |
| ip_hash | — (—) | — (—) | — (—) | — (—) | — (—) | 4.0 (4) | 80.0 | 10/100 |
| hash_client | — (—) | — (—) | — (—) | — (—) | — (—) | 3.0 (3) | 60.0 | 10/100 |
| random_two | — (—) | — (—) | — (—) | — (—) | — (—) | 4.0 (4) | 80.0 | 10/100 |
## Matriz 4.3 — estrategia de descubrimiento de backends (decisión de diseño)

| Criterio (peso) | Servidores estáticos con nombre | DNS con resolve (elegida) | Regenerar config + reload |
|---|---|---|---|
| Escalar sin tocar la config (30) | 1 | 5 | 3 |
| Pesos/backup por servidor (20) | 5 | 2 | 5 |
| Simplicidad (20) | 4 | 4 | 2 |
| Robustez ante cambios (30) | 3 | 4 | 3 |
| **Puntaje /100** | **60** | **78** | **64** |

Decisión: DNS con `resolve` para el stack principal; servidores estáticos con nombre solo para el experimento de pesos (`compose.weighted.yml`). Plan B si `resolve` fallara: generar `backend1…backendN` con un script.
