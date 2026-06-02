package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.DemoImportResultDTO;
import com.hfusionhub.entity.BidProject;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.BidProjectMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.service.BidDemoImportService;
import com.hfusionhub.service.KnowledgeBaseService;
import com.hfusionhub.service.VectorizationService;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.stereotype.Service;

/**
 * 招投标演示数据导入实现（垂直化冷启动）。
 *
 * <p>一键导入「招投标」演示环境，与 {@code DemoImportServiceImpl} 同构：
 * 按「用户 + 名称/标题」判重幂等；AI 服务不可用时文档保持 PENDING/FAILED，
 * 可在文档页稍后重试，不影响其余数据。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BidDemoImportServiceImpl implements BidDemoImportService {

    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final DocumentMapper documentMapper;
    private final BidProjectMapper bidProjectMapper;
    private final VectorizationService vectorizationService;
    private final KnowledgeBaseService knowledgeBaseService;

    private static final String DEMO_KB_NAME = "招投标演示知识库";
    private static final String DEMO_KB_DESC = "一键导入的招投标演示知识库（招标公告、投标人须知、评标办法、合同条款），可直接体验投标项目解读";
    private static final String DEMO_KB_CATEGORY = "tender";
    private static final String DEMO_RESOURCE_DIR = "demo/bid/";

    /** 资质库（P1-6：撰写时自动复用资质/人员/业绩） */
    private static final String DEMO_QUALIFICATION_KB_NAME = "招投标演示·企业资质库";
    private static final String DEMO_QUALIFICATION_KB_DESC = "一键导入的企业资质库（营业执照、资质证书、人员证书、业绩证明），撰写资质文件/商务标时自动检索复用";
    private static final String DEMO_QUALIFICATION_KB_CATEGORY = "qualification";
    private static final String DEMO_QUALIFICATION_RESOURCE_DIR = "demo/bid/qualification/";

    /** 历史标书库（P1-6：撰写商务/技术标时复用成熟范文） */
    private static final String DEMO_HISTORY_KB_NAME = "招投标演示·历史标书库";
    private static final String DEMO_HISTORY_KB_DESC = "一键导入的历史标书库（成熟商务标/技术方案范文），撰写时检索命中复用其表述与结构";
    private static final String DEMO_HISTORY_KB_CATEGORY = "bid_history";
    private static final String DEMO_HISTORY_RESOURCE_DIR = "demo/bid/history/";

    /** 示例招标文档文件名 -> 展示标题 */
    private static final Map<String, String> DEMO_TITLES = Map.of(
            "tender-notice.md", "滨海园区智能化改造项目招标公告（演示）",
            "bidder-instructions.md", "投标人须知（演示）",
            "evaluation-method.md", "评标办法（演示）",
            "contract-terms.md", "合同主要条款（演示）");

    /** 示例资质库文档文件名 -> 展示标题 */
    private static final Map<String, String> DEMO_QUALIFICATION_TITLES = Map.of(
            "qualifications.md", "企业资质文件库（演示）");

    /** 示例历史标书文档文件名 -> 展示标题 */
    private static final Map<String, String> DEMO_HISTORY_TITLES = Map.of(
            "history-bid-commercial.md", "历史标书·商务标范文（演示）",
            "history-bid-technical.md", "历史标书·技术方案范文（演示）");

    /** 示例投标项目（可直接触发解读，演示「项目→解读→需求清单」闭环） */
    private static final String DEMO_PROJECT_TITLE = "示例：滨海园区智能化改造项目";
    private static final String DEMO_PROJECT_TENDER_NUMBER = "BH-2026-0618";
    private static final BigDecimal DEMO_PROJECT_BUDGET = new BigDecimal("12600000");

    /** 行业免费试用样例（P2-6）：与离线评测语料同源的脱敏招标文件 + 示例项目 */
    private static final Map<String, IndustrySample> INDUSTRY_SAMPLES = Map.of(
            "construction", new IndustrySample(
                    "construction", "工程施工",
                    "招投标演示·工程施工行业样例库",
                    "工程施工行业方案包免费试用样例：蓉城市政道路提升改造工程脱敏招标文件（招标公告、投标人须知、评标办法），与行业方案包离线评测语料同源",
                    "demo/bid/industry/construction/",
                    Map.of(
                            "tender-notice.md", "蓉城市政道路提升改造工程招标公告（样例）",
                            "bidder-instructions.md", "投标人须知（样例）",
                            "evaluation-method.md", "评标办法（样例）"),
                    "示例：蓉城市政道路提升改造工程", "CJ-2026-0721", new BigDecimal("86000000")),
            "it", new IndustrySample(
                    "it", "IT 集成",
                    "招投标演示·IT 集成行业样例库",
                    "IT 集成行业方案包免费试用样例：云谷智慧园区数据中心建设项目脱敏招标文件（招标公告、投标人须知、评标办法），与行业方案包离线评测语料同源",
                    "demo/bid/industry/it/",
                    Map.of(
                            "tender-notice.md", "云谷智慧园区数据中心建设项目招标公告（样例）",
                            "bidder-instructions.md", "投标人须知（样例）",
                            "evaluation-method.md", "评标办法（样例）"),
                    "示例：云谷智慧园区数据中心建设项目", "YG-2026-0908", new BigDecimal("58000000")));

    @Value("${demo.upload-dir:uploads/documents}")
    private String uploadDir;

    @Override
    public DemoImportResultDTO importBidDemoData() {
        Long userId = JwtUtils.getCurrentUserId();

        // 三类知识库：招标文件 + 资质库 + 历史标书库（撰写时自动检索复用）
        KnowledgeBase kb = importKnowledgeBase(userId, DEMO_KB_NAME, DEMO_KB_DESC, DEMO_KB_CATEGORY);
        DocumentImport docs = importDocuments(kb, DEMO_RESOURCE_DIR, DEMO_TITLES);
        KnowledgeBase qualificationKb = importKnowledgeBase(userId, DEMO_QUALIFICATION_KB_NAME,
                DEMO_QUALIFICATION_KB_DESC, DEMO_QUALIFICATION_KB_CATEGORY);
        DocumentImport qualificationDocs = importDocuments(qualificationKb,
                DEMO_QUALIFICATION_RESOURCE_DIR, DEMO_QUALIFICATION_TITLES);
        KnowledgeBase historyKb = importKnowledgeBase(userId, DEMO_HISTORY_KB_NAME,
                DEMO_HISTORY_KB_DESC, DEMO_HISTORY_KB_CATEGORY);
        DocumentImport historyDocs = importDocuments(historyKb,
                DEMO_HISTORY_RESOURCE_DIR, DEMO_HISTORY_TITLES);
        int projectImported = importDemoProject(userId, kb.getId(),
                DEMO_PROJECT_TITLE, DEMO_PROJECT_TENDER_NUMBER, DEMO_PROJECT_BUDGET);

        List<DemoImportResultDTO.SectionResult> sections = new ArrayList<>();
        sections.add(section("bid_kb", "招标文件知识库", docs.imported(), docs.skipped()));
        sections.add(section("bid_qualification", "企业资质库", qualificationDocs.imported(), qualificationDocs.skipped()));
        sections.add(section("bid_history", "历史标书库", historyDocs.imported(), historyDocs.skipped()));
        sections.add(section("bid_project", "示例投标项目", projectImported, projectImported == 0 ? 1 : 0));

        String message = buildMessage(docs, qualificationDocs, historyDocs, projectImported);
        log.info("招投标演示数据导入完成: tenderKbId={}, qualKbId={}, histKbId={}, "
                        + "tenderDocs={}/{}, qualDocs={}/{}, histDocs={}/{}, projectImported={}",
                kb.getId(), qualificationKb.getId(), historyKb.getId(),
                docs.imported(), docs.skipped(),
                qualificationDocs.imported(), qualificationDocs.skipped(),
                historyDocs.imported(), historyDocs.skipped(), projectImported);
        return DemoImportResultDTO.builder()
                .knowledgeBaseId(kb.getId())
                .knowledgeBaseName(kb.getName())
                .importedCount(docs.imported() + qualificationDocs.imported() + historyDocs.imported())
                .skippedCount(docs.skipped() + qualificationDocs.skipped() + historyDocs.skipped())
                .parseFailedCount(docs.parseFailed() + qualificationDocs.parseFailed() + historyDocs.parseFailed())
                .sections(sections)
                .message(message)
                .build();
    }

    @Override
    public DemoImportResultDTO clearBidDemoData() {
        Long userId = JwtUtils.getCurrentUserId();

        int projectsRemoved = clearDemoProjects(userId);
        int kbRemovedTotal = 0;
        String[] kbNames = {DEMO_KB_NAME, DEMO_QUALIFICATION_KB_NAME, DEMO_HISTORY_KB_NAME};
        String[] kbLabels = {"招标文件知识库", "企业资质库", "历史标书库"};
        List<DemoImportResultDTO.SectionResult> sections = new ArrayList<>();
        for (int i = 0; i < kbNames.length; i++) {
            int removed = 0;
            KnowledgeBase kb = findKbByName(userId, kbNames[i]);
            if (kb != null) {
                try {
                    // 知识库移入回收站（保留文档与索引，7 天内可恢复）
                    knowledgeBaseService.delete(kb.getId());
                    removed = 1;
                    kbRemovedTotal++;
                } catch (Exception e) {
                    log.warn("清除招投标演示知识库失败: name={}, kbId={}, 原因={}",
                            kbNames[i], kb.getId(), e.getMessage());
                }
            }
            sections.add(section("bid_kb_" + i, kbLabels[i], removed, 0));
        }
        sections.add(section("bid_project", "示例投标项目", projectsRemoved, 0));

        String message = (projectsRemoved + kbRemovedTotal) > 0
                ? "招投标演示数据已清除（知识库进入回收站，7 天内可恢复）"
                : "未发现需要清除的招投标演示数据";
        log.info("招投标演示数据清除完成: userId={}, projects={}, kbs={}", userId, projectsRemoved, kbRemovedTotal);
        return DemoImportResultDTO.builder()
                .sections(sections)
                .message(message)
                .build();
    }

    // ── 知识库 + 文档 ────────────────────────────────────────────────────

    /** 按名称 + 用户判重幂等创建知识库（tender / qualification / bid_history 共用） */
    private KnowledgeBase importKnowledgeBase(Long userId, String name, String description, String category) {
        KnowledgeBase kb = findKbByName(userId, name);
        if (kb != null) {
            return kb;
        }
        kb = new KnowledgeBase();
        kb.setName(name);
        kb.setDescription(description);
        kb.setCategory(category);
        kb.setUserId(userId);
        kb.setStatus(CommonConstants.KB_STATUS_NORMAL);
        knowledgeBaseMapper.insert(kb);
        log.info("招投标演示知识库已创建: name={}, kbId={}, userId={}", name, kb.getId(), userId);
        return kb;
    }

    /** 按资源目录 + 标题映射导入文档并触发向量化（各演示知识库共用） */
    private DocumentImport importDocuments(KnowledgeBase kb, String resourceDir, Map<String, String> titles) {
        List<Resource> resources = loadResources(resourceDir);
        int imported = 0;
        int skipped = 0;
        int parseFailed = 0;
        for (Resource resource : resources) {
            String fileName = resource.getFilename();
            String title = titles.getOrDefault(fileName, fileName);

            if (documentExists(kb.getId(), title)) {
                skipped++;
                continue;
            }
            try {
                long docId = createDocument(kb.getId(), resource, title);
                imported++;
                try {
                    vectorizationService.startVectorization(docId, null);
                } catch (Exception e) {
                    parseFailed++;
                    log.warn("招投标演示文档触发解析失败: docId={}, title={}, 原因={}（AI 服务不可用时可在文档页稍后重试）",
                            docId, title, e.getMessage());
                }
            } catch (IOException e) {
                log.error("招投标演示文档写入失败: {}", title, e);
                throw new BusinessException("招投标演示文档导入失败: " + title);
            }
        }
        return new DocumentImport(imported, skipped, parseFailed);
    }

    // ── 示例投标项目 ─────────────────────────────────────────────────────

    private int importDemoProject(Long userId, Long kbId, String title,
                                  String tenderNumber, BigDecimal budget) {
        boolean exists = bidProjectMapper.selectCount(new LambdaQueryWrapper<BidProject>()
                        .eq(BidProject::getCreatedBy, userId)
                        .eq(BidProject::getTitle, title))
                > 0;
        if (exists) {
            return 0;
        }
        BidProject project = new BidProject();
        project.setKnowledgeBaseId(kbId);
        project.setTitle(title);
        project.setTenderNumber(tenderNumber);
        project.setBudget(budget);
        project.setStatus(BidProject.STATUS_INTERPRETING);
        project.setCreatedBy(userId);
        bidProjectMapper.insert(project);
        log.info("示例投标项目已创建: id={}, kbId={}, userId={}", project.getId(), kbId, userId);
        return 1;
    }

    @Override
    public DemoImportResultDTO importBidIndustrySamples(String industry) {
        IndustrySample def = INDUSTRY_SAMPLES.get(industry);
        if (def == null) {
            throw new BusinessException(StatusCode.BAD_REQUEST,
                    "不支持的行业: " + industry + "（可选 construction / it，对应行业方案包）");
        }
        Long userId = JwtUtils.getCurrentUserId();

        KnowledgeBase kb = importKnowledgeBase(userId, def.kbName(), def.kbDesc(), "tender");
        DocumentImport docs = importDocuments(kb, def.resourceDir(), def.titles());
        int projectImported = importDemoProject(userId, kb.getId(),
                def.projectTitle(), def.tenderNumber(), def.budget());

        List<DemoImportResultDTO.SectionResult> sections = new ArrayList<>();
        sections.add(section("bid_industry_" + def.code(), def.kbName() + "（样例文档）",
                docs.imported(), docs.skipped()));
        sections.add(section("bid_industry_project_" + def.code(), "示例投标项目",
                projectImported, projectImported == 0 ? 1 : 0));

        StringBuilder msg = new StringBuilder("「").append(def.label())
                .append("」行业免费试用样例已就绪");
        if (docs.imported() > 0) {
            msg.append("，新导入 ").append(docs.imported()).append(" 篇脱敏招标文件");
        }
        if (projectImported > 0) {
            msg.append("，并创建示例投标项目「").append(def.projectTitle()).append("」");
        }
        if (docs.skipped() > 0) {
            msg.append("，跳过已存在的 ").append(docs.skipped()).append(" 篇");
        }
        if (docs.parseFailed() > 0) {
            msg.append("；有 ").append(docs.parseFailed())
                    .append(" 篇文档触发解析失败（AI 服务不可用？可稍后在文档页重试）");
        }
        msg.append("。该样例与「").append(def.label())
                .append("行业方案包」的离线评测语料同源，可到「投标项目」打开示例项目体验解读→撰写→废标自检闭环。");
        log.info("招投标行业免费试用样例导入完成: industry={}, kbId={}, docs={}/{}, project={}",
                def.code(), kb.getId(), docs.imported(), docs.skipped(), projectImported);
        return DemoImportResultDTO.builder()
                .knowledgeBaseId(kb.getId())
                .knowledgeBaseName(kb.getName())
                .importedCount(docs.imported())
                .skippedCount(docs.skipped())
                .parseFailedCount(docs.parseFailed())
                .sections(sections)
                .message(msg.toString())
                .build();
    }

    private int clearDemoProjects(Long userId) {
        List<BidProject> projects = bidProjectMapper.selectList(new LambdaQueryWrapper<BidProject>()
                .eq(BidProject::getCreatedBy, userId)
                .eq(BidProject::getTitle, DEMO_PROJECT_TITLE));
        int removed = 0;
        for (BidProject project : projects) {
            try {
                bidProjectMapper.deleteById(project.getId());
                removed++;
            } catch (Exception e) {
                log.warn("清除示例投标项目失败: id={}, 原因={}", project.getId(), e.getMessage());
            }
        }
        return removed;
    }

    // ── 通用辅助 ────────────────────────────────────────────────────────

    /** 文档导入计数 */
    private record DocumentImport(int imported, int skipped, int parseFailed) {}

    /** 行业免费试用样例定义（P2-6）：知识库元信息 + 资源目录 + 示例项目 */
    private record IndustrySample(String code, String label, String kbName, String kbDesc,
                                  String resourceDir, Map<String, String> titles,
                                  String projectTitle, String tenderNumber, BigDecimal budget) {}

    private DemoImportResultDTO.SectionResult section(String section, String label, int imported, int skipped) {
        return DemoImportResultDTO.SectionResult.builder()
                .section(section)
                .label(label)
                .importedCount(imported)
                .skippedCount(skipped)
                .build();
    }

    private String buildMessage(DocumentImport docs, DocumentImport qualificationDocs,
                                DocumentImport historyDocs, int projectImported) {
        StringBuilder sb = new StringBuilder("招投标演示环境已就绪");
        int importedTotal = docs.imported() + qualificationDocs.imported() + historyDocs.imported();
        int skippedTotal = docs.skipped() + qualificationDocs.skipped() + historyDocs.skipped();
        int parseFailedTotal = docs.parseFailed() + qualificationDocs.parseFailed() + historyDocs.parseFailed();
        if (importedTotal > 0) {
            sb.append("，新导入 ").append(importedTotal).append(" 篇文档（招标文件 ")
                    .append(docs.imported()).append("、资质库 ").append(qualificationDocs.imported())
                    .append("、历史标书 ").append(historyDocs.imported()).append("）");
        }
        if (projectImported > 0) {
            sb.append("，并创建示例投标项目「").append(DEMO_PROJECT_TITLE).append("」");
        }
        if (skippedTotal > 0) {
            sb.append("，跳过已存在的 ").append(skippedTotal).append(" 篇");
        }
        if (parseFailedTotal > 0) {
            sb.append("；有 ").append(parseFailedTotal).append(" 篇文档触发解析失败（AI 服务不可用？可稍后在文档页重试）");
        }
        sb.append("。可到「投标项目」打开示例项目，点击「解读」体验完整流程；"
                + "撰写标书时会自动复用企业资质库与历史标书库。");
        return sb.toString();
    }

    private KnowledgeBase findKbByName(Long userId, String name) {
        return knowledgeBaseMapper.selectOne(new LambdaQueryWrapper<KnowledgeBase>()
                .eq(KnowledgeBase::getName, name)
                .eq(KnowledgeBase::getUserId, userId)
                .last("LIMIT 1"));
    }

    private boolean documentExists(Long kbId, String title) {
        Long count = documentMapper.selectCount(new LambdaQueryWrapper<Document>()
                .eq(Document::getKnowledgeBaseId, kbId)
                .eq(Document::getTitle, title));
        return count != null && count > 0;
    }

    private List<Resource> loadResources(String resourceDir) {
        try {
            Resource[] resources =
                    new PathMatchingResourcePatternResolver().getResources("classpath:" + resourceDir + "*.md");
            return new ArrayList<>(List.of(resources));
        } catch (IOException e) {
            throw new BusinessException("读取招投标演示文档资源失败");
        }
    }

    private long createDocument(Long kbId, Resource resource, String title) throws IOException {
        // 写入文件到上传目录（与 DocumentServiceImpl 的路径约定一致；支持绝对/相对路径）
        Path uploadPath = Paths.get(uploadDir);
        if (!uploadPath.isAbsolute()) {
            uploadPath = Paths.get(System.getProperty("user.dir"), uploadDir);
        }
        Files.createDirectories(uploadPath);
        String fileName = UUID.randomUUID() + ".md";
        Path file = uploadPath.resolve(fileName);
        Files.copy(resource.getInputStream(), file, StandardCopyOption.REPLACE_EXISTING);

        String content = new String(resource.getInputStream().readAllBytes(), StandardCharsets.UTF_8);

        Document document = new Document();
        document.setKnowledgeBaseId(kbId);
        document.setTitle(title);
        document.setContent(content);
        document.setFilePath(file.toString());
        document.setFileType(".md");
        document.setFileSize(Files.size(file));
        document.setStatus(DocumentStatus.PENDING.getCode());
        documentMapper.insert(document);
        return document.getId();
    }
}
