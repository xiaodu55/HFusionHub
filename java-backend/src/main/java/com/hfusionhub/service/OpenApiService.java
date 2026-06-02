package com.hfusionhub.service;

import com.hfusionhub.dto.OpenApiBidCheckResponse;
import com.hfusionhub.dto.OpenApiChatRequest;
import com.hfusionhub.dto.OpenApiChatResponse;

/**
 * 开放 API 服务 — API Key 鉴权 + 限流 + 调用 + 计费记录
 *
 * @author HFusionHub Team
 */
public interface OpenApiService {

    /**
     * 处理一次开放 API 对话调用。
     *
     * @param apiKey   明文 API Key（来自 Authorization 或 X-API-Key）
     * @param request  对话请求
     * @return 对话响应
     */
    OpenApiChatResponse chat(String apiKey, OpenApiChatRequest request);

    /**
     * 开放 API 废标自检（P2-7 /openapi/bid/check）。
     *
     * <p>以 API Key 所属应用的所有者身份，在其租户上下文内对指定投标项目执行自检；
     * 需租户已开通 {@code openapi} 模块。</p>
     *
     * @param apiKey    明文 API Key
     * @param projectId 投标项目 ID（须属于 Key 所属租户）
     * @return 自检统计
     */
    OpenApiBidCheckResponse bidCheck(String apiKey, Long projectId);
}
