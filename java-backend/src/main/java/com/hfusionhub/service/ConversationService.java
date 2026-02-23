package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.dto.ConversationCreateDTO;
import com.hfusionhub.dto.ConversationInfoDTO;
import com.hfusionhub.dto.ConversationQueryDTO;
import com.hfusionhub.dto.MessageInfoDTO;
import com.hfusionhub.dto.MessageSendDTO;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 对话服务接口
 *
 * @author HFusionHub Team
 */
public interface ConversationService {

    /**
     * 创建对话
     *
     * @param dto 创建信息
     * @return 对话信息
     */
    ConversationInfoDTO create(ConversationCreateDTO dto);

    /**
     * 删除对话
     *
     * @param id 对话ID
     */
    void delete(Long id);

    /**
     * 获取对话详情
     *
     * @param id 对话ID
     * @return 对话信息
     */
    ConversationInfoDTO getById(Long id);

    /**
     * 分页查询对话列表
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    PageResult<ConversationInfoDTO> list(ConversationQueryDTO queryDTO);

    /**
     * 获取当前用户的对话列表
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    PageResult<ConversationInfoDTO> listByCurrentUser(ConversationQueryDTO queryDTO);

    /**
     * 发送消息
     *
     * @param dto 消息内容
     * @return 消息信息
     */
    MessageInfoDTO sendMessage(MessageSendDTO dto);

    /**
     * 获取对话历史消息
     *
     * @param conversationId 对话ID
     * @return 消息列表
     */
    List<MessageInfoDTO> getMessages(Long conversationId);

    /**
     * 发送消息（流式响应）
     *
     * @param dto 消息内容
     * @param emitter SSE emitter
     */
    void sendMessageStream(MessageSendDTO dto, SseEmitter emitter);

    /**
     * 发送消息（流式响应，指定用户ID，用于异步线程）
     *
     * @param dto 消息内容
     * @param emitter SSE emitter
     * @param currentUserId 当前用户ID
     */
    void sendMessageStream(MessageSendDTO dto, SseEmitter emitter, Long currentUserId);

    /**
     * 发送消息（流式响应，支持取消）
     *
     * @param dto 消息内容
     * @param emitter SSE emitter
     * @param currentUserId 当前用户ID
     * @param cancelled 取消标志，客户端断开时设为true
     */
    void sendMessageStream(MessageSendDTO dto, SseEmitter emitter, Long currentUserId, AtomicBoolean cancelled);

    /**
     * 主动取消指定的流式请求，并等待服务端保存已接收的部分结果。
     */
    boolean cancelMessageStream(String requestId, Long currentUserId);
}
