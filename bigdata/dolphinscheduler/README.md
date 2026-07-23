# HFusionData Analytics — DolphinScheduler(标准档)

## 部署

```bash
docker compose -f docker/docker-compose.analytics.yml --profile analytics --profile analytics-full up -d dolphinscheduler
```

- UI: http://localhost:12345/dolphinscheduler/ui(默认 admin / ***REMOVED-BY-REWRITE***)
- 元库: H2 mem(镜像默认)。**DS 容器重启会清空元数据** —— 重启后重跑一次
  引导脚本即可(约 30s 重建项目+工作流)。文件库与 3.2.1 的 MySQL 模式 DDL
  存在 schema 兼容问题(PUBLIC schema 缺失),故保持 mem 库。

## 首次准备(一次性)

worker 任务经 `docker exec analytics-spark` 提交,需要静态 docker CLI:

```bash
curl -L -x http://127.0.0.1:7890 -o /tmp/docker.tgz \
  https://download.docker.com/linux/static/stable/x86_64/docker-24.0.9.tgz
tar -xzf /tmp/docker.tgz -C /tmp docker
cp /tmp/docker bigdata/dolphinscheduler/docker   # 该二进制已 gitignore
```

compose 已将其挂载为 worker 内的 /usr/local/bin/docker。

## 流水线引导(幂等)

```bash
python bigdata/dolphinscheduler/bootstrap_dolphinscheduler.py --dt 2026-09-02
```

创建项目 HFusionData + 六任务工作流(full-import → dwd-transform →
dws-aggregate → quality-check[门禁,失败阻断下游] → ads-build → ch-sync),
自动发布并按 --dt 触发一次,轮询至终态。

## 踩坑记录(3.2.1 API 与文档差异)

1. API 基路径为 /dolphinscheduler(/ui 是前端静态资源,POST /ui/login 405)。
2. 全部写接口走**表单编码**(JSON body 被当作缺失 @RequestParam 拒绝)。
3. 认证为 sessionId 请求头(登录响应 data.sessionId)。
4. 启动路由为 `/executors/start-process-instance`(非文档的 /executors/start),
   且必须携带 scheduleTime / warningType / warningGroupId 等全量参数。
5. 任务定义 JSON 缺 `isCache` 字段会在 transformTask NPE
   (ProcessServiceImpl 1964 行 getIsCache().getCode())。
6. 宿主机 CPU 饱和会触发 master/worker 过载保护拒绝消费命令 —— 已在
   application.yaml 覆盖中关闭(仅 dev)。
