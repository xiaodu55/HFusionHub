package com.hfusionhub.service.impl;

import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.dto.EvalCorpusImportResultDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.service.EvalCorpusImportService;
import com.hfusionhub.service.VectorizationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 评测语料导入服务实现（复用 DemoImportServiceImpl 的 classpath 资源导入模式）。
 *
 * <p>语料：resources/eval-corpus/**（115 篇带 frontmatter 的中文业务 markdown，
 * 来源 ragenteval 评测集配套语料）。文档标题 = frontmatter doc_id（业务码），
 * 评测集 expected_doc_ids 中的业务码经本服务返回的 docIdMap 翻译为系统文档 ID。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class EvalCorpusImportServiceImpl implements EvalCorpusImportService {

    private static final String CORPUS_RESOURCE_DIR = "eval-corpus/";
    private static final String EVAL_KB_NAME = "评测语料库";
    private static final String EVAL_KB_DESC = "评估中枢专用语料（ragenteval 中文业务文档集），供生成质量/检索指标评估使用";
    private static final Pattern DOC_ID_PATTERN = Pattern.compile("^doc_id:\\s*(\\S+)", Pattern.MULTILINE);

    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final DocumentMapper documentMapper;
    private final VectorizationService vectorizationService;

    @Value("${app.upload.dir:uploads/documents}")
    private String uploadDir;

    @Override
    public EvalCorpusImportResultDTO importCorpus(Long userId) {
        KnowledgeBase kb = findEvalKb(userId);
        if (kb == null) {
            kb = new KnowledgeBase();
            kb.setName(EVAL_KB_NAME);
            kb.setDescription(EVAL_KB_DESC);
            kb.setUserId(userId);
            kb.setStatus(CommonConstants.KB_STATUS_NORMAL);
            knowledgeBaseMapper.insert(kb);
            log.info("评测知识库已创建: kbId={}, userId={}", kb.getId(), userId);
        }

        int imported = 0;
        int skipped = 0;
        int parseFailed = 0;
        Map<String, String> docIdMap = new LinkedHashMap<>();

        for (Resource resource : loadCorpusResources()) {
            String docCode;
            String content;
            try {
                content = new String(resource.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
                docCode = extractDocId(content);
            } catch (IOException e) {
                log.warn("评测语料读取失败: {}", resource.getFilename(), e);
                skipped++;
                continue;
            }
            if (docCode == null) {
                // 无 doc_id frontmatter 的元文件（模板/索引）不入库
                skipped++;
                continue;
            }

            String title = docCode;
            if (documentExists(kb.getId(), title)) {
                skipped++;
                Document existing = documentMapper.selectList(
                                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<Document>()
                                        .eq(Document::getKnowledgeBaseId, kb.getId())
                                        .eq(Document::getTitle, title)
                                        .last("LIMIT 1"))
                        .stream().findFirst().orElse(null);
                if (existing != null) {
                    docIdMap.put(docCode, String.valueOf(existing.getId()));
                }
                continue;
            }

            try {
                long docId = createDocument(kb.getId(), resource, title, content);
                imported++;
                docIdMap.put(docCode, String.valueOf(docId));
                try {
                    vectorizationService.startVectorization(docId, null);
                } catch (Exception e) {
                    parseFailed++;
                    log.warn("评测语料触发解析失败: docId={}, docCode={}（可在文档页稍后重试）",
                            docId, docCode, e);
                }
            } catch (IOException e) {
                log.error("评测语料写入失败: {}", docCode, e);
                skipped++;
            }
        }

        EvalCorpusImportResultDTO result = new EvalCorpusImportResultDTO();
        result.setKnowledgeBaseId(kb.getId());
        result.setKnowledgeBaseName(kb.getName());
        result.setImportedCount(imported);
        result.setSkippedCount(skipped);
        result.setParseFailedCount(parseFailed);
        result.setDocIdMap(docIdMap);
        log.info("评测语料导入完成: kbId={}, imported={}, skipped={}, parseFailed={}",
                kb.getId(), imported, skipped, parseFailed);
        return result;
    }

    private KnowledgeBase findEvalKb(Long userId) {
        return knowledgeBaseMapper.selectList(
                        new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<KnowledgeBase>()
                                .eq(KnowledgeBase::getUserId, userId)
                                .eq(KnowledgeBase::getName, EVAL_KB_NAME)
                                .last("LIMIT 1"))
                .stream().findFirst().orElse(null);
    }

    private List<Resource> loadCorpusResources() {
        try {
            Resource[] resources = new PathMatchingResourcePatternResolver()
                    .getResources("classpath*:" + CORPUS_RESOURCE_DIR + "**/*.md");
            List<Resource> out = new ArrayList<>(List.of(resources));
            // 排除 _meta 元文件（模板/索引，无 doc_id 或非语料）
            out.removeIf(r -> {
                String path = r.getFilename() != null ? r.getFilename() : "";
                try {
                    return path.contains("_meta") || r.getURL().getPath().contains("_meta");
                } catch (IOException e) {
                    return false;
                }
            });
            return out;
        } catch (IOException e) {
            throw new IllegalStateException("读取评测语料资源失败", e);
        }
    }

    private String extractDocId(String markdown) {
        Matcher matcher = DOC_ID_PATTERN.matcher(markdown);
        return matcher.find() ? matcher.group(1) : null;
    }

    private boolean documentExists(Long kbId, String title) {
        return documentMapper.selectCount(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<Document>()
                        .eq(Document::getKnowledgeBaseId, kbId)
                        .eq(Document::getTitle, title)) > 0;
    }

    private long createDocument(Long kbId, Resource resource, String title, String content) throws IOException {
        Path uploadPath = Paths.get(uploadDir);
        if (!uploadPath.isAbsolute()) {
            uploadPath = Paths.get(System.getProperty("user.dir"), uploadDir);
        }
        Files.createDirectories(uploadPath);
        String fileName = UUID.randomUUID() + ".md";
        Path file = uploadPath.resolve(fileName);
        Files.copy(resource.getInputStream(), file, StandardCopyOption.REPLACE_EXISTING);

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
