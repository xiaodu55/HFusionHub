package com.hfusionhub.enums;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 文档处理状态枚举
 *
 * @author HFusionHub Team
 */
@Getter
@AllArgsConstructor
public enum DocumentStatus {

    PENDING(0, "待解析"),
    PROCESSING(1, "解析中"),
    COMPLETED(2, "已完成"),
    FAILED(3, "失败");

    private final Integer code;
    private final String description;

    /**
     * 根据code获取枚举
     */
    public static DocumentStatus fromCode(Integer code) {
        if (code == null) {
            return null;
        }
        for (DocumentStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        return null;
    }
}
