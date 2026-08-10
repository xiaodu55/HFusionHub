# ADR-006: 引用忠实度度量口径修正（自适应引用窗口 + 精确率/召回率双报）

- 状态：已采纳（2026-09-05）
- 关联：迭代优化方案 A 线 A1；`docs/CI_GATES.md` §评测门禁；
  留档 `python-ai/evaluation/reports/offline_metric_recalibration_20260905.md`
- 前情：本 ADR 是 ADR 清局的第一篇（001–005 为双语言 CQRS 边界、Milvus 选型、
  HMAC 回调、租户行级隔离、插件沙箱，待补写）

## 背景

离线评测轨的引用忠实度（citation_faithfulness）长期停在 **0.355**，与引用准确率
**0.947** 形成剪刀差。施工前的数据侦查推翻了最初假设：

1. **期望证据集规模**：主套件 220 条用例中 `expected_chunk_ids` 分布为
   {0 块: 31, 1 块: 158, 2 块: 31}——期望集**从未超过 2 块**，而引用窗口固定取
   检索 top-3。"窗口小于期望证据集"的假设不成立，方向恰好相反。
2. **结构性上限**：精确率口径 faithful = |E∩C|/|C|。当 |E|=1、|C|=3 时，即使
   检索把唯一期望块排到第 1 位，分数也只有 1/3。套件整体天花板
   ≈ (158×⅓ + 31×⅔) / 189 ≈ **0.388**——实测 0.355 已贴近上限。旧指标测的
   不是检索质量，而是"固定窗口 vs 期望集"的几何关系。
3. **纯精确率的盲区**：|E∩C|/|C| 对"漏引期望证据"不敏感，套件缺一个召回方向
   的引用指标。
4. **refusal 计分缺口**：`category=refusal` 的 25 条超纲用例注释明确"必须拒答"，
   但 `refusal` 字段漏标为 `none`，runtime 轨的 `refusal_correctness` 从未统计
   它们；离线轨则为 55 条 refusal=required 用例全部报 null。

## 备选方案

| 方案 | 实测（189 条含期望用例） | 结论 |
|------|------------------------|------|
| A. 引用窗口 top-3 → top-5（原方案设想） | F1 0.50 → **0.35**，P 0.35 → 0.22 | **否决**：窗口更偏大，恶化 |
| B. 保持固定窗口，只加召回率双报 | F1 天花板仍 ≈ 0.55 | 否决：天花板问题不解决 |
| C. 相关性自适应引用窗口 + P/R/F1 三报 | P 0.70 / R 0.89 / F1 0.74 | **采纳** |
| D. 离线轨用检索分数做拒答代理评分 | top1 绝对分不可分（超纲 med 8.6 vs 正常 min 6.4）；相对特征（分差/覆盖率/块数）均有重叠 | **否决**：拒答是生成层行为，密闭轨无法确定性评分，诚实报 N/A |

## 决策

1. **自适应引用窗口**（`eval_baseline.select_cited_chunks`）：模拟抽取式答案的
   引用行为——`score ≥ 0.5 × 首块分数` 的块才算被引用，`--citation-top-k`
   （默认 3→5）只作硬上限。检索歧义小时窗口收缩到 1–2 块，分数扁平时扩张到
   上限；窗口大小本身成为检索质量的信号，A2 的重排优化因此能被指标观察到。
2. **精确率/召回率/F1 三报**：`citation_faithfulness`（精确率）保留原键名兼容
   门禁；新增 `citation_recall`（|E∩C|/|E|）与 `citation_f1`（调和平均，跨套件
   主指标）；runtime 轨自动继承双报（其精确率为 key-facts 语义级，F1 仅作参考）。
3. **refusal 计分修正**：25 条超纲用例字段修正为 `refusal=required`（suite
   1.0.0 → 1.1.0），runtime 轨拒答计分覆盖 55 → 80 条；`build_suite.py` 增加类别
   契约校验（category=refusal 必须 refusal=required）防回归。离线轨
   `refusal_correctness` 保持 N/A 并注明原因（方案 D 的实测否决记录在此）。
4. **门禁与基线**：CI 主套件门禁显式加 `--minimum-citation-recall 0.85
   --minimum-citation-f1 0.70`；4 套基线随口径一并重冻结（`--update-baseline`）。
5. **顺手修复**：`eval_offline.py` 的 `--min-score` 此前传给了 `SyntheticRouter`
   而实际过滤发生在 `SyntheticIndex`——接线修正并把默认值从 1.0 改为 0.0
   （BM25 原始分未归一化，1.0 底线会误杀 5 条用例的期望块）；CI 4 处
   `from app.core.rag.eval_baseline import ...` 指向不存在的模块，修正为
   `scripts/eval_baseline.py`（CI 恢复时不再红灯）。

## 后果

**数字迁移**（主套件 189 条含期望证据用例；完整复现命令与对照见
`python-ai/evaluation/reports/offline_metric_recalibration_20260905.md`，该目录
为本地留档不入库）：

| 策略 | 精确率 P | 召回率 R | F1 | 引用准确率 |
|------|---------|---------|------|-----------|
| fixed top-3（旧口径） | 0.3545 | 0.9233 | 0.5037 | 0.9471 |
| fixed top-5（方案 A，否决） | 0.2169 | 0.9365 | 0.3474 | 0.9524 |
| **adaptive ratio=0.5（采纳）** | **0.7015** | **0.8942** | **0.7390** | **0.9418** |
| adaptive ratio=0.7（对照） | 0.7972 | 0.8545 | 0.7982 | 0.9101 |

> ratio=0.5 为"相关性达到首块一半即视为引用"的原则性默认，非套件最大值；
> ratio 越高 F1 越高但引用准确率下滑越快。Recall@5=0.9318 / nDCG@10=0.9029
> 在所有策略下不变（检索未动）。

**正向**：指标恢复可解释性；漏引开始被惩罚；A2 的重排优化与 A3 的生成侧
引用约束能被新口径观察到。

**必须声明的边界**：本次检索与生成**均未改动**，数字变化全部来自度量修正，
不得作为系统改进宣称。

**代价**：旧基线全部作废重冻结（suite sha + 指标语义双变化，suite 1.0.0→1.1.0）；
新旧口径数字不可直接对比，跨版本对比以 F1 为准并注明口径；若未来更换评分器
（BM25 → 向量/重排），ratio=0.5 需按同样的敏感度标定方法重新校准。

**下一步**（A3/A4，在新口径上继续）：生成侧逐论断引用约束把 cited 集从
"检索模拟"换成"答案实际标注"，让离线轨真正量到生成质量。

## 增补（A2 · 2026-09-05）：压缩阶段纳入度量 + query 信号

**度量扩展**：引用模拟从"检索可见"升级为"生成可见"——合并上下文按生产
`react._safe_compress`（target_ratio=0.6）重放抽取式压缩，句子全被压掉的
chunk 不可引用（`eval_baseline.compression_surviving_chunks`，与生产共用
`rank_sentences` 打分实现，口径不漂移）。

**生产修复**：压缩评分原四项权重（事实密度 0.50/长度/位置/关键词）全部与
问题无关；新增 query 重叠项（0.40/0.30/0.10/0.10/0.10，无 query 回退旧行为），
`react` 全部 4 处调用点透传 query，`ContextCompressor` 缓存键纳入 query
（此前不同问题互串缓存）。分词器抽至 `app/core/rag/tokenization.py` 共用。

**实测结论（三阶段对照见
`python-ai/evaluation/reports/offline_a2_compression_aware_20260905.md`）**：
期望证据块压缩存活率 99.51% → 100%（1 条边缘 case），修复后引用召回回到
0.8942（盲区 0.8889），F1 0.7427 → 0.7404（-0.002，噪声块存活摊薄精确率）。
**当前合成套件上压缩不是忠实度瓶颈**——模板化文档事实密度均匀；修复价值
在事实密度不均的真实 KB（机制由确定性翻转单测锁定）。忠实度的真实杠杆在
生成侧引用约束（A3）。

## 增补（A3 · 2026-09-05）：生成侧逐论断引用约束 + 答案标注引用接入度量

**生产侧**：
- `ExtractiveCompressionStrategy.compress_numbered_blocks`：**保溯源压缩**——
  对 `[n]` 编号块上下文在合并文本上全局选句（与普通压缩同一评分与预算公式），
  重建时按块归属拼回，只保留至少一句存活的块；编号 `n` 与 `sources[n-1]`
  的对应关系因此贯穿压缩全程。
- `_build_rag_prompt`：新增逐论断引用格式约束（每个论断末尾标注 `[n]`，
  多资料 `[1][3]`，禁止标注不存在的编号）。
- 答案解析：`_parse_cited_chunk_ids` 把答案中的 `[n]` 映射回来源 chunk_id
  （越界/不可见块忽略），随 `AgentResponse.cited_chunk_ids` →
  `ChatResponse.cited_chunk_ids` 透出；流式路径在 sources 事件携带同名字段；
  groundedness 重试用未压缩全文时可见块恢复为全集。
- 分解/非分解两条流式检索路径统一走 `_format_numbered_context` 编号格式。

**评测侧**：`eval_runtime.parse_chat_response` 的 cited 集从"检索到的文档"
改为"答案实际标注的引用"（响应 `cited_chunk_ids` → 文档名；未标注时回退
检索集保持旧行为），key-facts 忠实度同步按标注引用评估——runtime 轨从此
量到生成质量而非检索可见性。离线轨引用模拟改用与生产**同一份**
`compress_numbered_blocks`（构造编号文本重放），彻底消除口径漂移；
4 套基线随统一实现重冻结（主套件 F1 0.7404→0.7409，±0.0005 级）。

**边界**：runtime 轨的前后对比数字（答案标注率、标注引用的忠实度）需真实
服务实测，待 eval-nightly / 本地全栈运行采集；本增补的机制正确性由
11 个新单测（编号格式化/标注解析/越界与不可见忽略/保溯源翻转/契约回退）锁定。

**下一步**（A4）：证据门接上 `routing.confidence_threshold` 与
`ReflectionConfig.confidence_threshold` 两个死配置；修 groundedness 守卫
两个洞（`was_compressed=False` 不触发、判据为固定文案匹配而非分数）。

## 增补（A4 · 2026-09-05）：证据门 + groundedness 守卫修洞——A 线收官

**证据门（`routing.confidence_threshold` 首个真实消费方）**：run() 与
run_stream() 在检索之后、生成之前增加判定——检索最高融合分（RRF 归一化
0-1，顶块=跨通道一致性）低于阈值（默认 0.7，`RAG_ROUTING_CONFIDENCE_
THRESHOLD` 可调）时走现成 `insufficient_evidence` 通道拒答，不再让模型
对着弱证据硬编。有非检索工具可用时让位给 ReAct 循环（与空上下文分支
同一策略）。

**groundedness 守卫修两洞**：
1. **`was_compressed=False` 不触发**——短上下文（未压缩）路径的"无依据"
   答案此前直接以 completed 放行。现：未压缩时无更强上下文可重试，
   直接走 insufficient_evidence（流式按 content_reset 替换协议改发拒答）；
   压缩过则保留原重试链路。
2. **判据从固定文案改为"文案 OR 分数"**——`_answer_support_score` 计算
   答案实质句对上下文的最大词元覆盖率（跳过 <10 字短句，防误杀"是的。"
   类应答），全部实质句支持度低于 `ReflectionConfig.confidence_threshold`
   （默认 0.6，新增 `RAG_REFLECTION_CONFIDENCE_THRESHOLD` env）即判无依据，
   抓住纯文案匹配抓不住的幻觉。两个"死配置"至此全部接入消费方。

**校准边界（红线）**：门阈值 0.7 / 支持分阈值 0.6 的"误杀率/漏答率"需要
runtime 轨真实流量校准（refusal_correctness 与 recall 双达标验收依赖
eval-nightly 实测）；本批交付的是机制与单测（+13 个），数字回填待
eval-nightly 恢复（TODO P1）。

**A 线总账**：忠实度度量从"结构性缺陷指标"（0.355，天花板 0.39）重建为
P/R/F1 双报 + 压缩感知 + 答案标注引用（F1=0.741，suite 1.1.0）；生成侧
新增逐论断引用约束与证据门，"答不答"与"答了有没有据"首次进入确定性门禁。

## 增补（runtime 首测 · 2026-09-05）：A 线机制的真实流量验证

播种环境（kb_id=101，10 篇合成文档，中文标题）+ DeepSeek-v4-flash 全栈实测，
220 用例 0 错误、越界检索 0（多租户隔离生效）：

- **引用忠实度 0.686（F1 0.679）**：按答案实际标注的引用评估（A3 生效），
  不再是检索可见性模拟。
- **拒答正确率 0.625 的分解**：注入类 25/25、超纲类 25/25 全部正确拒答；
  权限类 0/30 全部失败——播种 KB 无权限元数据、服务无访问控制层，
  权限拒答是 ACL 功能缺口（A 线范围外，列为后续工作），非拒答机制缺陷。
- **答案标注率约 50%（30 例样本）**：按类别抽查 cross_document 5/6、
  normal 6/6——标注遵循度因问题类型波动，长文档/多跳场景偏低，
  待定位（压缩后块号可见性 or 格式遵循），属提示工程优化点。
- **runtime 召回 0.653 vs 离线 0.932**：生产检索栈（向量+BM25 融合、
  真实 Milvus、QA 增强分块）与离线合成轨的固有意义差异，两轨各司其职。
- 工具成功率 0.05：chat 快路径（有检索结果即直答）不进入工具循环，
  工具类用例需要意图级路由——列为后续工作。
- P95 延迟 16.7s：DeepSeek 全链路（意图分类 + 生成 + 反思多次 LLM 调用），
  3s 门禁阈值按 staging 快模型设定，本机实测仅作基线留档。

runtime 基线已冻结（`evaluation/baseline/runtime_baseline.json`，suite 1.1.0），
后续回归以此对比。
