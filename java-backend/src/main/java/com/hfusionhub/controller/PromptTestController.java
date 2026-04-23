package com.hfusionhub.controller;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.PromptTestRequest;
import com.hfusionhub.dto.PromptTestResponse;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 提示词测试台控制器 — 不创建对话，纯评测模板效果
 *
 * @author HFusionHub Team
 */
@Slf4j
@Tag(name = "提示词测试台", description = "选择模板和问题，查看回答、来源、耗时与 Token 消耗")
@RestController
@RequestMapping("/prompt-templates")
@RequiredArgsConstructor
public class PromptTestController {

    private final AiClient aiClient;
    private final KnowledgeBaseMapper knowledgeBaseMapper;

    @Operation(summary = "运行提示词测试", description = "使用模板内容作为系统指令，向 AI 发送测试问题并返回回答、来源、耗时与 Token 消耗。不创建对话，不持久化消息。")
    @PostMapping("/test")
    public R<PromptTestResponse> test(@Valid @RequestBody PromptTestRequest request) {
        Long currentUserId = JwtUtils.getCurrentUserId();

        // 1. 验证知识库权限（如果指定了）
        if (request.getKnowledgeBaseId() != null && request.getKnowledgeBaseId() > 0) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(request.getKnowledgeBaseId());
            if (kb == null) {
                throw new BusinessException("知识库不存在");
            }
            if (!kb.getUserId().equals(currentUserId)) {
                throw new BusinessException("无权访问该知识库");
            }
        }

        // 2. 计时 + 调用 AI（模板通过 system_prompt 字段传递，支持 8000 字符）
        long startTime = System.currentTimeMillis();
        AiClient.ChatResponse aiResponse;
        try {
            if (request.getKnowledgeBaseId() != null && request.getKnowledgeBaseId() > 0) {
                // KB 绑定 → Agent V1 检索增强
                aiResponse = aiClient.agentV1Chat(
                        request.getQuestion(),
                        null, // conversationId: null（不关联对话）
                        request.getKnowledgeBaseId(),
                        List.of(), // history: 测试台无历史
                        request.getTemplateContent(), // systemPrompt: 支持 8000 字符
                        "detailed",
                        5,
                        null, // requestId: null（测试台不幂等）
                        currentUserId);
            } else {
                // 纯 LLM 对话
                aiResponse = aiClient.chat(
                        request.getQuestion(),
                        null, // conversationId: null
                        null, // knowledgeBaseId: null
                        List.of(), // history: 测试台无历史
                        request.getTemplateContent(), // systemPrompt: 支持 8000 字符
                        currentUserId);
            }
        } catch (Exception e) {
            log.error("提示词测试台调用 AI 失败: {}", e.getMessage(), e);
            throw new BusinessException("AI 服务调用失败: " + e.getMessage());
        }

        long elapsedMs = System.currentTimeMillis() - startTime;

        // 4. 组装响应
        PromptTestResponse response = PromptTestResponse.builder()
                .content(aiResponse.getContent() != null ? aiResponse.getContent() : aiResponse.getAnswer())
                .model(aiResponse.getModel())
                .tokenCount(aiResponse.getTokenCount())
                .tokenUsage(aiResponse.getTokenUsage())
                .sources(aiResponse.getSources())
                .elapsedMs(elapsedMs)
                .build();

        log.info(
                "提示词测试台: elapsedMs={}, model={}, tokenCount={}, hasSources={}",
                elapsedMs,
                response.getModel(),
                response.getTokenCount(),
                response.getSources() != null && !response.getSources().isEmpty());

        return R.ok("测试完成", response);
    }
}
