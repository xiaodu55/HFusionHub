package com.hfusionhub.common.constant;

/**
 * 通用常量
 *
 * @author HFusionHub Team
 */
public interface CommonConstants {

    /**
     * 默认当前页
     */
    int DEFAULT_PAGE = 1;

    /**
     * 默认每页条数
     */
    int DEFAULT_PAGE_SIZE = 10;

    /**
     * 最大每页条数
     */
    int MAX_PAGE_SIZE = 100;

    /**
     * 排序方向：升序
     */
    String ORDER_ASC = "asc";

    /**
     * 排序方向：降序
     */
    String ORDER_DESC = "desc";

    /**
     * 默认排序字段
     */
    String DEFAULT_ORDER_BY = "created_at";

    /**
     * 用户状态：正常
     */
    int USER_STATUS_NORMAL = 0;

    /**
     * 用户状态：禁用
     */
    int USER_STATUS_DISABLED = 1;

    /**
     * 知识库状态：正常
     */
    int KB_STATUS_NORMAL = 0;

    /**
     * 知识库状态：禁用
     */
    int KB_STATUS_DISABLED = 1;

    /**
     * 角色：普通用户
     */
    String ROLE_USER = "user";

    /**
     * 角色：管理员
     */
    String ROLE_ADMIN = "admin";

    /**
     * Redis Key 前缀：用户 Token
     */
    String REDIS_TOKEN_PREFIX = "hf:token:";

    /**
     * Redis Key 前缀：用户信息
     */
    String REDIS_USER_PREFIX = "hf:user:";

    /**
     * Redis Key 前缀：验证码
     */
    String REDIS_CODE_PREFIX = "hf:code:";

    /**
     * Redis Key 前缀：接口限流
     */
    String REDIS_LIMIT_PREFIX = "hf:limit:";
}
