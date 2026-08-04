package com.hfusionhub.service.impl;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * Agent 任务域纯函数工具。
 *
 * <p>审批令牌哈希的签名（{@link AgentTaskServiceImpl#pauseForApproval}）与
 * 恢复校验（{@link AgentTaskDecisionService}）必须共享同一实现，否则规则在
 * 一侧演进会导致全部审批恢复失败——因此收口于此，禁止两侧各自持有副本。</p>
 *
 * @author HFusionHub Team
 */
final class AgentTaskSupport {

    private AgentTaskSupport() {}

    /**
     * 运行耗时钳制（时钟回拨防护）：调用方未传时长（<=0）且 run 有 startedAt 时
     * 以墙钟相减兜底；startedAt 晚于当前墙钟（NTP 校正/宿主机休眠恢复）会得到
     * 负值，一律钳为 0 —— 负耗时入库会经 model_usage_record.latency_ms 传导到
     * 运营数仓，被质量门禁 R4 拦截。
     */
    static long clampDuration(long durationMs, LocalDateTime startedAt) {
        long actual = durationMs;
        if (actual <= 0 && startedAt != null) {
            actual = Math.max(0, java.time.Duration.between(startedAt, LocalDateTime.now()).toMillis());
        }
        return Math.max(0, actual);
    }

    /** 审批令牌绑定哈希：对工具入参做键序规范化 JSON 后取 SHA-256。 */
    static String canonicalToolInputHash(String input) {
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            String canonical = mapper.writeValueAsString(sortJson(mapper.readTree(input == null ? "{}" : input)));
            return sha256(canonical);
        } catch (Exception e) {
            throw new com.hfusionhub.common.exception.BusinessException("invalid tool input");
        }
    }

    private static String sha256(String input) {
        try {
            java.security.MessageDigest md = java.security.MessageDigest.getInstance("SHA-256");
            byte[] hash = md.digest(input.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte b : hash) hex.append(String.format("%02x", b));
            return hex.toString();
        } catch (Exception e) {
            return input; // fallback — should never happen
        }
    }

    private static Object sortJson(com.fasterxml.jackson.databind.JsonNode node) {
        if (node.isObject()) {
            Map<String, Object> sorted = new java.util.TreeMap<>();
            node.fields().forEachRemaining(entry -> sorted.put(entry.getKey(), sortJson(entry.getValue())));
            return sorted;
        }
        if (node.isArray()) {
            List<Object> values = new java.util.ArrayList<>();
            node.forEach(value -> values.add(sortJson(value)));
            return values;
        }
        if (node.isTextual()) return node.textValue();
        if (node.isBoolean()) return node.booleanValue();
        if (node.isNumber()) return node.numberValue();
        if (node.isNull()) return null;
        throw new IllegalArgumentException("unsupported JSON node");
    }
}
