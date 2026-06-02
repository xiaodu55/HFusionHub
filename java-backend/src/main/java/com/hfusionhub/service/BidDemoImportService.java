package com.hfusionhub.service;

import com.hfusionhub.dto.DemoImportResultDTO;

/**
 * 招投标演示数据导入（垂直化冷启动）。
 *
 * <p>一键为当前租户导入「招投标」演示环境：招标文件知识库（4 篇脱敏招标文件，
 * 与离线评测语料同源）+ 一个示例投标项目（可直接触发解读）。幂等可重复导入。</p>
 *
 * @author HFusionHub Team
 */
public interface BidDemoImportService {

    /**
     * 导入招投标演示环境：建招标文件知识库 + 导入 4 篇示例文档 + 建示例投标项目。
     *
     * @return 导入结果（知识库 ID/名称、文档导入计数、分项结果、提示信息）
     */
    DemoImportResultDTO importBidDemoData();

    /**
     * 清除已导入的招投标演示数据：示例投标项目删除、招标文件知识库移入回收站。
     *
     * @return 清除结果
     */
    DemoImportResultDTO clearBidDemoData();

    /**
     * 导入指定行业的免费试用样例（P2-6）：建行业样例知识库 + 导入 3 篇脱敏招标文件
     * + 建对应示例投标项目（与行业方案包的离线评测语料同源，试用即体验售卖质量）。
     *
     * @param industry 行业 code（construction 工程施工 / it IT 集成），对应行业方案包
     * @return 导入结果（知识库 ID/名称、文档导入计数、分项结果、提示信息）
     */
    DemoImportResultDTO importBidIndustrySamples(String industry);
}
