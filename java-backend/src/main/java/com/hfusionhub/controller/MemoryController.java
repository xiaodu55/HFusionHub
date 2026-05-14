package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.MemoryEntry;
import com.hfusionhub.service.MemoryService;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/memory")
@RequiredArgsConstructor
public class MemoryController {

    private final MemoryService memoryService;

    @GetMapping
    public R<List<MemoryEntry>> list(
            @RequestParam(required = false) String type, @RequestParam(required = false) Long conversationId) {
        return R.ok(memoryService.listByUser(type, conversationId));
    }

    @PostMapping
    public R<MemoryEntry> save(@Valid @RequestBody MemoryEntry entry) {
        return R.ok(memoryService.save(entry));
    }

    @PutMapping("/{id}")
    public R<MemoryEntry> update(@PathVariable Long id, @RequestBody MemoryEntry entry) {
        return R.ok(memoryService.update(id, entry));
    }

    @DeleteMapping("/{id}")
    public R<Void> delete(@PathVariable Long id) {
        memoryService.delete(id);
        return R.ok();
    }
}
