package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.MessageInfoDTO;
import com.hfusionhub.dto.MessageSendDTO;
import com.hfusionhub.entity.Conversation;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.Message;
import com.hfusionhub.mapper.ConversationMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.service.KbShareService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * 消息持久化（自 ConversationServiceImpl 收口，R15-24 第三批）——
 * 用户/助手消息落库（requestId 幂等：唯一键冲突后回查已有消息）与
 * Message → MessageInfoDTO 转换（V1 元数据从 sources 提取）的统一入口。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class MessagePersistenceService {

    private final MessageMapper messageMapper;
    private final ConversationMapper conversationMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final KbShareService kbShareService;

    @Transactional
    public Message saveUserMessage(MessageSendDTO dto, String requestId) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        Conversation conversation = conversationMapper.selectById(dto.getConversationId());
        if (conversation == null) throw new BusinessException("对话不存在");
        if (!conversation.getUserId().equals(currentUserId)) throw new BusinessException("无权发送消息");
        if (conversation.getKnowledgeBaseId() != null) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(conversation.getKnowledgeBaseId());
            if (kb == null || kb.getDeleted() == 1 || kb.getStatus() != 0) throw new BusinessException("关联的知识库已被删除或禁用");
            if (!kb.getUserId().equals(currentUserId) && !kbShareService.canRead(currentUserId, kb.getId()))
                throw new BusinessException("无权访问关联的知识库");
        }
        Message existingUser = findUserByRequestId(requestId);
        if (existingUser != null) {
            return existingUser;
        }
        Message userMessage = new Message();
        userMessage.setConversationId(dto.getConversationId());
        userMessage.setRole("user");
        userMessage.setContent(dto.getContent());
        userMessage.setRequestId(requestId);
        try {
            messageMapper.insert(userMessage);
        } catch (DuplicateKeyException e) {
            existingUser = findUserByRequestId(requestId);
            if (existingUser != null) {
                return existingUser;
            }
            throw e;
        }
        return userMessage;
    }

    /**
     * 阶段 3: 短事务保存助手消息并更新对话标题
     */
    @Transactional
    public MessageInfoDTO saveAssistantMessage(
            Long conversationId,
            String content,
            String model,
            int tokenCount,
            List<Map<String, Object>> sources,
            Conversation conversation,
            String userContent) {
        return saveAssistantMessage(
                conversationId, content, model, tokenCount, sources, conversation, userContent, null);
    }

    @Transactional
    public MessageInfoDTO saveAssistantMessage(
            Long conversationId,
            String content,
            String model,
            int tokenCount,
            List<Map<String, Object>> sources,
            Conversation conversation,
            String userContent,
            String requestId) {
        Message existingAssistant = findAssistantByRequestId(requestId);
        if (existingAssistant != null) {
            return convertToMessageInfoDTO(existingAssistant);
        }
        Message msg = new Message();
        msg.setConversationId(conversationId);
        msg.setRole("assistant");
        msg.setContent(content);
        msg.setModel(model);
        msg.setTokenCount(tokenCount);
        msg.setSources(sources);
        msg.setRequestId(requestId);
        try {
            messageMapper.insert(msg);
        } catch (DuplicateKeyException e) {
            existingAssistant = findAssistantByRequestId(requestId);
            if (existingAssistant != null) {
                return convertToMessageInfoDTO(existingAssistant);
            }
            throw e;
        }
        if ("新对话".equals(conversation.getTitle()) && StringUtils.hasText(userContent)) {
            conversation.setTitle(userContent.length() > 50 ? userContent.substring(0, 50) + "..." : userContent);
            conversationMapper.updateById(conversation);
        }
        return convertToMessageInfoDTO(msg);
    }

    /**
     * Save assistant message from a full AiClient.ChatResponse, preserving
     * Agent V1 metadata (status, agent_run_id, tool_calls_count,
     * token_usage) alongside the core answer + sources.
     */
    @Transactional
    public MessageInfoDTO saveAssistantMessageV1(
            Long conversationId,
            AiClient.ChatResponse aiResponse,
            Conversation conversation,
            String userContent,
            String requestId) {
        Message existingAssistant = findAssistantByRequestId(requestId);
        if (existingAssistant != null) {
            return convertToMessageInfoDTO(existingAssistant);
        }
        // Primary content: prefer answer if content is null (V1 path sends both).
        String primaryContent = aiResponse.getContent() != null ? aiResponse.getContent() : aiResponse.getAnswer();

        Message msg = new Message();
        msg.setConversationId(conversationId);
        msg.setRole("assistant");
        msg.setContent(primaryContent != null ? primaryContent : "");
        msg.setModel(aiResponse.getModel());
        msg.setTokenCount(aiResponse.getTokenCount());
        msg.setSources(aiResponse.getSources());
        msg.setRequestId(requestId);

        // Agent V1 metadata — stored as sources extension.
        // Existing sources already contain citations; append V1 run metadata
        // as a reserved entry so the frontend can render status badges.
        if (aiResponse.getStatus() != null || aiResponse.getAgentRunId() != null) {
            List<Map<String, Object>> enrichedSources =
                    new java.util.ArrayList<>(msg.getSources() != null ? msg.getSources() : List.of());
            Map<String, Object> v1Meta = new HashMap<>();
            v1Meta.put("_v1", true);
            if (aiResponse.getStatus() != null) {
                v1Meta.put("status", aiResponse.getStatus());
            }
            if (aiResponse.getAgentRunId() != null) {
                v1Meta.put("agent_run_id", aiResponse.getAgentRunId());
            }
            if (aiResponse.getToolCallsCount() > 0) {
                v1Meta.put("tool_calls_count", aiResponse.getToolCallsCount());
            }
            if (aiResponse.getTokenUsage() != null) {
                v1Meta.put("token_usage", aiResponse.getTokenUsage());
            }
            if (aiResponse.getErrorDetail() != null) {
                v1Meta.put("error_detail", aiResponse.getErrorDetail());
            }
            enrichedSources.add(v1Meta);
            msg.setSources(enrichedSources);
        }

        try {
            messageMapper.insert(msg);
        } catch (DuplicateKeyException e) {
            existingAssistant = findAssistantByRequestId(requestId);
            if (existingAssistant != null) {
                return convertToMessageInfoDTO(existingAssistant);
            }
            throw e;
        }
        if ("新对话".equals(conversation.getTitle()) && StringUtils.hasText(userContent)) {
            conversation.setTitle(userContent.length() > 50 ? userContent.substring(0, 50) + "..." : userContent);
            conversationMapper.updateById(conversation);
        }
        return convertToMessageInfoDTO(msg);
    }

    public Message findUserByRequestId(String requestId) {
        return findMessageByRequestId("user", requestId);
    }

    public Message findAssistantByRequestId(String requestId) {
        return findMessageByRequestId("assistant", requestId);
    }

    private Message findMessageByRequestId(String role, String requestId) {
        if (!StringUtils.hasText(requestId)) {
            return null;
        }
        return messageMapper.selectOne(
                new LambdaQueryWrapper<Message>().eq(Message::getRole, role).eq(Message::getRequestId, requestId));
    }

    /**
     * Message → MessageInfoDTO, extracting Agent V1 metadata from sources
     * when present.
     */
    public MessageInfoDTO convertToMessageInfoDTO(Message message) {
        List<Map<String, Object>> rawSources = message.getSources();
        List<Map<String, Object>> visibleSources = new java.util.ArrayList<>();
        String v1Status = null;
        String v1AgentRunId = null;
        Integer v1ToolCallsCount = null;

        if (rawSources != null) {
            for (Map<String, Object> entry : rawSources) {
                if (Boolean.TRUE.equals(entry.get("_v1"))) {
                    v1Status = (String) entry.get("status");
                    v1AgentRunId = (String) entry.get("agent_run_id");
                    Object tcc = entry.get("tool_calls_count");
                    if (tcc instanceof Number n) {
                        v1ToolCallsCount = n.intValue();
                    }
                } else {
                    visibleSources.add(entry);
                }
            }
        }

        return MessageInfoDTO.builder()
                .id(message.getId())
                .conversationId(message.getConversationId())
                .role(message.getRole())
                .content(message.getContent())
                .tokenCount(message.getTokenCount())
                .model(message.getModel())
                .sources(visibleSources.isEmpty() ? null : visibleSources)
                .createdAt(message.getCreatedAt())
                .status(v1Status)
                .agentRunId(v1AgentRunId)
                .toolCallsCount(v1ToolCallsCount)
                .build();
    }
}
