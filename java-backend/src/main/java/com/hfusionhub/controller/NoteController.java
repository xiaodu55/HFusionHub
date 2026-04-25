package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.Note;
import com.hfusionhub.service.NoteService;
import com.hfusionhub.tenant.TenantContext;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 用户笔记管理
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/note")
@RequiredArgsConstructor
@Tag(name = "笔记管理", description = "用户笔记的创建、列表、查看、更新、删除")
public class NoteController {

    private final NoteService noteService;

    @Operation(summary = "我的笔记列表", description = "当前用户的笔记列表（最新在前）")
    @GetMapping("/my")
    public R<List<Note>> myNotes(@RequestParam(defaultValue = "100") int limit) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(noteService.listMyNotes(userId, limit));
    }

    @Operation(summary = "笔记详情", description = "查看单条笔记（仅本人）")
    @GetMapping("/{id}")
    public R<Note> detail(@PathVariable Long id) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(noteService.getNote(userId, id));
    }

    @Operation(summary = "创建笔记", description = "手动创建笔记")
    @PostMapping
    public R<Note> create(@Valid @RequestBody NoteCreateDTO dto) {
        Long userId = JwtUtils.getCurrentUserId();
        Note note = noteService.createNote(
                userId,
                TenantContext.getTenantId(),
                dto.getKnowledgeBaseId(),
                null,
                null,
                dto.getTitle(),
                dto.getContent(),
                "manual");
        return R.ok("创建成功", note);
    }

    @Operation(summary = "更新笔记", description = "更新笔记标题/内容（仅本人）")
    @PutMapping("/{id}")
    public R<Note> update(@PathVariable Long id, @RequestBody Map<String, String> body) {
        Long userId = JwtUtils.getCurrentUserId();
        String title = body == null ? null : body.get("title");
        String content = body == null ? null : body.get("content");
        Note note = noteService.updateNote(userId, id, title, content);
        return R.ok("更新成功", note);
    }

    @Operation(summary = "删除笔记", description = "删除笔记（仅本人）")
    @DeleteMapping("/{id}")
    public R<Void> delete(@PathVariable Long id) {
        Long userId = JwtUtils.getCurrentUserId();
        noteService.deleteNote(userId, id);
        return R.ok("删除成功", null);
    }

    @Data
    public static class NoteCreateDTO {
        @Size(max = 200, message = "标题长度不能超过200")
        private String title;

        @NotBlank(message = "笔记内容不能为空")
        @Size(max = 50000, message = "笔记内容不能超过50000字符")
        private String content;

        private Long knowledgeBaseId;
    }
}
