package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.BidDraft;
import com.hfusionhub.service.BidWriteService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 标书撰写控制器（招投标垂直化 · P1）
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/bid/write")
@RequiredArgsConstructor
@Tag(name = "标书撰写", description = "标书分节撰写（同步/流式）与分节审批")
public class BidWriteController {

    private final BidWriteService bidWriteService;

    @PostMapping("/{id}")
    @Operation(summary = "同步撰写标书", description = "按分节生成标书草稿并落库，推进项目至 drafting")
    public R<List<BidDraft>> write(@PathVariable Long id) {
        return R.ok("撰写完成", bidWriteService.write(id));
    }

    @PostMapping(value = "/{id}/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @Operation(summary = "流式撰写标书", description = "SSE 逐节推送 bid_section_started/completed，run_completed 落库")
    public SseEmitter writeStream(@PathVariable Long id) {
        SseEmitter emitter = new SseEmitter(300000L); // 5 分钟超时，与聊天流一致
        bidWriteService.writeStream(id, emitter);
        return emitter;
    }

    @GetMapping("/{id}/drafts")
    @Operation(summary = "查询标书分节", description = "查询项目的全部分节草稿（最新版本优先）")
    public R<List<BidDraft>> listDrafts(@PathVariable Long id) {
        return R.ok(bidWriteService.listDrafts(id));
    }

    @PutMapping("/{id}/status")
    @Operation(summary = "分节人工审批", description = "approved|rejected，approved 记录审批人（每节强制审批）")
    public R<Void> updateDraftStatus(@PathVariable Long id, @RequestParam String status) {
        bidWriteService.updateDraftStatus(id, status);
        return R.ok();
    }
}
