package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.RagAnswerFeedbackDTO;
import com.hfusionhub.entity.AgentEvaluationCase;
import com.hfusionhub.entity.AgentEvaluationDataset;
import com.hfusionhub.entity.Conversation;
import com.hfusionhub.entity.Message;
import com.hfusionhub.entity.RagAnswerFeedback;
import com.hfusionhub.mapper.ConversationMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.mapper.RagAnswerFeedbackMapper;
import com.hfusionhub.service.AgentEvaluationService;
import com.hfusionhub.service.RagAnswerFeedbackService;
import com.hfusionhub.tenant.TenantContext;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@Service
@RequiredArgsConstructor
public class RagAnswerFeedbackServiceImpl implements RagAnswerFeedbackService {
    private static final String REGRESSION_DATASET_NAME = "用户差评回归集";

    private final RagAnswerFeedbackMapper feedbackMapper;
    private final MessageMapper messageMapper;
    private final ConversationMapper conversationMapper;
    private final AgentEvaluationService evaluationService;

    @Override
    @Transactional
    public RagAnswerFeedback save(RagAnswerFeedbackDTO dto) {
        Long userId = JwtUtils.getCurrentUserId();
        Message message = messageMapper.selectById(dto.getMessageId());
        if (message == null || !"assistant".equals(message.getRole())) {
            throw new BusinessException("只能评价有效的助手回答");
        }
        Conversation conversation = conversationMapper.selectById(message.getConversationId());
        if (conversation == null || !Objects.equals(conversation.getUserId(), userId)) {
            throw new BusinessException("无权评价该回答");
        }

        RagAnswerFeedback feedback = feedbackMapper.selectOne(
                new LambdaQueryWrapper<RagAnswerFeedback>()
                        .eq(RagAnswerFeedback::getUserId, userId)
                        .eq(RagAnswerFeedback::getMessageId, message.getId()));
        boolean created = feedback == null;
        if (created) {
            feedback = new RagAnswerFeedback();
            feedback.setTenantId(TenantContext.requireTenantId());
            feedback.setUserId(userId);
            feedback.setConversationId(conversation.getId());
            feedback.setMessageId(message.getId());
            feedback.setKnowledgeBaseId(resolveKnowledgeBaseId(conversation, message));
        }
        feedback.setRating(dto.getRating());
        feedback.setReason(trimToNull(dto.getReason()));
        feedback.setExpectedAnswer(trimToNull(dto.getExpectedAnswer()));
        if (created) {
            feedbackMapper.insert(feedback);
        } else {
            feedbackMapper.updateById(feedback);
        }

        if ("DOWN".equals(feedback.getRating())
                && StringUtils.hasText(feedback.getExpectedAnswer())
                && feedback.getEvaluationCaseId() == null) {
            AgentEvaluationCase evalCase = promoteToEvaluationCase(feedback, message, conversation, userId);
            feedback.setEvaluationCaseId(evalCase.getId());
            feedbackMapper.updateById(feedback);
        }
        return feedback;
    }

    @Override
    public List<RagAnswerFeedback> listByConversation(Long conversationId) {
        Long userId = JwtUtils.getCurrentUserId();
        Conversation conversation = conversationMapper.selectById(conversationId);
        if (conversation == null || !Objects.equals(conversation.getUserId(), userId)) {
            throw new BusinessException("无权访问该会话反馈");
        }
        return feedbackMapper.selectList(new LambdaQueryWrapper<RagAnswerFeedback>()
                .eq(RagAnswerFeedback::getConversationId, conversationId)
                .eq(RagAnswerFeedback::getUserId, userId)
                .orderByDesc(RagAnswerFeedback::getUpdatedAt));
    }

    private AgentEvaluationCase promoteToEvaluationCase(
            RagAnswerFeedback feedback, Message assistant, Conversation conversation, Long userId) {
        AgentEvaluationDataset dataset = evaluationService.listDatasets(userId, feedback.getKnowledgeBaseId(), 1, 100)
                .stream()
                .filter(item -> REGRESSION_DATASET_NAME.equals(item.getName()))
                .filter(item -> Objects.equals(item.getKnowledgeBaseId(), feedback.getKnowledgeBaseId()))
                .findFirst()
                .orElseGet(() -> {
                    AgentEvaluationDataset created = new AgentEvaluationDataset();
                    created.setName(REGRESSION_DATASET_NAME);
                    created.setDescription("由用户差评和期望答案自动沉淀，用于持续回归验证。");
                    created.setKnowledgeBaseId(feedback.getKnowledgeBaseId());
                    created.setUserId(userId);
                    created.setDimensions(List.of("answer_correctness", "citation_consistency"));
                    return evaluationService.createDataset(created);
                });

        Message queryMessage = messageMapper.selectOne(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, conversation.getId())
                .eq(Message::getRole, "user")
                .lt(Message::getId, assistant.getId())
                .orderByDesc(Message::getId)
                .last("LIMIT 1"));
        AgentEvaluationCase evalCase = new AgentEvaluationCase();
        evalCase.setDatasetId(dataset.getId());
        evalCase.setQuery(queryMessage == null ? "" : queryMessage.getContent());
        evalCase.setExpectedAnswer(feedback.getExpectedAnswer());
        evalCase.setExpectedSources(extractDocumentIds(assistant));
        evalCase.setMetadata(Map.of(
                "origin", "answer_feedback",
                "feedback_id", feedback.getId(),
                "message_id", assistant.getId(),
                "reason", feedback.getReason() == null ? "" : feedback.getReason()));
        return evaluationService.addCase(userId, evalCase);
    }

    private Long resolveKnowledgeBaseId(Conversation conversation, Message message) {
        if (conversation.getKnowledgeBaseId() != null) {
            return conversation.getKnowledgeBaseId();
        }
        if (message.getSources() != null) {
            for (Map<String, Object> source : message.getSources()) {
                Object value = source.get("knowledge_base_id");
                if (value instanceof Number number) {
                    return number.longValue();
                }
            }
        }
        return null;
    }

    private List<String> extractDocumentIds(Message message) {
        List<String> ids = new ArrayList<>();
        if (message.getSources() != null) {
            for (Map<String, Object> source : message.getSources()) {
                Object value = source.get("document_id");
                if (value != null && !ids.contains(String.valueOf(value))) {
                    ids.add(String.valueOf(value));
                }
            }
        }
        return ids;
    }

    private String trimToNull(String value) {
        return StringUtils.hasText(value) ? value.trim() : null;
    }
}
