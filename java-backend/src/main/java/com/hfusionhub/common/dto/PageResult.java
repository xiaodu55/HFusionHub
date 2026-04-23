package com.hfusionhub.common.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.Collections;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 分页返回结果
 *
 * @param <T> 数据类型
 * @author HFusionHub Team
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "分页返回结果")
public class PageResult<T> {

    @Schema(description = "当前页码")
    private long page;

    @Schema(description = "每页条数")
    private long pageSize;

    @Schema(description = "总记录数")
    private long total;

    @Schema(description = "总页数")
    private long totalPages;

    @Schema(description = "数据列表")
    private List<T> records;

    @Schema(description = "是否有上一页")
    private boolean hasPrevious;

    @Schema(description = "是否有下一页")
    private boolean hasNext;

    /**
     * 创建空的分页结果
     *
     * @param page     当前页码
     * @param pageSize 每页条数
     * @return 空的分页结果
     */
    public static <T> PageResult<T> empty(long page, long pageSize) {
        return new PageResult<>(page, pageSize, 0, 0, Collections.emptyList(), false, false);
    }

    /**
     * 创建分页结果
     *
     * @param page       当前页码
     * @param pageSize   每页条数
     * @param total      总记录数
     * @param records    数据列表
     * @return 分页结果
     */
    public static <T> PageResult<T> of(long page, long pageSize, long total, List<T> records) {
        long totalPages = (total + pageSize - 1) / pageSize;
        boolean hasPrevious = page > 1;
        boolean hasNext = page < totalPages;
        return new PageResult<>(page, pageSize, total, totalPages, records, hasPrevious, hasNext);
    }

    /**
     * 从 MyBatis Plus 分页结果创建
     *
     * @param page       当前页码
     * @param pageSize   每页条数
     * @param total      总记录数
     * @param records    数据列表
     * @return 分页结果
     */
    public static <T> PageResult<T> fromIPage(long page, long pageSize, long total, List<T> records) {
        return of(page, pageSize, total, records);
    }
}
