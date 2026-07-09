package com.hfusionhub.service;

import com.hfusionhub.dto.KbShareInfoDTO;
import java.util.List;

/**
 * 知识库共享服务
 *
 * @author HFusionHub Team
 */
public interface KbShareService {

    /**
     * 知识库所有者将知识库共享给指定用户。
     *
     * @param permission "read"（只读，默认）| "read_write"（可上传文档）
     */
    KbShareInfoDTO share(Long knowledgeBaseId, Long targetUserId, String permission);

    /**
     * 用户对知识库的有效权限（Batch 10 资源级授权矩阵）。
     *
     * @return "owner" | "read_write" | "read" | null（无任何权限）
     */
    String getEffectivePermission(Long userId, Long knowledgeBaseId);

    /**
     * 列出当前用户（所有者）在某知识库下的共享记录。
     */
    List<KbShareInfoDTO> listShares(Long knowledgeBaseId);

    /**
     * 列出共享给当前用户的知识库。
     */
    List<KbShareInfoDTO> listSharedToMe();

    /**
     * 撤销共享（仅所有者）。
     */
    void revoke(Long knowledgeBaseId, Long shareId);

    /**
     * 判断用户是否可读该知识库（所有者或已被共享）。
     */
    boolean canRead(Long userId, Long knowledgeBaseId);
}
