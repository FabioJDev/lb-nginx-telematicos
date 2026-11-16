# Esquema de diapositivas (20 min)

Fuente Marp: `presentacion.md` → `make slides` genera `presentacion.pdf` y `presentacion.html`.

1. **Portada** — Balanceador de carga web con NGINX · Grupo 3 · integrantes · curso.
2. **Problema y objetivo** — un servidor = punto único de falla + techo de capacidad; objetivo general.
3. **Conceptos (dibujo)** — proxy directo vs inverso; L4 vs L7 (qué puede decidir cada uno).
4. **Algoritmos (dibujo)** — round-robin, least_conn, ip_hash/source, hash consistente, random two.
5. **Alternativas: matriz 4.1** — criterios, pesos y cómo se mide cada uno; puntajes.
6. **Sensibilidad y reflexión** — ranking estable; HAProxy > NGINX en balanceo puro; por qué NGINX.
7. **Arquitectura** — diagrama de redes y servicios; decisiones clave.
8. **Cumplimiento R-01…R-25** — tabla compacta con enlaces/evidencia.
9. **Demo en vivo** — guion de 5 min (navegador, Grafana, ip_hash, falla, escalado).
10. **Resultados: algoritmos (M-05)** — media y p99 con barras de error; significancia.
11. **Resultados: trampa de ip_hash (E-05)** — distribución apilada.
12. **Resultados: resiliencia (M-03/E-07)** — línea de tiempo con eventos; detección/recuperación.
13. **Resultados: escalabilidad y quiebre (E-02/E-13)** — throughput y p95 vs N; eficiencia.
14. **Matriz 4.2 y conclusiones** — algoritmo recomendado con datos; limitaciones; trabajo futuro (HA, Kubernetes).
15. **Preguntas** — repositorio y referencias.
