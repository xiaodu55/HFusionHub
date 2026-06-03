-- ============================================================
-- V73: 平台内建插件（P2-3）—— bid_docx / bid_quote 上架
--
-- 0) plugin.tenant_id 改为可空 —— V32 曾 MODIFY 为 NOT NULL（组织模型时代），
--    但平台级行（tenant_id NULL = 平台内建）与 bid_template / bid_subscription
--    （V67/V69，均 tenant_id 可空 = 平台级）同一模式；V73 前已把 plugin 表加入
--    TENANT_IGNORE_TABLES，服务层过滤平台+自有（见 MybatisPlusConfig + PluginServiceImpl）
-- 1) 两个插件进 plugin 表（tenant_id NULL = 平台内建）
-- 2) container_image 指向插件镜像（dev 由 scripts/plugin-provision.sh 构建并载入 dind）
-- 3) image_digest 留空 —— 环境相关（本地构建镜像的 config digest 每次环境不同），
--    由 scripts/plugin-provision.sh 按环境回填（UPDATE 本行 image_digest）
-- 4) manifest_hash / artifact_hash 留空 —— 种子非用户上传安装，供应链校验门槛在 image_digest
-- ============================================================

ALTER TABLE plugin MODIFY COLUMN tenant_id BIGINT DEFAULT NULL COMMENT '所属租户ID（NULL = 平台内建插件）';

INSERT INTO plugin (
    plugin_id, name, display_name, description, version, author, license,
    source, status, plugin_kind, sandbox_config, permissions, tool_specs_json,
    container_image, image_digest, tenant_id, enabled, installed_by, installed_at
) VALUES
-- ── bid_docx：标书 docx 导出 ─────────────────────────────────────────
('bid_docx@1.0.0', 'bid_docx', '标书 docx 导出',
 '标书 docx 导出插件：把已审批的标书分节草稿渲染为 .docx 投标文件（平台内建，容器沙箱执行）。',
 '1.0.0', 'HFusionHub Platform', 'Apache-2.0',
 'wheel', 'active', 'declarative',
 JSON_OBJECT(
     'network', JSON_OBJECT('allowed_domains', JSON_ARRAY(), 'blocked_domains', JSON_ARRAY(), 'timeout_seconds', 30),
     'filesystem', JSON_OBJECT('read_only_paths', JSON_ARRAY(), 'blocked_paths', JSON_ARRAY()),
     'resources', JSON_OBJECT('cpu_seconds', 10, 'memory_mb', 256),
     'runner', JSON_OBJECT('mode', 'container', 'fail_closed', TRUE)),
 JSON_ARRAY('bid:draft:read'),
 JSON_ARRAY(
     JSON_OBJECT(
         'name', 'bid_export_docx',
         'description', '将标书分节草稿渲染为 .docx 投标文件，返回 base64 字节与文件元信息（filename/size_bytes/chars）。输入 sections 为 [{key,title,content}] 分节数组。',
         'read_only', FALSE,
         'parameters', JSON_OBJECT(
             'type', 'object',
             'properties', JSON_OBJECT(
                 'sections', JSON_OBJECT('type', 'array',
                     'items', JSON_OBJECT('type', 'object',
                         'properties', JSON_OBJECT(
                             'key', JSON_OBJECT('type', 'string', 'description', '分节标识'),
                             'title', JSON_OBJECT('type', 'string', 'description', '分节标题'),
                             'content', JSON_OBJECT('type', 'string', 'description', '分节正文'))),
                     'description', '标书分节数组'),
                 'title', JSON_OBJECT('type', 'string', 'description', '投标文件标题'),
                 'meta', JSON_OBJECT('type', 'object', 'description', '封面元信息',
                     'properties', JSON_OBJECT(
                         'tender_number', JSON_OBJECT('type', 'string'),
                         'project_title', JSON_OBJECT('type', 'string'),
                         'bidder_name', JSON_OBJECT('type', 'string'),
                         'deadline', JSON_OBJECT('type', 'string'),
                         'budget', JSON_OBJECT('type', 'string')))),
             'required', JSON_ARRAY('sections')))),
 'hfusionhub-plugin-bid-docx:1.0.0', NULL, NULL, 1, NULL, NULL),

-- ── bid_quote：投标报价表导出 ───────────────────────────────────────
('bid_quote@1.0.0', 'bid_quote', '投标报价表导出',
 '投标报价表导出插件：把报价明细渲染为 .xlsx 报价表，内嵌评分点计算（复用 bid_calc_scoring 确定性逻辑）（平台内建，容器沙箱执行）。',
 '1.0.0', 'HFusionHub Platform', 'Apache-2.0',
 'wheel', 'active', 'declarative',
 JSON_OBJECT(
     'network', JSON_OBJECT('allowed_domains', JSON_ARRAY(), 'blocked_domains', JSON_ARRAY(), 'timeout_seconds', 30),
     'filesystem', JSON_OBJECT('read_only_paths', JSON_ARRAY(), 'blocked_paths', JSON_ARRAY()),
     'resources', JSON_OBJECT('cpu_seconds', 10, 'memory_mb', 256),
     'runner', JSON_OBJECT('mode', 'container', 'fail_closed', TRUE)),
 JSON_ARRAY('bid:quote:write'),
 JSON_ARRAY(
     JSON_OBJECT(
         'name', 'bid_export_quote',
         'description', '将投标报价明细渲染为 .xlsx 报价表，返回 base64 字节与文件元信息（filename/size_bytes/totals/lines/scoring）。输入 items 为 [{name,spec,unit,qty,unit_price,tax_rate}] 报价明细数组；可选 points/scores 内嵌评分点计算。',
         'read_only', FALSE,
         'parameters', JSON_OBJECT(
             'type', 'object',
             'properties', JSON_OBJECT(
                 'items', JSON_OBJECT('type', 'array',
                     'items', JSON_OBJECT('type', 'object',
                         'properties', JSON_OBJECT(
                             'name', JSON_OBJECT('type', 'string', 'description', '品名/条目名'),
                             'spec', JSON_OBJECT('type', 'string', 'description', '规格型号'),
                             'unit', JSON_OBJECT('type', 'string', 'description', '单位'),
                             'qty', JSON_OBJECT('type', 'number', 'description', '数量'),
                             'unit_price', JSON_OBJECT('type', 'number', 'description', '单价（未税）'),
                             'tax_rate', JSON_OBJECT('type', 'number', 'description', '税率（0.06 = 6%）')),
                         'required', JSON_ARRAY('name', 'qty', 'unit_price')),
                     'description', '报价明细数组'),
                 'meta', JSON_OBJECT('type', 'object', 'description', '报价元信息',
                     'properties', JSON_OBJECT(
                         'tender_number', JSON_OBJECT('type', 'string'),
                         'project_title', JSON_OBJECT('type', 'string'),
                         'bidder_name', JSON_OBJECT('type', 'string'),
                         'deadline', JSON_OBJECT('type', 'string'),
                         'currency', JSON_OBJECT('type', 'string'))),
                 'points', JSON_OBJECT('type', 'array', 'description', '评分点（可选，内嵌评分计算）',
                     'items', JSON_OBJECT('type', 'object',
                         'properties', JSON_OBJECT(
                             'name', JSON_OBJECT('type', 'string'),
                             'max_score', JSON_OBJECT('type', 'number'),
                             'weight', JSON_OBJECT('type', 'number')),
                         'required', JSON_ARRAY('name', 'max_score'))),
                 'scores', JSON_OBJECT('type', 'array', 'description', '实得分（可选）',
                     'items', JSON_OBJECT('type', 'object',
                         'properties', JSON_OBJECT(
                             'name', JSON_OBJECT('type', 'string'),
                             'score', JSON_OBJECT('type', 'number')),
                         'required', JSON_ARRAY('name', 'score')))),
             'required', JSON_ARRAY('items')))),
 'hfusionhub-plugin-bid-quote:1.0.0', NULL, NULL, 1, NULL, NULL);
