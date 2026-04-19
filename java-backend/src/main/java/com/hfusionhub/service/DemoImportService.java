package com.hfusionhub.service;

import com.hfusionhub.dto.DemoImportResultDTO;

/**
 * 演示数据服务 — 一键导入示例知识库，帮助新用户快速体验 RAG 问答
 *
 * @author HFusionHub Team
 */
public interface DemoImportService {

    /**
     * 导入演示知识库（幂等）：创建/复用「演示知识库」，导入内置示例文档并触发解析。
     *
     * @return 导入结果
     */
    DemoImportResultDTO importDemoKnowledgeBase();
}
