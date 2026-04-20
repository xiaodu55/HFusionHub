package com.hfusionhub.service;

/**
 * 操作审计服务 — 记录敏感操作（C1）
 *
 * @author HFusionHub Team
 */
public interface AuditLogService {

    /**
     * 记录一次敏感操作（失败不抛出，不影响主流程）。
     *
     * @param action     动作，如 app.publish
     * @param targetType 目标类型，如 app / app_api_key / kb_share / system_notice
     * @param targetId   目标ID（可空）
     * @param detail     摘要（不含敏感数据，可空）
     */
    void record(String action, String targetType, String targetId, String detail);
}
