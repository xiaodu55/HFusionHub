package com.hfusionhub.common.dto;

import com.hfusionhub.common.constant.CommonConstants;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 分页查询基类
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "分页查询参数")
public class PageQuery {

    @Schema(description = "当前页码", example = "1")
    private Integer page = CommonConstants.DEFAULT_PAGE;

    @Schema(description = "每页条数", example = "10")
    private Integer pageSize = CommonConstants.DEFAULT_PAGE_SIZE;

    @Schema(description = "排序字段", example = "created_at")
    private String orderBy = CommonConstants.DEFAULT_ORDER_BY;

    @Schema(description = "排序方向", example = "desc")
    private String orderDirection = CommonConstants.ORDER_DESC;

    /**
     * 获取偏移量
     *
     * @return 偏移量
     */
    public long getOffset() {
        return (long) (getPage() - 1) * getPageSize();
    }

    /**
     * 校验分页参数
     */
    public void validate() {
        if (page == null || page < 1) {
            this.page = CommonConstants.DEFAULT_PAGE;
        }
        if (pageSize == null || pageSize < 1) {
            this.pageSize = CommonConstants.DEFAULT_PAGE_SIZE;
        }
        if (pageSize > CommonConstants.MAX_PAGE_SIZE) {
            this.pageSize = CommonConstants.MAX_PAGE_SIZE;
        }
        if (orderBy == null || orderBy.isEmpty()) {
            this.orderBy = CommonConstants.DEFAULT_ORDER_BY;
        }
        if (orderDirection == null
                || (!orderDirection.equals(CommonConstants.ORDER_ASC)
                        && !orderDirection.equals(CommonConstants.ORDER_DESC))) {
            this.orderDirection = CommonConstants.ORDER_DESC;
        }
    }
}
