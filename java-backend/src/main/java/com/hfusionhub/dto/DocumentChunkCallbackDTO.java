package com.hfusionhub.dto;

import lombok.Data;

import java.util.List;
import java.util.Map;

/** Lightweight chunk metadata returned by the indexing worker callback. */
@Data
public class DocumentChunkCallbackDTO {
    private String chunkId;
    private Integer index;
    private String blockType;
    private List<String> outlinePath;
    private String contentExcerpt;
    private Integer charCount;
    private Map<String, Object> metadata;
    private String embeddingModel;
    private Integer embeddingDimension;
    private String embeddingVersion;
}
