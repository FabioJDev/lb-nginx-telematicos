# Mejoras avanzadas medidas (A-01, A-03, A-04)

Generado por `analysis/avanzadas.py` a partir de las corridas de `results/`.

## A-01 · Limitación de tasa por cliente

Escenario `ratelimit.yml`: 120 llegadas/s durante 90 s; ≈ 2/3 de un mismo cliente (`X-Client-Id: cliente-abusivo`) y ≈ 1/3 de clientes distintos. Límite: 50 req/s por cliente, ráfaga 100 (`nginx/extras/features/ratelimit/`).

Corridas: 6 (ratelimit: 3, none: 3). Valores: media ± desviación entre repeticiones.

| Configuración | Peticiones del abusivo | 429 al abusivo | Peticiones normales | 429 a normales | p95 normales | Peticiones que llegan a los backends |
|---|---|---|---|---|---|---|
| `LB_FEATURE=none` | 7 192 ± 84 | 0 ± 0 (0,0 ± 0,0 %) | 3 608 ± 84 | 0 ± 0 (0,0 ± 0,0 %) | 22,0 ± 0,0 ms | 10 800 ± 0 |
| `LB_FEATURE=ratelimit` | 7 170 ± 38 | 2 571 ± 38 (35,9 ± 0,3 %) | 3 630 ± 38 | 0 ± 0 (0,0 ± 0,0 %) | 22,0 ± 0,0 ms | 8 229 ± 38 |

## A-03 · TLS + HTTP/2 en el balanceador

Sin corridas A03 en results/.

## A-04 · Alta disponibilidad del balanceador

Sin corridas A04 en results/.
