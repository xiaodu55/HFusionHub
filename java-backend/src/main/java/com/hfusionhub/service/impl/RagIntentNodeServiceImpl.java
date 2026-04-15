package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.RagIntentNodeCreateDTO;
import com.hfusionhub.dto.RagIntentNodeInfoDTO;
import com.hfusionhub.dto.RagIntentNodeQueryDTO;
import com.hfusionhub.dto.RagIntentNodeUpdateDTO;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.RagIntentNode;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.RagIntentNodeMapper;
import com.hfusionhub.service.RagIntentNodeService;
import com.hfusionhub.tenant.TenantContext;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class RagIntentNodeServiceImpl implements RagIntentNodeService {

    private static final String LEVEL_DOMAIN = "DOMAIN";
    private static final String LEVEL_CATEGORY = "CATEGORY";
    private static final String LEVEL_TOPIC = "TOPIC";
    private static final String KIND_KB = "KB";
    private static final String KIND_SYSTEM = "SYSTEM";
    private static final String KIND_MCP = "MCP";

    private final RagIntentNodeMapper ragIntentNodeMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final JwtUtils jwtUtils;

    @Override
    @Transactional
    public RagIntentNodeInfoDTO create(RagIntentNodeCreateDTO dto) {
        Long userId = jwtUtils.getCurrentUserId();
        assertUniqueCode(userId, dto.getIntentCode(), null);

        RagIntentNode parent = loadAndValidateParent(userId, dto.getParentId(), dto.getLevel());
        validateRouteTarget(userId, dto.getLevel(), dto.getKind(), dto.getKnowledgeBaseId(), dto.getMcpToolId());

        RagIntentNode node = new RagIntentNode();
        node.setUserId(userId);
        node.setTenantId(TenantContext.getTenantId() == null ? 1L : TenantContext.getTenantId());
        node.setParentId(parent == null ? null : parent.getId());
        node.setIntentCode(dto.getIntentCode().trim());
        node.setName(dto.getName().trim());
        node.setDescription(trimToNull(dto.getDescription()));
        node.setLevel(dto.getLevel());
        node.setKind(dto.getKind());
        node.setKnowledgeBaseId(dto.getKnowledgeBaseId());
        node.setMcpToolId(dto.getMcpToolId());
        node.setTopK(defaultIfNull(dto.getTopK(), 5));
        node.setRouteConfig(trimToNull(dto.getRouteConfig()));
        node.setEnabled(defaultIfNull(dto.getEnabled(), 1));
        node.setSortOrder(defaultIfNull(dto.getSortOrder(), 0));
        ragIntentNodeMapper.insert(node);
        return convert(node, loadKnowledgeBaseNames(List.of(node)));
    }

    @Override
    @Transactional
    public RagIntentNodeInfoDTO update(Long id, RagIntentNodeUpdateDTO dto) {
        Long userId = jwtUtils.getCurrentUserId();
        RagIntentNode node = requireOwnedNode(userId, id);

        String nextLevel = dto.getLevel() != null ? dto.getLevel() : node.getLevel();
        String nextKind = dto.getKind() != null ? dto.getKind() : node.getKind();
        Long nextParentId = dto.getParentId() != null ? dto.getParentId() : node.getParentId();
        Long nextKnowledgeBaseId = dto.getKnowledgeBaseId() != null ? dto.getKnowledgeBaseId() : node.getKnowledgeBaseId();
        Long nextMcpToolId = dto.getMcpToolId() != null ? dto.getMcpToolId() : node.getMcpToolId();

        if (dto.getIntentCode() != null && !dto.getIntentCode().equals(node.getIntentCode())) {
            assertUniqueCode(userId, dto.getIntentCode(), id);
            node.setIntentCode(dto.getIntentCode().trim());
        }
        if (nextParentId != null && Objects.equals(nextParentId, id)) {
            throw new BusinessException("Intent node cannot be its own parent");
        }
        if (nextParentId != null && isDescendant(userId, id, nextParentId)) {
            throw new BusinessException("Intent node cannot be moved under its descendant");
        }
        loadAndValidateParent(userId, nextParentId, nextLevel);
        validateRouteTarget(userId, nextLevel, nextKind, nextKnowledgeBaseId, nextMcpToolId);

        if (dto.getParentId() != null || (dto.getLevel() != null && LEVEL_DOMAIN.equals(dto.getLevel()))) {
            node.setParentId(LEVEL_DOMAIN.equals(nextLevel) ? null : nextParentId);
        }
        if (dto.getName() != null) {
            node.setName(dto.getName().trim());
        }
        if (dto.getDescription() != null) {
            node.setDescription(trimToNull(dto.getDescription()));
        }
        if (dto.getLevel() != null) {
            node.setLevel(dto.getLevel());
        }
        if (dto.getKind() != null) {
            node.setKind(dto.getKind());
        }
        if (dto.getKnowledgeBaseId() != null || KIND_SYSTEM.equals(nextKind)) {
            node.setKnowledgeBaseId(KIND_SYSTEM.equals(nextKind) ? null : dto.getKnowledgeBaseId());
        }
        if (dto.getMcpToolId() != null || !KIND_MCP.equals(nextKind)) {
            node.setMcpToolId(KIND_MCP.equals(nextKind) ? dto.getMcpToolId() : null);
        }
        if (dto.getTopK() != null) {
            node.setTopK(dto.getTopK());
        }
        if (dto.getRouteConfig() != null) {
            node.setRouteConfig(trimToNull(dto.getRouteConfig()));
        }
        if (dto.getEnabled() != null) {
            node.setEnabled(dto.getEnabled());
        }
        if (dto.getSortOrder() != null) {
            node.setSortOrder(dto.getSortOrder());
        }
        ragIntentNodeMapper.updateById(node);
        return convert(node, loadKnowledgeBaseNames(List.of(node)));
    }

    @Override
    @Transactional
    public void delete(Long id) {
        Long userId = jwtUtils.getCurrentUserId();
        requireOwnedNode(userId, id);
        List<RagIntentNode> all = listOwnedNodes(userId, null);
        Map<Long, List<RagIntentNode>> byParent = all.stream()
                .collect(Collectors.groupingBy(node -> node.getParentId() == null ? 0L : node.getParentId()));
        List<Long> ids = collectSubtreeIds(id, byParent);
        ragIntentNodeMapper.deleteBatchIds(ids);
    }

    @Override
    public RagIntentNodeInfoDTO getById(Long id) {
        Long userId = jwtUtils.getCurrentUserId();
        RagIntentNode node = requireOwnedNode(userId, id);
        return convert(node, loadKnowledgeBaseNames(List.of(node)));
    }

    @Override
    public PageResult<RagIntentNodeInfoDTO> list(RagIntentNodeQueryDTO queryDTO) {
        queryDTO.validate();
        Long userId = jwtUtils.getCurrentUserId();
        Page<RagIntentNode> page = new Page<>(queryDTO.getPage(), queryDTO.getPageSize());
        LambdaQueryWrapper<RagIntentNode> wrapper = baseQuery(userId, queryDTO.getEnabled())
                .eq(queryDTO.getParentId() != null, RagIntentNode::getParentId, queryDTO.getParentId())
                .eq(StringUtils.hasText(queryDTO.getLevel()), RagIntentNode::getLevel, queryDTO.getLevel())
                .eq(StringUtils.hasText(queryDTO.getKind()), RagIntentNode::getKind, queryDTO.getKind());
        if (StringUtils.hasText(queryDTO.getKeyword())) {
            String keyword = queryDTO.getKeyword().trim();
            wrapper.and(w -> w.like(RagIntentNode::getName, keyword)
                    .or()
                    .like(RagIntentNode::getIntentCode, keyword));
        }
        wrapper.orderByAsc(RagIntentNode::getSortOrder).orderByDesc(RagIntentNode::getUpdatedAt);
        Page<RagIntentNode> result = ragIntentNodeMapper.selectPage(page, wrapper);
        Map<Long, String> kbNames = loadKnowledgeBaseNames(result.getRecords());
        List<RagIntentNodeInfoDTO> records = result.getRecords().stream()
                .map(node -> convert(node, kbNames))
                .toList();
        return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), result.getTotal(), records);
    }

    @Override
    public List<RagIntentNodeInfoDTO> tree(Integer enabled) {
        Long userId = jwtUtils.getCurrentUserId();
        List<RagIntentNode> nodes = listOwnedNodes(userId, enabled);
        Map<Long, String> kbNames = loadKnowledgeBaseNames(nodes);
        Map<Long, RagIntentNodeInfoDTO> dtoById = new HashMap<>();
        for (RagIntentNode node : nodes) {
            dtoById.put(node.getId(), convert(node, kbNames));
        }
        List<RagIntentNodeInfoDTO> roots = new ArrayList<>();
        for (RagIntentNode node : nodes) {
            RagIntentNodeInfoDTO dto = dtoById.get(node.getId());
            if (node.getParentId() == null || !dtoById.containsKey(node.getParentId())) {
                roots.add(dto);
            } else {
                dtoById.get(node.getParentId()).getChildren().add(dto);
            }
        }
        return roots;
    }

    @Override
    public List<Map<String, Object>> routeCandidates() {
        List<Map<String, Object>> candidates = new ArrayList<>();
        for (RagIntentNodeInfoDTO root : tree(1)) {
            collectRouteCandidates(root, new ArrayList<>(), candidates);
        }
        return candidates;
    }

    private void collectRouteCandidates(
            RagIntentNodeInfoDTO node,
            List<String> parentPath,
            List<Map<String, Object>> candidates) {
        List<String> path = new ArrayList<>(parentPath);
        path.add(node.getName());
        if (LEVEL_TOPIC.equals(node.getLevel())) {
            Map<String, Object> candidate = new HashMap<>();
            candidate.put("id", node.getId());
            candidate.put("intent_code", node.getIntentCode());
            candidate.put("name", node.getName());
            candidate.put("description", node.getDescription());
            candidate.put("kind", node.getKind());
            candidate.put("knowledge_base_id", node.getKnowledgeBaseId());
            candidate.put("mcp_tool_id", node.getMcpToolId());
            candidate.put("top_k", node.getTopK());
            candidate.put("route_config", node.getRouteConfig());
            candidate.put("path", String.join("/", path));
            candidates.add(candidate);
        }
        for (RagIntentNodeInfoDTO child : node.getChildren()) {
            collectRouteCandidates(child, path, candidates);
        }
    }

    private LambdaQueryWrapper<RagIntentNode> baseQuery(Long userId, Integer enabled) {
        return new LambdaQueryWrapper<RagIntentNode>()
                .eq(RagIntentNode::getUserId, userId)
                .eq(enabled != null, RagIntentNode::getEnabled, enabled);
    }

    private List<RagIntentNode> listOwnedNodes(Long userId, Integer enabled) {
        return ragIntentNodeMapper.selectList(baseQuery(userId, enabled)
                .orderByAsc(RagIntentNode::getSortOrder)
                .orderByAsc(RagIntentNode::getId));
    }

    private RagIntentNode requireOwnedNode(Long userId, Long id) {
        RagIntentNode node = ragIntentNodeMapper.selectById(id);
        if (node == null || !Objects.equals(node.getUserId(), userId)) {
            throw new BusinessException("Intent node not found");
        }
        return node;
    }

    private void assertUniqueCode(Long userId, String intentCode, Long excludeId) {
        LambdaQueryWrapper<RagIntentNode> wrapper = new LambdaQueryWrapper<RagIntentNode>()
                .eq(RagIntentNode::getUserId, userId)
                .eq(RagIntentNode::getIntentCode, intentCode.trim())
                .ne(excludeId != null, RagIntentNode::getId, excludeId);
        if (ragIntentNodeMapper.selectCount(wrapper) > 0) {
            throw new BusinessException("Intent code already exists");
        }
    }

    private RagIntentNode loadAndValidateParent(Long userId, Long parentId, String level) {
        if (LEVEL_DOMAIN.equals(level)) {
            if (parentId != null) {
                throw new BusinessException("DOMAIN nodes cannot have a parent");
            }
            return null;
        }
        if (parentId == null) {
            throw new BusinessException(level + " nodes require a parent");
        }
        RagIntentNode parent = requireOwnedNode(userId, parentId);
        if (LEVEL_CATEGORY.equals(level) && !LEVEL_DOMAIN.equals(parent.getLevel())) {
            throw new BusinessException("CATEGORY parent must be DOMAIN");
        }
        if (LEVEL_TOPIC.equals(level) && !LEVEL_CATEGORY.equals(parent.getLevel())) {
            throw new BusinessException("TOPIC parent must be CATEGORY");
        }
        return parent;
    }

    private void validateRouteTarget(Long userId, String level, String kind, Long knowledgeBaseId, Long mcpToolId) {
        if (KIND_KB.equals(kind) && knowledgeBaseId != null) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(knowledgeBaseId);
            if (kb == null || !Objects.equals(kb.getUserId(), userId)) {
                throw new BusinessException("Knowledge base not found");
            }
        }
        if (LEVEL_TOPIC.equals(level) && KIND_KB.equals(kind) && knowledgeBaseId == null) {
            throw new BusinessException("TOPIC KB intent requires a knowledge base");
        }
        if (LEVEL_TOPIC.equals(level) && KIND_MCP.equals(kind) && mcpToolId == null) {
            throw new BusinessException("TOPIC MCP intent requires a tool ID");
        }
    }

    private boolean isDescendant(Long userId, Long ancestorId, Long candidateId) {
        List<RagIntentNode> all = listOwnedNodes(userId, null);
        Map<Long, Long> parentById = all.stream()
                .collect(Collectors.toMap(RagIntentNode::getId, RagIntentNode::getParentId));
        Long cursor = candidateId;
        Set<Long> visited = new HashSet<>();
        while (cursor != null && visited.add(cursor)) {
            if (Objects.equals(cursor, ancestorId)) {
                return true;
            }
            cursor = parentById.get(cursor);
        }
        return false;
    }

    private List<Long> collectSubtreeIds(Long rootId, Map<Long, List<RagIntentNode>> byParent) {
        List<Long> ids = new ArrayList<>();
        ArrayDeque<Long> queue = new ArrayDeque<>();
        queue.add(rootId);
        while (!queue.isEmpty()) {
            Long id = queue.removeFirst();
            ids.add(id);
            for (RagIntentNode child : byParent.getOrDefault(id, List.of())) {
                queue.add(child.getId());
            }
        }
        return ids;
    }

    private Map<Long, String> loadKnowledgeBaseNames(List<RagIntentNode> nodes) {
        Set<Long> kbIds = nodes.stream()
                .map(RagIntentNode::getKnowledgeBaseId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());
        if (kbIds.isEmpty()) {
            return Map.of();
        }
        return knowledgeBaseMapper.selectBatchIds(kbIds).stream()
                .collect(Collectors.toMap(KnowledgeBase::getId, KnowledgeBase::getName));
    }

    private RagIntentNodeInfoDTO convert(RagIntentNode node, Map<Long, String> kbNames) {
        return RagIntentNodeInfoDTO.builder()
                .id(node.getId())
                .userId(node.getUserId())
                .parentId(node.getParentId())
                .intentCode(node.getIntentCode())
                .name(node.getName())
                .description(node.getDescription())
                .level(node.getLevel())
                .kind(node.getKind())
                .knowledgeBaseId(node.getKnowledgeBaseId())
                .knowledgeBaseName(node.getKnowledgeBaseId() == null
                        ? null
                        : kbNames.get(node.getKnowledgeBaseId()))
                .mcpToolId(node.getMcpToolId())
                .topK(node.getTopK())
                .routeConfig(node.getRouteConfig())
                .enabled(node.getEnabled())
                .sortOrder(node.getSortOrder())
                .createdAt(node.getCreatedAt())
                .updatedAt(node.getUpdatedAt())
                .build();
    }

    private static String trimToNull(String value) {
        if (!StringUtils.hasText(value)) {
            return null;
        }
        return value.trim();
    }

    private static Integer defaultIfNull(Integer value, Integer fallback) {
        return value == null ? fallback : value;
    }
}
