package com.hfusionhub.service;

import com.hfusionhub.dto.OpenApiChatRequest;
import com.hfusionhub.dto.OpenApiChatResponse;

/**
 * 开放 API 对话服务 — API Key 鉴权 + 限流 + 调用 + 计费记录
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
}
