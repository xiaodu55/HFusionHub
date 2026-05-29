package com.hfusionhub.dto;

import com.hfusionhub.entity.BidRequirement;
import com.hfusionhub.entity.BidScoringMethod;
import com.hfusionhub.entity.TenderElement;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 投标项目详情返回（项目 + 要素 + 评分办法 + 需求清单）
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "投标项目详情返回")
public class BidProjectDetailDTO {

    @Schema(description = "项目基本信息")
    private BidProjectInfoDTO project;

    @Schema(description = "招标结构化要素")
    private List<TenderElement> elements;

    @Schema(description = "评分办法")
    private List<BidScoringMethod> scoringMethods;

    @Schema(description = "需求清单")
    private List<BidRequirement> requirements;
}
