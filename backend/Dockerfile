# backend/Dockerfile
# Imagen base documentada: node:24-alpine (Node.js 24 LTS sobre Alpine Linux).
# La app usa solo el módulo 'http' de Node: no hay npm install ni dependencias,
# por eso la imagen es mínima y el build es instantáneo.
FROM node:24-alpine

# Metadatos
LABEL org.opencontainers.image.title="lbnginx-backend" \
      org.opencontainers.image.description="Backend HTTP instrumentado para el balanceador NGINX (Servicios Telemáticos 2026-02)" \
      org.opencontainers.image.source="https://github.com/<org>/lb-nginx-telematicos"

WORKDIR /app
COPY server.js .

# Ejecuta como usuario no privilegiado (la imagen oficial ya trae el usuario 'node')
USER node

# Puerto interno del backend. NO se publica al host (solo 'expose' en compose).
EXPOSE 3000

ENV PORT=3000 \
    NODE_ENV=production

# Healthcheck definido aquí y también en docker-compose.yml (el de compose manda)
HEALTHCHECK --interval=5s --timeout=2s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/health || exit 1

CMD ["node", "server.js"]
