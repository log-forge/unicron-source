# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS node-base

ENV NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FETCH_RETRIES=5 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=20000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=120000 \
    NPM_CONFIG_FETCH_TIMEOUT=300000 \
    NPM_CONFIG_FUND=false

FROM node-base AS development-dependencies-env
COPY ./central/unicron/frontend /app
WORKDIR /app
RUN --mount=type=cache,target=/root/.npm npm ci

FROM node-base AS production-dependencies-env
COPY ./central/unicron/frontend/package*.json /app/
WORKDIR /app
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev

FROM node-base AS build-env
COPY ./central/unicron/frontend /app/
COPY --from=development-dependencies-env /app/node_modules /app/node_modules
WORKDIR /app
ENV NODE_OPTIONS="--enable-source-maps"
ARG VITE_BETTER_AUTH_URL=
ARG VITE_AUTH_BASE_URL=/unicron/auth
ARG VITE_API_BASE_URL=/unicron/api
ARG VITE_EXTERNAL_API_BASE_URL=
ARG VITE_SHOW_RQ_DEVTOOLS=true
ARG VITE_AUTH_MODE=cookie
ENV VITE_AUTH_MODE=${VITE_AUTH_MODE}
ENV VITE_BETTER_AUTH_URL=${VITE_BETTER_AUTH_URL}
ENV VITE_AUTH_BASE_URL=${VITE_AUTH_BASE_URL}
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_EXTERNAL_API_BASE_URL=${VITE_EXTERNAL_API_BASE_URL}
ENV VITE_SHOW_RQ_DEVTOOLS=${VITE_SHOW_RQ_DEVTOOLS}
RUN npm run build

FROM node-base
ENV NODE_OPTIONS="--enable-source-maps"
COPY ./central/unicron/frontend/package*.json /app/
COPY --from=production-dependencies-env /app/node_modules /app/node_modules
COPY --from=build-env /app/build /app/build
COPY --from=build-env /app/dist /app/dist
WORKDIR /app
CMD ["npm", "run", "start"]
