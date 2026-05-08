# Swagger UI 配置指南

## 当前状态

HFusionHub 已集成 Swagger UI（基于 SpringDoc OpenAPI 3），提供完整的 REST API 文档和交互式测试界面。

## 访问地址

### 开发环境
- **Swagger UI**：http://localhost:8080/swagger-ui/index.html
- **OpenAPI JSON**：http://localhost:8080/v3/api-docs
- **OpenAPI YAML**：http://localhost:8080/v3/api-docs.yaml

### 生产环境
⚠️ **安全建议**：生产环境应关闭 Swagger UI 或限制访问

---

## 开发环境配置（已启用）

当前 `application.yml` 配置：

```yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
    operations-sorter: alpha
    tags-sorter: alpha
  packages-to-scan: com.hfusionhub.controller
```

---

## 生产环境配置

### 方案 1：完全关闭（推荐）

编辑 `java-backend/src/main/resources/application-prod.yml`：

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

启动时指定 profile：
```bash
java -jar hfusionhub-backend.jar --spring.profiles.active=prod
```

### 方案 2：IP 白名单限制

通过 Nginx 反向代理限制访问（示例 `deploy/nginx.conf`）：

```nginx
location /swagger-ui {
    allow 10.0.0.0/8;        # 内网
    allow 192.168.0.0/16;    # 内网
    deny all;
    proxy_pass http://java-backend:8080;
}

location /v3/api-docs {
    allow 10.0.0.0/8;
    allow 192.168.0.0/16;
    deny all;
    proxy_pass http://java-backend:8080;
}
```

### 方案 3：Basic Auth 认证

Spring Security 配置（示例）：

```java
@Bean
public SecurityFilterChain swaggerSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/swagger-ui/**", "/v3/api-docs/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
```

配置用户名密码：
```yaml
spring:
  security:
    user:
      name: swagger-admin
      password: ${SWAGGER_PASSWORD}  # 环境变量注入
```

---

## API 文档标注

### Controller 示例

```java
@RestController
@RequestMapping("/knowledge-base")
@Tag(name = "知识库管理", description = "知识库 CRUD、共享、统计")
public class KnowledgeBaseController {

    @GetMapping("/my")
    @Operation(summary = "我的知识库", description = "分页查询当前用户创建的知识库")
    public R<PageResult<KnowledgeBaseVO>> myKnowledgeBases(
            @Parameter(description = "页码", example = "1") @RequestParam(defaultValue = "1") long page,
            @Parameter(description = "每页大小", example = "10") @RequestParam(defaultValue = "10") long pageSize) {
        // ...
    }
}
```

### 常用注解

| 注解 | 用途 | 示例 |
|------|------|------|
| `@Tag` | Controller 分组 | `@Tag(name = "用户管理")` |
| `@Operation` | 接口描述 | `@Operation(summary = "登录")` |
| `@Parameter` | 参数说明 | `@Parameter(description = "用户ID")` |
| `@Schema` | DTO 字段说明 | `@Schema(description = "邮箱", example = "user@example.com")` |

---

## 性能优化

### 减少启动扫描时间

限制包扫描范围（已配置）：
```yaml
springdoc:
  packages-to-scan: com.hfusionhub.controller
```

### 懒加载（可选）

```yaml
springdoc:
  swagger-ui:
    enabled: true
    lazy: true  # UI 懒加载，减少首次访问开销
```

---

## 常见问题

### 1. Swagger UI 404

**原因**：`springdoc.swagger-ui.enabled=false` 或未添加依赖

**解决**：
```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.2.0</version>
</dependency>
```

### 2. 接口显示不全

**原因**：Controller 未在 `packages-to-scan` 范围内

**解决**：检查包路径配置或移除该限制

### 3. 生产环境泄露 API

**原因**：未关闭 Swagger 或未配置访问限制

**解决**：采用上述方案 1（完全关闭）或方案 2/3（访问控制）

---

## 验证步骤

1. **启动服务**
   ```bash
   cd java-backend && mvn spring-boot:run
   ```

2. **访问 Swagger UI**
   ```
   http://localhost:8080/swagger-ui/index.html
   ```

3. **测试接口**
   - 点击 `/user/login` → "Try it out"
   - 输入 `{"username":"admin","password":"<docker/.env 中的 ADMIN_PASSWORD>"}`
   - 执行并验证响应

4. **复制 Token**
   - 从响应中复制 `data` 字段（Sa-Token）
   - 点击右上角 "Authorize"
   - 输入 Token → "Authorize"
   - 所有需要认证的接口现在可测试

---

## 生产环境部署建议

| 环境 | Swagger UI | 策略 |
|------|-----------|------|
| 本地开发 | ✅ 启用 | 完整功能 |
| 测试环境 | ✅ 启用 | IP 白名单或 VPN |
| 预生产 | ⚠️ 限制 | Basic Auth |
| 生产环境 | ❌ 关闭 | 完全禁用 |

---

**最后更新**：2026-08-19  
**相关文档**：[api.md](api.md)（API 参考）、[java-backend.md](java-backend.md)（Java 后端开发指南）
