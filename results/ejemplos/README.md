# results/ejemplos/

Aquí se versiona **al menos una corrida completa de cada prueba mínima** (M-00 a M-06) tal como
la dejó `scripts/run-test.sh`, para que el jurado pueda inspeccionar los datos crudos sin
reproducir las pruebas. El resto de `results/` está en `.gitignore`.

Para copiar una corrida aquí:

```bash
cp -r results/20261117-101500_M05_round_robin_3b_rep1 results/ejemplos/
```

Cada carpeta contiene: `metadata.json`, `artillery.json`, `artillery.log`, `nginx_access.jsonl`,
`stub_status.csv`, `docker_stats.csv`, `events.csv` y, tras `make analyze`, `resumen.json`,
`distribucion_backend.csv`, `serie_1s.csv` y `figuras/*.png`.

> Regla del proyecto: ninguna cifra del README, del informe o de las diapositivas puede existir
> sin un archivo de origen en `results/`. Esta carpeta está vacía hasta que el equipo ejecute las pruebas.
