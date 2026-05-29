package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.CommonConstants;
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

    /** 示例招标文档文件名 -> 展示标题 */
    private static final Map<String, String> DEMO_TITLES = Map.of(
            "tender-notice.md", "滨海园区智能化改造项目招标公告（演示）",
            "bidder-instructions.md", "投标人须知（演示）",
            "evaluation-method.md", "评标办法（演示）",
            "contract-terms.md", "合同主要条款（演示）");

    /** 示例投标项目（可直接触发解读，演示「项目→解读→需求清单」闭环） */
    private static final String DEMO_PROJECT_TITLE = "示例：滨海园区智能化改造项目";
    private static final String DEMO_PROJECT_TENDER_NUMBER = "BH-2026-0618";
    private static final BigDecimal DEMO_PROJECT_BUDGET = new BigDecimal("12600000");

    @Value("${demo.upload-dir:uploads/documents}")
    private String uploadDir;

    @Override
    public DemoImportResultDTO importBidDemoData() {
        Long userId = JwtUtils.getCurrentUserId();

        KnowledgeBase kb = importTenderKnowledgeBase(userId);
        DocumentImport docs = importTenderDocuments(kb);
        int projectImported = importDemoProject(userId, kb.getId());

        List<DemoImportResultDTO.SectionResult> sections = new ArrayList<>();
        sections.add(section("bid_kb", "招标文件知识库", docs.imported(), docs.skipped()));
        sections.add(section("bid_project", "示例投标项目", projectImported, projectImported == 0 ? 1 : 0));

        String message = buildMessage(docs, projectImported);
        log.info("招投标演示数据导入完成: kbId={}, importedDocs={}, skippedDocs={}, projectImported={}",
                kb.getId(), docs.imported(), docs.skipped(), projectImported);
        return DemoImportResultDTO.builder()
                .knowledgeBaseId(kb.getId())
                .knowledgeBaseName(kb.getName())
                .importedCount(docs.imported())
                .skippedCount(docs.skipped())
                .parseFailedCount(docs.parseFailed())
                .sections(sections)
                .message(message)
                .build();
    }

    @Override
    public DemoImportResultDTO clearBidDemoData() {
        Long userId = JwtUtils.getCurrentUserId();

        int projectsRemoved = clearDemoProjects(userId);
        KnowledgeBase kb = findTenderKb(userId);
        int kbRemoved = 0;
        if (kb != null) {
            try {
                // 知识库移入回收站（保留文档与索引，7 天内可恢复）
                knowledgeBaseService.delete(kb.getId());
                kbRemoved = 1;
            } catch (Exception e) {
                log.warn("清除招投标演示知识库失败: kbId={}, 原因={}", kb.getId(), e.getMessage());
            }
        }

        List<DemoImportResultDTO.SectionResult> sections = new ArrayList<>();
        sections.add(section("bid_kb", "招标文件知识库", kbRemoved, 0));
        sections.add(section("bid_project", "示例投标项目", projectsRemoved, 0));

        String message = (projectsRemoved + kbRemoved) > 0
                ? "招投标演示数据已清除（知识库进入回收站，7 天内可恢复）"
                : "未发现需要清除的招投标演示数据";
        log.info("招投标演示数据清除完成: userId={}, projects={}, kb={}", userId, projectsRemoved, kbRemoved);
        return DemoImportResultDTO.builder()
                .sections(sections)
                .message(message)
                .build();
    }

    // ── 知识库 + 文档 ────────────────────────────────────────────────────

    private KnowledgeBase importTenderKnowledgeBase(Long userId) {
        KnowledgeBase kb = findTenderKb(userId);
        if (kb != null) {
            return kb;
        }
        kb = new KnowledgeBase();
        kb.setName(DEMO_KB_NAME);
        kb.setDescription(DEMO_KB_DESC);
        kb.setCategory(DEMO_KB_CATEGORY);
        kb.setUserId(userId);
        kb.setStatus(CommonConstants.KB_STATUS_NORMAL);
        knowledgeBaseMapper.insert(kb);
        log.info("招投标演示知识库已创建: kbId={}, userId={}", kb.getId(), userId);
        return kb;
    }

    private DocumentImport importTenderDocuments(KnowledgeBase kb) {
        List<Resource> resources = loadResources(DEMO_RESOURCE_DIR);
        int imported = 0;
        int skipped = 0;
        int parseFailed = 0;
        for (Resource resource : resources) {
            String fileName = resource.getFilename();
            String title = DEMO_TITLES.getOrDefault(fileName, fileName);

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

    private int importDemoProject(Long userId, Long kbId) {
        boolean exists = bidProjectMapper.selectCount(new LambdaQueryWrapper<BidProject>()
                        .eq(BidProject::getCreatedBy, userId)
                        .eq(BidProject::getTitle, DEMO_PROJECT_TITLE))
                > 0;
        if (exists) {
            return 0;
        }
        BidProject project = new BidProject();
        project.setKnowledgeBaseId(kbId);
        project.setTitle(DEMO_PROJECT_TITLE);
        project.setTenderNumber(DEMO_PROJECT_TENDER_NUMBER);
        project.setBudget(DEMO_PROJECT_BUDGET);
        project.setStatus(BidProject.STATUS_INTERPRETING);
        project.setCreatedBy(userId);
        bidProjectMapper.insert(project);
        log.info("示例投标项目已创建: id={}, kbId={}, userId={}", project.getId(), kbId, userId);
        return 1;
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

    private DemoImportResultDTO.SectionResult section(String section, String label, int imported, int skipped) {
        return DemoImportResultDTO.SectionResult.builder()
                .section(section)
                .label(label)
                .importedCount(imported)
                .skippedCount(skipped)
                .build();
    }

    private String buildMessage(DocumentImport docs, int projectImported) {
        StringBuilder sb = new StringBuilder("招投标演示环境已就绪");
        if (docs.imported() > 0) {
            sb.append("，新导入 ").append(docs.imported()).append(" 篇招标文件");
        }
        if (projectImported > 0) {
            sb.append("，并创建示例投标项目「").append(DEMO_PROJECT_TITLE).append("」");
        }
        if (docs.skipped() > 0) {
            sb.append("，跳过已存在的 ").append(docs.skipped()).append(" 篇");
        }
        if (docs.parseFailed() > 0) {
            sb.append("；有 ").append(docs.parseFailed()).append(" 篇文档触发解析失败（AI 服务不可用？可稍后在文档页重试）");
        }
        sb.append("。可到「投标项目」打开示例项目，点击「解读」体验完整流程。");
        return sb.toString();
    }

    private KnowledgeBase findTenderKb(Long userId) {
        return knowledgeBaseMapper.selectOne(new LambdaQueryWrapper<KnowledgeBase>()
                .eq(KnowledgeBase::getName, DEMO_KB_NAME)
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
