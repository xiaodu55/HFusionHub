package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

@Data
@TableName("rag_answer_feedback")
public class RagAnswerFeedback extends BaseEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long tenantId;
    private Long userId;
    private Long conversationId;
    private Long messageId;
    private Long knowledgeBaseId;
    private String rating;
    private String reason;
    private String expectedAnswer;
    private Long evaluationCaseId;
}
