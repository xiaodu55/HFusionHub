package com.hfusionhub.common.constant;

/**
 * 状态码常量
 *
 * @author HFusionHub Team
 */
public interface StatusCode {

    /**
     * 成功
     */
    int SUCCESS = 200;

    /**
     * 参数错误
     */
    int BAD_REQUEST = 400;

    /**
     * 未认证
     */
    int UNAUTHORIZED = 401;

    /**
     * 无权限
     */
    int FORBIDDEN = 403;

    /**
     * 资源不存在
     */
    int NOT_FOUND = 404;

    /**
     * 请求过于频繁
     */
    int TOO_MANY_REQUESTS = 429;

    /**
     * 系统内部错误
     */
    int INTERNAL_ERROR = 500;

    /**
     * 服务不可用
     */
    int SERVICE_UNAVAILABLE = 503;

    // ==================== 业务错误码 (1000-1999) ====================

    /**
     * 用户名或密码错误
     */
    int LOGIN_ERROR = 1001;

    /**
     * 用户已被禁用
     */
    int USER_DISABLED = 1002;

    /**
     * 用户已存在
     */
    int USER_EXISTS = 1003;

    /**
     * Token 已过期
     */
    int TOKEN_EXPIRED = 1004;

    /**
     * Token 无效
     */
    int TOKEN_INVALID = 1005;

    // ==================== 知识库错误码 (2000-2999) ====================

    /**
     * 知识库不存在
     */
    int KNOWLEDGE_BASE_NOT_FOUND = 2001;

    /**
     * 知识库名称已存在
     */
    int KNOWLEDGE_BASE_EXISTS = 2002;

    /**
     * 文档不存在
     */
    int DOCUMENT_NOT_FOUND = 2003;

    /**
     * 文件格式不支持
     */
    int FILE_FORMAT_ERROR = 2004;

    /**
     * 文件大小超出限制
     */
    int FILE_SIZE_EXCEEDED = 2005;

    // ==================== 对话错误码 (3000-3999) ====================

    /**
     * 对话不存在
     */
    int CONVERSATION_NOT_FOUND = 3001;

    /**
     * 消息发送失败
     */
    int MESSAGE_SEND_FAILED = 3002;

    /**
     * AI 服务不可用
     */
    int AI_SERVICE_UNAVAILABLE = 3003;
}
