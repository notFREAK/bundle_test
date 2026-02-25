FROM rust:1.82 AS build
WORKDIR /src
COPY . .
RUN cargo build --release
FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /src/target/release/gateway-rust /app/gateway-rust
EXPOSE 3002
CMD ["/app/gateway-rust"]
