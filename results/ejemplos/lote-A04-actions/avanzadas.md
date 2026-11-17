# Mejoras avanzadas medidas (A-01, A-03, A-04)

Generado por `analysis/avanzadas.py` a partir de las corridas de `results/`.

## A-01 · Limitación de tasa

Sin corridas A01 en results/.

## A-03 · TLS + HTTP/2 en el balanceador

Sin corridas A03 en results/.

## A-04 · Alta disponibilidad del balanceador (keepalived + IP flotante)

Carga `constante.yml` contra la VIP `172.31.250.100`; `docker kill` del NGINX activo en t = 60 s y vuelta en t = 120 s. Sonda propia cada 100 ms (conexión nueva, timeout 1 s) que registra qué NGINX respondió (`X-LB-Host`).

| Corrida | Peticiones (Artillery) | Fallidas | Disponibilidad | Failover: 1.ª respuesta de lb2 tras el kill | Sondas fallidas en el failover | Sondas fallidas en el failback | Atendía al final |
|---|---|---|---|---|---|---|---|
| `20261117-163201_A04_round_robin_3b_ha-kill_rep1` | 53 954 | 30 | 99,94 % | 3,42 s | 33 | 0 | lb |
| `20261117-163624_A04_round_robin_3b_ha-kill_rep2` | 53 942 | 40 | 99,93 % | 3,08 s | 29 | 0 | lb |
| `20261117-163956_A04_round_robin_3b_ha-kill_rep3` | 53 948 | 32 | 99,94 % | 3,03 s | 28 | 0 | lb |

Failover medio: 3,18 ± 0,21 s · disponibilidad media: 99,94 ± 0,01 %.
