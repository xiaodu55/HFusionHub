package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.dto.RagIntentNodeCreateDTO;
import com.hfusionhub.dto.RagIntentNodeInfoDTO;
import com.hfusionhub.dto.RagIntentNodeQueryDTO;
import com.hfusionhub.dto.RagIntentNodeUpdateDTO;

import java.util.List;
import java.util.Map;

public interface RagIntentNodeService {

    RagIntentNodeInfoDTO create(RagIntentNodeCreateDTO dto);

    RagIntentNodeInfoDTO update(Long id, RagIntentNodeUpdateDTO dto);

    void delete(Long id);

    RagIntentNodeInfoDTO getById(Long id);

    PageResult<RagIntentNodeInfoDTO> list(RagIntentNodeQueryDTO queryDTO);

    List<RagIntentNodeInfoDTO> tree(Integer enabled);

    List<Map<String, Object>> routeCandidates();
}
