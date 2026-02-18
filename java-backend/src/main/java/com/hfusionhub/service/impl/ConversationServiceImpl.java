package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.ConversationCreateDTO;
import com.hfusionhub.dto.ConversationInfoDTO;
import com.hfusionhub.dto.ConversationQueryDTO;
import com.hfusionhub.dto.MessageInfoDTO;
import com.hfusionhub.dto.MessageSendDTO;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.entity.Conversation;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.Message;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.ConversationMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.ConversationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Collectors;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 对话服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ConversationServiceImpl implements ConversationService {

    private final ConversationMapper conversationMapper;
    private final MessageMapper messageMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final UserMapper userMapper;
    private final AiClient aiClient;
    private final WebClient webClient;

    @Value("${ai-service.base-url:http://localhost:8001}")
    private String baseUrl;

    @Value("${python-ai.internal-token:}")
    private String internalApiToken;

    @Override
    @Transactional
    public ConversationInfoDTO create(ConversationCreateDTO dto) {
        // 1. 获取当前用户
        Long currentUserId = JwtUtils.getCurrentUserId();

        // 2. 如果指定了知识库，验证知识库存在且属于当前用户
        if (dto.getKnowledgeBaseId() != null) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(dto.getKnowledgeBaseId());
            if (kb == null) {
                throw new BusinessException("知识库不存在");
            }
            if (!kb.getUserId().equals(currentUserId)) {
                throw new BusinessException("无权访问该知识库");
            }
        }

        // 3. 创建对话
        Conversation conversation = new Conversation();
        conversation.setKnowledgeBaseId(dto.getKnowledgeBaseId());
        conversation.setUserId(currentUserId);
        conversation.setTitle(StringUtils.hasText(dto.getTitle()) ? dto.getTitle() : "新对话");
        conversationMapper.insert(conversation);

        // 4. 转换为 DTO
        return convertToInfoDTO(conversation);
    }

    @Override
    @Transactional
    public void delete(Long id) {
        // 1. 查询对话
        Conversation conversation = conversationMapper.selectById(id);
        if (conversation == null) {
            throw new BusinessException("对话不存在");
        }

        // 2. 验证权限
        Long currentUserId = JwtUtils.getCurrentUserId();
        if (!conversation.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权删除该对话");
        }

        // 3. 逻辑删除对话
        conversationMapper.deleteById(id);

        // 4. 删除对话下的所有消息
        LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Message::getConversationId, id);
        messageMapper.delete(wrapper);
    }

    @Override
    public ConversationInfoDTO getById(Long id) {
        // 1. 查询对话
        Conversation conversation = conversationMapper.selectById(id);
        if (conversation == null) {
            throw new BusinessException("对话不存在");
        }
        if (!conversation.getUserId().equals(JwtUtils.getCurrentUserId())) {
            throw new BusinessException("无权访问该对话");
        }

        // 2. 转换为 DTO
        return convertToInfoDTO(conversation);
    }

    @Override
    public PageResult<ConversationInfoDTO> list(ConversationQueryDTO queryDTO) {
        return listByCurrentUser(queryDTO);
    }

    @Override
    public PageResult<ConversationInfoDTO> listByCurrentUser(ConversationQueryDTO queryDTO) {
        // 1. 获取当前用户
        Long currentUserId = JwtUtils.getCurrentUserId();

        // 2. 构建查询条件
        LambdaQueryWrapper<Conversation> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Conversation::getUserId, currentUserId)
                .eq(queryDTO.getKnowledgeBaseId() != null, Conversation::getKnowledgeBaseId, queryDTO.getKnowledgeBaseId())
                .like(StringUtils.hasText(queryDTO.getTitle()), Conversation::getTitle, queryDTO.getTitle())
                .orderByDesc(Conversation::getCreatedAt);

        // 3. 分页查询
        Page<Conversation> page = new Page<>(queryDTO.getPage(), queryDTO.getPageSize());
        Page<Conversation> result = conversationMapper.selectPage(page, wrapper);

        // 4. 批量转换为 DTO（优化 N+1 查询）
        List<ConversationInfoDTO> records = batchConvertToInfoDTO(result.getRecords());

        // 5. 返回分页结果
        return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), result.getTotal(), records);
    }

    @Override
    @Transactional
    public MessageInfoDTO sendMessage(MessageSendDTO dto) {
        // 1. 查询对话
        Conversation conversation = conversationMapper.selectById(dto.getConversationId());
        if (conversation == null) {
            throw new BusinessException("对话不存在");
        }

        // 2. 验证权限
        Long currentUserId = JwtUtils.getCurrentUserId();
        if (!conversation.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权发送消息");
        }

        // 3. 保存用户消息
        Message userMessage = new Message();
        userMessage.setConversationId(dto.getConversationId());
        userMessage.setRole("user");
        userMessage.setContent(dto.getContent());
        messageMapper.insert(userMessage);

        // 4. 获取对话历史
        List<Map<String, String>> history = getChatHistory(conversation.getId());

        // 5. 调用 Python AI 服务获取回复
        try {
            AiClient.ChatResponse aiResponse = aiClient.chat(
                    dto.getContent(),
                    dto.getConversationId(),
                    conversation.getKnowledgeBaseId(),
                    history
            );

            // 保存助手消息
            Message assistantMessage = new Message();
            assistantMessage.setConversationId(dto.getConversationId());
            assistantMessage.setRole("assistant");
            assistantMessage.setContent(aiResponse.getContent());
            assistantMessage.setModel(aiResponse.getModel());
            assistantMessage.setTokenCount(aiResponse.getTokenCount());
            assistantMessage.setSources(aiResponse.getSources());
            messageMapper.insert(assistantMessage);

            // 6. 更新对话标题（如果是第一条消息）
            if ("新对话".equals(conversation.getTitle()) && StringUtils.hasText(dto.getContent())) {
                String title = dto.getContent();
                if (title.length() > 50) {
                    title = title.substring(0, 50) + "...";
                }
                conversation.setTitle(title);
                conversationMapper.updateById(conversation);
            }

            // 7. 返回助手消息
            return convertToMessageInfoDTO(assistantMessage);

        } catch (Exception e) {
            log.error("Failed to get AI response: {}", e.getMessage(), e);

            // Fallback to mock response if AI service fails
            Message assistantMessage = new Message();
            assistantMessage.setConversationId(dto.getConversationId());
            assistantMessage.setRole("assistant");
            assistantMessage.setContent("抱歉，AI服务暂时不可用。请稍后再试。");
            assistantMessage.setModel("fallback");
            assistantMessage.setTokenCount(0);
            messageMapper.insert(assistantMessage);

            return convertToMessageInfoDTO(assistantMessage);
        }
    }

    /**
     * Get chat history for conversation
     */
    private List<Map<String, String>> getChatHistory(Long conversationId) {
        LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Message::getConversationId, conversationId)
                .orderByAsc(Message::getCreatedAt)
                .last("LIMIT 20");  // Keep last 20 messages for context

        List<Message> messages = messageMapper.selectList(wrapper);

        return messages.stream()
                .map(m -> {
                    Map<String, String> map = new HashMap<>();
                    map.put("role", m.getRole());
                    map.put("content", m.getContent());
                    return map;
                })
                .collect(Collectors.toList());
    }

    @Override
    public List<MessageInfoDTO> getMessages(Long conversationId) {
        // 1. 查询对话
        Conversation conversation = conversationMapper.selectById(conversationId);
        if (conversation == null) {
            throw new BusinessException("对话不存在");
        }

        // 2. 验证权限
        Long currentUserId = JwtUtils.getCurrentUserId();
        if (!conversation.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权访问该对话");
        }

        // 3. 查询消息列表（使用自定义 XML 查询，确保 sources JSON 正确反序列化）
        List<Message> messages = messageMapper.selectByConversationId(conversationId);

        // 4. 转换为 DTO
        return messages.stream()
                .map(this::convertToMessageInfoDTO)
                .collect(Collectors.toList());
    }

    @Override
    public void sendMessageStream(MessageSendDTO dto, SseEmitter emitter) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        sendMessageStream(dto, emitter, currentUserId, new AtomicBoolean(false));
    }

    @Override
    public void sendMessageStream(MessageSendDTO dto, SseEmitter emitter, Long currentUserId) {
        sendMessageStream(dto, emitter, currentUserId, new AtomicBoolean(false));
    }

    @Override
    public void sendMessageStream(MessageSendDTO dto, SseEmitter emitter, Long currentUserId, AtomicBoolean cancelled) {
        // 1. 查询对话
        Conversation conversation = conversationMapper.selectById(dto.getConversationId());
        if (conversation == null) {
            emitter.completeWithError(new BusinessException("对话不存在"));
            return;
        }

        // 2. 验证权限
        if (!conversation.getUserId().equals(currentUserId)) {
            emitter.completeWithError(new BusinessException("无权发送消息"));
            return;
        }

        // 3. 保存用户消息
        Message userMessage = new Message();
        userMessage.setConversationId(dto.getConversationId());
        userMessage.setRole("user");
        userMessage.setContent(dto.getContent());
        messageMapper.insert(userMessage);

        // 4. 获取对话历史
        List<Map<String, String>> history = getChatHistory(conversation.getId());

        // 5. 使用 HttpURLConnection 实现真正的流式响应（简单可靠）
        String requestId = java.util.UUID.randomUUID().toString();
        StringBuilder responseBuilder = new StringBuilder();
        java.util.List<Map<String, Object>> accumulatedSources = new java.util.ArrayList<>();

        try {
            // 构建请求体
            com.fasterxml.jackson.databind.ObjectMapper objectMapper = new com.fasterxml.jackson.databind.ObjectMapper();
            long startTime = System.currentTimeMillis();
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("message", dto.getContent());
            requestBody.put("conversation_id", dto.getConversationId());
            requestBody.put("knowledge_base_id", conversation.getKnowledgeBaseId());
            requestBody.put("history", history != null ? history : List.of());
            requestBody.put("stream", true);
            requestBody.put("request_id", requestId);

            String url = baseUrl + "/api/chat/stream";
            log.info("Starting streaming request to Python AI: {}, requestId: {}, kbId: {}", url, requestId, conversation.getKnowledgeBaseId());

            // 使用 HttpURLConnection 进行流式请求
            java.net.URL apiUrl = new java.net.URL(url);
            java.net.HttpURLConnection connection = (java.net.HttpURLConnection) apiUrl.openConnection();
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
            connection.setRequestProperty("Accept", "text/event-stream");
            if (internalApiToken == null || internalApiToken.isBlank()) {
                throw new BusinessException("PYTHON_AI_INTERNAL_TOKEN 未配置");
            }
            connection.setRequestProperty("X-Internal-Token", internalApiToken);
            connection.setDoOutput(true);
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(300000); // 5 minutes - RAG pipeline can be slow

            // 发送请求体
            byte[] bodyBytes = objectMapper.writeValueAsBytes(requestBody);
            try (java.io.OutputStream os = connection.getOutputStream()) {
                os.write(bodyBytes);
                os.flush();
            }

            // 读取流式响应
            int responseCode = connection.getResponseCode();
            if (responseCode != 200) {
                log.error("Python AI returned status: {}", responseCode);
                throw new RuntimeException("Python AI service returned status: " + responseCode);
            }

            try (java.io.BufferedReader reader = new java.io.BufferedReader(
                    new java.io.InputStreamReader(connection.getInputStream(), java.nio.charset.StandardCharsets.UTF_8))) {
                String line;
                int lineCount = 0;
                long firstContentTime = 0;
                while ((line = reader.readLine()) != null) {
                    lineCount++;
                    // 检查是否被取消
                    if (cancelled.get()) {
                        log.info("Stream cancelled by client, cancelling Python AI request: {}", requestId);
                        aiClient.cancelRequest(requestId);
                        break;
                    }

                    // 解析 SSE 数据
                    if (line.startsWith("data: ")) {
                        String data = line.substring(6).trim();
                        if ("[DONE]".equals(data)) {
                            log.info("Stream completed, received {} lines, requestId: {}", lineCount, requestId);
                            // 流式响应完成
                            emitter.send(SseEmitter.event().data("[DONE]"));
                            emitter.complete();

                            // 保存助手消息（包含 sources）
                            Message assistantMessage = new Message();
                            assistantMessage.setConversationId(dto.getConversationId());
                            assistantMessage.setRole("assistant");
                            assistantMessage.setContent(responseBuilder.toString());
                            assistantMessage.setModel("streaming");
                            assistantMessage.setTokenCount(0);
                            assistantMessage.setSources(accumulatedSources);
                            log.info("Saving assistant message - content length: {}, sources count: {}, requestId: {}",
                                    responseBuilder.length(), accumulatedSources.size(), requestId);
                            messageMapper.insert(assistantMessage);
                            log.info("Saved assistant message successfully, requestId: {}", requestId);
                        } else if (!data.isEmpty()) {
                            try {
                                // 解析 JSON 数据
                                com.fasterxml.jackson.databind.JsonNode jsonNode = objectMapper.readTree(data);
                                String content = jsonNode.has("content") ? jsonNode.get("content").asText() : "";
                                boolean isCancelled = jsonNode.has("cancelled") && jsonNode.get("cancelled").asBoolean();
                                com.fasterxml.jackson.databind.JsonNode sourcesNode = jsonNode.get("sources");

                                // 调试日志：记录接收到的数据类型
                                if (sourcesNode != null || !content.isEmpty()) {
                                    log.debug("Received chunk - content length: {}, hasSources: {}, requestId: {}",
                                            content.length(), sourcesNode != null, requestId);
                                }

                                if (isCancelled) {
                                    log.info("Python AI request cancelled: {}", requestId);
                                    emitter.send(SseEmitter.event().data("[DONE]"));
                                    emitter.complete();
                                    break;
                                }

                                // 处理 sources 信息
                                if (sourcesNode != null && sourcesNode.isArray() && sourcesNode.size() > 0) {
                                    // 累积 sources 用于后续保存
                                    List<Map<String, Object>> newSources = objectMapper.treeToValue(sourcesNode, List.class);
                                    accumulatedSources.addAll(newSources);
                                    // 转发 sources 给前端
                                    Map<String, Object> sourcesEvent = new HashMap<>();
                                    sourcesEvent.put("sources", newSources);
                                    emitter.send(SseEmitter.event().data(sourcesEvent, MediaType.APPLICATION_JSON));
                                    log.info("Forwarded {} sources to frontend, requestId: {}, total accumulated: {}", sourcesNode.size(), requestId, accumulatedSources.size());
                                } else if (sourcesNode != null) {
                                    log.debug("Sources node present but empty or not array, requestId: {}", requestId);
                                }

                                if (!content.isEmpty()) {
                                    if (firstContentTime == 0) {
                                        firstContentTime = System.currentTimeMillis();
                                        log.info("First content chunk received after {}ms, requestId: {}", firstContentTime - startTime, requestId);
                                    }
                                    responseBuilder.append(content);
                                    // 发送 SSE 事件给前端（确保格式与 Python AI 一致）
                                    Map<String, String> eventData = new HashMap<>();
                                    eventData.put("content", content);
                                    emitter.send(SseEmitter.event().data(eventData, MediaType.APPLICATION_JSON));
                                    if (lineCount % 50 == 0) {
                                        log.debug("Processed {} lines, content length: {}, requestId: {}", lineCount, responseBuilder.length(), requestId);
                                    }
                                }
                            } catch (Exception e) {
                                log.warn("Failed to parse chunk: {}", data);
                            }
                        }
                    }
                }
            } finally {
                connection.disconnect();
            }

            // 确保 emitter 总是关闭（如果 [DONE] 没有被正确发送）
            if (responseBuilder.length() > 0) {
                try {
                    // 如果有内容但没收到 [DONE]，手动补发
                    emitter.send(SseEmitter.event().data("[DONE]"));
                    emitter.complete();
                    log.info("Manually completed stream, content length: {}, requestId: {}", responseBuilder.length(), requestId);
                } catch (IllegalStateException alreadyComplete) {
                    // emitter 已经关闭，忽略
                }
                // 检查是否已经保存过消息（避免重复保存）
                LambdaQueryWrapper<Message> checkWrapper = new LambdaQueryWrapper<>();
                checkWrapper.eq(Message::getConversationId, dto.getConversationId())
                        .eq(Message::getContent, responseBuilder.toString())
                        .last("LIMIT 1");
                Message existingMessage = messageMapper.selectOne(checkWrapper);
                if (existingMessage == null) {
                    // 保存助手消息（如果之前没有保存）
                    try {
                        Message assistantMessage = new Message();
                        assistantMessage.setConversationId(dto.getConversationId());
                        assistantMessage.setRole("assistant");
                        assistantMessage.setContent(responseBuilder.toString());
                        assistantMessage.setModel("streaming");
                        assistantMessage.setTokenCount(0);
                        assistantMessage.setSources(accumulatedSources);
                        messageMapper.insert(assistantMessage);
                        log.info("Saved assistant message (fallback) with {} sources, requestId: {}", accumulatedSources.size(), requestId);
                    } catch (Exception saveEx) {
                        log.error("Failed to save assistant message: {}", saveEx.getMessage());
                    }
                } else {
                    log.info("Message already exists, skipping save, requestId: {}", requestId);
                }
            } else {
                try {
                    emitter.send(SseEmitter.event().data("[DONE]"));
                    emitter.complete();
                } catch (IllegalStateException alreadyComplete) {
                    // 忽略
                }
            }

        } catch (Exception e) {
            log.error("Failed to start streaming: {}", e.getMessage(), e);
            try {
                String errorMessage = "抱歉，AI服务暂时不可用。请稍后再试。";
                emitter.send(SseEmitter.event().data(errorMessage));
                emitter.send(SseEmitter.event().data("[DONE]"));
                emitter.complete();

                // 保存错误消息到数据库
                Message assistantMessage = new Message();
                assistantMessage.setConversationId(dto.getConversationId());
                assistantMessage.setRole("assistant");
                assistantMessage.setContent(errorMessage);
                assistantMessage.setModel("error");
                assistantMessage.setTokenCount(0);
                messageMapper.insert(assistantMessage);
            } catch (Exception ex) {
                emitter.completeWithError(ex);
            }
        }
    }

    /**
     * 批量转换 Conversation 为 ConversationInfoDTO（优化 N+1 查询）
     */
    private List<ConversationInfoDTO> batchConvertToInfoDTO(List<Conversation> conversations) {
        if (conversations.isEmpty()) {
            return List.of();
        }

        // 1. 收集所有 ID
        List<Long> conversationIds = conversations.stream()
                .map(Conversation::getId)
                .collect(Collectors.toList());

        List<Long> kbIds = conversations.stream()
                .map(Conversation::getKnowledgeBaseId)
                .filter(id -> id != null)
                .distinct()
                .collect(Collectors.toList());

        List<Long> userIds = conversations.stream()
                .map(Conversation::getUserId)
                .filter(id -> id != null)
                .distinct()
                .collect(Collectors.toList());

        // 2. 批量查询知识库
        Map<Long, String> kbNameMap = new HashMap<>();
        if (!kbIds.isEmpty()) {
            List<KnowledgeBase> kbs = knowledgeBaseMapper.selectBatchIds(kbIds);
            kbs.forEach(kb -> kbNameMap.put(kb.getId(), kb.getName()));
        }

        // 3. 批量查询用户
        Map<Long, String> userNameMap = new HashMap<>();
        if (!userIds.isEmpty()) {
            List<User> users = userMapper.selectBatchIds(userIds);
            users.forEach(user -> {
                String name = user.getNickname() != null ? user.getNickname() : user.getUsername();
                userNameMap.put(user.getId(), name);
            });
        }

        // 4. 批量查询消息数量
        Map<Long, Long> messageCountMap = new HashMap<>();
        LambdaQueryWrapper<Message> countWrapper = new LambdaQueryWrapper<>();
        countWrapper.in(Message::getConversationId, conversationIds);
        countWrapper.select(Message::getConversationId, Message::getId);
        List<Message> allMessages = messageMapper.selectList(countWrapper);
        allMessages.forEach(m -> {
            messageCountMap.merge(m.getConversationId(), 1L, Long::sum);
        });

        // 5. 批量查询最后一条消息
        Map<Long, String> lastMessageMap = new HashMap<>();
        if (!conversationIds.isEmpty()) {
            // 使用子查询获取每个对话的最新消息
            for (Long convId : conversationIds) {
                LambdaQueryWrapper<Message> lastWrapper = new LambdaQueryWrapper<>();
                lastWrapper.eq(Message::getConversationId, convId)
                        .orderByDesc(Message::getCreatedAt)
                        .last("LIMIT 1");
                Message lastMessage = messageMapper.selectOne(lastWrapper);
                if (lastMessage != null) {
                    lastMessageMap.put(convId, lastMessage.getContent());
                }
            }
        }

        // 6. 组装结果
        return conversations.stream()
                .map(conv -> ConversationInfoDTO.builder()
                        .id(conv.getId())
                        .knowledgeBaseId(conv.getKnowledgeBaseId())
                        .knowledgeBaseName(conv.getKnowledgeBaseId() != null ? kbNameMap.getOrDefault(conv.getKnowledgeBaseId(), "未知知识库") : null)
                        .userId(conv.getUserId())
                        .userName(conv.getUserId() != null ? userNameMap.getOrDefault(conv.getUserId(), "未知用户") : null)
                        .title(conv.getTitle())
                        .messageCount(messageCountMap.getOrDefault(conv.getId(), 0L).intValue())
                        .lastMessage(lastMessageMap.get(conv.getId()))
                        .createdAt(conv.getCreatedAt())
                        .updatedAt(conv.getUpdatedAt())
                        .build())
                .collect(Collectors.toList());
    }

    /**
     * Conversation 转换为 ConversationInfoDTO
     */
    private ConversationInfoDTO convertToInfoDTO(Conversation conversation) {
        // 获取知识库名称
        String kbName = null;
        if (conversation.getKnowledgeBaseId() != null) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(conversation.getKnowledgeBaseId());
            kbName = kb != null ? kb.getName() : "未知知识库";
        }

        // 获取创建人名称
        String userName = null;
        if (conversation.getUserId() != null) {
            User user = userMapper.selectById(conversation.getUserId());
            userName = user != null ? (user.getNickname() != null ? user.getNickname() : user.getUsername()) : "未知用户";
        }

        // 获取消息数量
        LambdaQueryWrapper<Message> countWrapper = new LambdaQueryWrapper<>();
        countWrapper.eq(Message::getConversationId, conversation.getId());
        Long messageCount = messageMapper.selectCount(countWrapper);

        // 获取最后一条消息
        LambdaQueryWrapper<Message> lastWrapper = new LambdaQueryWrapper<>();
        lastWrapper.eq(Message::getConversationId, conversation.getId())
                .orderByDesc(Message::getCreatedAt)
                .last("LIMIT 1");
        Message lastMessage = messageMapper.selectOne(lastWrapper);

        return ConversationInfoDTO.builder()
                .id(conversation.getId())
                .knowledgeBaseId(conversation.getKnowledgeBaseId())
                .knowledgeBaseName(kbName)
                .userId(conversation.getUserId())
                .userName(userName)
                .title(conversation.getTitle())
                .messageCount(messageCount.intValue())
                .lastMessage(lastMessage != null ? lastMessage.getContent() : null)
                .createdAt(conversation.getCreatedAt())
                .updatedAt(conversation.getUpdatedAt())
                .build();
    }

    /**
     * Message 转换为 MessageInfoDTO
     */
    private MessageInfoDTO convertToMessageInfoDTO(Message message) {
        return MessageInfoDTO.builder()
                .id(message.getId())
                .conversationId(message.getConversationId())
                .role(message.getRole())
                .content(message.getContent())
                .tokenCount(message.getTokenCount())
                .model(message.getModel())
                .sources(message.getSources())
                .createdAt(message.getCreatedAt())
                .build();
    }
}
