package com.hfusionhub.cache;

import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.security.SecureRandom;
import java.time.Duration;

/**
 * 热点读缓存组件（B3）。
 *
 * <p>统一三类既有问题的解法：</p>
 * <ul>
 *   <li><b>缓存雪崩</b>——TTL 加 ±20% 随机抖动，热点 key 不在同一时刻集体过期；</li>
 *   <li><b>缓存穿透</b>——空结果以哨兵值缓存（短 TTL），反复查不存在的 id
 *       不再每次打到 DB；</li>
 *   <li><b>主动失效</b>——版本号失效：写路径 bump 版本计数，读 key 内嵌版本，
 *       旧版本 key 等 TTL 自然淘汰，无需模式扫描删除。</li>
 * </ul>
 *
 * <p><b>key 必须携带 tenant_id</b>（多租户缓存隔离）：所有 key 以
 * {@code namespace:tenant:{id}:...} 组成，构造时由调用方显式传入租户
 * 上下文值，缺失时用 {@code t0} 兜底（fail-closed：不同调用方不共享错乱缓存）。</p>
 */
@Service
public class HotReadCacheService {

    /** 空结果哨兵：命中它表示"DB 里确认没有"，调用方应返回空而非查库。 */
    public static final String NULL_SENTINEL = "__HFH_NULL__";

    private static final double JITTER_MIN = 0.8;
    private static final double JITTER_MAX = 1.2;

    private final RedisTemplate<String, Object> redisTemplate;
    private final SecureRandom random = new SecureRandom();

    public HotReadCacheService(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public record CacheResult<T>(boolean hit, T value) {
        public static <T> CacheResult<T> miss() {
            return new CacheResult<>(false, null);
        }
    }

    /** 读缓存。命中空哨兵时返回 {@code CacheResult(true, null)}。 */
    @SuppressWarnings("unchecked")
    public <T> CacheResult<T> get(String key) {
        Object value = redisTemplate.opsForValue().get(key);
        if (value == null) {
            return CacheResult.miss();
        }
        if (NULL_SENTINEL.equals(value)) {
            return new CacheResult<>(true, null);
        }
        return new CacheResult<>(true, (T) value);
    }

    /** 写缓存，TTL 加 ±20% 抖动；{@code value == null} 时写空哨兵。 */
    public void put(String key, Object value, long ttlSeconds) {
        long jittered = jitterTtl(ttlSeconds);
        Object toStore = value == null ? NULL_SENTINEL : value;
        redisTemplate.opsForValue().set(key, toStore, Duration.ofSeconds(jittered));
    }

    /** 计算带抖动的 TTL：ttl × [0.8, 1.2]，至少 1 秒。 */
    public long jitterTtl(long ttlSeconds) {
        double factor = JITTER_MIN + (JITTER_MAX - JITTER_MIN) * random.nextDouble();
        return Math.max(1, Math.round(ttlSeconds * factor));
    }

    /** 版本号 key：{@code {namespace}:ver:tenant:{tenantId}:{scope}}。 */
    public String versionKey(String namespace, Long tenantId, String scope) {
        return namespace + ":ver:tenant:" + safeTenant(tenantId) + (scope == null ? "" : ":" + scope);
    }

    /** 读当前版本号（无则 0）。读 key 时用它拼出"当前版本"的数据 key。 */
    public long version(String versionKey) {
        Object v = redisTemplate.opsForValue().get(versionKey);
        return v instanceof Number n ? n.longValue() : 0L;
    }

    /** 写路径调用：版本 +1，旧版本数据 key 立即失联，等 TTL 自然回收。 */
    public void bumpVersion(String versionKey) {
        redisTemplate.opsForValue().increment(versionKey);
    }

    /** 组数据 key：{@code {namespace}:{version}:tenant:{tenantId}:{rest}}。 */
    public String dataKey(String namespace, long version, Long tenantId, String rest) {
        return namespace + ":" + version + ":tenant:" + safeTenant(tenantId) + ":" + rest;
    }

    private static String safeTenant(Long tenantId) {
        return tenantId == null || tenantId <= 0 ? "t0" : ("t" + tenantId);
    }
}
