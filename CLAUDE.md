# CLAUDE.md — Proyecto 2: Balanceador de carga web con NGINX

Servicios Telemáticos 2026-02 · Grupo 3 · Fabio Jordan C., Juan David Morales

## Contexto

La especificación completa está en `docs/especificacion.pdf` (fuente: `docs/especificacion.docx`).
Léela antes de cada fase y respeta los IDs de requisitos (R-xx) y de pruebas (M-xx, E-xx, A-xx).
El enunciado oficial del curso está en `docs/enunciado/`.

## Reglas no negociables

- Todo corre en contenedores con Docker Compose. Nunca instales nada en el host
  (ni nginx, ni node, ni pip). Herramientas auxiliares también en contenedores.
- `nginx.conf`, plantillas y políticas se montan como volúmenes `:ro`. Jamás `COPY`.
- Los backends no publican puertos al host (solo `expose`).
- Imágenes con versión fijada (nunca `:latest`); regístralas en el README y en `docs/entorno.md`.
- Prohibido inventar resultados: toda cifra del README o del informe debe salir
  de un archivo dentro de `results/`. Si una prueba falla, documéntalo tal cual.
- Tras cada cambio: `docker compose config -q`, `make nginx-test`, `make smoke`.
- Scripts `.sh` con finales de línea LF y bit ejecutable (`git update-index --chmod=+x`).
- Commits pequeños por fase (Conventional Commits, en español). No hagas push
  sin que te lo pidamos.
- Código comentado y documentación en español.

## Entorno

Windows 11 + WSL2 + Docker Desktop. El repo vive dentro del sistema de archivos
de WSL (`~/proyectos/...`), no en `/mnt/c`. Recursos limitados: un solo portátil
genera la carga y la atiende; registra siempre el uso de CPU durante las pruebas.

## Comandos clave

```
make up | make down | make ps | make logs | make smoke | make nginx-test
make policy P=least_conn | make scale N=5 | make status | make reload
make test-min | make test-algoritmos | make test-resiliencia | make test-escalabilidad
make analyze | make matrix | make monitoring-up
```

## Estructura (resumen)

- `backend/` app Node.js instrumentada + tienda web (`tienda.js`: `pg` y `redis`, fijadas en `package-lock.json`).
- `db/init/` esquema y datos de PostgreSQL. `compose.capturas.yml` + `scripts/capturas.sh`: capturas de evidencia.
- `nginx/` configuración montada: `nginx.conf`, `templates/` (envsubst), `policies/`, `extras/`.
- `artillery/` escenarios YAML + `lib/processor.js`.
- `scripts/` ejecutor de pruebas (`run-test.sh`) y lotes (`test-*.sh`).
- `analysis/` contenedor Python: tablas CSV, gráficas PNG y matrices de decisión.
- `monitoring/` Prometheus + Grafana aprovisionados.
- `docs/` especificación, matrices, informe IEEE, resultados.
