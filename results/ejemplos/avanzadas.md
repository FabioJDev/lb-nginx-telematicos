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

Negociación comprobada con curl (contenedor):

```
http_version=2 ssl_verify_result=18 time_connect=0.000655 time_appconnect=0.007363 time_total=0.008701
* ALPN: curl offers h2,http/1.1
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384 / x25519 / RSASSA-PSS
* ALPN: server accepted h2
< HTTP/2 200 
< x-lb-policy: round_robin
< x-lb-host: c2c6657c1f11
```

Misma carga (`constante.yml`, 100 usuarios/s, 3 peticiones por usuario, 180 s) por `http://lb` y `https://lb`. Cada usuario virtual abre su propia conexión: con HTTPS cada uno paga un handshake TLS. El tiempo de respuesta de Artillery empieza con la conexión ya abierta; la duración de la sesión (`vusers.session_length`) sí incluye conexión y handshake.

| Protocolo | Respuesta p95 | Respuesta p99 | Sesión completa (mediana) | Sesión completa (p95) | CPU media del balanceador | CPU máx. del balanceador | Errores |
|---|---|---|---|---|---|---|---|
| http | 22,0 ± 0,0 ms | 23,2 ± 0,5 ms | 63,4 ± 0,0 ms | 67,8 ± 0,8 ms | 6,0 ± 0,7 % | 15,8 ± 6,0 % | 0,00 ± 0,00 % |
| https | 22,0 ± 0,0 ms | 23,8 ± 0,0 ms | 64,7 ± 0,0 ms | 68,7 ± 0,0 ms | 8,1 ± 0,2 % | 14,3 ± 1,6 % | 0,00 ± 0,00 % |

## A-04 · Alta disponibilidad del balanceador (keepalived + IP flotante)

Carga `constante.yml` (100 usuarios/s, 180 s) contra la VIP `172.31.250.100`; `docker kill` del NGINX activo en t = 60 s y vuelta en t = 120 s. Sonda propia cada 100 ms (conexión nueva, timeout 1 s) que registra qué NGINX respondió (`X-LB-Host`). `preempt-on`: lb recupera la VIP al volver (defecto de VRRP); `preempt-off`: `nopreempt`, la VIP se queda en lb2.

### Por configuración (media ± desviación)

| Configuración | Corridas | Disponibilidad | Failover (1.ª respuesta de lb2) | Errores en el failover | Sesión más larga en el failover | Errores en la vuelta de lb | Atendía al final |
|---|---|---|---|---|---|---|---|
| `preempt-on` | 3 | 99,93 ± 0,02 % | 3,71 ± 0,12 s | 31 ± 8 | 4,23 ± 0,01 s | 9 ± 2 | lb |
| `preempt-off` | 3 | 99,95 ± 0,00 % | 3,50 ± 0,11 s | 28 ± 3 | 3,85 ± 0,31 s | 0 ± 0 | lb2 |

### Por corrida

| Corrida | Peticiones | Fallidas (tipo) | Disponibilidad | Failover | Sondas fallidas (failover / vuelta) | Errores Artillery (failover / vuelta) |
|---|---|---|---|---|---|---|
| `20261117-173433_A04_round_robin_3b_ha-preempt-on_rep1` | 53 915 | 49 (ECONNREFUSED 32 · ECONNRESET 17) | 99,91 % | 3,61 s | 33 / 0 | 40 / 9 |
| `20261117-173834_A04_round_robin_3b_ha-preempt-on_rep2` | 53 946 | 33 (ECONNREFUSED 17 · ECONNRESET 16) | 99,94 % | 3,67 s | 35 / 0 | 25 / 8 |
| `20261117-174235_A04_round_robin_3b_ha-preempt-on_rep3` | 53 939 | 38 (ECONNREFUSED 18 · ECONNRESET 20) | 99,93 % | 3,84 s | 37 / 0 | 27 / 11 |
| `20261117-174635_A04_round_robin_3b_ha-preempt-off_rep1` | 53 947 | 30 (ECONNREFUSED 22 · ECONNRESET 8) | 99,94 % | 3,63 s | 35 / 0 | 30 / 0 |
| `20261117-175036_A04_round_robin_3b_ha-preempt-off_rep2` | 53 958 | 25 (ECONNREFUSED 16 · ECONNRESET 9) | 99,95 % | 3,43 s | 33 / 0 | 25 / 0 |
| `20261117-175437_A04_round_robin_3b_ha-preempt-off_rep3` | 53 952 | 28 (ECONNREFUSED 20 · ECONNRESET 8) | 99,95 % | 3,45 s | 33 / 0 | 28 / 0 |
