package com.hfusionhub.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class RagAnswerFeedbackDTO {
    @NotNull
    private Long messageId;

    @NotBlank
    @Pattern(regexp = "UP|DOWN")
    private String rating;

    @Size(max = 500)
    private String reason;

    @Size(max = 10000)
    private String expectedAnswer;
}
