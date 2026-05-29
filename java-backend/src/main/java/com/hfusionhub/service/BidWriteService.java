package com.hfusionhub.service;

import com.hfusionhub.entity.BidDraft;
import java.util.List;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 标书撰写服务（招投标垂直化 · P1）
 *
 * @author HFusionHub Team
 */
public interface BidWriteService {

    /**
     * 同步撰写标书全部分节并落库（幂等覆盖 + 版本递增），推进项目至 drafting。
     *
     * @param projectId 投标项目 ID
     * @return 落库后的分节草稿列表
     */
    List<BidDraft> write(Long projectId);

    /**
     * 流式撰写标书：SSE 逐节推送（bid_section_started/completed），
     * run_completed 时统一落库并推进项目状态。
     *
     * @param projectId 投标项目 ID
     * @param emitter   SSE emitter（转发给前端）
     */
    void writeStream(Long projectId, SseEmitter emitter);

    /**
     * 查询项目的全部分节草稿（按版本号降序）。
     */
    List<BidDraft> listDrafts(Long projectId);

    /**
     * 分节人工审批（P1-8）：approved|rejected，approved 记录审批人。
     *
     * @param draftId  分节草稿 ID
     * @param status   approved|rejected
     */
    void updateDraftStatus(Long draftId, String status);
}
