# ADR-005: 插件沙箱——纵深防御的分层隔离与信任链

- 状态：已采纳（插件体系 V25+ 演进，2026-09-08 补写）
- 关联：`python-ai/app/core/plugin/sandbox_runner.py`（子进程隔离）、
  `docker/plugin-runner/app.py`（:9100 隔离执行器）、
  `docs/PLUGIN_RUNNER_TLS.md`、`docs/PLUGIN_BUILTINS.md`、
  `.github/workflows/plugin-security.yml`、R15-1/6/7（沙箱修复批次）

## 背景

插件意味着运行**不受信任的第三方代码**，且插件可声明 HTTP 端点
（声明式工具）与文件产物——若与 AI 主进程同进程执行，恶意插件的
import 副作用、资源耗尽、内网访问、文件遍历都是单点失守。
需要回答：代码在哪执行、能碰什么网络/文件、产物存哪、谁签名可信任。

## 决策（纵深防御五层）

1. **子进程隔离**（`sandbox_runner.py`）：插件代码在 fork 子进程执行，
   父子经 stdin/stdout JSON-lines 管道通信——主进程零 sys.path 污染、
   零共享内存；子进程内 CPU/内存 `resource.setrlimit`（POSIX）或
   psutil（Windows）限制、网络经子进程内 monkey-patch 限制、
   文件系统走 allowed-path 校验、超时强杀；
2. **manifest 沙箱声明 default-deny**（R15-6 收口）：未声明 sandbox 段
   = 禁网 + 限写，不做"无声明即无限制"的 fail-open；Windows 下无法
   施加的资源限制显式 warning 而非静默跳过；
3. **独立执行器容器**（plugin-runner :9100 + dind）：插件执行与 AI 服务
   进程/容器双隔离；runner 对 Docker daemon 走 TLS（证书由
   `scripts/generate-runner-tls.sh` 生成，见 PLUGIN_RUNNER_TLS.md），
   引擎不可用时 `/health` 503 fail-closed；容器镜像按 digest 固定；
4. **产物存储按租户分桶**（R15-28）：插件工件写
   `hfusionhub-t<tenantId>` MinIO 租户桶，读取回退默认桶兼容旧对象；
5. **签名信任链 + CI 门禁**：`scripts/plugin-provision.sh` 生成平台
   签名私钥（不入库），`python-ai/plugins/trust/` 只存公钥信任策略；
   `plugin-security.yml` 对容器插件测试**任何 skip 即 fail**。

## 结果与测量

- R15-1（async 内同步起事件循环导致 container 模式静默不可用）、
  R15-7（runner 事件循环阻塞 + 结果解析 fail-open）两批修复后，
  bid_docx/bid_quote 等容器插件真实可达且结果解析 fail-closed；
- 声明式插件端点 SSRF 防护补齐私网/link-local 段与 DNS 解析校验
  （R15-19）。

## 后果与边界

- 子进程隔离是**纵深防御而非绝对边界**——文档明示 root/ptrace 级
  攻击者可绕过；更强隔离（独立 VM/Kata）明确不在当前投入范围；
- Windows 开发机部分资源限制天然不可用（显式告警），staging 真机
  演练（隔离 Docker/K8s runner）仍为待执行项（R15-30）；
- 内置 20+ 演示业务工具与 MCP 外部工具不走本沙箱，各自受
  策略审批/白名单约束（`docs/PLUGIN_BUILTINS.md`）。
