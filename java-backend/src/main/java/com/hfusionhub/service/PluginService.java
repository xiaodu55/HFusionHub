package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.entity.Plugin;

import java.math.BigDecimal;
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
     * 创建低代码插件及其声明式 HTTP GET 工具。
     */
    Plugin createDeclarative(Map<String, Object> manifest);

    /**
     * 上传 wheel 文件并安装插件
     */
    Plugin installWithWheel(Map<String, Object> manifest, byte[] wheelData, String wheelFilename);

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
     * 设置金丝雀流量权重
     */
    Plugin setCanary(String pluginId, BigDecimal weight);

    /**
     * 提合金丝雀为正式版本
     */
    Plugin promoteCanary(String pluginId);

    /**
     * 回滚到上一版本
     */
    Plugin rollback(String pluginId);

    /**
     * 导出审计日志
     */
    List<Map<String, Object>> exportAuditLogs(String pluginId, String format, int limit);

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

    /**
     * 获取插件的所有版本信息（用于金丝雀路由）
     */
    List<Map<String, Object>> getPluginVersions(Long pluginId);
}
