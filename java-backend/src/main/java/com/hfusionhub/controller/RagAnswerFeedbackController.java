package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.RagAnswerFeedbackDTO;
import com.hfusionhub.entity.RagAnswerFeedback;
import com.hfusionhub.service.RagAnswerFeedbackService;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/rag/feedback")
@RequiredArgsConstructor
public class RagAnswerFeedbackController {
    private final RagAnswerFeedbackService feedbackService;

    @PostMapping
    public R<RagAnswerFeedback> save(@Valid @RequestBody RagAnswerFeedbackDTO dto) {
        return R.ok(feedbackService.save(dto));
    }

    @GetMapping
    public R<List<RagAnswerFeedback>> list(@RequestParam Long conversationId) {
        return R.ok(feedbackService.listByConversation(conversationId));
    }
}
