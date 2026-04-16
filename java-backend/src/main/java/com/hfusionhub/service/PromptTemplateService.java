package com.hfusionhub.service;

import com.hfusionhub.dto.PromptTemplateInfoDTO;
import com.hfusionhub.dto.PromptTemplateSaveDTO;
import com.hfusionhub.dto.PromptTemplateVersionDTO;
import com.hfusionhub.entity.PromptTemplate;

import java.util.List;

public interface PromptTemplateService {
    List<PromptTemplateInfoDTO> listMine();
    List<PromptTemplateInfoDTO> listRecycleBin(String keyword);
    PromptTemplateInfoDTO create(PromptTemplateSaveDTO dto);
    PromptTemplateInfoDTO update(Long id, PromptTemplateSaveDTO dto);
    PromptTemplateInfoDTO publish(Long id, Integer expectedVersion);
    PromptTemplateInfoDTO unpublish(Long id, Integer expectedVersion);
    void delete(Long id);
    void restore(Long id);
    void purge(Long id);
    PromptTemplate getPublishedOwned(Long id, Long userId);

    /** List all version snapshots for a template, newest first. */
    List<PromptTemplateVersionDTO> listVersions(Long templateId);

    /** Rollback to a specific version snapshot (by its primary key).
     *  The restored content becomes a new DRAFT version;
     *  it must be re-published to affect conversations. */
    PromptTemplateInfoDTO rollback(Long templateId, Long versionId, Integer expectedVersion);
}
