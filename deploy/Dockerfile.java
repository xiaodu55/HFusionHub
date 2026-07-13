# HFusionHub Java Backend Dockerfile
# Multi-stage: build with Maven, run with JRE 17 slim (与 pom.xml java.version=17 一致)

FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
# Cache Maven dependencies
RUN mvn dependency:go-offline -q || true
COPY src/ src/
RUN mvn -DskipTests package -q

FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
RUN addgroup -S hfusionhub && adduser -S hfusionhub -G hfusionhub
COPY --from=build /app/target/*.jar app.jar
USER hfusionhub
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
