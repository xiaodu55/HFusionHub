package com.hfusionhub.client;

import com.hfusionhub.support.AbstractItMySQLTest;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

/**
 * Java→Python 集成冒烟测试 — 覆盖 CI 单测各自独立时的关键盲区。
 *
 * <p>仅在 CI 设置 {@code CI_SMOKE_PYTHON_URL} 时执行（本地默认跳过）。验证：
 * 生产 {@link RestTemplate}（JdkClientHttpRequestFactory 显式锁定 HTTP/1.1）
 * 实际调通 Python AI 的一个需 internal-token 的 /api 端点。若未来有人回退
 * h2c 升级（JDK HttpClient 默认 HTTP_2 对明文 http 发 {@code Upgrade: h2c}），
 * uvicorn/h11 会回 400 "Invalid HTTP request received."，本测试即失败。</p>
 *
 * <p>为什么选 /api/stats/vector-counts 而非 /api/parse：它轻量、无副作用、
 * 不依赖文件与 Milvus（Milvus 不可达时返回 0），又能验证 internal-token
 * + tenant + HTTP 传输全链路。</p>
 */
@EnabledIfEnvironmentVariable(named = "CI_SMOKE_PYTHON_URL", matches = ".+")
class PythonEngineSmokeTest extends AbstractItMySQLTest {

    @Autowired
    private RestTemplate restTemplate;

    @Value("${python-ai.internal-token:}")
    private String internalToken;

    // 冒烟只验证 Java→Python HTTP 链路，Redis 与断言无关；
    // 测试 profile 下上下文不提供真实 RedisConnectionFactory，需 mock。
    @MockBean
    private RedisConnectionFactory redisConnectionFactory;

    @MockBean
    private StringRedisTemplate stringRedisTemplate;

    @Test
    void javaRestTemplateReachesPythonEngine() {
        String url = System.getenv("CI_SMOKE_PYTHON_URL") + "/api/stats/vector-counts";
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Internal-Token", internalToken);
        headers.set("X-Tenant-Id", "1");
        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(Map.of("knowledge_base_ids", List.of(1)), headers);

        ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.POST, entity, String.class);

        assertTrue(
                response.getStatusCode().is2xxSuccessful(),
                "Java→Python 冒烟失败: HTTP " + response.getStatusCode() + " — " + response.getBody());
        assertNotNull(response.getBody());
        assertFalse(
                response.getBody().contains("Invalid HTTP request"),
                "h2c 升级回归: Python 拒绝了明文 HTTP/1.1 升级请求 — " + response.getBody());
    }
}
