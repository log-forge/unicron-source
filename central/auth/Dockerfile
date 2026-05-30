# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS node-base

ENV NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FETCH_RETRIES=5 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=20000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=120000 \
    NPM_CONFIG_FETCH_TIMEOUT=300000 \
    NPM_CONFIG_FUND=false

# ---- Build
FROM node-base AS build
WORKDIR /app
COPY ./central/auth/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY ./central/auth/tsconfig.json ./
COPY ./central/auth/tsup.config.mjs ./
COPY ./central/auth/src ./src
RUN npm run build

# ---- Run
FROM node-base AS run
ENV NODE_ENV=production
ENV NODE_OPTIONS="--enable-source-maps"
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
COPY --from=build /app/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev
COPY --from=build /app/dist ./dist
USER app
EXPOSE 3020

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD sh -c "wget -qO- http://localhost:${PORT:-3020}/readyz || exit 1"

CMD ["node", "dist/index.js"]
