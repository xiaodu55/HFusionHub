package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.result.R;
import com.hfusionhub.service.VectorReconciliationService;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Admin API to trigger and inspect MySQL ↔ vector store reconciliation.
 *
 * <p>Read-only and idempotent; safe to run repeatedly.  Executes the same
 * comparison a scheduled job would run, exposing it on demand.</p>
 */
@Slf4j
@RestController
@RequestMapping("/admin/vector-reconciliation")
@RequiredArgsConstructor
public class VectorReconciliationController {

    private final VectorReconciliationService reconciliationService;

    @SaCheckRole("admin")
    @GetMapping("/documents/{documentId}")
    @Operation(summary = "Reconcile a single document (admin only)")
    public R<VectorReconciliationService.ReconciliationResult> reconcileDocument(
            @PathVariable Long documentId) {
        return R.ok(reconciliationService.reconcileDocument(documentId));
    }

    @SaCheckRole("admin")
    @GetMapping("/all")
    @Operation(summary = "Reconcile all documents (admin only)")
    public R<Map<String, Object>> reconcileAll() {
        return R.ok(reconciliationService.reconcileAll());
    }
}
