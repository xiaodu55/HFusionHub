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
import com.hfusionhub.entity.Conversation;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.Message;
import com.hfusionhub.mapper.ConversationMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.service.ConversationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.stream.Collectors;

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

        // 2. 转换为 DTO
        return convertToInfoDTO(conversation);
    }

    @Override
    public PageResult<ConversationInfoDTO> list(ConversationQueryDTO queryDTO) {
        // 1. 构建查询条件
        LambdaQueryWrapper<Conversation> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(queryDTO.getKnowledgeBaseId() != null, Conversation::getKnowledgeBaseId, queryDTO.getKnowledgeBaseId())
                .like(StringUtils.hasText(queryDTO.getTitle()), Conversation::getTitle, queryDTO.getTitle())
                .orderByDesc(Conversation::getCreatedAt);

        // 2. 分页查询
        Page<Conversation> page = new Page<>(queryDTO.getPage(), queryDTO.getPageSize());
        Page<Conversation> result = conversationMapper.selectPage(page, wrapper);

        // 3. 转换为 DTO
        List<ConversationInfoDTO> records = result.getRecords().stream()
                .map(this::convertToInfoDTO)
                .collect(Collectors.toList());

        // 4. 返回分页结果
        return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), result.getTotal(), records);
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

        // 4. 转换为 DTO
        List<ConversationInfoDTO> records = result.getRecords().stream()
                .map(this::convertToInfoDTO)
                .collect(Collectors.toList());

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

        // 4. TODO: 调用 Python AI 服务获取回复
        // 这里暂时返回一个模拟的助手回复
        Message assistantMessage = new Message();
        assistantMessage.setConversationId(dto.getConversationId());
        assistantMessage.setRole("assistant");
        assistantMessage.setContent("这是一个模拟的AI回复。实际项目中，这里会调用Python AI服务。");
        assistantMessage.setModel("mock-model");
        assistantMessage.setTokenCount(0);
        messageMapper.insert(assistantMessage);

        // 5. 更新对话标题（如果是第一条消息）
        if ("新对话".equals(conversation.getTitle()) && StringUtils.hasText(dto.getContent())) {
            String title = dto.getContent();
            if (title.length() > 50) {
                title = title.substring(0, 50) + "...";
            }
            conversation.setTitle(title);
            conversationMapper.updateById(conversation);
        }

        // 6. 返回助手消息
        return convertToMessageInfoDTO(assistantMessage);
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

        // 3. 查询消息列表
        LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Message::getConversationId, conversationId)
                .orderByAsc(Message::getCreatedAt);
        List<Message> messages = messageMapper.selectList(wrapper);

        // 4. 转换为 DTO
        return messages.stream()
                .map(this::convertToMessageInfoDTO)
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
                .createdAt(message.getCreatedAt())
                .build();
    }
}
