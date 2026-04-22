package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.ConversationCreateDTO;
import com.hfusionhub.dto.ConversationInfoDTO;
import com.hfusionhub.dto.ConversationQueryDTO;
import com.hfusionhub.dto.AgentTaskDetailDTO;
import com.hfusionhub.dto.MessageInfoDTO;
import com.hfusionhub.dto.MessageSendDTO;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.entity.Conversation;
import com.hfusionhub.entity.PromptTemplate;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.Message;
import com.hfusionhub.entity.User;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.mapper.ConversationMapper;
import com.hfusionhub.mapper.PromptTemplateMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.service.ConversationService;
import com.hfusionhub.service.AgentTaskService;
import com.hfusionhub.service.MemoryService;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.config.QuotaProperties;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.tenant.TenantContext;
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
    private final PromptTemplateMapper promptTemplateMapper;
    private final MessageMapper messageMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final UserMapper userMapper;
    private final AiClient aiClient;
    private final AgentTaskService agentTaskService;
    private final MemoryService memoryService;
    private final UsageLedgerService usageLedgerService;
    private final QuotaProperties quotaProperties;
    private final com.hfusionhub.service.AgentStreamEventProcessor streamEventProcessor;
    private final com.hfusionhub.service.RagIntentNodeService ragIntentNodeService;
    private final com.hfusionhub.service.KbShareService kbShareService;

    private static final int REQUEST_ID_MAX_LENGTH = 64;
    public static final String ASSISTANT_REQUEST_SUFFIX = ":assistant";
    private final ConcurrentMap<String, StreamCancellation> activeStreamRequests = new ConcurrentHashMap<>();

    /**
     * C2: 知识库可读校验 — 所有者或已被共享（只读协作）。
     */
    private void assertCanReadKnowledgeBase(KnowledgeBase kb, Long userId) {
        if (kb == null) {
            throw new BusinessException("知识库不存在");
        }
        boolean owned = kb.getUserId().equals(userId);
        boolean shared = !owned && kbShareService.canRead(userId, kb.getId());
        if (!owned && !shared) {
            throw new BusinessException("无权访问该知识库");
        }
    }

    @Override
    @Transactional
    public ConversationInfoDTO create(ConversationCreateDTO dto) {
        // 1. 获取当前用户
        Long currentUserId = JwtUtils.getCurrentUserId();

        // 2. 如果指定了知识库，验证知识库存在且可读（所有者或已被共享）
        if (dto.getKnowledgeBaseId() != null) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(dto.getKnowledgeBaseId());
            assertCanReadKnowledgeBase(kb, currentUserId);
        }

        // 3. 创建对话
        if (dto.getPromptTemplateId() != null) {
            PromptTemplate template = promptTemplateMapper.selectById(dto.getPromptTemplateId());
            if (template == null || !currentUserId.equals(template.getUserId())
                    || !PromptTemplate.STATUS_PUBLISHED.equals(template.getStatus())) {
                throw new BusinessException("请选择属于你的已发布提示词模板");
            }
        }

        Conversation conversation = new Conversation();
        conversation.setKnowledgeBaseId(dto.getKnowledgeBaseId());
        conversation.setPromptTemplateId(dto.getPromptTemplateId());
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
    public void rename(Long id, String title) {
        Conversation conversation = conversationMapper.selectById(id);
        if (conversation == null) {
            throw new BusinessException("对话不存在");
        }
        if (!conversation.getUserId().equals(JwtUtils.getCurrentUserId())) {
            throw new BusinessException("无权修改该对话");
        }
        String normalized = title == null ? "" : title.trim();
        if (normalized.isBlank()) {
            throw new BusinessException("对话名称不能为空");
        }
        if (normalized.length() > 100) {
            throw new BusinessException("对话名称不能超过 100 个字符");
        }
        conversation.setTitle(normalized);
        conversationMapper.updateById(conversation);
    }

    @Override
    public void clearMessages(Long id) {
        Conversation conversation = conversationMapper.selectById(id);
        if (conversation == null) {
            throw new BusinessException("对话不存在");
        }
        if (!conversation.getUserId().equals(JwtUtils.getCurrentUserId())) {
            throw new BusinessException("无权清空该对话");
        }
        LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Message::getConversationId, id);
        messageMapper.delete(wrapper);
    }

    @Override
    public void deleteMessage(Long conversationId, Long messageId) {
        Conversation conversation = conversationMapper.selectById(conversationId);
        if (conversation == null) {
            throw new BusinessException("对话不存在");
        }
        if (!conversation.getUserId().equals(JwtUtils.getCurrentUserId())) {
            throw new BusinessException("无权操作该对话");
        }
        Message message = messageMapper.selectById(messageId);
        if (message == null || !conversationId.equals(message.getConversationId())) {
            throw new BusinessException("消息不存在");
        }
        messageMapper.deleteById(messageId);
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
        Long currentUserId = JwtUtils.getCurrentUserId();
        List<Map<String, String>> history = getChatHistory(conversation.getId());
        history = withConversationInstructions(history, conversation, currentUserId, dto.getContent());

        // 阶段 2: 事务外调用 AI（释放数据库连接）
        // Agent V1: 有知识库 → /api/agent/v1/chat; 无知识库 → /api/chat
        // Agent V1 Step 3: userId MUST come from the authenticated Java session;
        // it is NEVER taken from the frontend DTO.  The model cannot forge it.
        // Agent V1 Step 5: server-side capability gate — the DTO may carry
        // capabilityProfile="approval_write", but the server validates it against
        // business rules before passing it to Python.  Regular chat is always null.
        String effectiveCapability = resolveCapabilityProfile(
                dto.getCapabilityProfile(), conversation, currentUserId);
        List<Map<String, Object>> intentContext = ragIntentNodeService.routeCandidates();
        // 用量账本：预占上界 = 输入估算 + 服务端最大输出（幂等键为 chat:<requestId>）
        final String usageKey = "chat:" + requestId;
        final long inputEstimate = estimateChatTokens(dto.getContent());
        final long reserveTokens = inputEstimate + quotaProperties.getChatMaxOutputTokens();
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, usageKey, reserveTokens, "message", requestId);
        AiClient.ChatResponse aiResponse;
        try {
            if (conversation.getKnowledgeBaseId() != null && conversation.getKnowledgeBaseId() > 0) {
                // V1 context guard: if Java cannot resolve the authenticated user,
                // fail loudly — do NOT silently route to a non-V1 path or save a
                // fallback answer that would mask the security gap.
                if (currentUserId == null || currentUserId <= 0) {
                    throw new BusinessException(
                            "Agent V1 配置错误：知识库会话需要已认证的用户上下文，但当前会话无法解析用户 ID。"
                            + "请确认 JWT 令牌有效且包含 subject 声明。");
                }
                aiResponse = aiClient.agentV1Chat(
                        dto.getContent(), dto.getConversationId(),
                        conversation.getKnowledgeBaseId(), history,
                        "detailed", 5, requestId, currentUserId,
                        effectiveCapability,
                        JwtUtils.hasRole(CommonConstants.ROLE_ADMIN) ? "admin" : "user",
                        intentContext);
            } else {
                aiResponse = aiClient.chat(
                        dto.getContent(), dto.getConversationId(),
                        conversation.getKnowledgeBaseId(), history, currentUserId, intentContext);
            }
        } catch (BusinessException e) {
            // Re-throw BusinessExceptions directly — they represent explicit
            // configuration or permission errors that MUST NOT be silently
            // converted to a fallback answer.
            usageLedgerService.release(UsageMeter.CHAT_TOKENS, usageKey);
            throw e;
        } catch (Exception e) {
            log.error("Failed to get AI response: {}", e.getMessage(), e);
            usageLedgerService.release(UsageMeter.CHAT_TOKENS, usageKey);
            return saveAssistantMessage(dto.getConversationId(),
                    aiUnavailableMessage(e), "fallback", 0, List.of(),
                    conversation, dto.getContent(), assistantRequestId);
        }

        // 阶段 3: 保存助手消息 + 更新标题（短事务）
        // 用量账本：按实际 token 结算，封顶在预占上界内（Python 未返回时按预占上界结算）
        long realTokens = aiResponse.getTokenCount() > 0
                ? aiResponse.getTokenCount() : reserveTokens;
        long chargeTokens = Math.min(reserveTokens, realTokens);
        usageLedgerService.settle(UsageMeter.CHAT_TOKENS, usageKey, chargeTokens, "message", requestId);
        return saveAssistantMessageV1(dto.getConversationId(), aiResponse,
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

    /**
     * Save assistant message from a full AiClient.ChatResponse, preserving
     * Agent V1 metadata (status, agent_run_id, tool_calls_count,
     * token_usage) alongside the core answer + sources.
     */
    @Transactional
    public MessageInfoDTO saveAssistantMessageV1(Long conversationId,
            AiClient.ChatResponse aiResponse,
            Conversation conversation, String userContent, String requestId) {
        Message existingAssistant = findAssistantByRequestId(requestId);
        if (existingAssistant != null) {
            return convertToMessageInfoDTO(existingAssistant);
        }
        // Primary content: prefer answer if content is null (V1 path sends both).
        String primaryContent = aiResponse.getContent() != null
                ? aiResponse.getContent()
                : aiResponse.getAnswer();

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

    /**
     * 聊天 token 预占估算：按内容长度粗估，至少 64 token。
     */
    private long estimateChatTokens(String content) {
        int length = content == null ? 0 : content.length();
        return Math.max(64, length / 4);
    }

    /**
     * 结算/退回流式聊天的用量，AtomicBoolean 保证只执行一次。
     * 在 Reactor 线程调用，需以预捕获的租户 ID 恢复 TenantContext。
     * 结算量 = min(预占上界, 输入估算 + 实际输出/4)，封顶在预留内。
     * 内部吞异常，避免账本失败影响 SSE 主流程。
     */
    private void finalizeChatUsage(Long tenantId, String usageKey, long reserveTokens,
                                   long inputEstimate, AtomicBoolean usageFinalized,
                                   boolean success, int outputChars) {
        if (usageFinalized.compareAndSet(false, true)) {
            TenantContext.runAs(tenantId, () -> {
                try {
                    if (success) {
                        long charge = Math.min(reserveTokens,
                                inputEstimate + Math.max(0, outputChars) / 4);
                        usageLedgerService.settle(
                                UsageMeter.CHAT_TOKENS, usageKey, charge, "message", usageKey);
                    } else {
                        usageLedgerService.release(UsageMeter.CHAT_TOKENS, usageKey);
                    }
                } catch (Exception e) {
                    log.warn("Failed to finalize chat usage for {}: {}", usageKey, e.getMessage());
                }
                return null;
            });
        }
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

        // Agent V1 Step 4: mark agent run as cancelled
        if (stream.getAgentRunId() != null) {
            try {
                agentTaskService.cancelRun(stream.getAgentRunId());
            } catch (Exception e) {
                log.warn("Failed to mark agent run {} as cancelled: {}",
                        stream.getAgentRunId(), e.getMessage());
            }
        }

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
    @Override
    public List<Map<String, String>> getChatHistory(Long conversationId) {
        LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Message::getConversationId, conversationId)
                .orderByDesc(Message::getCreatedAt)
                .last("LIMIT 20");

        List<Message> messages = messageMapper.selectList(wrapper);
        java.util.Collections.reverse(messages); // return in chronological order

        return messages.stream()
                .filter(ConversationServiceImpl::shouldIncludeInChatHistory)
                .map(m -> {
                    Map<String, String> map = new HashMap<>();
                    map.put("role", m.getRole());
                    map.put("content", m.getContent());
                    return map;
                })
                .collect(Collectors.toList());
    }

    static boolean shouldIncludeInChatHistory(Message message) {
        if (message == null || message.getContent() == null || message.getContent().isBlank()) {
            return false;
        }
        // Replies produced by the old development fallback can contain the
        // fully assembled prompt. Keep them visible for audit, but never send
        // them back to a real model as conversation context.
        return !("assistant".equals(message.getRole())
                && "mock-model".equals(message.getModel()));
    }

    @Override
    public List<Map<String, String>> getChatHistoryWithInstructions(
            Long conversationId, Long userId, String query) {
        Conversation conversation = conversationMapper.selectById(conversationId);
        if (conversation == null) {
            throw new BusinessException("对话不存在");
        }
        if (!conversation.getUserId().equals(userId)) {
            throw new BusinessException("无权访问该对话");
        }
        return withConversationInstructions(getChatHistory(conversationId), conversation, userId, query);
    }

    /**
     * Add only active, user-owned memories to the model context.  The marker
     * makes their provenance explicit and keeps memory separate from chat
     * history; the Python service still treats the knowledge-base scope as
     * authoritative for document retrieval.
     */
    private List<Map<String, String>> withRelevantMemories(
            List<Map<String, String>> history,
            Long userId,
            Long knowledgeBaseId,
            String query) {
        if (userId == null) return history;
        var memories = memoryService.getRelevantMemories(userId, knowledgeBaseId, query, 5);
        if (memories.isEmpty()) return history;
        StringBuilder context = new StringBuilder("User-provided long-term memory (use only when relevant):\n");
        for (var memory : memories) {
            context.append("- ").append(memory.getType()).append(": ")
                    .append(memory.getContent()).append("\n");
        }
        List<Map<String, String>> enriched = new java.util.ArrayList<>();
        enriched.add(Map.of("role", "system", "content", context.toString()));
        enriched.addAll(history);
        return enriched;
    }

    /** Resolve the selected template at request time and add it as a controlled system instruction. */
    private List<Map<String, String>> withConversationInstructions(
            List<Map<String, String>> history,
            Conversation conversation,
            Long userId,
            String query) {
        List<Map<String, String>> enriched = withRelevantMemories(
                history, userId, conversation.getKnowledgeBaseId(), query);
        if (conversation.getPromptTemplateId() == null || userId == null) return enriched;

        PromptTemplate template = promptTemplateMapper.selectById(conversation.getPromptTemplateId());
        if (template == null || !userId.equals(template.getUserId())
                || !PromptTemplate.STATUS_PUBLISHED.equals(template.getStatus())) {
            return enriched;
        }

        List<Map<String, String>> withTemplate = new java.util.ArrayList<>();
        withTemplate.add(Map.of(
                "role", "system",
                "content", "Conversation instruction (follow this unless it conflicts with system safety rules):\n"
                        + template.getContent()));
        withTemplate.addAll(enriched);
        return withTemplate;
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

    // ================================================================
    // V13: 队列模式入口
    // ================================================================

    @Override
    @Transactional
    public Long enqueueMessage(MessageSendDTO dto, Long currentUserId) {
        // 1. 查询对话
        Conversation conversation = conversationMapper.selectById(dto.getConversationId());
        if (conversation == null) {
            throw new BusinessException("对话不存在");
        }

        // 2. 验证权限
        if (!conversation.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权发送消息");
        }

        // 3. 验证关联知识库
        if (conversation.getKnowledgeBaseId() != null) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(conversation.getKnowledgeBaseId());
            if (kb == null || kb.getDeleted() == 1 || kb.getStatus() != 0) {
                throw new BusinessException("关联的知识库已被删除或禁用");
            }
            if (!kb.getUserId().equals(currentUserId) && !kbShareService.canRead(currentUserId, kb.getId())) {
                throw new BusinessException("无权访问关联的知识库");
            }
        }

        // 4. Idempotency check
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
            log.info("Idempotent: assistant message already exists for requestId={}, returning taskId from message",
                    requestId);
            // Return a synthetic taskId — the frontend should fetch existing message directly
            throw new BusinessException("该消息已处理完成，请刷新对话查看回复");
        }

        // 5. 保存用户消息
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

        // 6. 创建 AgentTask（PENDING）
        AgentTask agentTask = agentTaskService.createTask(
                requestId, currentUserId, conversation.getId(),
                conversation.getKnowledgeBaseId(), dto.getContent());

        // 7. 入队 PENDING Run
        agentTaskService.enqueueRun(agentTask.getId());

        log.info("Message enqueued: taskId={} conversationId={} userId={} isKbBound={}",
                agentTask.getId(), conversation.getId(), currentUserId,
                conversation.getKnowledgeBaseId() != null && conversation.getKnowledgeBaseId() > 0);

        return agentTask.getId();
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
            if (!kb.getUserId().equals(currentUserId) && !kbShareService.canRead(currentUserId, kb.getId())) {
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

        // 3.5. Agent V1 Step 5: resolve capability profile with server-side gate.
        // The DTO may request "approval_write", but the server validates it against
        // business rules.  Regular chat is always forced to null.
        String streamingCapability = resolveCapabilityProfile(
                dto.getCapabilityProfile(), conversation, currentUserId);

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
        history = withConversationInstructions(history, conversation, currentUserId, dto.getContent());
        List<Map<String, Object>> intentContext = ragIntentNodeService.routeCandidates();

        // 5.5. Agent V1 Step 4: 创建持久化 agent_task 和 agent_run
        final AgentTask agentTask = agentTaskService.createTask(
                requestId, currentUserId, conversation.getId(),
                conversation.getKnowledgeBaseId(), dto.getContent());
        final String runUuid = java.util.UUID.randomUUID().toString();
        final AgentRun agentRun = agentTaskService.startRun(
                agentTask.getId(), runUuid, null, "detailed", 5);
        streamCancellation.setAgentRunId(agentRun.getId());
        streamCancellation.setAgentTaskId(agentTask.getId());
        log.info("Agent task tracking: taskId={} runId={} runUuid={}",
                agentTask.getId(), agentRun.getId(), runUuid);

        // 6. 使用 WebClient Flux 实现真正的流式响应
        StringBuilder responseBuilder = new StringBuilder();
        java.util.List<Map<String, Object>> accumulatedSources = new java.util.ArrayList<>();
        boolean[] assistantSaved = {false};
        final com.fasterxml.jackson.databind.ObjectMapper objectMapper = new com.fasterxml.jackson.databind.ObjectMapper();

        // Agent V1 Step 3: KB-bound streaming MUST go through the V1 endpoint
        // so that the execution context (user_id, permissions, mode) is created
        // and the permission boundary is enforced on every tool call.
        final boolean isKbBound = conversation.getKnowledgeBaseId() != null
                && conversation.getKnowledgeBaseId() > 0;
        if (isKbBound && (currentUserId == null || currentUserId <= 0)) {
            emitter.completeWithError(new BusinessException(
                    "Agent V1 配置错误：知识库会话需要已认证的用户上下文，但当前会话无法解析用户 ID。"
                    + "请确认 JWT 令牌有效且包含 subject 声明。"));
            return;
        }

        // 用量账本：预占上界 = 输入估算 + 服务端最大输出（幂等键为 chat:<requestId>）。
        // 流式回调和 doFinally 在 Reactor 线程执行，先捕获租户 ID，结算/退回用
        // TenantContext.runAs 恢复上下文。
        final Long streamTenantId = TenantContext.requireTenantId();
        final String usageKey = "chat:" + requestId;
        final long streamInputEstimate = estimateChatTokens(dto.getContent());
        final long streamReserveTokens = streamInputEstimate + quotaProperties.getChatMaxOutputTokens();
        final AtomicBoolean usageFinalized = new AtomicBoolean(false);
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, usageKey, streamReserveTokens, "message", requestId);

        reactor.core.publisher.Flux<String> sseFlux;
        if (isKbBound) {
            sseFlux = aiClient.agentV1ChatStream(
                    dto.getContent(), dto.getConversationId(),
                    conversation.getKnowledgeBaseId(), history, requestId, currentUserId,
                    streamingCapability, intentContext);
        } else {
            sseFlux = aiClient.streamChat(
                    dto.getContent(), dto.getConversationId(),
                    conversation.getKnowledgeBaseId(), history, requestId,
                    currentUserId, intentContext);
        }

        sseFlux = sseFlux.doFinally(signalType -> {
                    // Reactor 线程无租户上下文，先恢复再结算/退回
                    TenantContext.runAs(streamTenantId, () -> {
                        // Usage safety net: if no subscriber path finalized the
                        // reservation (edge case), settle on completion else release.
                        if (usageFinalized.compareAndSet(false, true)) {
                            if (signalType == reactor.core.publisher.SignalType.ON_COMPLETE) {
                                long charge = Math.min(streamReserveTokens,
                                        streamInputEstimate + responseBuilder.length() / 4);
                                usageLedgerService.settle(
                                        UsageMeter.CHAT_TOKENS, usageKey, charge, "message", usageKey);
                            } else {
                                usageLedgerService.release(UsageMeter.CHAT_TOKENS, usageKey);
                            }
                        }
                        // Cleanup: remove from active requests and signal completion
                        activeStreamRequests.remove(requestId, streamCancellation);
                        streamCancellation.completed.complete(null);
                        return null;
                    });
                });

        reactor.core.Disposable subscription = sseFlux.subscribe(
                chunk -> TenantContext.runAs(streamTenantId, () -> {
                    if (cancelled.get()) return;

                    // Python streaming emits SSE formatted lines:
                    //   data: {json}\n\n
                    //   data: [DONE]\n\n
                    //
                    // WebFlux StringDecoder splits by \n, so each Flux element
                    // is one line (prefix + payload, or empty separator).
                    // Strip the "data: " / "data:" prefix before JSON parsing.

                    // ── Step 1: normalise the raw payload ──────────────────
                    String data = com.hfusionhub.service.AgentStreamEventProcessor.stripSsePrefix(chunk);
                    if (data == null) return;   // empty / separator line

                    // ── Step 2: [DONE] sentinel ───────────────────────────
                    if ("[DONE]".equals(data)) {
                        log.info("Stream completed, requestId: {}", requestId);
                        try {
                            emitter.send(SseEmitter.event().data("[DONE]"));
                            emitter.complete();
                        } catch (Exception ignored) {}
                        if (responseBuilder.length() > 0) {
                                assistantSaved[0] = saveStreamAssistantMessage(
                                        dto.getConversationId(), responseBuilder.toString(),
                                        "streaming", accumulatedSources, assistantRequestId);
                            }
                        finalizeChatUsage(streamTenantId, usageKey, streamReserveTokens,
                                streamInputEstimate, usageFinalized, true, responseBuilder.length());
                        return;
                    }

                    // ── Step 3: parse JSON payload ────────────────────────
                    try {
                        com.fasterxml.jackson.databind.JsonNode jsonNode = objectMapper.readTree(data);

                        // ── Agent V1 Step 4: intercept structured events for persistence ──
                        if (jsonNode.has("event")) {
                            streamEventProcessor.handleLine(chunk, agentRun.getId());
                            // Forward structured events to frontend (for progress UI)
                            try {
                                Map<String, Object> eventMap = objectMapper.treeToValue(jsonNode, Map.class);
                                emitter.send(SseEmitter.event().data(eventMap, MediaType.APPLICATION_JSON));
                            } catch (Exception ignored) {}
                            return;
                        }

                        String content = jsonNode.has("content") ? jsonNode.get("content").asText() : "";
                        boolean isCancelled = jsonNode.has("cancelled") && jsonNode.get("cancelled").asBoolean();
                        com.fasterxml.jackson.databind.JsonNode sourcesNode = jsonNode.get("sources");

                        if (isCancelled) {
                            log.info("Python AI request cancelled: {}", requestId);
                            agentTaskService.cancelRun(agentRun.getId());
                            finalizeChatUsage(streamTenantId, usageKey, streamReserveTokens,
                                    streamInputEstimate, usageFinalized, false, 0);
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
                }),
                error -> TenantContext.runAs(streamTenantId, () -> {
                    // onError
                    finalizeChatUsage(streamTenantId, usageKey, streamReserveTokens,
                            streamInputEstimate, usageFinalized, false, 0);
                    if (cancelled.get()) {
                        log.info("Stream cancelled by client, requestId: {}", requestId);
                        agentTaskService.cancelRun(agentRun.getId());
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
                    agentTaskService.failRun(agentRun.getId(),
                            "internal_error",
                            error.getMessage() != null ? error.getMessage() : "Unknown streaming error",
                            null);
                    try {
                        String errorMessage = aiUnavailableMessage(error instanceof Exception ? (Exception) error : new RuntimeException(error));
                        emitter.send(SseEmitter.event().data(Map.of("content", errorMessage)));
                        emitter.send(SseEmitter.event().data("[DONE]"));
                        emitter.complete();
                        saveStreamAssistantMessage(dto.getConversationId(), errorMessage, "error", List.of(), assistantRequestId);
                    } catch (Exception ex) {
                        emitter.completeWithError(ex);
                    }
                }),
                () -> TenantContext.runAs(streamTenantId, () -> {
                    // onComplete: ensure emitter is closed and assistant saved.
                    finalizeChatUsage(streamTenantId, usageKey, streamReserveTokens,
                            streamInputEstimate, usageFinalized,
                            responseBuilder.length() > 0, responseBuilder.length());
                    // Agent V1 Step 5 safety net: if the run is still in 'running'
                    // state (no run_completed / run_error / approval_required was
                    // received), converge it to failed so nothing stays running forever.
                    try {
                        AgentRun finalRunState = agentTaskService.getRunById(agentRun.getId());
                        if (finalRunState != null
                                && "running".equals(finalRunState.getStatus())) {
                            log.warn("Agent run {} completed SSE stream but is still 'running' — "
                                    + "forcing failed convergence", agentRun.getId());
                            agentTaskService.failRun(agentRun.getId(),
                                    "internal_error",
                                    "Stream completed without terminal event; forced failed convergence",
                                    null);
                        }
                    } catch (Exception convergenceError) {
                        log.warn("Failed to check/converge agent run state on complete: {}",
                                convergenceError.getMessage());
                    }
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
                })
        );

        // Track the subscription for cancellation
        streamCancellation.setSubscription(subscription);
    }

    // ── Agent V1 Step 5: capability profile resolution ──────────────────────

    /**
     * Resolve the effective capability profile with server-side validation.
     *
     * Rules:
     *   - {@code "approval_write"} is only allowed for KB-bound conversations
     *     where the authenticated user owns the KB.  Otherwise it is rejected.
     *   - {@code null} / empty / unrecognised values → forced to {@code null}
     *     (regular read-only V1.0 chat).
     *   - The frontend MUST NOT directly control this; it merely sends a
     *     request hint.  The server always decides the effective value.
     *
     * @param requested   value from {@link MessageSendDTO#getCapabilityProfile()}
     * @param conversation the current conversation
     * @param currentUserId authenticated user ID from JWT
     * @return {@code "approval_write"} if allowed, otherwise {@code null}
     */
    private String resolveCapabilityProfile(
            String requested,
            Conversation conversation,
            Long currentUserId
    ) {
        if (!"approval_write".equals(requested)) {
            return null;  // unrecognised or absent → V1.0 read-only
        }
        // approval_write requires a KB-bound conversation.
        if (conversation.getKnowledgeBaseId() == null
                || conversation.getKnowledgeBaseId() <= 0) {
            log.warn("capabilityProfile=approval_write rejected: conversation {} has no KB",
                    conversation.getId());
            return null;
        }
        // User must be authenticated.
        if (currentUserId == null || currentUserId <= 0) {
            log.warn("capabilityProfile=approval_write rejected: no authenticated user");
            return null;
        }
        // The authenticated user must own the KB.
        KnowledgeBase kb = knowledgeBaseMapper.selectById(conversation.getKnowledgeBaseId());
        if (kb == null || !currentUserId.equals(kb.getUserId())) {
            log.warn("capabilityProfile=approval_write rejected: user {} does not own KB {}",
                    currentUserId, conversation.getKnowledgeBaseId());
            return null;
        }
        log.info("capabilityProfile=approval_write granted for conversation {} (KB {}, user {})",
                conversation.getId(), conversation.getKnowledgeBaseId(), currentUserId);
        return "approval_write";
    }

    // ──────────────────────────────────────────────────────────────────────

    private static final class StreamCancellation {
        private final AtomicBoolean cancelled;
        private final Long userId;
        private final CompletableFuture<Void> completed = new CompletableFuture<>();
        private volatile reactor.core.Disposable subscription;
        private volatile Long agentRunId;  // Agent V1: current agent_run ID for status updates
        private volatile Long agentTaskId; // Agent V1: current agent_task ID

        private StreamCancellation(AtomicBoolean cancelled, Long userId) {
            this.cancelled = cancelled;
            this.userId = userId;
        }

        private void setSubscription(reactor.core.Disposable subscription) {
            this.subscription = subscription;
        }

        private void setAgentRunId(Long agentRunId) {
            this.agentRunId = agentRunId;
        }

        private Long getAgentRunId() {
            return agentRunId;
        }

        private void setAgentTaskId(Long taskId) {
            this.agentTaskId = taskId;
        }

        private Long getAgentTaskId() {
            return agentTaskId;
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
        List<Long> promptTemplateIds = conversations.stream().map(Conversation::getPromptTemplateId).filter(id -> id != null).distinct().collect(Collectors.toList());
        List<Long> userIds = conversations.stream().map(Conversation::getUserId).filter(id -> id != null).distinct().collect(Collectors.toList());

        // 批量查询知识库名称
        Map<Long, String> kbNameMap = new HashMap<>();
        if (!kbIds.isEmpty()) {
            knowledgeBaseMapper.selectBatchIds(kbIds).forEach(kb -> kbNameMap.put(kb.getId(), kb.getName()));
        }

        Map<Long, String> promptTemplateNameMap = new HashMap<>();
        if (!promptTemplateIds.isEmpty()) {
            promptTemplateMapper.selectBatchIds(promptTemplateIds)
                    .forEach(template -> promptTemplateNameMap.put(template.getId(), template.getName()));
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
                        .promptTemplateId(conv.getPromptTemplateId())
                        .promptTemplateName(conv.getPromptTemplateId() == null ? null : promptTemplateNameMap.get(conv.getPromptTemplateId()))
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
        String promptTemplateName = null;
        if (conversation.getPromptTemplateId() != null) {
            PromptTemplate template = promptTemplateMapper.selectById(conversation.getPromptTemplateId());
            promptTemplateName = template != null ? template.getName() : null;
        }

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
                .promptTemplateId(conversation.getPromptTemplateId())
                .promptTemplateName(promptTemplateName)
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
     * Message → MessageInfoDTO, extracting Agent V1 metadata from sources
     * when present.
     */
    private MessageInfoDTO convertToMessageInfoDTO(Message message) {
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
