# backend/Dockerfile
# Imagen base documentada: node:24-alpine (Node.js 24 LTS sobre Alpine Linux).
# Dependencias fijadas en package-lock.json: pg (PostgreSQL) y redis (sesiones
# compartidas). El resto del servidor usa solo módulos nativos de Node.
FROM node:24-alpine

LABEL org.opencontainers.image.title="lbnginx-backend" \
      org.opencontainers.image.description="Backend instrumentado + tienda web (PostgreSQL, Redis) para el balanceador NGINX (Servicios Telemáticos 2026-02)"

WORKDIR /app

# Capa de dependencias primero: se reutiliza mientras package*.json no cambie
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund && npm cache clean --force

COPY server.js tienda.js ./
COPY public ./public

# Ejecuta como usuario no privilegiado (la imagen oficial ya trae el usuario 'node')
USER node

# Puerto interno del backend. NO se publica al host (solo 'expose' en compose).
EXPOSE 3000

ENV PORT=3000 \
    NODE_ENV=production

# Liveness: el proceso responde. La disponibilidad de la base de datos se consulta en /ready.
HEALTHCHECK --interval=5s --timeout=2s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/health || exit 1

CMD ["node", "server.js"]
