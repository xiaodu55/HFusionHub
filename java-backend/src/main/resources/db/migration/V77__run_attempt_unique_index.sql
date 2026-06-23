-- V77: S4 并发守卫 — agent_run (task_id, attempt_number) 唯一约束
-- 背景（docs/REPAIR_ROADMAP.md S4）：enqueueRun/retryTask/requeueTask 的
-- 状态检查→attempt 计算→INSERT 非原子，并发重试/恢复会插入两个相同
-- attempt 的 PENDING run，导致重复执行与重复计费。唯一索引使重复插入
-- 在 DB 层失败，代码层捕获 DuplicateKeyException 转为友好冲突错误。

-- 先清理历史双重入队产生的重复行（同一 task_id + attempt_number 保留最早一条）
DELETE FROM `agent_run`
WHERE `id` NOT IN (
    SELECT `id` FROM (
        SELECT MIN(`id`) AS `id` FROM `agent_run` GROUP BY `task_id`, `attempt_number`
    ) AS `keep_rows`
);

ALTER TABLE `agent_run` ADD UNIQUE INDEX `uk_run_task_attempt` (`task_id`, `attempt_number`);

-- S5（文档向量化重处理并发）由代码层文档级行锁（DocumentMapper.selectByIdForUpdate）
-- + MAX(attempt)+1 计算守卫；document_index_job 含软删除列，MySQL 无部分索引，
-- 不在此处加唯一约束（避免软删行与活跃行冲突导致误报）。
