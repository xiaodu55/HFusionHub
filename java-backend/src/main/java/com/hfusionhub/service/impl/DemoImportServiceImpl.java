package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.DemoImportResultDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.service.DemoImportService;
import com.hfusionhub.service.VectorizationService;
import java.io.IOException;
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
 * 演示知识库导入实现。
 *
 * <p>流程：创建/复用「演示知识库」→ 逐篇导入内置示例文档（标题幂等，可重复导入）→
 * 触发解析与向量化。单篇解析失败不影响其余文档（AI 服务不可用时文档保持
 * PENDING/FAILED，用户可在文档页稍后重试）。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DemoImportServiceImpl implements DemoImportService {

    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final DocumentMapper documentMapper;
    private final VectorizationService vectorizationService;

    private static final String DEMO_KB_NAME = "演示知识库";
    private static final String DEMO_KB_DESC = "一键导入的示例知识库（员工手册、产品目录、权限矩阵），可直接体验 RAG 问答";
    private static final String DEMO_RESOURCE_DIR = "demo/kb/";

    /** 示例文档文件名 → 展示标题 */
    private static final Map<String, String> DEMO_TITLES = Map.of(
            "employee-handbook.md", "员工手册（演示）",
            "product-catalog.md", "产品目录（演示）",
            "permissions-matrix.md", "权限矩阵（演示）");

    @Value("${demo.upload-dir:uploads/documents}")
    private String uploadDir;

    @Override
    public DemoImportResultDTO importDemoKnowledgeBase() {
        Long userId = JwtUtils.getCurrentUserId();

        // 1. 创建或复用演示知识库
        KnowledgeBase kb = findDemoKb(userId);
        boolean createdKb = false;
        if (kb == null) {
            kb = new KnowledgeBase();
            kb.setName(DEMO_KB_NAME);
            kb.setDescription(DEMO_KB_DESC);
            kb.setUserId(userId);
            kb.setStatus(CommonConstants.KB_STATUS_NORMAL);
            knowledgeBaseMapper.insert(kb);
            createdKb = true;
            log.info("演示知识库已创建: kbId={}, userId={}", kb.getId(), userId);
        }

        // 2. 读取内置示例文档
        List<Resource> resources = loadDemoResources();
        if (resources.isEmpty()) {
            throw new BusinessException("未找到内置演示文档资源");
        }

        // 3. 逐篇导入（标题幂等）
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
                    // 触发解析与向量化；失败仅记录，不影响其余文档
                    vectorizationService.startVectorization(docId, null);
                } catch (Exception e) {
                    parseFailed++;
                    log.warn("演示文档触发解析失败: docId={}, title={}, 原因={}（AI 服务不可用时可在文档页稍后重试）", docId, title, e.getMessage());
                }
            } catch (IOException e) {
                log.error("演示文档写入失败: {}", title, e);
                throw new BusinessException("演示文档导入失败: " + title);
            }
        }

        String message = buildMessage(createdKb, imported, skipped, parseFailed);
        log.info(
                "演示知识库导入完成: kbId={}, imported={}, skipped={}, parseFailed={}",
                kb.getId(),
                imported,
                skipped,
                parseFailed);

        return DemoImportResultDTO.builder()
                .knowledgeBaseId(kb.getId())
                .knowledgeBaseName(kb.getName())
                .importedCount(imported)
                .skippedCount(skipped)
                .parseFailedCount(parseFailed)
                .message(message)
                .build();
    }

    private KnowledgeBase findDemoKb(Long userId) {
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

    private List<Resource> loadDemoResources() {
        try {
            Resource[] resources =
                    new PathMatchingResourcePatternResolver().getResources("classpath:" + DEMO_RESOURCE_DIR + "*.md");
            return new ArrayList<>(List.of(resources));
        } catch (IOException e) {
            throw new BusinessException("读取演示文档资源失败");
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

    private String buildMessage(boolean createdKb, int imported, int skipped, int parseFailed) {
        StringBuilder sb = new StringBuilder();
        if (createdKb) {
            sb.append("已创建演示知识库");
        } else {
            sb.append("演示知识库已存在");
        }
        if (imported > 0) {
            sb.append("，新导入 ").append(imported).append(" 篇文档");
        }
        if (skipped > 0) {
            sb.append("，跳过已存在的 ").append(skipped).append(" 篇");
        }
        if (parseFailed > 0) {
            sb.append("；有 ").append(parseFailed).append(" 篇触发解析失败（AI 服务不可用？可稍后在文档页重试）");
        }
        return sb.toString();
    }
}
