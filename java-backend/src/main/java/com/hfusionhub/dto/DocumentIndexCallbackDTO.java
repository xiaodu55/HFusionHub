package com.hfusionhub.dto;

import lombok.Data;

import java.util.List;

/** Callback contract between the Python indexing worker and Java API. */
@Data
public class DocumentIndexCallbackDTO {
    private String status;
    private Integer chunkCount;
    private String message;
    private String indexVersion;
    private List<DocumentChunkCallbackDTO> chunks;
}
