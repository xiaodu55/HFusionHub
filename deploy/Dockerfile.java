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
# 运行身份钉死为 10001：`adduser -S` 让 busybox 从 Alpine 系统池挑第一个空号，
# 基镜像里占了哪些号由上游决定，重建即可能换号。同一个号必须与
# deploy/Dockerfile.python、helm values.yaml 的 podSecurity 一致（门禁：
# scripts/static-checks.py --container-uid）。
# /app/uploads 是 java 唯一的写入点（uploads/documents、chat-images、avatars 都相对
# user.dir=/app），镜像里不建它，空卷/空 PVC 就以 root 属主挂上来，非 root 进程
# 的第一次 mkdir 就是 AccessDenied。
RUN addgroup -S -g 10001 hfusionhub && adduser -S -u 10001 -G hfusionhub hfusionhub \
    && mkdir -p /app/uploads && chown -R hfusionhub:hfusionhub /app/uploads
COPY --from=build /app/target/*.jar app.jar
USER hfusionhub
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
