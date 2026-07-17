"""
AgentWorkflow 模块单元测试

测试覆盖：
1. 数据模型测试
2. 枚举定义测试
3. 工作流节点测试（7种节点）
4. 工作流测试
5. 工作流引擎测试
6. 工作流构建器测试
7. 工厂类测试
8. 全局实例管理测试
9. 集成测试
"""

import time
from typing import Any

import pytest

from app.core.rag.agent_workflow import (
    # 节点
    ConditionNode,
    EndNode,
    LoopNode,
    MergeNode,
    NodeResult,
    NodeStatus,
    NodeType,
    ParallelNode,
    StartNode,
    TaskNode,
    # 工作流
    Workflow,
    WorkflowBuilder,
    WorkflowConfig,
    # 数据模型
    WorkflowContext,
    WorkflowEngine,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowFactory,
    WorkflowHistory,
    WorkflowResult,
    # 枚举
    WorkflowStatus,
    # 全局实例
    get_workflow_engine,
    reset_workflow_engine,
)

# ============================================================
# 1. 数据模型测试
# ============================================================

class TestWorkflowContext:
    """WorkflowContext 数据模型测试"""

    def test_create_context(self):
        """测试创建上下文"""
        context = WorkflowContext(
            workflow_id="wf-001",
            run_id="run-001",
            variables={"key": "value"}
        )

        assert context.workflow_id == "wf-001"
        assert context.run_id == "run-001"
        assert context.variables == {"key": "value"}

    def test_set_get_variable(self):
        """测试设置和获取变量"""
        context = WorkflowContext(
            workflow_id="wf-001",
            run_id="run-001"
        )

        context.set_variable("test_key", "test_value")

        assert context.get_variable("test_key") == "test_value"
        assert context.get_variable("nonexistent", "default") == "default"

    def test_set_get_node_output(self):
        """测试设置和获取节点输出"""
        context = WorkflowContext(
            workflow_id="wf-001",
            run_id="run-001"
        )

        context.set_node_output("node_1", {"result": "success"})

        assert context.get_node_output("node_1") == {"result": "success"}
        assert context.get_node_output("nonexistent") is None


class TestNodeResult:
    """NodeResult 数据模型测试"""

    def test_create_result(self):
        """测试创建结果"""
        result = NodeResult(
            node_id="node-001",
            status=NodeStatus.COMPLETED,
            output={"result": "success"}
        )

        assert result.node_id == "node-001"
        assert result.status == NodeStatus.COMPLETED
        assert result.output == {"result": "success"}

    def test_result_to_dict(self):
        """测试结果转字典"""
        result = NodeResult(
            node_id="node-001",
            status=NodeStatus.FAILED,
            error="Something went wrong",
            duration_ms=150.5
        )

        d = result.to_dict()

        assert d["node_id"] == "node-001"
        assert d["status"] == "failed"
        assert d["error"] == "Something went wrong"
        assert d["duration_ms"] == 150.5


class TestWorkflowResult:
    """WorkflowResult 数据模型测试"""

    def test_create_result(self):
        """测试创建结果"""
        result = WorkflowResult(
            workflow_id="wf-001",
            run_id="run-001",
            status=WorkflowStatus.COMPLETED
        )

        assert result.workflow_id == "wf-001"
        assert result.run_id == "run-001"
        assert result.status == WorkflowStatus.COMPLETED

    def test_result_to_dict(self):
        """测试结果转字典"""
        result = WorkflowResult(
            workflow_id="wf-001",
            run_id="run-001",
            status=WorkflowStatus.FAILED,
            error="Execution failed",
            duration_ms=500.0
        )

        d = result.to_dict()

        assert d["workflow_id"] == "wf-001"
        assert d["status"] == "failed"
        assert d["error"] == "Execution failed"
        assert d["duration_ms"] == 500.0


class TestWorkflowConfig:
    """WorkflowConfig 数据模型测试"""

    def test_create_config(self):
        """测试创建配置"""
        config = WorkflowConfig()

        assert config.max_retries == 3
        assert config.timeout_seconds == 300.0
        assert config.enable_history is True

    def test_config_to_dict(self):
        """测试配置转字典"""
        config = WorkflowConfig(
            max_retries=5,
            timeout_seconds=600.0,
            enable_history=False
        )

        d = config.to_dict()

        assert d["max_retries"] == 5
        assert d["timeout_seconds"] == 600.0
        assert d["enable_history"] is False

    def test_config_from_dict(self):
        """测试从字典创建配置"""
        d = {
            "max_retries": 10,
            "timeout_seconds": 1200.0,
            "max_history": 200
        }

        config = WorkflowConfig.from_dict(d)

        assert config.max_retries == 10
        assert config.timeout_seconds == 1200.0
        assert config.max_history == 200


class TestWorkflowEvent:
    """WorkflowEvent 数据模型测试"""

    def test_create_event(self):
        """测试创建事件"""
        event = WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_STARTED,
            workflow_id="wf-001",
            run_id="run-001"
        )

        assert event.event_type == WorkflowEventType.WORKFLOW_STARTED
        assert event.workflow_id == "wf-001"

    def test_event_to_dict(self):
        """测试事件转字典"""
        event = WorkflowEvent(
            event_type=WorkflowEventType.NODE_COMPLETED,
            workflow_id="wf-001",
            run_id="run-001",
            node_id="node-001",
            data={"output": "test"}
        )

        d = event.to_dict()

        assert d["event_type"] == "node_completed"
        assert d["node_id"] == "node-001"
        assert d["data"]["output"] == "test"


class TestWorkflowHistory:
    """WorkflowHistory 数据模型测试"""

    def test_create_history(self):
        """测试创建历史记录"""
        history = WorkflowHistory(
            run_id="run-001",
            workflow_id="wf-001",
            status=WorkflowStatus.COMPLETED,
            start_time=1234567890.0,
            end_time=1234567900.0,
            duration_ms=10000.0
        )

        assert history.run_id == "run-001"
        assert history.status == WorkflowStatus.COMPLETED

    def test_history_to_dict(self):
        """测试历史记录转字典"""
        history = WorkflowHistory(
            run_id="run-001",
            workflow_id="wf-001",
            status=WorkflowStatus.FAILED,
            start_time=1234567890.0,
            end_time=1234567900.0,
            duration_ms=10000.0,
            error="Failed"
        )

        d = history.to_dict()

        assert d["run_id"] == "run-001"
        assert d["status"] == "failed"
        assert d["error"] == "Failed"


# ============================================================
# 2. 枚举定义测试
# ============================================================

class TestEnums:
    """枚举定义测试"""

    def test_workflow_status(self):
        """测试工作流状态枚举"""
        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"

    def test_node_type(self):
        """测试节点类型枚举"""
        assert NodeType.START.value == "start"
        assert NodeType.END.value == "end"
        assert NodeType.TASK.value == "task"
        assert NodeType.CONDITION.value == "condition"
        assert NodeType.PARALLEL.value == "parallel"
        assert NodeType.LOOP.value == "loop"
        assert NodeType.MERGE.value == "merge"

    def test_node_status(self):
        """测试节点状态枚举"""
        assert NodeStatus.PENDING.value == "pending"
        assert NodeStatus.RUNNING.value == "running"
        assert NodeStatus.COMPLETED.value == "completed"
        assert NodeStatus.FAILED.value == "failed"
        assert NodeStatus.SKIPPED.value == "skipped"

    def test_workflow_event_type(self):
        """测试工作流事件类型枚举"""
        assert WorkflowEventType.WORKFLOW_STARTED.value == "workflow_started"
        assert WorkflowEventType.WORKFLOW_COMPLETED.value == "workflow_completed"
        assert WorkflowEventType.NODE_STARTED.value == "node_started"
        assert WorkflowEventType.NODE_COMPLETED.value == "node_completed"


# ============================================================
# 3. 工作流节点测试
# ============================================================

class TestStartNode:
    """StartNode 测试"""

    @pytest.mark.asyncio
    async def test_execute(self):
        """测试执行开始节点"""
        node = StartNode()
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        result = await node.execute(context)

        assert result["status"] == "started"
        assert "timestamp" in result

    def test_node_properties(self):
        """测试节点属性"""
        node = StartNode(node_id="start_1", name="开始节点")

        assert node.node_id == "start_1"
        assert node.node_type == NodeType.START
        assert node.name == "开始节点"


class TestEndNode:
    """EndNode 测试"""

    @pytest.mark.asyncio
    async def test_execute(self):
        """测试执行结束节点"""
        node = EndNode()
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        result = await node.execute(context)

        assert result["status"] == "completed"
        assert "timestamp" in result

    def test_node_properties(self):
        """测试节点属性"""
        node = EndNode(node_id="end_1", name="结束节点")

        assert node.node_id == "end_1"
        assert node.node_type == NodeType.END
        assert node.name == "结束节点"


class TestTaskNode:
    """TaskNode 测试"""

    @pytest.mark.asyncio
    async def test_execute(self):
        """测试执行任务节点"""
        async def my_task(context: WorkflowContext) -> Any:
            return {"result": "success"}

        node = TaskNode(node_id="task_1", task=my_task, name="测试任务")
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        result = await node.execute(context)

        assert result == {"result": "success"}
        assert context.get_node_output("task_1") == {"result": "success"}

    @pytest.mark.asyncio
    async def test_execute_with_kwargs(self):
        """测试执行带参数的任务节点"""
        async def my_task(param1: str, param2: int = 10) -> Any:
            return {"param1": param1, "param2": param2}

        node = TaskNode(
            node_id="task_2",
            task=my_task,
            name="带参数任务",
            param1="hello",
            param2=20
        )
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        result = await node.execute(context)

        assert result["param1"] == "hello"
        assert result["param2"] == 20


class TestConditionNode:
    """ConditionNode 测试"""

    @pytest.mark.asyncio
    async def test_execute_true(self):
        """测试条件节点（真分支）"""
        async def my_condition(context: WorkflowContext) -> bool:
            return True

        node = ConditionNode(
            node_id="cond_1",
            condition=my_condition,
            true_branch="task_true",
            false_branch="task_false"
        )
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        result = await node.execute(context)

        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_get_next_nodes_true(self):
        """测试获取下一个节点（真分支）"""
        async def my_condition(context: WorkflowContext) -> bool:
            return True

        node = ConditionNode(
            node_id="cond_1",
            condition=my_condition,
            true_branch="task_true",
            false_branch="task_false"
        )
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        await node.execute(context)
        next_nodes = await node.get_next_nodes(context)

        assert next_nodes == ["task_true"]

    @pytest.mark.asyncio
    async def test_get_next_nodes_false(self):
        """测试获取下一个节点（假分支）"""
        async def my_condition(context: WorkflowContext) -> bool:
            return False

        node = ConditionNode(
            node_id="cond_1",
            condition=my_condition,
            true_branch="task_true",
            false_branch="task_false"
        )
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        await node.execute(context)
        next_nodes = await node.get_next_nodes(context)

        assert next_nodes == ["task_false"]


class TestParallelNode:
    """ParallelNode 测试"""

    @pytest.mark.asyncio
    async def test_execute(self):
        """测试执行并行节点"""
        node = ParallelNode(
            node_id="parallel_1",
            branch_nodes=["task_a", "task_b", "task_c"],
            name="并行执行"
        )
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        result = await node.execute(context)

        assert result["branches"] == ["task_a", "task_b", "task_c"]

    @pytest.mark.asyncio
    async def test_get_next_nodes(self):
        """测试获取分支节点"""
        node = ParallelNode(
            node_id="parallel_1",
            branch_nodes=["task_a", "task_b"]
        )
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        next_nodes = await node.get_next_nodes(context)

        assert set(next_nodes) == {"task_a", "task_b"}


class TestLoopNode:
    """LoopNode 测试"""

    @pytest.mark.asyncio
    async def test_execute_continue(self):
        """测试执行循环节点（继续）"""
        iteration = [0]

        async def my_condition(context: WorkflowContext) -> bool:
            iteration[0] += 1
            return iteration[0] < 3

        node = LoopNode(
            node_id="loop_1",
            loop_body=["task_in_loop"],
            condition=my_condition,
            max_iterations=10
        )
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        result = await node.execute(context)

        assert result["continue"] is True
        assert result["iteration"] == 1

    @pytest.mark.asyncio
    async def test_execute_stop(self):
        """测试执行循环节点（停止）"""
        async def my_condition(context: WorkflowContext) -> bool:
            return False

        node = LoopNode(
            node_id="loop_1",
            loop_body=["task_in_loop"],
            condition=my_condition,
            max_iterations=10
        )
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        result = await node.execute(context)

        assert result["continue"] is False

    @pytest.mark.asyncio
    async def test_max_iterations_exceeded(self):
        """测试超过最大迭代次数"""
        async def my_condition(context: WorkflowContext) -> bool:
            return True

        node = LoopNode(
            node_id="loop_1",
            loop_body=["task_in_loop"],
            condition=my_condition,
            max_iterations=2
        )
        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")

        # 第一次执行
        await node.execute(context)
        # 第二次执行
        await node.execute(context)
        # 第三次执行应该抛出异常
        with pytest.raises(ValueError, match="Max iterations"):
            await node.execute(context)

    def test_reset(self):
        """测试重置循环计数器"""
        node = LoopNode(
            node_id="loop_1",
            loop_body=[],
            condition=lambda ctx: True
        )
        node._iteration = 5

        node.reset()

        assert node._iteration == 0


class TestMergeNode:
    """MergeNode 测试"""

    @pytest.mark.asyncio
    async def test_execute(self):
        """测试执行合并节点"""
        node = MergeNode(
            node_id="merge_1",
            expected_inputs=2,
            name="合并"
        )
        node.add_input_node("task_a")
        node.add_input_node("task_b")

        context = WorkflowContext(workflow_id="wf-001", run_id="run-001")
        context.set_node_output("task_a", {"result": "a"})
        context.set_node_output("task_b", {"result": "b"})

        result = await node.execute(context)

        assert "task_a" in result
        assert "task_b" in result
        assert result["task_a"] == {"result": "a"}


# ============================================================
# 4. 工作流测试
# ============================================================

class TestWorkflow:
    """Workflow 测试"""

    def test_create_workflow(self):
        """测试创建工作流"""
        workflow = Workflow(
            workflow_id="wf-001",
            name="测试工作流",
            description="这是一个测试"
        )

        assert workflow.workflow_id == "wf-001"
        assert workflow.name == "测试工作流"
        assert workflow.status == WorkflowStatus.PENDING

    def test_add_node(self):
        """测试添加节点"""
        workflow = Workflow(workflow_id="wf-001")
        start = StartNode()
        end = EndNode()

        workflow.add_node(start)
        workflow.add_node(end)

        assert workflow.get_node_count() == 2
        assert workflow._start_node_id == "start"
        assert workflow._end_node_id == "end"

    def test_add_edge(self):
        """测试添加边"""
        workflow = Workflow(workflow_id="wf-001")
        start = StartNode()
        end = EndNode()

        workflow.add_node(start)
        workflow.add_node(end)
        workflow.add_edge("start", "end")

        assert "end" in start._next_nodes

    def test_remove_node(self):
        """测试移除节点"""
        workflow = Workflow(workflow_id="wf-001")
        start = StartNode()
        end = EndNode()

        workflow.add_node(start)
        workflow.add_node(end)
        workflow.remove_node("end")

        assert workflow.get_node_count() == 1
        assert workflow.get_node("end") is None

    def test_validate_valid(self):
        """测试验证有效工作流"""
        workflow = Workflow(workflow_id="wf-001")
        start = StartNode()
        end = EndNode()

        workflow.add_node(start)
        workflow.add_node(end)
        workflow.add_edge("start", "end")

        is_valid, message = workflow.validate()

        assert is_valid is True
        assert message == "Valid"

    def test_validate_no_start(self):
        """测试验证无开始节点"""
        workflow = Workflow(workflow_id="wf-001")
        end = EndNode()

        workflow.add_node(end)

        is_valid, message = workflow.validate()

        assert is_valid is False
        assert "start" in message.lower()

    def test_validate_no_end(self):
        """测试验证无结束节点"""
        workflow = Workflow(workflow_id="wf-001")
        start = StartNode()

        workflow.add_node(start)

        is_valid, message = workflow.validate()

        assert is_valid is False
        assert "end" in message.lower()

    def test_to_dict(self):
        """测试工作流转字典"""
        workflow = Workflow(workflow_id="wf-001", name="测试")
        workflow.add_node(StartNode())
        workflow.add_node(EndNode())

        d = workflow.to_dict()

        assert d["workflow_id"] == "wf-001"
        assert d["name"] == "测试"
        assert len(d["nodes"]) == 2

    def test_event_listener(self):
        """测试事件监听器"""
        workflow = Workflow(workflow_id="wf-001")
        events = []

        workflow.add_event_listener(
            WorkflowEventType.WORKFLOW_STARTED,
            lambda e: events.append(e)
        )

        event = WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_STARTED,
            workflow_id="wf-001",
            run_id="run-001"
        )
        workflow._emit_event(event)

        assert len(events) == 1


# ============================================================
# 5. 工作流引擎测试
# ============================================================

class TestWorkflowEngine:
    """WorkflowEngine 测试"""

    def setup_method(self):
        """测试前设置"""
        reset_workflow_engine()

    def teardown_method(self):
        """测试后清理"""
        reset_workflow_engine()

    @pytest.mark.asyncio
    async def test_execute_simple_workflow(self):
        """测试执行简单工作流"""
        # 创建工作流
        builder = WorkflowBuilder("wf-001", "测试工作流")

        async def task1(context: WorkflowContext) -> Any:
            return {"step": 1}

        async def task2(context: WorkflowContext) -> Any:
            return {"step": 2}

        builder.add_start()
        builder.add_task(task1, node_id="task1", name="任务1")
        builder.add_task(task2, node_id="task2", name="任务2")
        builder.add_end()

        builder.connect("start", "task1")
        builder.connect("task1", "task2")
        builder.connect("task2", "end")

        workflow = builder.build()

        # 执行工作流
        engine = WorkflowEngine()
        result = await engine.execute(workflow)

        assert result.status == WorkflowStatus.COMPLETED
        assert len(result.node_results) == 4  # start, task1, task2, end

    @pytest.mark.asyncio
    async def test_execute_with_variables(self):
        """测试执行带变量的工作流"""
        builder = WorkflowBuilder("wf-002", "变量测试")

        async def task1(context: WorkflowContext) -> Any:
            value = context.get_variable("input_value", 0)
            return {"result": value * 2}

        builder.add_start()
        builder.add_task(task1, node_id="task1")
        builder.add_end()

        builder.connect("start", "task1")
        builder.connect("task1", "end")

        workflow = builder.build()

        # 执行工作流
        engine = WorkflowEngine()
        result = await engine.execute(workflow, variables={"input_value": 21})

        assert result.status == WorkflowStatus.COMPLETED
        # 检查变量是否传递
        assert result.context.get_variable("input_value") == 21

    @pytest.mark.asyncio
    async def test_execute_with_condition(self):
        """测试执行带条件的工作流"""
        builder = WorkflowBuilder("wf-003", "条件测试")

        async def check_value(context: WorkflowContext) -> bool:
            return context.get_variable("value", 0) > 10

        async def high_value(context: WorkflowContext) -> Any:
            return {"path": "high"}

        async def low_value(context: WorkflowContext) -> Any:
            return {"path": "low"}

        builder.add_start()
        builder.add_condition(
            check_value,
            true_branch="high",
            false_branch="low",
            node_id="cond"
        )
        builder.add_task(high_value, node_id="high", name="高值路径")
        builder.add_task(low_value, node_id="low", name="低值路径")
        builder.add_end()

        builder.connect("start", "cond")
        builder.connect("cond", "high")
        builder.connect("cond", "low")
        builder.connect("high", "end")
        builder.connect("low", "end")

        workflow = builder.build()

        # 测试高值路径
        engine = WorkflowEngine()
        result = await engine.execute(workflow, variables={"value": 20})

        assert result.status == WorkflowStatus.COMPLETED

        # 测试低值路径
        result2 = await engine.execute(workflow, variables={"value": 5})

        assert result2.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_task_failure(self):
        """测试任务失败"""
        builder = WorkflowBuilder("wf-004", "失败测试")

        async def failing_task(context: WorkflowContext) -> Any:
            raise ValueError("Task failed")

        builder.add_start()
        builder.add_task(failing_task, node_id="failing")
        builder.add_end()

        builder.connect("start", "failing")
        builder.connect("failing", "end")

        workflow = builder.build()

        engine = WorkflowEngine()
        result = await engine.execute(workflow)

        assert result.status == WorkflowStatus.FAILED
        assert "Task failed" in result.error

    @pytest.mark.asyncio
    async def test_execute_invalid_workflow(self):
        """测试执行无效工作流"""
        workflow = Workflow(workflow_id="wf-005", name="无效工作流")
        # 没有开始和结束节点

        engine = WorkflowEngine()
        result = await engine.execute(workflow)

        assert result.status == WorkflowStatus.FAILED

    def test_get_history(self):
        """测试获取历史记录"""
        engine = WorkflowEngine()

        # 添加一些历史记录
        engine._history.append(WorkflowHistory(
            run_id="run-001",
            workflow_id="wf-001",
            status=WorkflowStatus.COMPLETED,
            start_time=time.time(),
            end_time=time.time(),
            duration_ms=100.0
        ))

        history = engine.get_history()

        assert len(history) == 1

    def test_get_history_by_workflow(self):
        """测试按工作流ID获取历史记录"""
        engine = WorkflowEngine()

        engine._history.append(WorkflowHistory(
            run_id="run-001",
            workflow_id="wf-001",
            status=WorkflowStatus.COMPLETED,
            start_time=time.time(),
            end_time=time.time(),
            duration_ms=100.0
        ))
        engine._history.append(WorkflowHistory(
            run_id="run-002",
            workflow_id="wf-002",
            status=WorkflowStatus.COMPLETED,
            start_time=time.time(),
            end_time=time.time(),
            duration_ms=200.0
        ))

        history = engine.get_history(workflow_id="wf-001")

        assert len(history) == 1
        assert history[0].workflow_id == "wf-001"

    def test_clear_history(self):
        """测试清除历史记录"""
        engine = WorkflowEngine()

        engine._history.append(WorkflowHistory(
            run_id="run-001",
            workflow_id="wf-001",
            status=WorkflowStatus.COMPLETED,
            start_time=time.time(),
            end_time=time.time(),
            duration_ms=100.0
        ))

        engine.clear_history()

        assert len(engine._history) == 0


# ============================================================
# 6. 工作流构建器测试
# ============================================================

class TestWorkflowBuilder:
    """WorkflowBuilder 测试"""

    def test_build_simple_workflow(self):
        """测试构建简单工作流"""
        builder = WorkflowBuilder("wf-001", "简单工作流")

        builder.add_start()
        builder.add_end()
        builder.connect("start", "end")

        workflow = builder.build()

        assert workflow.workflow_id == "wf-001"
        assert workflow.get_node_count() == 2

    def test_build_with_tasks(self):
        """测试构建带任务的工作流"""
        async def my_task(context: WorkflowContext) -> Any:
            return "done"

        builder = WorkflowBuilder("wf-002", "带任务工作流")

        builder.add_start()
        builder.add_task(my_task, node_id="task1")
        builder.add_task(my_task, node_id="task2")
        builder.add_end()

        builder.connect("start", "task1")
        builder.connect("task1", "task2")
        builder.connect("task2", "end")

        workflow = builder.build()

        assert workflow.get_node_count() == 4

    def test_auto_generate_node_id(self):
        """测试自动生成节点ID"""
        async def my_task(context: WorkflowContext) -> Any:
            return "done"

        builder = WorkflowBuilder("wf-003")

        builder.add_start()
        builder.add_task(my_task)
        builder.add_task(my_task)
        builder.add_end()

        workflow = builder.build()

        # 检查自动生成的ID
        node_ids = [n.node_id for n in workflow.get_all_nodes()]
        assert "start" in node_ids
        assert "end" in node_ids
        assert any(n.startswith("task_") for n in node_ids)


# ============================================================
# 7. 工厂类测试
# ============================================================

class TestWorkflowFactory:
    """WorkflowFactory 测试"""

    def test_create_workflow(self):
        """测试创建工作流"""
        workflow = WorkflowFactory.create(
            workflow_id="wf-001",
            name="测试工作流"
        )

        assert workflow is not None
        assert workflow.workflow_id == "wf-001"

    def test_create_engine(self):
        """测试创建工作流引擎"""
        engine = WorkflowFactory.create_engine()

        assert engine is not None
        assert isinstance(engine, WorkflowEngine)


# ============================================================
# 8. 全局实例管理测试
# ============================================================

class TestGlobalInstanceManagement:
    """全局实例管理测试"""

    def setup_method(self):
        """测试前设置"""
        reset_workflow_engine()

    def teardown_method(self):
        """测试后清理"""
        reset_workflow_engine()

    def test_get_workflow_engine(self):
        """测试获取全局引擎实例"""
        engine = get_workflow_engine()

        assert engine is not None
        assert isinstance(engine, WorkflowEngine)

    def test_get_singleton(self):
        """测试单例模式"""
        engine1 = get_workflow_engine()
        engine2 = get_workflow_engine()

        assert engine1 is engine2

    def test_reset(self):
        """测试重置实例"""
        engine1 = get_workflow_engine()
        reset_workflow_engine()
        engine2 = get_workflow_engine()

        assert engine1 is not engine2


# ============================================================
# 9. 集成测试
# ============================================================

class TestIntegration:
    """集成测试"""

    def setup_method(self):
        """测试前设置"""
        reset_workflow_engine()

    def teardown_method(self):
        """测试后清理"""
        reset_workflow_engine()

    @pytest.mark.asyncio
    async def test_full_workflow_execution(self):
        """测试完整工作流执行"""
        # 创建复杂工作流
        builder = WorkflowBuilder("wf-complex", "复杂工作流")

        # 定义任务
        async def init_task(context: WorkflowContext) -> Any:
            context.set_variable("counter", 0)
            return {"initialized": True}

        async def process_task(context: WorkflowContext) -> Any:
            counter = context.get_variable("counter", 0)
            context.set_variable("counter", counter + 1)
            return {"processed": counter + 1}

        async def final_task(context: WorkflowContext) -> Any:
            counter = context.get_variable("counter", 0)
            return {"final_count": counter}

        # 构建工作流
        builder.add_start()
        builder.add_task(init_task, node_id="init", name="初始化")
        builder.add_task(process_task, node_id="process", name="处理")
        builder.add_task(final_task, node_id="final", name="完成")
        builder.add_end()

        builder.connect("start", "init")
        builder.connect("init", "process")
        builder.connect("process", "final")
        builder.connect("final", "end")

        workflow = builder.build()

        # 验证工作流
        is_valid, message = workflow.validate()
        assert is_valid is True

        # 执行工作流
        engine = WorkflowEngine()
        result = await engine.execute(workflow)

        # 验证结果
        assert result.status == WorkflowStatus.COMPLETED
        assert len(result.node_results) == 5  # start, init, process, final, end

        # 验证历史记录
        history = engine.get_history()
        assert len(history) == 1
        assert history[0].status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_multiple_executions(self):
        """测试多次执行"""
        builder = WorkflowBuilder("wf-multi", "多次执行测试")

        async def count_task(context: WorkflowContext) -> Any:
            count = context.get_variable("count", 0)
            context.set_variable("count", count + 1)
            return {"count": count + 1}

        builder.add_start()
        builder.add_task(count_task, node_id="count")
        builder.add_end()

        builder.connect("start", "count")
        builder.connect("count", "end")

        workflow = builder.build()

        engine = WorkflowEngine()

        # 执行多次
        for i in range(3):
            result = await engine.execute(workflow, variables={"count": 0})
            assert result.status == WorkflowStatus.COMPLETED

        # 验证历史记录
        history = engine.get_history()
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_workflow_with_loop(self):
        """测试带循环的工作流"""
        builder = WorkflowBuilder("wf-loop", "循环测试")

        iteration = [0]

        async def loop_condition(context: WorkflowContext) -> bool:
            iteration[0] += 1
            return iteration[0] < 3

        async def loop_body(context: WorkflowContext) -> Any:
            count = context.get_variable("count", 0)
            context.set_variable("count", count + 1)
            return {"iteration": count + 1}

        builder.add_start()
        builder.add_loop(
            loop_body=["loop_task"],
            condition=loop_condition,
            max_iterations=10,
            node_id="loop"
        )
        builder.add_task(loop_body, node_id="loop_task", name="循环体")
        builder.add_end()

        builder.connect("start", "loop")
        builder.connect("loop", "loop_task")
        builder.connect("loop_task", "loop")
        builder.connect("loop", "end")

        workflow = builder.build()

        engine = WorkflowEngine()
        result = await engine.execute(workflow, variables={"count": 0})

        # 验证循环执行
        assert result.status == WorkflowStatus.COMPLETED
