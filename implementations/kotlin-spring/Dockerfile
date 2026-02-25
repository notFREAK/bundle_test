FROM gradle:8.10-jdk21 AS build
WORKDIR /src
COPY . .
RUN gradle bootJar --no-daemon
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/build/libs/*.jar app.jar
EXPOSE 8082
ENTRYPOINT ["java","-jar","/app/app.jar","--server.port=8082"]
