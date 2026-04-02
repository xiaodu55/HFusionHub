package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.entity.Plugin;

import java.util.List;
import java.util.Map;

/**
 * 工具插件服务接口
 *
 * @author HFusionHub Team
 */
public interface PluginService {

    /**
     * 安装插件（校验 manifest → 写入 registry → 记录依赖 → 审计日志）
     */
    Plugin install(Map<String, Object> manifest);

    /**
     * 根据插件ID获取详情
     */
    Plugin getByPluginId(String pluginId);

    /**
     * 分页查询已安装插件
     */
    PageResult<Plugin> list(int page, int pageSize, String status);

    /**
     * 查询所有已启用的插件
     */
    List<Plugin> listEnabled();

    /**
     * 启用插件
     */
    Plugin enable(String pluginId);

    /**
     * 禁用插件
     */
    Plugin disable(String pluginId, String reason);

    /**
     * 更新插件状态
     */
    Plugin updateStatus(String pluginId, String status);

    /**
     * 卸载插件（逻辑删除 + 审计日志）
     */
    void uninstall(String pluginId, String reason);

    /**
     * 获取插件安装者的已安装插件数
     */
    int countByUserId(Long userId);

    /**
     * 获取插件审计日志
     */
    List<Map<String, Object>> getAuditLogs(Long pluginId, int limit);

    /**
     * 为 Python AI 返回插件的 ToolSpec 列表（含 permissions）
     */
    List<Map<String, Object>> getPluginToolSpecs();
}
