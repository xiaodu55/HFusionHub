package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.DemoImportResultDTO;
import com.hfusionhub.entity.App;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.MemoryEntry;
import com.hfusionhub.entity.Note;
import com.hfusionhub.entity.PromptTemplate;
import com.hfusionhub.entity.SystemNotice;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.AppMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.MemoryEntryMapper;
import com.hfusionhub.mapper.NoteMapper;
import com.hfusionhub.mapper.PromptTemplateMapper;
import com.hfusionhub.mapper.SystemNoticeMapper;
import com.hfusionhub.service.DemoImportService;
import com.hfusionhub.service.KnowledgeBaseService;
import com.hfusionhub.service.PromptTemplateService;
import com.hfusionhub.service.VectorizationService;
import com.hfusionhub.tenant.TenantContext;
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
 * 演示数据导入实现。
 *
 * <p>一键为各菜单导入示例数据：知识库（文档）、回答方案、我的笔记、我的记忆、
 * 应用发布、系统公告。全部按「用户 + 名称/标题」判重，幂等可重复导入；
 * 单项失败不影响其余数据。AI 服务不可用时文档保持 PENDING/FAILED，
 * 用户可在文档页稍后重试。</p>
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
    private final PromptTemplateMapper promptTemplateMapper;
    private final NoteMapper noteMapper;
    private final MemoryEntryMapper memoryEntryMapper;
    private final AppMapper appMapper;
    private final SystemNoticeMapper systemNoticeMapper;
    private final KnowledgeBaseService knowledgeBaseService;
    private final PromptTemplateService promptTemplateService;

    private static final String DEMO_KB_NAME = "演示知识库";
    private static final String DEMO_KB_DESC = "一键导入的示例知识库（员工手册、产品目录、权限矩阵），可直接体验 RAG 问答";
    private static final String DEMO_RESOURCE_DIR = "demo/kb/";
    private static final String DEMO_NOTE_RESOURCE_DIR = "demo/notes/";

    /** 示例文档文件名 -> 展示标题 */
    private static final Map<String, String> DEMO_TITLES = Map.of(
            "employee-handbook.md", "员工手册（演示）",
            "product-catalog.md", "产品目录（演示）",
            "permissions-matrix.md", "权限矩阵（演示）");

    /** 示例笔记文件名 -> 展示标题 */
    private static final Map<String, String> DEMO_NOTE_TITLES = Map.of(
            "weekly-meeting.md", "项目周会纪要（示例）",
            "rag-tuning.md", "RAG 调优笔记（示例）");

    private static final String DEMO_APP_NAME = "演示问答应用";
    private static final String DEMO_APP_DESC = "一键导入的示例应用（草稿）：绑定演示知识库与「客服答疑」回答方案，可体验开放 API 发布流程";
    private static final String DEMO_NOTICE_TITLE = "欢迎使用 HFusionHub";

    /** 示例回答方案（与前端「回答方案」页的内置示例保持一致） */
    private record DemoPrompt(String name, String description, String content) {}

    private static final List<DemoPrompt> DEMO_PROMPTS = List.of(
            new DemoPrompt(
                    "客服答疑",
                    "适合售前、售后和制度咨询，统一先给结论再给处理步骤。",
                    """
                    你是企业客服助手，请使用简洁、友好的中文回答。
                    回答顺序：
                    1. 先直接给出结论；
                    2. 再列出最多 5 个处理步骤；
                    3. 使用知识库资料时标明来源；
                    4. 资料不足时明确说明“现有资料不足”，不要猜测；
                    5. 涉及退款、权限或人工审批时，提醒用户联系人工客服。"""),
            new DemoPrompt(
                    "文档总结",
                    "把长文整理成重点、风险和下一步行动，适合内部资料阅读。",
                    """
                    你是文档整理助手，请严格依据用户提供的资料回答，不补充资料中没有的信息。
                    请按以下结构输出：
                    1. 一句话结论；
                    2. 关键要点（3 到 6 条）；
                    3. 风险或待确认事项；
                    4. 下一步行动。
                    内容较长时优先使用分组标题和项目符号，保持表达清晰。"""),
            new DemoPrompt(
                    "代码审查",
                    "统一代码评审格式，优先发现安全、正确性和维护性问题。",
                    """
                    你是资深代码审查助手，请先指出影响正确性或安全性的高风险问题。
                    请按以下结构输出：
                    1. 问题等级：严重、高、中、低；
                    2. 问题位置和原因；
                    3. 修改建议，必要时给出简短代码示例；
                    4. 没有发现问题的方面也要明确说明。
                    不要为了凑数量而提出无关紧要的建议。"""));

    @Value("${demo.upload-dir:uploads/documents}")
    private String uploadDir;

    @Override
    public DemoImportResultDTO importDemoData() {
        Long userId = JwtUtils.getCurrentUserId();
        Long tenantId = resolveTenantId();

        // 1. 知识库 + 示例文档（原有逻辑）
        KnowledgeBase kb = importDemoKnowledgeBase(userId);
        DocumentImport docs = importDemoDocuments(kb);

        // 2. 其他菜单的示例数据（单项失败不影响整体）
        List<DemoImportResultDTO.SectionResult> sections = new ArrayList<>();
        sections.add(section("kb", "知识库文档", docs.imported(), docs.skipped()));
        sections.add(importPromptTemplates(userId));
        sections.add(importNotes(userId, tenantId, kb.getId()));
        sections.add(importMemories(userId, kb.getId()));
        Long templateId = findTemplateId(userId, "客服答疑");
        sections.add(importApp(userId, tenantId, kb.getId(), templateId));
        sections.add(importNotice());

        String message = buildMessage(sections, docs.parseFailed());
        log.info("演示数据导入完成: kbId={}, sections={}", kb.getId(), sections);
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
    public DemoImportResultDTO clearDemoData() {
        Long userId = JwtUtils.getCurrentUserId();
        Long tenantId = resolveTenantId();

        List<DemoImportResultDTO.SectionResult> sections = new ArrayList<>();
        sections.add(clearDemoKb(userId));
        sections.add(clearPromptTemplates(userId));
        sections.add(clearNotes(userId));
        sections.add(clearMemories(userId));
        sections.add(clearApp(userId));
        sections.add(clearNotice());

        int total = sections.stream().mapToInt(DemoImportResultDTO.SectionResult::getImportedCount).sum();
        String message = total > 0
                ? "演示数据已清除（知识库与回答方案进入回收站，7 天内可恢复）"
                : "未发现需要清除的演示数据";
        log.info("演示数据清除完成: userId={}, sections={}", userId, sections);
        return DemoImportResultDTO.builder()
                .knowledgeBaseId(null)
                .knowledgeBaseName(DEMO_KB_NAME)
                .sections(sections)
                .message(message)
                .build();
    }

    // ── 清除演示数据 ────────────────────────────────────────────────────

    private DemoImportResultDTO.SectionResult clearDemoKb(Long userId) {
        KnowledgeBase kb = findDemoKb(userId);
        if (kb == null) {
            return section("kb", "知识库文档", 0, 0);
        }
        try {
            // 知识库移入回收站（保留文档与索引，可恢复），其下文档一并进入回收站
            knowledgeBaseService.delete(kb.getId());
            return section("kb", "知识库文档", 1, 0);
        } catch (Exception e) {
            log.warn("清除演示知识库失败: kbId={}, 原因={}", kb.getId(), e.getMessage());
            return section("kb", "知识库文档", 0, 0);
        }
    }

    private DemoImportResultDTO.SectionResult clearPromptTemplates(Long userId) {
        int removed = 0;
        for (DemoPrompt demo : DEMO_PROMPTS) {
            PromptTemplate template = promptTemplateMapper.selectOne(new LambdaQueryWrapper<PromptTemplate>()
                    .eq(PromptTemplate::getUserId, userId)
                    .eq(PromptTemplate::getName, demo.name())
                    .last("LIMIT 1"));
            if (template == null) {
                continue;
            }
            try {
                promptTemplateService.delete(template.getId());
                removed++;
            } catch (Exception e) {
                log.warn("清除回答方案失败: id={}, 原因={}", template.getId(), e.getMessage());
            }
        }
        return section("prompts", "回答方案", removed, 0);
    }

    private DemoImportResultDTO.SectionResult clearNotes(Long userId) {
        int removed = 0;
        for (Resource resource : loadResources(DEMO_NOTE_RESOURCE_DIR, "示例笔记")) {
            String title = DEMO_NOTE_TITLES.getOrDefault(resource.getFilename(), resource.getFilename());
            Note note = noteMapper.selectOne(new LambdaQueryWrapper<Note>()
                    .eq(Note::getUserId, userId)
                    .eq(Note::getTitle, title)
                    .last("LIMIT 1"));
            if (note == null) {
                continue;
            }
            try {
                noteMapper.deleteById(note.getId());
                removed++;
            } catch (Exception e) {
                log.warn("清除示例笔记失败: id={}, 原因={}", note.getId(), e.getMessage());
            }
        }
        return section("notes", "我的笔记", removed, 0);
    }

    private DemoImportResultDTO.SectionResult clearMemories(Long userId) {
        int removed = 0;
        for (String content : List.of("回答风格偏好", "演示知识库包含员工手册")) {
            MemoryEntry entry = memoryEntryMapper.selectOne(new LambdaQueryWrapper<MemoryEntry>()
                    .eq(MemoryEntry::getUserId, userId)
                    .like(MemoryEntry::getContent, content)
                    .last("LIMIT 1"));
            if (entry == null) {
                continue;
            }
            try {
                memoryEntryMapper.deleteById(entry.getId());
                removed++;
            } catch (Exception e) {
                log.warn("清除示例记忆失败: id={}, 原因={}", entry.getId(), e.getMessage());
            }
        }
        return section("memory", "我的记忆", removed, 0);
    }

    private DemoImportResultDTO.SectionResult clearApp(Long userId) {
        App app = appMapper.selectOne(new LambdaQueryWrapper<App>()
                .eq(App::getUserId, userId)
                .eq(App::getName, DEMO_APP_NAME)
                .last("LIMIT 1"));
        if (app == null) {
            return section("apps", "应用发布", 0, 0);
        }
        try {
            appMapper.deleteById(app.getId());
            return section("apps", "应用发布", 1, 0);
        } catch (Exception e) {
            log.warn("清除示例应用失败: id={}, 原因={}", app.getId(), e.getMessage());
            return section("apps", "应用发布", 0, 0);
        }
    }

    private DemoImportResultDTO.SectionResult clearNotice() {
        SystemNotice notice = systemNoticeMapper.selectOne(new LambdaQueryWrapper<SystemNotice>()
                .eq(SystemNotice::getTitle, DEMO_NOTICE_TITLE)
                .last("LIMIT 1"));
        if (notice == null) {
            return section("notices", "公告管理", 0, 0);
        }
        try {
            systemNoticeMapper.deleteById(notice.getId());
            return section("notices", "公告管理", 1, 0);
        } catch (Exception e) {
            log.warn("清除欢迎公告失败: id={}, 原因={}", notice.getId(), e.getMessage());
            return section("notices", "公告管理", 0, 0);
        }
    }

    /** 文档导入计数 */
    private record DocumentImport(int imported, int skipped, int parseFailed) {}

    // ── 知识库 + 文档 ────────────────────────────────────────────────────

    private KnowledgeBase importDemoKnowledgeBase(Long userId) {
        KnowledgeBase kb = findDemoKb(userId);
        if (kb != null) {
            return kb;
        }
        kb = new KnowledgeBase();
        kb.setName(DEMO_KB_NAME);
        kb.setDescription(DEMO_KB_DESC);
        kb.setUserId(userId);
        kb.setStatus(CommonConstants.KB_STATUS_NORMAL);
        knowledgeBaseMapper.insert(kb);
        log.info("演示知识库已创建: kbId={}, userId={}", kb.getId(), userId);
        return kb;
    }

    private DocumentImport importDemoDocuments(KnowledgeBase kb) {
        List<Resource> resources = loadResources(DEMO_RESOURCE_DIR, "演示文档");
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
                    log.warn("演示文档触发解析失败: docId={}, title={}, 原因={}（AI 服务不可用时可在文档页稍后重试）",
                            docId, title, e.getMessage());
                }
            } catch (IOException e) {
                log.error("演示文档写入失败: {}", title, e);
                throw new BusinessException("演示文档导入失败: " + title);
            }
        }
        return new DocumentImport(imported, skipped, parseFailed);
    }

    // ── 回答方案 ────────────────────────────────────────────────────────

    private DemoImportResultDTO.SectionResult importPromptTemplates(Long userId) {
        int imported = 0;
        int skipped = 0;
        for (DemoPrompt demo : DEMO_PROMPTS) {
            boolean exists = promptTemplateMapper.selectCount(new LambdaQueryWrapper<PromptTemplate>()
                    .eq(PromptTemplate::getUserId, userId)
                    .eq(PromptTemplate::getName, demo.name())) > 0;
            if (exists) {
                skipped++;
                continue;
            }
            PromptTemplate template = new PromptTemplate();
            template.setUserId(userId);
            template.setName(demo.name());
            template.setDescription(demo.description());
            template.setContent(demo.content());
            template.setStatus(PromptTemplate.STATUS_PUBLISHED);
            template.setVersion(1);
            template.setDeleted(0);
            promptTemplateMapper.insert(template);
            imported++;
        }
        return section("prompts", "回答方案", imported, skipped);
    }

    private Long findTemplateId(Long userId, String name) {
        PromptTemplate template = promptTemplateMapper.selectOne(new LambdaQueryWrapper<PromptTemplate>()
                .eq(PromptTemplate::getUserId, userId)
                .eq(PromptTemplate::getName, name)
                .last("LIMIT 1"));
        return template != null ? template.getId() : null;
    }

    // ── 我的笔记 ────────────────────────────────────────────────────────

    private DemoImportResultDTO.SectionResult importNotes(Long userId, Long tenantId, Long kbId) {
        int imported = 0;
        int skipped = 0;
        for (Resource resource : loadResources(DEMO_NOTE_RESOURCE_DIR, "示例笔记")) {
            String title = DEMO_NOTE_TITLES.getOrDefault(resource.getFilename(), resource.getFilename());
            boolean exists = noteMapper.selectCount(new LambdaQueryWrapper<Note>()
                    .eq(Note::getUserId, userId)
                    .eq(Note::getTitle, title)) > 0;
            if (exists) {
                skipped++;
                continue;
            }
            try {
                Note note = new Note();
                note.setUserId(userId);
                note.setTenantId(tenantId);
                note.setKnowledgeBaseId(kbId);
                note.setTitle(title);
                note.setContent(resource.getContentAsString(StandardCharsets.UTF_8));
                note.setSource("manual");
                noteMapper.insert(note);
                imported++;
            } catch (IOException e) {
                log.error("示例笔记读取失败: {}", title, e);
            }
        }
        return section("notes", "我的笔记", imported, skipped);
    }

    // ── 我的记忆 ────────────────────────────────────────────────────────

    private DemoImportResultDTO.SectionResult importMemories(Long userId, Long kbId) {
        int imported = 0;
        int skipped = 0;
        MemoryEntry preference = new MemoryEntry();
        preference.setUserId(userId);
        preference.setType("user_preference");
        preference.setContent("回答风格偏好：使用简洁的中文，先给结论再给步骤。");
        preference.setEntities("[]");
        preference.setImportance(0.8);

        MemoryEntry fact = new MemoryEntry();
        fact.setUserId(userId);
        fact.setType("entity_fact");
        fact.setContent("演示知识库包含员工手册、产品目录、权限矩阵三类示例文档。");
        fact.setEntities("[\"演示知识库\"]");
        fact.setKnowledgeBaseId(kbId);
        fact.setImportance(0.6);

        for (MemoryEntry entry : List.of(preference, fact)) {
            boolean exists = memoryEntryMapper.selectCount(new LambdaQueryWrapper<MemoryEntry>()
                    .eq(MemoryEntry::getUserId, userId)
                    .eq(MemoryEntry::getType, entry.getType())
                    .eq(MemoryEntry::getContent, entry.getContent())) > 0;
            if (exists) {
                skipped++;
                continue;
            }
            memoryEntryMapper.insert(entry);
            imported++;
        }
        return section("memory", "我的记忆", imported, skipped);
    }

    // ── 应用发布 ────────────────────────────────────────────────────────

    private DemoImportResultDTO.SectionResult importApp(Long userId, Long tenantId, Long kbId, Long templateId) {
        boolean exists = appMapper.selectCount(new LambdaQueryWrapper<App>()
                .eq(App::getUserId, userId)
                .eq(App::getName, DEMO_APP_NAME)) > 0;
        if (exists) {
            return section("apps", "应用发布", 0, 1);
        }
        App app = new App();
        app.setName(DEMO_APP_NAME);
        app.setDescription(DEMO_APP_DESC);
        app.setUserId(userId);
        app.setTenantId(tenantId);
        app.setKnowledgeBaseId(kbId);
        app.setPromptTemplateId(templateId);
        app.setStyle("concise");
        app.setStatus(0);
        appMapper.insert(app);
        return section("apps", "应用发布", 1, 0);
    }

    // ── 系统公告 ────────────────────────────────────────────────────────

    private DemoImportResultDTO.SectionResult importNotice() {
        boolean exists = systemNoticeMapper.selectCount(new LambdaQueryWrapper<SystemNotice>()
                .eq(SystemNotice::getTitle, DEMO_NOTICE_TITLE)) > 0;
        if (exists) {
            return section("notices", "公告管理", 0, 1);
        }
        SystemNotice notice = new SystemNotice();
        notice.setTitle(DEMO_NOTICE_TITLE);
        notice.setContent("演示数据已就绪：可以打开「知识库」查看演示知识库，在「智能对话」中绑定它提问，"
                + "或到「回答方案」「我的笔记」「应用发布」体验各菜单的示例数据。");
        notice.setLevel("info");
        notice.setPublisher("admin");
        notice.setScope("all");
        systemNoticeMapper.insert(notice);
        return section("notices", "公告管理", 1, 0);
    }

    // ── 通用辅助 ────────────────────────────────────────────────────────

    private Long resolveTenantId() {
        Long tenantId = TenantContext.getTenantId();
        return tenantId != null ? tenantId : 1L;
    }

    private DemoImportResultDTO.SectionResult section(String section, String label, int imported, int skipped) {
        return DemoImportResultDTO.SectionResult.builder()
                .section(section)
                .label(label)
                .importedCount(imported)
                .skippedCount(skipped)
                .build();
    }

    private String buildMessage(List<DemoImportResultDTO.SectionResult> sections, int parseFailed) {
        StringBuilder sb = new StringBuilder("演示数据已就绪");
        int totalImported = sections.stream().mapToInt(DemoImportResultDTO.SectionResult::getImportedCount).sum();
        int totalSkipped = sections.stream().mapToInt(DemoImportResultDTO.SectionResult::getSkippedCount).sum();
        if (totalImported > 0) {
            sb.append("，新导入 ").append(totalImported).append(" 项");
        }
        if (totalSkipped > 0) {
            sb.append("，跳过已存在的 ").append(totalSkipped).append(" 项");
        }
        if (parseFailed > 0) {
            sb.append("；有 ").append(parseFailed).append(" 篇文档触发解析失败（AI 服务不可用？可稍后在文档页重试）");
        }
        return sb.toString();
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

    private List<Resource> loadResources(String resourceDir, String description) {
        try {
            Resource[] resources =
                    new PathMatchingResourcePatternResolver().getResources("classpath:" + resourceDir + "*.md");
            return new ArrayList<>(List.of(resources));
        } catch (IOException e) {
            throw new BusinessException("读取" + description + "资源失败");
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
