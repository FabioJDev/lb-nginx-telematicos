# Mejoras avanzadas medidas (A-01, A-03, A-04)

Generado por `analysis/avanzadas.py` a partir de las corridas de `results/`.

## A-01 · Limitación de tasa

Sin corridas A01 en results/.

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

Misma carga (`constante.yml`, 100 usuarios/s, 3 peticiones por usuario, 180 s) por `http://lb` y `https://lb`. Cada usuario virtual abre su propia conexión: con HTTPS cada uno paga un handshake TLS.

| Protocolo | Latencia media | p95 | p99 | CPU media del balanceador | CPU máx. del balanceador | Errores |
|---|---|---|---|---|---|---|
| http | 20,5 ± 0,1 ms | 22,0 ± 0,0 ms | 23,2 ± 0,5 ms | 6,0 ± 0,7 % | 15,8 ± 6,0 % | 0,00 ± 0,00 % |
| https | — | 22,0 ± 0,0 ms | 23,8 ± 0,0 ms | 8,1 ± 0,2 % | 14,3 ± 1,6 % | 0,00 ± 0,00 % |

## A-04 · Alta disponibilidad del balanceador

Sin corridas A04 en results/.
