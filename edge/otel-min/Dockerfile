# --- build stage ---
FROM --platform=$BUILDPLATFORM golang:1.24.11-alpine AS build

RUN apk add --no-cache ca-certificates git && update-ca-certificates
WORKDIR /src

ENV GOTOOLCHAIN=auto \
    GOFLAGS="-ldflags=-s -w"

RUN --mount=type=cache,target=/root/.cache/go-build \
    go install go.opentelemetry.io/collector/cmd/builder@v0.138.0

ARG TARGETOS=linux
ARG TARGETARCH

COPY builder.yaml .

RUN --mount=type=cache,target=/root/.cache/go-build \
    GOOS="${TARGETOS}" GOARCH="${TARGETARCH:-$(go env GOARCH)}" CGO_ENABLED=0 \
    /go/bin/builder --config ./builder.yaml

# --- runtime stage ---
FROM gcr.io/distroless/static AS runtime

ARG USER_UID=10001

WORKDIR /otelcol

COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=build /src/_build/otelcol-edge-herald /otelcol/otelcol

USER ${USER_UID}

EXPOSE 4317 4318

ENTRYPOINT ["/otelcol/otelcol"]
CMD ["--config", "/etc/otel/config.yaml"]
