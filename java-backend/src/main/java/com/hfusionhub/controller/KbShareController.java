package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.KbShareInfoDTO;
import com.hfusionhub.service.KbShareService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 知识库共享控制器
 *
 * @author HFusionHub Team
 */
@Tag(name = "知识库共享", description = "将知识库共享给其他用户（只读）")
@RestController
@RequestMapping("/knowledge-base/share")
@RequiredArgsConstructor
public class KbShareController {

    private final KbShareService kbShareService;
    private final com.hfusionhub.service.AuditLogService auditLogService;

    @Operation(summary = "共享知识库给用户")
    @PostMapping
    public R<KbShareInfoDTO> share(@RequestBody Map<String, Object> body) {
        Long knowledgeBaseId = Long.valueOf(String.valueOf(body.get("knowledgeBaseId")));
        Long targetUserId = Long.valueOf(String.valueOf(body.get("targetUserId")));
        KbShareInfoDTO dto = kbShareService.share(knowledgeBaseId, targetUserId);
        auditLogService.record("kb.share", "kb_share", String.valueOf(dto.getId()),
                "共享知识库 " + knowledgeBaseId + " 给用户 " + targetUserId);
        return R.ok("共享成功", dto);
    }

    @Operation(summary = "某知识库的共享记录（所有者）")
    @GetMapping("/{knowledgeBaseId}")
    public R<List<KbShareInfoDTO>> listShares(@PathVariable Long knowledgeBaseId) {
        return R.ok(kbShareService.listShares(knowledgeBaseId));
    }

    @Operation(summary = "共享给我的知识库")
    @GetMapping("/to-me")
    public R<List<KbShareInfoDTO>> listSharedToMe() {
        return R.ok(kbShareService.listSharedToMe());
    }

    @Operation(summary = "撤销共享")
    @DeleteMapping("/{knowledgeBaseId}/{shareId}")
    public R<Void> revoke(@PathVariable Long knowledgeBaseId, @PathVariable Long shareId) {
        kbShareService.revoke(knowledgeBaseId, shareId);
        auditLogService.record("kb.share.revoke", "kb_share", String.valueOf(shareId),
                "撤销知识库 " + knowledgeBaseId + " 的共享");
        return R.ok("已撤销共享", null);
    }
}
