package com.hfusionhub.controller;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.KnowledgeBaseCreateDTO;
import com.hfusionhub.dto.KnowledgeBaseInfoDTO;
import com.hfusionhub.dto.KnowledgeBaseQueryDTO;
import com.hfusionhub.dto.KnowledgeBaseUpdateDTO;
import com.hfusionhub.service.KnowledgeBaseService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 知识库控制器
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/knowledge-base")
@RequiredArgsConstructor
@Tag(name = "知识库管理", description = "知识库的增删改查")
public class KnowledgeBaseController {

    private final KnowledgeBaseService knowledgeBaseService;

    /**
     * 创建知识库
     *
     * @param createDTO 创建请求
     * @return 知识库信息
     */
    @PostMapping
    @Operation(summary = "创建知识库", description = "创建一个新的知识库")
    public R<KnowledgeBaseInfoDTO> create(@Valid @RequestBody KnowledgeBaseCreateDTO createDTO) {
        KnowledgeBaseInfoDTO info = knowledgeBaseService.create(createDTO);
        return R.ok("创建成功", info);
    }

    /**
     * 更新知识库
     *
     * @param id        知识库ID
     * @param updateDTO 更新请求
     * @return 知识库信息
     */
    @PutMapping("/{id}")
    @Operation(summary = "更新知识库", description = "更新知识库信息")
    public R<KnowledgeBaseInfoDTO> update(@PathVariable Long id,
                                          @Valid @RequestBody KnowledgeBaseUpdateDTO updateDTO) {
        KnowledgeBaseInfoDTO info = knowledgeBaseService.update(id, updateDTO);
        return R.ok("更新成功", info);
    }

    /**
     * 删除知识库
     *
     * @param id 知识库ID
     * @return 结果
     */
    @DeleteMapping("/{id}")
    @Operation(summary = "删除知识库", description = "删除指定知识库")
    public R<Void> delete(@PathVariable Long id) {
        knowledgeBaseService.delete(id);
        return R.ok();
    }

    /**
     * 获取知识库详情
     *
     * @param id 知识库ID
     * @return 知识库信息
     */
    @GetMapping("/{id}")
    @Operation(summary = "获取知识库详情", description = "根据ID获取知识库详细信息")
    public R<KnowledgeBaseInfoDTO> getById(@PathVariable Long id) {
        KnowledgeBaseInfoDTO info = knowledgeBaseService.getById(id);
        return R.ok(info);
    }

    /**
     * 分页查询知识库列表
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    @GetMapping("/list")
    @Operation(summary = "分页查询知识库列表", description = "分页查询所有知识库")
    public R<PageResult<KnowledgeBaseInfoDTO>> list(KnowledgeBaseQueryDTO queryDTO) {
        PageResult<KnowledgeBaseInfoDTO> result = knowledgeBaseService.list(queryDTO);
        return R.ok(result);
    }

    /**
     * 获取当前用户的知识库列表
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    @GetMapping("/my")
    @Operation(summary = "获取我的知识库列表", description = "获取当前用户的知识库列表")
    public R<PageResult<KnowledgeBaseInfoDTO>> listByCurrentUser(KnowledgeBaseQueryDTO queryDTO) {
        PageResult<KnowledgeBaseInfoDTO> result = knowledgeBaseService.listByCurrentUser(queryDTO);
        return R.ok(result);
    }
}
