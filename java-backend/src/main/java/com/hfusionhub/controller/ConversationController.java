package com.hfusionhub.controller;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.ConversationCreateDTO;
import com.hfusionhub.dto.ConversationInfoDTO;
import com.hfusionhub.dto.ConversationQueryDTO;
import com.hfusionhub.dto.MessageInfoDTO;
import com.hfusionhub.dto.MessageSendDTO;
import com.hfusionhub.service.ConversationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 对话控制器
 *
 * @author HFusionHub Team
 */
@Tag(name = "对话管理", description = "对话创建、消息发送、历史查询")
@RestController
@RequestMapping("/conversation")
@RequiredArgsConstructor
public class ConversationController {

    private final ConversationService conversationService;

    @Operation(summary = "创建对话", description = "创建新的对话")
    @PostMapping
    public R<ConversationInfoDTO> create(@Valid @RequestBody ConversationCreateDTO dto) {
        ConversationInfoDTO info = conversationService.create(dto);
        return R.ok("创建成功", info);
    }

    @Operation(summary = "删除对话", description = "删除指定对话")
    @DeleteMapping("/{id}")
    public R<Void> delete(
            @Parameter(description = "对话ID") @PathVariable Long id) {
        conversationService.delete(id);
        return R.ok();
    }

    @Operation(summary = "获取对话详情", description = "获取指定对话的详细信息")
    @GetMapping("/{id}")
    public R<ConversationInfoDTO> getById(
            @Parameter(description = "对话ID") @PathVariable Long id) {
        ConversationInfoDTO info = conversationService.getById(id);
        return R.ok(info);
    }

    @Operation(summary = "分页查询对话列表", description = "分页查询所有对话")
    @GetMapping("/list")
    public R<PageResult<ConversationInfoDTO>> list(ConversationQueryDTO queryDTO) {
        PageResult<ConversationInfoDTO> result = conversationService.list(queryDTO);
        return R.ok(result);
    }

    @Operation(summary = "获取我的对话列表", description = "获取当前用户的对话列表")
    @GetMapping("/my")
    public R<PageResult<ConversationInfoDTO>> listByCurrentUser(ConversationQueryDTO queryDTO) {
        PageResult<ConversationInfoDTO> result = conversationService.listByCurrentUser(queryDTO);
        return R.ok(result);
    }

    @Operation(summary = "发送消息", description = "向对话发送消息")
    @PostMapping("/message")
    public R<MessageInfoDTO> sendMessage(@Valid @RequestBody MessageSendDTO dto) {
        MessageInfoDTO info = conversationService.sendMessage(dto);
        return R.ok("发送成功", info);
    }

    @Operation(summary = "获取对话历史", description = "获取指定对话的所有消息")
    @GetMapping("/{id}/messages")
    public R<List<MessageInfoDTO>> getMessages(
            @Parameter(description = "对话ID") @PathVariable Long id) {
        List<MessageInfoDTO> messages = conversationService.getMessages(id);
        return R.ok(messages);
    }
}
