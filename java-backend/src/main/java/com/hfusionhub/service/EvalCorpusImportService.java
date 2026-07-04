package com.hfusionhub.service;

import com.hfusionhub.dto.EvalCorpusImportResultDTO;

/**
 * 评测语料导入服务：把 eval-corpus 资源（115 篇中文业务 markdown）批量导入
 * 为「评测语料库」知识库，用于评估中枢（eval_harness）的检索/生成质量评估。
 *
 * @author HFusionHub Team
 */
public interface EvalCorpusImportService {

    /**
     * 导入评测语料（幂等）：单知识库、按 frontmatter doc_id 判重。
     * 文档标题 = 业务码（如 PROD_AIR_001），与评测集 expected_doc_ids 对应。
     *
     * @param userId 归属用户（当前管理员）
     * @return 导入结果（含业务码 → 文档ID 映射）
     */
    EvalCorpusImportResultDTO importCorpus(Long userId);
}
