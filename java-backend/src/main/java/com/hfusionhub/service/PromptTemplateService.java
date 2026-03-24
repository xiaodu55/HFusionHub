package com.hfusionhub.service;

import com.hfusionhub.dto.PromptTemplateInfoDTO;
import com.hfusionhub.dto.PromptTemplateSaveDTO;
import com.hfusionhub.entity.PromptTemplate;

import java.util.List;

public interface PromptTemplateService {
    List<PromptTemplateInfoDTO> listMine();
    PromptTemplateInfoDTO create(PromptTemplateSaveDTO dto);
    PromptTemplateInfoDTO update(Long id, PromptTemplateSaveDTO dto);
    PromptTemplateInfoDTO publish(Long id);
    PromptTemplateInfoDTO unpublish(Long id);
    void delete(Long id);
    PromptTemplate getPublishedOwned(Long id, Long userId);
}
