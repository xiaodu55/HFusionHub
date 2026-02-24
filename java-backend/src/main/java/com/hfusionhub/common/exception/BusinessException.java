package com.hfusionhub.common.exception;

import com.hfusionhub.common.constant.StatusCode;
import lombok.Getter;

/**
 * 业务异常
 *
 * @author HFusionHub Team
 */
@Getter
public class BusinessException extends RuntimeException {

    /**
     * 错误码
     */
    private final int code;

    public BusinessException(String message) {
        super(message);
        this.code = StatusCode.BAD_REQUEST;
    }

    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
    }

    public BusinessException(int code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }
}
