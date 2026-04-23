package com.hfusionhub.service;

import com.hfusionhub.entity.DocumentChunk;
import com.hfusionhub.mapper.DocumentChunkMapper;
import java.util.*;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

/**
 * Detects and reports inconsistencies between the MySQL chunk index and the
 * vector store (Milvus Lite or cluster).
 *
 * <p>This service is intentionally read-only and idempotent.  It can be called
 * from a scheduled job, an admin endpoint, or a CLI tool without side effects.
 * </p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class VectorReconciliationService {

    private final DocumentChunkMapper documentChunkMapper;
    private final RestTemplate restTemplate;

    @Value("${python-ai.base-url:http://localhost:9000}")
    private String pythonEngineUrl;

    @Value("${python-ai.internal-token:}")
    private String internalApiToken;

    /**
     * Summary of a reconciliation pass.
     */
    public record ReconciliationResult(
            int mysqlChunkCount,
            int vectorChunkCount,
            List<String> orphanVectorIds,
            List<Long> missingVectorDocIds,
            boolean healthy) {}

    /**
     * Compare MySQL chunks against the vector store for a single document.
     *
     * @param documentId the document to reconcile
     * @return reconciliation result
     */
    public ReconciliationResult reconcileDocument(Long documentId) {
        // MySQL side: all chunk IDs for this document
        List<DocumentChunk> mysqlChunks = documentChunkMapper.selectList(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<DocumentChunk>()
                        .eq(DocumentChunk::getDocumentId, documentId));
        Set<String> mysqlIds =
                mysqlChunks.stream().map(DocumentChunk::getChunkId).collect(Collectors.toSet());

        // Vector store side: all chunk IDs for this document
        Set<String> vectorIds = fetchVectorChunkIds(documentId);

        // Orphan vectors: in Milvus but not in MySQL
        List<String> orphans =
                vectorIds.stream().filter(id -> !mysqlIds.contains(id)).sorted().toList();

        // Missing vectors: in MySQL but not in Milvus
        List<Long> missingDocIds = mysqlIds.stream()
                .filter(id -> !vectorIds.contains(id))
                .map(id -> documentId)
                .distinct()
                .toList();

        boolean healthy = orphans.isEmpty() && missingDocIds.isEmpty();
        if (!healthy) {
            log.warn(
                    "Document {} reconciliation: orphans={}, missing_vectors={}",
                    documentId,
                    orphans.size(),
                    missingDocIds.size());
        }

        return new ReconciliationResult(mysqlIds.size(), vectorIds.size(), orphans, missingDocIds, healthy);
    }

    /**
     * Global reconciliation across all documents with persisted chunks.
     */
    public Map<String, Object> reconcileAll() {
        // Get all distinct document IDs that have chunks in MySQL
        List<DocumentChunk> allChunks = documentChunkMapper.selectList(null);
        Set<Long> docIds = allChunks.stream().map(DocumentChunk::getDocumentId).collect(Collectors.toSet());

        int totalMysqlChunks = allChunks.size();
        List<String> allOrphans = new ArrayList<>();
        List<Long> allMissing = new ArrayList<>();
        int healthyDocs = 0;
        int unhealthyDocs = 0;

        for (Long docId : docIds) {
            ReconciliationResult result = reconcileDocument(docId);
            allOrphans.addAll(result.orphanVectorIds());
            allMissing.addAll(result.missingVectorDocIds());
            if (result.healthy()) {
                healthyDocs++;
            } else {
                unhealthyDocs++;
            }
        }

        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("total_documents", docIds.size());
        summary.put("total_mysql_chunks", totalMysqlChunks);
        summary.put("healthy_documents", healthyDocs);
        summary.put("unhealthy_documents", unhealthyDocs);
        summary.put("total_orphan_vectors", allOrphans.size());
        summary.put("total_missing_vectors", allMissing.size());
        summary.put("orphan_chunk_ids", allOrphans.stream().limit(100).toList());
        summary.put("healthy", allOrphans.isEmpty() && allMissing.isEmpty());
        return summary;
    }

    /**
     * Fetch all chunk IDs for a document from the vector store via the Python
     * worker's internal API.
     */
    private Set<String> fetchVectorChunkIds(Long documentId) {
        if (internalApiToken == null || internalApiToken.isBlank()) {
            log.warn("PYTHON_AI_INTERNAL_TOKEN not configured; skipping vector lookup for document {}", documentId);
            return Set.of();
        }
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.set("X-Internal-Token", internalApiToken);

            ResponseEntity<String> response = restTemplate.exchange(
                    pythonEngineUrl + "/api/chunks/" + documentId + "?page=1&size=100000",
                    HttpMethod.GET,
                    new HttpEntity<>(headers),
                    String.class);

            if (response.getBody() == null) {
                return Set.of();
            }

            @SuppressWarnings("unchecked")
            Map<String, Object> body = objectMapper().readValue(response.getBody(), Map.class);
            Object dataObj = body.get("data");
            if (dataObj instanceof Map<?, ?> data) {
                Object recordsObj = data.get("records");
                if (recordsObj instanceof List<?> records) {
                    return records.stream()
                            .filter(Map.class::isInstance)
                            .map(r -> (Map<?, ?>) r)
                            .map(r -> String.valueOf(r.get("chunk_id")))
                            .filter(Objects::nonNull)
                            .collect(Collectors.toSet());
                }
            }
        } catch (Exception e) {
            log.debug("Vector chunk ID fetch failed for document {}: {}", documentId, e.getMessage());
        }
        return Set.of();
    }

    private com.fasterxml.jackson.databind.ObjectMapper objectMapper() {
        return new com.fasterxml.jackson.databind.ObjectMapper();
    }
}
