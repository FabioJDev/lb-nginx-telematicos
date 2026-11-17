# =============================================================================
# Makefile — Proyecto 2: Balanceador de carga web con NGINX
# Todas las tareas invocan únicamente docker / docker compose (R-01): nada se
# instala en el host. Ejecutar desde WSL2 (o Linux/macOS).
#
#   make help            lista de objetivos
# =============================================================================
SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

COMPOSE        ?= docker compose
COMPOSE_W      := $(COMPOSE) -f docker-compose.yml -f compose.weighted.yml
COMPOSE_H      := $(COMPOSE) -f docker-compose.yml -f compose.haproxy.yml
SCRIPTS        := scripts
P              ?= round_robin
N              ?= 3
F              ?= none
REPS           ?= 3

.PHONY: help env up up-clean down down-v ps logs logs-lb logs-backend build compare sesiones db-shell db-reset \
        test-tienda test-cache test-haproxy \
        smoke nginx-test reload status config policy feature keepalive scale \
        monitoring-up monitoring-down cadvisor-up weighted-up weighted-down \
        haproxy-up haproxy-down \
        test-smoke test-seq test-min test-algoritmos test-resiliencia \
        test-escalabilidad test-quiebre test-ext test-all \
        analyze matrix fix-perms clean-results rotate-logs \
        informe slides check-eol shellcheck

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Ciclo de vida del stack
# ---------------------------------------------------------------------------
env: ## Crea .env a partir de .env.example si no existe
	@test -f .env || { cp .env.example .env && echo "creado .env desde .env.example"; }

build: env ## Construye las imágenes locales (backend, analysis)
	$(COMPOSE) build backend
	$(COMPOSE) --profile tools build analysis

up: env ## Levanta el stack base (lb + backends) con el override de desarrollo
	$(COMPOSE) up -d --build --remove-orphans
	$(SCRIPTS)/wait-healthy.sh lb 1
	$(COMPOSE) ps

up-clean: env ## Levanta el stack SIN docker-compose.override.yml (despliegue "limpio")
	$(COMPOSE) -f docker-compose.yml up -d --build --remove-orphans
	$(COMPOSE) -f docker-compose.yml ps

down: ## Baja el stack (conserva volúmenes)
	$(COMPOSE) --profile monitoring --profile cadvisor --profile loadtest --profile tools down --remove-orphans

down-v: ## Baja el stack y BORRA volúmenes (datos de Prometheus/Grafana)
	$(COMPOSE) --profile monitoring --profile cadvisor --profile loadtest --profile tools down -v --remove-orphans

ps: ## Estado de los servicios (los backends no deben mostrar puertos)
	$(COMPOSE) --profile monitoring ps

logs: ## Logs de todos los servicios (seguir con Ctrl+C para salir)
	$(COMPOSE) logs -f --tail=100

logs-lb: ## Logs del balanceador (incluye mensajes del watcher)
	$(COMPOSE) logs -f --tail=100 lb

logs-backend: ## Logs de los backends
	$(COMPOSE) logs -f --tail=100 backend

config: ## Valida y muestra la configuración Compose efectiva
	$(COMPOSE) config -q && echo "docker-compose: OK" && $(COMPOSE) config

# ---------------------------------------------------------------------------
# Operación del balanceador
# ---------------------------------------------------------------------------
smoke: ## 30 peticiones a /api/info; falla si hay menos de 3 nodos distintos o errores
	$(SCRIPTS)/smoke.sh 30

nginx-test: ## nginx -t dentro del contenedor + muestra http.conf generado
	$(COMPOSE) exec -T lb nginx -t
	@echo "--- /etc/nginx/generated/http.conf (primeras 60 líneas) ---"
	$(COMPOSE) exec -T lb sh -c 'head -60 /etc/nginx/generated/http.conf'

reload: ## nginx -t && nginx -s reload (recarga elegante sin reiniciar)
	$(COMPOSE) exec -T lb sh -c 'nginx -t && nginx -s reload && echo "nginx recargado"'

status: ## stub_status + backends activos + política vigente
	$(SCRIPTS)/status.sh

policy: ## Cambia la política de balanceo: make policy P=least_conn
	$(SCRIPTS)/set-policy.sh $(P)

feature: ## Activa una función L7 extra: make feature F=ratelimit|microcache|none
	$(SCRIPTS)/set-env.sh LB_FEATURE $(F) --recreate-lb

keepalive: ## keepalive hacia upstream: make keepalive K=on|off
	$(SCRIPTS)/set-env.sh LB_UPSTREAM_KEEPALIVE $(K) --recreate-lb

scale: ## Escala los backends sin recrear los existentes: make scale N=5
	$(SCRIPTS)/scale.sh $(N)

# ---------------------------------------------------------------------------
# Perfiles adicionales
# ---------------------------------------------------------------------------
monitoring-up: env ## Levanta Prometheus + exporter + Pushgateway + Grafana
	$(COMPOSE) --profile monitoring up -d
	@echo "Grafana:    http://localhost:$$(grep -E '^GRAFANA_PORT=' .env | cut -d= -f2 || echo 3000)"
	@echo "Prometheus: http://localhost:$$(grep -E '^PROMETHEUS_PORT=' .env | cut -d= -f2 || echo 9090)"

monitoring-down: ## Baja solo los servicios de monitoreo
	$(COMPOSE) --profile monitoring stop nginx-exporter prometheus pushgateway grafana

cadvisor-up: env ## Levanta cAdvisor (CPU/RAM por contenedor; puede no funcionar en Docker Desktop)
	$(COMPOSE) --profile cadvisor up -d cadvisor

weighted-up: env ## Stack con backend lento + pesos (E-03): make weighted-up
	$(COMPOSE_W) up -d --build --remove-orphans
	$(SCRIPTS)/wait-healthy.sh lb 1

weighted-down: ## Vuelve al stack normal
	$(COMPOSE_W) rm -sf backend-slow || true
	$(COMPOSE) up -d --force-recreate --no-deps lb

haproxy-up: env ## Añade HAProxy sobre los mismos backends (A-05)
	$(COMPOSE_H) up -d haproxy
	@echo "HAProxy:    http://localhost:$$(grep -E '^HAPROXY_PUBLIC_PORT=' .env | cut -d= -f2 || echo 8090)"
	@echo "Stats:      http://localhost:$$(grep -E '^HAPROXY_STATS_PORT=' .env | cut -d= -f2 || echo 8404)/stats"

haproxy-down: ## Quita HAProxy
	$(COMPOSE_H) rm -sf haproxy || true

# ---------------------------------------------------------------------------
# Pruebas (todas dejan una carpeta por corrida en results/)
# ---------------------------------------------------------------------------
test-smoke: ## Escenario smoke.yml de Artillery (10 s) con el ejecutor completo
	$(SCRIPTS)/run-test.sh M00 smoke.yml

test-seq: ## M-02: 1000 peticiones secuenciales y conteo por backend
	$(SCRIPTS)/test-seq.sh 1000

test-min: ## M-00 a M-06 en secuencia (REPS=3 por defecto; QUICK=1 para 1 repetición)
	REPS=$(REPS) $(SCRIPTS)/test-min.sh

test-algoritmos: ## Compara políticas con rampa.yml (POLICIES="..." REPS=3)
	REPS=$(REPS) $(SCRIPTS)/test-algoritmos.sh

test-resiliencia: ## M-03: elimina un backend en caliente bajo carga y lo repone
	$(SCRIPTS)/test-resiliencia.sh $(P)

test-escalabilidad: ## E-02: misma carga con N = 1, 2, 3, 5, 7 backends
	$(SCRIPTS)/test-escalabilidad.sh

test-quiebre: ## E-13: punto de quiebre con N = 1, 3, 5
	$(SCRIPTS)/test-quiebre.sh

test-tienda: ## E-16: compra completa con cada política y sesiones en memoria/Redis (SESSIONS=, POLICIES=)
	REPS=$(REPS) $(SCRIPTS)/test-tienda.sh

test-cache: ## A-02: microcaché del catálogo vs sin caché (tienda-lectura.yml)
	REPS=$(REPS) $(SCRIPTS)/test-cache.sh

test-haproxy: ## A-05: NGINX vs HAProxy con los mismos backends y la misma carga
	REPS=$(REPS) $(SCRIPTS)/test-haproxy.sh

sesiones: ## Cambia dónde viven las sesiones y recrea los backends: make sesiones S=memory|redis
	$(SCRIPTS)/set-env.sh SESSION_STORE $(S) --recreate-backend

db-shell: ## Consola psql de la base de datos de la tienda
	$(COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

db-reset: ## Borra y recrea la base de datos (vuelve a cargar db/init)
	$(COMPOSE) stop postgres
	$(COMPOSE) rm -f postgres
	docker volume rm $${COMPOSE_PROJECT_NAME:-lbnginx}_pgdata || true
	$(COMPOSE) up -d postgres
	$(SCRIPTS)/wait-healthy.sh postgres 1 120

test-ext: ## Pruebas extendidas: make test-ext E=E03|E04|E05|E06|E07|E08|E09|E10|E11|E12|E14|E15|E17|E18|E19|all
	$(SCRIPTS)/test-extendidas.sh $(E)

test-all: test-min test-algoritmos test-escalabilidad test-quiebre ## Todo lo anterior (varias horas)

# ---------------------------------------------------------------------------
# Análisis y documentación
# ---------------------------------------------------------------------------
analyze: env ## Genera CSV y PNG para todas las corridas (contenedor analysis)
	$(COMPOSE) --profile tools build analysis
	$(COMPOSE) --profile tools run --rm analysis

compare: env ## Comparación consolidada de todas las políticas -> docs/comparacion-algoritmos.md
	$(COMPOSE) --profile tools build analysis
	$(COMPOSE) --profile tools run --rm analysis python compare_all.py

matrix: env ## Matrices de decisión (4.1 sensibilidad, 4.2 con datos) -> docs/decision-matrix-generada.md
	$(COMPOSE) --profile tools build analysis
	$(COMPOSE) --profile tools run --rm analysis python decision_matrix.py

fix-perms: ## Devuelve al usuario actual la propiedad de results/ y docs/figuras (escritos por contenedores)
	docker run --rm -v "$$PWD/results:/r" -v "$$PWD/docs:/d" alpine:3.20 chown -R $$(id -u):$$(id -g) /r /d

clean-results: ## Borra las corridas de results/ (pide confirmación; conserva ejemplos/)
	@ls -d results/*/ 2>/dev/null | grep -v '^results/ejemplos/$$' || { echo "no hay corridas"; exit 0; }
	@read -r -p "¿Borrar las corridas anteriores (ejemplos/ se conserva)? [s/N] " r; \
	  [ "$$r" = "s" ] && find results -mindepth 1 -maxdepth 1 -type d ! -name ejemplos -exec rm -rf {} + && echo "listo" || echo "cancelado"

rotate-logs: ## Rota logs/nginx/access.json (reabre con nginx -s reopen)
	$(SCRIPTS)/rotate-logs.sh

informe: ## Compila docs/informe/informe.tex a PDF con un contenedor TeX Live
	docker run --rm -v "$$PWD/docs/informe:/work" -w /work texlive/texlive:TL2024-historic \
	  latexmk -pdf -interaction=nonstopmode -halt-on-error informe.tex

slides: ## Exporta slides/presentacion.md (Marp) a PDF y HTML
	docker run --rm -e MARP_USER="$$(id -u):$$(id -g)" -v "$$PWD:/home/marp/app" -e LANG=C.UTF-8 marpteam/marp-cli:v4.5.1 slides/presentacion.md --pdf --allow-local-files -o slides/presentacion.pdf
	docker run --rm -e MARP_USER="$$(id -u):$$(id -g)" -v "$$PWD:/home/marp/app" -e LANG=C.UTF-8 marpteam/marp-cli:v4.5.1 slides/presentacion.md --html --allow-local-files -o slides/presentacion.html

# ---------------------------------------------------------------------------
# Calidad
# ---------------------------------------------------------------------------
check-eol: ## Falla si algún .sh/.conf/.yml tiene finales CRLF
	@if grep -rlI $$'\r' --include='*.sh' --include='*.conf' --include='*.template' --include='*.yml' . ; then \
	  echo "ERROR: archivos con CRLF (ver arriba). Ejecuta: git add --renormalize ."; exit 1; \
	else echo "finales de línea: OK"; fi

shellcheck: ## Analiza los scripts con shellcheck (en contenedor)
	docker run --rm -v "$$PWD:/mnt" koalaman/shellcheck:v0.10.0 -x -S warning -P SCRIPTDIR scripts/*.sh scripts/in-container/*.sh nginx/dev/*.sh
