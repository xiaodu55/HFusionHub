package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.dto.ConversationCreateDTO;
import com.hfusionhub.dto.ConversationInfoDTO;
import com.hfusionhub.dto.ConversationQueryDTO;
import com.hfusionhub.dto.MessageInfoDTO;
import com.hfusionhub.dto.MessageSendDTO;

import java.util.List;

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
}
