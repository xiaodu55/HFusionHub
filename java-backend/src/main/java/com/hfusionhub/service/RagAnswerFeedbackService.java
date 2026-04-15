package com.hfusionhub.service;

import com.hfusionhub.dto.RagAnswerFeedbackDTO;
import com.hfusionhub.entity.RagAnswerFeedback;

import java.util.List;

public interface RagAnswerFeedbackService {
    RagAnswerFeedback save(RagAnswerFeedbackDTO dto);
    List<RagAnswerFeedback> listByConversation(Long conversationId);
}
