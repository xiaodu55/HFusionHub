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
import org.springframework.http.MediaType;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;
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

    private static final int REQUEST_ID_MAX_LENGTH = 64;
    private static final String ASSISTANT_REQUEST_SUFFIX = ":assistant";
    private final ConcurrentMap<String, StreamCancellation> activeStreamRequests = new ConcurrentHashMap<>();

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
    public MessageInfoDTO sendMessage(MessageSendDTO dto) {
        // 幂等检查：如果 requestId 已存在，直接返回已保存的响应
        String requestId = normalizeRequestId(dto.getRequestId());
        String assistantRequestId = assistantRequestId(requestId);
        Message existingAssistant = findAssistantByRequestId(assistantRequestId);
        if (existingAssistant != null) {
            return convertToMessageInfoDTO(existingAssistant);
        }

        // 阶段 1: 验证 + 保存用户消息（短事务）
        Message userMessage = saveUserMessage(dto, requestId);
        Conversation conversation = conversationMapper.selectById(dto.getConversationId());
        List<Map<String, String>> history = getChatHistory(conversation.getId());

        // 阶段 2: 事务外调用 AI（释放数据库连接）
        AiClient.ChatResponse aiResponse;
        try {
            aiResponse = aiClient.chat(
                    dto.getContent(), dto.getConversationId(),
                    conversation.getKnowledgeBaseId(), history);
        } catch (Exception e) {
            log.error("Failed to get AI response: {}", e.getMessage(), e);
            return saveAssistantMessage(dto.getConversationId(),
                    aiUnavailableMessage(e), "fallback", 0, List.of(),
                    conversation, dto.getContent(), assistantRequestId);
        }

        // 阶段 3: 保存助手消息 + 更新标题（短事务）
        return saveAssistantMessage(dto.getConversationId(),
                aiResponse.getContent(), aiResponse.getModel(), aiResponse.getTokenCount(),
                aiResponse.getSources(),
                conversation, dto.getContent(), assistantRequestId);
    }

    /**
     * 阶段 1: 短事务保存用户消息
     */
    @Transactional
    public Message saveUserMessage(MessageSendDTO dto) {
        return saveUserMessage(dto, normalizeRequestId(dto.getRequestId()));
    }

    @Transactional
    public Message saveUserMessage(MessageSendDTO dto, String requestId) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        Conversation conversation = conversationMapper.selectById(dto.getConversationId());
        if (conversation == null) throw new BusinessException("对话不存在");
        if (!conversation.getUserId().equals(currentUserId)) throw new BusinessException("无权发送消息");
        if (conversation.getKnowledgeBaseId() != null) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(conversation.getKnowledgeBaseId());
            if (kb == null || kb.getDeleted() == 1 || kb.getStatus() != 0)
                throw new BusinessException("关联的知识库已被删除或禁用");
            if (!kb.getUserId().equals(currentUserId))
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
    public MessageInfoDTO saveAssistantMessage(Long conversationId,
            String content, String model, int tokenCount,
            List<Map<String, Object>> sources,
            Conversation conversation, String userContent) {
        return saveAssistantMessage(conversationId, content, model, tokenCount, sources, conversation, userContent, null);
    }

    @Transactional
    public MessageInfoDTO saveAssistantMessage(Long conversationId,
            String content, String model, int tokenCount,
            List<Map<String, Object>> sources,
            Conversation conversation, String userContent, String requestId) {
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

    static String normalizeRequestId(String requestId) {
        if (!StringUtils.hasText(requestId)) {
            return null;
        }
        String trimmed = requestId.trim();
        if (trimmed.length() <= REQUEST_ID_MAX_LENGTH) {
            return trimmed;
        }
        return hashedRequestId("r:", trimmed);
    }

    static String assistantRequestId(String requestId) {
        if (!StringUtils.hasText(requestId)) {
            return null;
        }
        String candidate = requestId + ASSISTANT_REQUEST_SUFFIX;
        if (candidate.length() <= REQUEST_ID_MAX_LENGTH) {
            return candidate;
        }
        return hashedRequestId("a:", requestId);
    }

    private static String hashedRequestId(String prefix, String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder(bytes.length * 2);
            for (byte b : bytes) {
                String part = Integer.toHexString(b & 0xff);
                if (part.length() == 1) {
                    hex.append('0');
                }
                hex.append(part);
            }
            int hashLength = REQUEST_ID_MAX_LENGTH - prefix.length();
            return prefix + hex.substring(0, hashLength);
        } catch (Exception e) {
            throw new IllegalStateException("Unable to hash request id", e);
        }
    }

    private Message findUserByRequestId(String requestId) {
        return findMessageByRequestId("user", requestId);
    }

    private Message findAssistantByRequestId(String requestId) {
        return findMessageByRequestId("assistant", requestId);
    }

    private Message findMessageByRequestId(String role, String requestId) {
        if (!StringUtils.hasText(requestId)) {
            return null;
        }
        return messageMapper.selectOne(new LambdaQueryWrapper<Message>()
                .eq(Message::getRole, role)
                .eq(Message::getRequestId, requestId));
    }

    @Override
    public boolean cancelMessageStream(String rawRequestId, Long currentUserId) {
        String requestId = normalizeRequestId(rawRequestId);
        if (requestId == null) {
            return false;
        }

        StreamCancellation stream = activeStreamRequests.get(requestId);
        if (stream == null) {
            return false;
        }
        if (stream.userId != null && !stream.userId.equals(currentUserId)) {
            throw new BusinessException("无权取消该流式请求");
        }

        stream.cancelled.set(true);
        // Cancel the Python task first so it stops producing new tokens, then
        // close the Java socket to unblock a readLine waiting for the next SSE
        // event.  The worker's finally block persists the partial response.
        aiClient.cancelRequest(requestId);
        stream.closeConnection();
        try {
            stream.completed.get(3, TimeUnit.SECONDS);
        } catch (Exception e) {
            log.debug("等待流式请求 {} 完成取消超时: {}", requestId, e.getMessage());
        }
        return true;
    }

    private boolean saveStreamAssistantMessage(Long conversationId,
            String content,
            String model,
            List<Map<String, Object>> sources,
            String requestId) {
        Message existingAssistant = findAssistantByRequestId(requestId);
        if (existingAssistant != null) {
            return true;
        }

        Message assistantMessage = new Message();
        assistantMessage.setConversationId(conversationId);
        assistantMessage.setRole("assistant");
        assistantMessage.setContent(content != null ? content : "");
        assistantMessage.setModel(model);
        assistantMessage.setTokenCount(0);
        assistantMessage.setSources(sources);
        assistantMessage.setRequestId(requestId);
        try {
            messageMapper.insert(assistantMessage);
            return true;
        } catch (DuplicateKeyException e) {
            existingAssistant = findAssistantByRequestId(requestId);
            if (existingAssistant != null) {
                return true;
            }
            throw e;
        }
    }

    private void sendExistingAssistantAndComplete(SseEmitter emitter, Message message) {
        try {
            if (message.getSources() != null && !message.getSources().isEmpty()) {
                Map<String, Object> sourcesEvent = new HashMap<>();
                sourcesEvent.put("sources", message.getSources());
                emitter.send(SseEmitter.event().data(sourcesEvent, MediaType.APPLICATION_JSON));
            }
            if (StringUtils.hasText(message.getContent())) {
                Map<String, String> eventData = new HashMap<>();
                eventData.put("content", message.getContent());
                emitter.send(SseEmitter.event().data(eventData, MediaType.APPLICATION_JSON));
            }
            emitter.send(SseEmitter.event().data("[DONE]"));
            emitter.complete();
        } catch (Exception e) {
            emitter.completeWithError(e);
        }
    }

    private String aiUnavailableMessage(Exception error) {
        String message = error.getMessage();
        if (message != null && message.contains("PYTHON_AI_INTERNAL_TOKEN 未配置")) {
            return "AI 服务尚未配置：请在启动 Java 后端和 Python AI 服务的两个终端中设置相同的 PYTHON_AI_INTERNAL_TOKEN，然后重启两个服务。";
        }
        if (error instanceof org.springframework.web.client.ResourceAccessException
                || (message != null && message.contains("AI service is unavailable"))) {
            return "AI 服务暂时不可用：Python AI 服务未启动或无法连接。请确认 http://localhost:9000/health 可访问后重试。";
        }
        return "抱歉，AI 服务暂时不可用。请稍后重试；若问题持续，请检查 Java 后端日志中的 AI 服务调用错误。";
    }

    /**
     * Get last 20 messages for chat context (newest first, returns oldest→newest order)
     */
    private List<Map<String, String>> getChatHistory(Long conversationId) {
        LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Message::getConversationId, conversationId)
                .orderByDesc(Message::getCreatedAt)
                .last("LIMIT 20");

        List<Message> messages = messageMapper.selectList(wrapper);
        java.util.Collections.reverse(messages); // return in chronological order

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

        // 2.5. 重新验证关联知识库
        if (conversation.getKnowledgeBaseId() != null) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(conversation.getKnowledgeBaseId());
            if (kb == null || kb.getDeleted() == 1 || kb.getStatus() != 0) {
                emitter.completeWithError(new BusinessException("关联的知识库已被删除或禁用"));
                return;
            }
            if (!kb.getUserId().equals(currentUserId)) {
                emitter.completeWithError(new BusinessException("无权访问关联的知识库"));
                return;
            }
        }

        // 3. Idempotency check. User and assistant messages must not share the same unique request_id.
        final String requestId;
        String rawRequestId = normalizeRequestId(dto.getRequestId());
        if (rawRequestId == null) {
            requestId = java.util.UUID.randomUUID().toString();
        } else {
            requestId = rawRequestId;
        }
        final String assistantRequestId = assistantRequestId(requestId);
        Message existingAssistant = findAssistantByRequestId(assistantRequestId);
        if (existingAssistant != null) {
            sendExistingAssistantAndComplete(emitter, existingAssistant);
            return;
        }
        StreamCancellation streamCancellation = new StreamCancellation(cancelled, currentUserId);
        activeStreamRequests.put(requestId, streamCancellation);

        // 4. 保存用户消息
        Message userMessage = findUserByRequestId(requestId);
        if (userMessage == null) {
            userMessage = new Message();
            userMessage.setConversationId(dto.getConversationId());
            userMessage.setRole("user");
            userMessage.setContent(dto.getContent());
            userMessage.setRequestId(requestId);
            try {
                messageMapper.insert(userMessage);
            } catch (DuplicateKeyException e) {
                userMessage = findUserByRequestId(requestId);
                if (userMessage == null) {
                    throw e;
                }
            }
        }

        // 5. 获取对话历史
        List<Map<String, String>> history = getChatHistory(conversation.getId());

        // 6. 使用 WebClient Flux 实现真正的流式响应
        StringBuilder responseBuilder = new StringBuilder();
        java.util.List<Map<String, Object>> accumulatedSources = new java.util.ArrayList<>();
        boolean[] assistantSaved = {false};
        final com.fasterxml.jackson.databind.ObjectMapper objectMapper = new com.fasterxml.jackson.databind.ObjectMapper();

        reactor.core.publisher.Flux<String> sseFlux = aiClient.streamChat(
                dto.getContent(), dto.getConversationId(),
                conversation.getKnowledgeBaseId(), history, requestId)
                .doFinally(signalType -> {
                    // Cleanup: remove from active requests and signal completion
                    activeStreamRequests.remove(requestId, streamCancellation);
                    streamCancellation.completed.complete(null);
                });

        reactor.core.Disposable subscription = sseFlux.subscribe(
                chunk -> {
                    if (cancelled.get()) return;

                    // Python streaming emits one JSON event per chunk.
                    // Each chunk is either a JSON object or [DONE] sentinel.
                    String data = chunk.strip();
                    if (data.isEmpty()) return;

                        if ("[DONE]".equals(data)) {
                        log.info("Stream completed, requestId: {}", requestId);
                        try {
                            emitter.send(SseEmitter.event().data("[DONE]"));
                            emitter.complete();
                        } catch (Exception ignored) {}
                        assistantSaved[0] = saveStreamAssistantMessage(
                                dto.getConversationId(), responseBuilder.toString(),
                                "streaming", accumulatedSources, assistantRequestId);
                        return;
                    }

                    try {
                        com.fasterxml.jackson.databind.JsonNode jsonNode = objectMapper.readTree(data);
                        String content = jsonNode.has("content") ? jsonNode.get("content").asText() : "";
                        boolean isCancelled = jsonNode.has("cancelled") && jsonNode.get("cancelled").asBoolean();
                        com.fasterxml.jackson.databind.JsonNode sourcesNode = jsonNode.get("sources");

                        if (isCancelled) {
                            log.info("Python AI request cancelled: {}", requestId);
                            try { emitter.send(SseEmitter.event().data("[DONE]")); emitter.complete(); } catch (Exception ignored) {}
                            return;
                        }

                        if (sourcesNode != null && sourcesNode.isArray() && sourcesNode.size() > 0) {
                            List<Map<String, Object>> newSources = objectMapper.treeToValue(sourcesNode, List.class);
                            accumulatedSources.addAll(newSources);
                            Map<String, Object> sourcesEvent = new HashMap<>();
                            sourcesEvent.put("sources", newSources);
                            emitter.send(SseEmitter.event().data(sourcesEvent, MediaType.APPLICATION_JSON));
                        }

                        if (!content.isEmpty()) {
                            responseBuilder.append(content);
                            Map<String, String> eventData = new HashMap<>();
                            eventData.put("content", content);
                            emitter.send(SseEmitter.event().data(eventData, MediaType.APPLICATION_JSON));
                        }
                    } catch (Exception e) {
                        log.warn("Failed to parse SSE chunk: {}", data, e);
                    }
                },
                error -> {
                    // onError
                    if (cancelled.get()) {
                        log.info("Stream cancelled by client, requestId: {}", requestId);
                        try {
                            if (!assistantSaved[0] && responseBuilder.length() > 0) {
                                assistantSaved[0] = saveStreamAssistantMessage(
                                        dto.getConversationId(),
                                        responseBuilder.toString(),
                                        "streaming",
                                        accumulatedSources,
                                        assistantRequestId);
                            }
                            emitter.send(SseEmitter.event().data("[DONE]"));
                            emitter.complete();
                        } catch (Exception completeError) {
                            log.debug("Failed to complete emitter after cancel: {}", completeError.getMessage());
                        }
                        return;
                    }
                    log.error("Streaming error: {}", error.getMessage(), error);
                    try {
                        String errorMessage = aiUnavailableMessage(error instanceof Exception ? (Exception) error : new RuntimeException(error));
                        emitter.send(SseEmitter.event().data(Map.of("content", errorMessage)));
                        emitter.send(SseEmitter.event().data("[DONE]"));
                        emitter.complete();
                        saveStreamAssistantMessage(dto.getConversationId(), errorMessage, "error", List.of(), assistantRequestId);
                    } catch (Exception ex) {
                        emitter.completeWithError(ex);
                    }
                },
                () -> {
                    // onComplete: ensure emitter is closed and assistant saved
                    if (responseBuilder.length() > 0) {
                        try {
                            emitter.send(SseEmitter.event().data("[DONE]"));
                            emitter.complete();
                        } catch (Exception alreadyComplete) {
                            // emitter already closed or IO error
                        }
                        if (!assistantSaved[0]) {
                            assistantSaved[0] = saveStreamAssistantMessage(
                                    dto.getConversationId(),
                                    responseBuilder.toString(),
                                    "streaming",
                                    accumulatedSources,
                                    assistantRequestId);
                        }
                    } else {
                        try {
                            emitter.send(SseEmitter.event().data("[DONE]"));
                            emitter.complete();
                        } catch (Exception alreadyComplete) {
                            // ignore
                        }
                    }
                }
        );

        // Track the subscription for cancellation
        streamCancellation.setSubscription(subscription);
    }

    private static final class StreamCancellation {
        private final AtomicBoolean cancelled;
        private final Long userId;
        private final CompletableFuture<Void> completed = new CompletableFuture<>();
        private volatile reactor.core.Disposable subscription;

        private StreamCancellation(AtomicBoolean cancelled, Long userId) {
            this.cancelled = cancelled;
            this.userId = userId;
        }

        private void setSubscription(reactor.core.Disposable subscription) {
            this.subscription = subscription;
        }

        private void closeConnection() {
            reactor.core.Disposable current = subscription;
            if (current != null && !current.isDisposed()) {
                current.dispose();
            }
        }
    }

    /**
     * 批量转换 Conversation → DTO。通过一次 SQL 聚合获取消息数量和最新消息。
     */
    private List<ConversationInfoDTO> batchConvertToInfoDTO(List<Conversation> conversations) {
        if (conversations.isEmpty()) {
            return List.of();
        }

        List<Long> conversationIds = conversations.stream().map(Conversation::getId).collect(Collectors.toList());
        List<Long> kbIds = conversations.stream().map(Conversation::getKnowledgeBaseId).filter(id -> id != null).distinct().collect(Collectors.toList());
        List<Long> userIds = conversations.stream().map(Conversation::getUserId).filter(id -> id != null).distinct().collect(Collectors.toList());

        // 批量查询知识库名称
        Map<Long, String> kbNameMap = new HashMap<>();
        if (!kbIds.isEmpty()) {
            knowledgeBaseMapper.selectBatchIds(kbIds).forEach(kb -> kbNameMap.put(kb.getId(), kb.getName()));
        }

        // 批量查询用户名
        Map<Long, String> userNameMap = new HashMap<>();
        if (!userIds.isEmpty()) {
            userMapper.selectBatchIds(userIds).forEach(u -> userNameMap.put(u.getId(),
                    u.getNickname() != null ? u.getNickname() : u.getUsername()));
        }

        // 一次 SQL 聚合：消息数量 + 最新消息
        Map<Long, Long> messageCountMap = new HashMap<>();
        Map<Long, String> lastMessageMap = new HashMap<>();
        List<Map<String, Object>> aggregates = messageMapper.aggregateByConversationIds(conversationIds);
        for (Map<String, Object> row : aggregates) {
            Long convId = toLong(row.get("conversationId"));
            if (convId == null) continue;
            messageCountMap.put(convId, toLong(row.get("msgCount")));
            lastMessageMap.put(convId, (String) row.get("lastMessage"));
        }

        return conversations.stream()
                .map(conv -> ConversationInfoDTO.builder()
                        .id(conv.getId())
                        .knowledgeBaseId(conv.getKnowledgeBaseId())
                        .knowledgeBaseName(conv.getKnowledgeBaseId() != null ? kbNameMap.getOrDefault(conv.getKnowledgeBaseId(), "未知知识库") : null)
                        .userId(conv.getUserId())
                        .userName(userNameMap.getOrDefault(conv.getUserId(), "未知用户"))
                        .title(conv.getTitle())
                        .messageCount(messageCountMap.getOrDefault(conv.getId(), 0L).intValue())
                        .lastMessage(lastMessageMap.get(conv.getId()))
                        .createdAt(conv.getCreatedAt())
                        .updatedAt(conv.getUpdatedAt())
                        .build())
                .collect(Collectors.toList());
    }

    private static Long toLong(Object value) {
        if (value instanceof Number n) return n.longValue();
        if (value instanceof String s) try { return Long.valueOf(s); } catch (NumberFormatException ignored) {}
        return null;
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
