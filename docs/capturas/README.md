# Capturas de evidencia

Generadas por `scripts/capturas.sh` el 2026-11-17 15:44 UTC en runnervmccnms
(2 CPU), con un navegador Chromium sin interfaz (Playwright 1.64.1) en la red
frontend. Cada política atiende 75 s de carga constante (`constante.yml`, 100 VU/s)
y `stub_status` se captura a los 50 s; Grafana, al terminar la carga (últimos 100 s: solo esa política).

| Evidencia | Archivos |
|---|---|
| M-00: la página `/nodo` cambia de color en cada petición (round_robin) | `nodo_1.png`, `nodo_2.png`, `nodo_3.png` |
| Tienda web a través del balanceador | `tienda.png` |
| M-01 / R-21 / R-18: `round_robin` | `stub_status_round_robin.png` (`.txt`), `distribucion_round_robin.txt`, `grafana_round_robin.png` |
| M-01 / R-21 / R-18: `least_conn` | `stub_status_least_conn.png` (`.txt`), `distribucion_least_conn.txt`, `grafana_least_conn.png` |
| M-01 / R-21 / R-18: `ip_hash` | `stub_status_ip_hash.png` (`.txt`), `distribucion_ip_hash.txt`, `grafana_ip_hash.png` |
| M-01 / R-21 / R-18: `hash_client` | `stub_status_hash_client.png` (`.txt`), `distribucion_hash_client.txt`, `grafana_hash_client.png` |
| M-01 / R-21 / R-18: `hash_remote_addr` | `stub_status_hash_remote_addr.png` (`.txt`), `distribucion_hash_remote_addr.txt`, `grafana_hash_remote_addr.png` |
| M-01 / R-21 / R-18: `random_two` | `stub_status_random_two.png` (`.txt`), `distribucion_random_two.txt`, `grafana_random_two.png` |
| M-01 / R-21 / R-18: `sticky_cookie` | `stub_status_sticky_cookie.png` (`.txt`), `distribucion_sticky_cookie.txt`, `grafana_sticky_cookie.png` |

`stub_status` es global: muestra la actividad del balanceador, no el reparto. El reparto por
backend de cada política está en `distribucion_<política>.txt` (contadores `backend.<nodo>` de
Artillery) y, con repeticiones, en `docs/resultados-minimos.md`.
