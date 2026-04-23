package com.hfusionhub.common.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import lombok.Data;

/**
 * Lightweight snapshot of a feature flag for internal Python sync.
 * Excludes audit-sensitive fields (operator IDs, whitelist/blacklist user IDs).
 */
@Data
@Schema(description = "Internal feature flag snapshot for Python sync")
public class FeatureFlagSnapshotDTO {

    @Schema(description = "Flag key")
    private String flagKey;

    @Schema(description = "Global enabled state")
    private Boolean enabled;

    @Schema(description = "Flag type")
    private String flagType;

    @Schema(description = "Percentage")
    private Integer percentage;

    @Schema(description = "Whitelist (only for evaluation; opaque to Python)")
    private String whitelist;

    @Schema(description = "Blacklist (only for evaluation; opaque to Python)")
    private String blacklist;

    @Schema(description = "Effective start")
    private LocalDateTime startTime;

    @Schema(description = "Effective end")
    private LocalDateTime endTime;

    @Schema(description = "Override rules")
    private List<SnapshotRule> rules;

    @Data
    @Schema(description = "Rule within snapshot")
    public static class SnapshotRule {
        @Schema(description = "Scope: global, tenant, user, kb, environment")
        private String scope;

        @Schema(description = "Scope value")
        private String scopeValue;

        @Schema(description = "Overridden enabled state")
        private Boolean enabled;

        @Schema(description = "Override percentage")
        private Integer percentage;

        @Schema(description = "Override whitelist")
        private String whitelist;

        @Schema(description = "Override blacklist")
        private String blacklist;
    }
}
