package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("user_model_config")
public class UserModelConfig {

    @TableId
    private Long id;
    private Long userId;
    private String providerType;
    private String providerName;
    private String baseUrl;
    private String modelName;
    private String apiKeyCiphertext;
    private Integer enabled;
    private String lastTestStatus;
    private String lastTestMessage;
    private LocalDateTime lastTestedAt;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}

