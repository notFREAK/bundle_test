FROM golang:1.24 AS build
WORKDIR /src
COPY . .
RUN go build -o /app/server main.go
FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /app/server ./server
EXPOSE 8080
ENTRYPOINT ["/app/server"]
