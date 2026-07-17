"""
AgentWorkflow 模块
工作流引擎模块，负责定义和执行Agent工作流

核心功能：
1. 工作流定义（顺序、并行、条件、循环）
2. 工作流节点管理（开始、结束、任务、条件、并行、循环）
3. 工作流状态管理（运行、暂停、完成、失败）
4. 工作流历史记录
5. 工作流可视化（DAG图）

设计模式：
- 状态模式：工作流状态管理
- 组合模式：节点组合
- 观察者模式：工作流事件通知
- 工厂模式：统一创建实例
"""

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ============================================================
# 1. 枚举定义
# ============================================================

class WorkflowStatus(str, Enum):
    """工作流状态"""
    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 运行中
    PAUSED = "paused"  # 暂停
    COMPLETED = "completed"  # 完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class NodeType(str, Enum):
    """节点类型"""
    START = "start"  # 开始节点
    END = "end"  # 结束节点
    TASK = "task"  # 任务节点
    CONDITION = "condition"  # 条件节点
    PARALLEL = "parallel"  # 并行节点
    LOOP = "loop"  # 循环节点
    MERGE = "merge"  # 合并节点


class NodeStatus(str, Enum):
    """节点状态"""
    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 运行中
    COMPLETED = "completed"  # 完成
    FAILED = "failed"  # 失败
    SKIPPED = "skipped"  # 跳过


class WorkflowEventType(str, Enum):
    """工作流事件类型"""
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_PAUSED = "workflow_paused"
    WORKFLOW_RESUMED = "workflow_resumed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_SKIPPED = "node_skipped"


# ============================================================
# 2. 数据模型
# ============================================================

@dataclass
class WorkflowContext:
    """工作流上下文"""
    workflow_id: str
    run_id: str
    variables: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_variable(self, key: str, value: Any):
        """设置变量"""
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """获取变量"""
        return self.variables.get(key, default)

    def get_node_output(self, node_id: str) -> Any:
        """获取节点输出"""
        return self.node_outputs.get(node_id)

    def set_node_output(self, node_id: str, output: Any):
        """设置节点输出"""
        self.node_outputs[node_id] = output


@dataclass
class NodeResult:
    """节点执行结果"""
    node_id: str
    status: NodeStatus
    output: Any = None
    error: str | None = None
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转为字典"""
        return {
            "node_id": self.node_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms
        }


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    workflow_id: str
    run_id: str
    status: WorkflowStatus
    node_results: list[NodeResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    error: str | None = None
    context: WorkflowContext | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为字典"""
        return {
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "status": self.status.value,
            "node_results": [nr.to_dict() for nr in self.node_results],
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "error": self.error
        }


@dataclass
class WorkflowConfig:
    """工作流配置"""
    max_retries: int = 3  # 最大重试次数
    timeout_seconds: float = 300.0  # 超时时间（秒）
    enable_history: bool = True  # 启用历史记录
    max_history: int = 100  # 最大历史记录数
    enable_logging: bool = True  # 启用日志

    def to_dict(self) -> dict[str, Any]:
        """转为字典"""
        return {
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "enable_history": self.enable_history,
            "max_history": self.max_history,
            "enable_logging": self.enable_logging
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowConfig":
        """从字典创建"""
        return cls(
            max_retries=data.get("max_retries", 3),
            timeout_seconds=data.get("timeout_seconds", 300.0),
            enable_history=data.get("enable_history", True),
            max_history=data.get("max_history", 100),
            enable_logging=data.get("enable_logging", True)
        )


@dataclass
class WorkflowEvent:
    """工作流事件"""
    event_type: WorkflowEventType
    workflow_id: str
    run_id: str
    node_id: str | None = None
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转为字典"""
        return {
            "event_type": self.event_type.value,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "data": self.data
        }


@dataclass
class WorkflowHistory:
    """工作流历史记录"""
    run_id: str
    workflow_id: str
    status: WorkflowStatus
    start_time: float
    end_time: float
    duration_ms: float
    node_results: list[NodeResult] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为字典"""
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "node_results": [nr.to_dict() for nr in self.node_results],
            "error": self.error
        }


# ============================================================
# 3. 工作流节点（组合模式）
# ============================================================

class BaseWorkflowNode(ABC):
    """工作流节点基类"""

    def __init__(
        self,
        node_id: str,
        node_type: NodeType,
        name: str = "",
        description: str = ""
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.name = name or node_id
        self.description = description
        self._next_nodes: list[str] = []  # 下一个节点ID列表
        self._status = NodeStatus.PENDING
        self._retry_count = 0

    @property
    def status(self) -> NodeStatus:
        """获取节点状态"""
        return self._status

    @status.setter
    def status(self, value: NodeStatus):
        """设置节点状态"""
        self._status = value

    def add_next_node(self, node_id: str):
        """添加下一个节点"""
        if node_id not in self._next_nodes:
            self._next_nodes.append(node_id)

    def remove_next_node(self, node_id: str):
        """移除下一个节点"""
        if node_id in self._next_nodes:
            self._next_nodes.remove(node_id)

    @abstractmethod
    async def execute(self, context: WorkflowContext) -> Any:
        """执行节点"""
        pass

    async def get_next_nodes(self, context: WorkflowContext) -> list[str]:
        """获取下一个节点ID列表"""
        return self._next_nodes.copy()

    def to_dict(self) -> dict[str, Any]:
        """转为字典"""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "name": self.name,
            "description": self.description,
            "next_nodes": self._next_nodes,
            "status": self._status.value
        }


class StartNode(BaseWorkflowNode):
    """开始节点"""

    def __init__(
        self,
        node_id: str = "start",
        name: str = "开始",
        description: str = "工作流开始"
    ):
        super().__init__(node_id, NodeType.START, name, description)

    async def execute(self, context: WorkflowContext) -> Any:
        """执行开始节点"""
        logger.info(f"Workflow {context.workflow_id} started")
        return {"status": "started", "timestamp": time.time()}


class EndNode(BaseWorkflowNode):
    """结束节点"""

    def __init__(
        self,
        node_id: str = "end",
        name: str = "结束",
        description: str = "工作流结束"
    ):
        super().__init__(node_id, NodeType.END, name, description)

    async def execute(self, context: WorkflowContext) -> Any:
        """执行结束节点"""
        logger.info(f"Workflow {context.workflow_id} completed")
        return {"status": "completed", "timestamp": time.time()}


class TaskNode(BaseWorkflowNode):
    """任务节点"""

    def __init__(
        self,
        node_id: str,
        task: Callable,
        name: str = "",
        description: str = "",
        **kwargs
    ):
        super().__init__(node_id, NodeType.TASK, name, description)
        self.task = task
        self.task_kwargs = kwargs

    async def execute(self, context: WorkflowContext) -> Any:
        """执行任务节点"""
        logger.info(f"Executing task node: {self.node_id}")

        # 向下兼容：如果 task 不接受 context 参数，就只传 kwargs
        import inspect
        sig = inspect.signature(self.task)
        if 'context' in sig.parameters:
            result = await self.task(context=context, **self.task_kwargs)
        else:
            result = await self.task(**self.task_kwargs)

        context.set_node_output(self.node_id, result)
        return result


class ConditionNode(BaseWorkflowNode):
    """条件节点"""

    def __init__(
        self,
        node_id: str,
        condition: Callable,
        true_branch: str = "",
        false_branch: str = "",
        name: str = "",
        description: str = ""
    ):
        super().__init__(node_id, NodeType.CONDITION, name, description)
        self.condition = condition
        self.true_branch = true_branch
        self.false_branch = false_branch

    async def execute(self, context: WorkflowContext) -> Any:
        """执行条件节点"""
        logger.info(f"Evaluating condition node: {self.node_id}")

        result = await self.condition(context)
        context.set_node_output(self.node_id, {"result": result})

        return {"result": result}

    async def get_next_nodes(self, context: WorkflowContext) -> list[str]:
        """根据条件结果获取下一个节点"""
        output = context.get_node_output(self.node_id)
        if output and output.get("result"):
            return [self.true_branch] if self.true_branch else []
        else:
            return [self.false_branch] if self.false_branch else []


class ParallelNode(BaseWorkflowNode):
    """并行节点"""

    def __init__(
        self,
        node_id: str,
        branch_nodes: list[str],
        name: str = "",
        description: str = ""
    ):
        super().__init__(node_id, NodeType.PARALLEL, name, description)
        self.branch_nodes = branch_nodes

    async def execute(self, context: WorkflowContext) -> Any:
        """执行并行节点"""
        logger.info(f"Starting parallel execution: {self.node_id}")
        return {"branches": self.branch_nodes}

    async def get_next_nodes(self, context: WorkflowContext) -> list[str]:
        """获取所有分支节点"""
        return self.branch_nodes.copy()


class LoopNode(BaseWorkflowNode):
    """循环节点"""

    def __init__(
        self,
        node_id: str,
        loop_body: list[str],
        condition: Callable,
        max_iterations: int = 100,
        name: str = "",
        description: str = ""
    ):
        super().__init__(node_id, NodeType.LOOP, name, description)
        self.loop_body = loop_body
        self.condition = condition
        self.max_iterations = max_iterations
        self._iteration = 0

    async def execute(self, context: WorkflowContext) -> Any:
        """执行循环节点"""
        logger.info(f"Starting loop: {self.node_id}")

        self._iteration += 1
        if self._iteration > self.max_iterations:
            raise ValueError(f"Max iterations ({self.max_iterations}) exceeded")

        # 检查循环条件
        should_continue = await self.condition(context)
        context.set_variable(f"{self.node_id}_iteration", self._iteration)

        return {"iteration": self._iteration, "continue": should_continue}

    async def get_next_nodes(self, context: WorkflowContext) -> list[str]:
        """根据循环条件获取下一个节点"""
        output = context.get_node_output(self.node_id)
        if output and output.get("continue"):
            return self.loop_body.copy()
        else:
            return self._next_nodes.copy()

    def reset(self):
        """重置循环计数器"""
        self._iteration = 0


class MergeNode(BaseWorkflowNode):
    """合并节点"""

    def __init__(
        self,
        node_id: str,
        expected_inputs: int = 1,
        name: str = "",
        description: str = ""
    ):
        super().__init__(node_id, NodeType.MERGE, name, description)
        self.expected_inputs = expected_inputs
        self._received_inputs: set[str] = set()

    def add_input_node(self, node_id: str):
        """添加输入节点"""
        self._received_inputs.add(node_id)

    async def execute(self, context: WorkflowContext) -> Any:
        """执行合并节点"""
        logger.info(f"Merging inputs at node: {self.node_id}")

        # 收集所有输入
        inputs = {}
        for node_id in self._received_inputs:
            output = context.get_node_output(node_id)
            if output is not None:
                inputs[node_id] = output

        context.set_node_output(self.node_id, inputs)
        return inputs


# ============================================================
# 4. 工作流
# ============================================================

class Workflow:
    """
    工作流

    管理工作流节点和执行逻辑
    """

    def __init__(
        self,
        workflow_id: str,
        name: str = "",
        description: str = "",
        config: WorkflowConfig | None = None
    ):
        self.workflow_id = workflow_id
        self.name = name or workflow_id
        self.description = description
        self.config = config or WorkflowConfig()
        self._nodes: dict[str, BaseWorkflowNode] = {}
        self._start_node_id: str | None = None
        self._end_node_id: str | None = None
        self._status = WorkflowStatus.PENDING
        self._event_listeners: dict[WorkflowEventType, list[Callable]] = {}

    @property
    def status(self) -> WorkflowStatus:
        """获取工作流状态"""
        return self._status

    @status.setter
    def status(self, value: WorkflowStatus):
        """设置工作流状态"""
        self._status = value

    def add_node(self, node: BaseWorkflowNode):
        """添加节点"""
        self._nodes[node.node_id] = node

        # 自动设置开始和结束节点
        if node.node_type == NodeType.START:
            self._start_node_id = node.node_id
        elif node.node_type == NodeType.END:
            self._end_node_id = node.node_id

        logger.debug(f"Added node: {node.node_id}")

    def remove_node(self, node_id: str):
        """移除节点"""
        if node_id in self._nodes:
            del self._nodes[node_id]
            if self._start_node_id == node_id:
                self._start_node_id = None
            if self._end_node_id == node_id:
                self._end_node_id = None

    def get_node(self, node_id: str) -> BaseWorkflowNode | None:
        """获取节点"""
        return self._nodes.get(node_id)

    def add_edge(self, from_node_id: str, to_node_id: str):
        """添加边（连接节点）"""
        from_node = self._nodes.get(from_node_id)
        to_node = self._nodes.get(to_node_id)

        if from_node and to_node:
            from_node.add_next_node(to_node_id)

            # 如果是合并节点，添加输入
            if to_node.node_type == NodeType.MERGE:
                to_node.add_input_node(from_node_id)

    def remove_edge(self, from_node_id: str, to_node_id: str):
        """移除边"""
        from_node = self._nodes.get(from_node_id)
        if from_node:
            from_node.remove_next_node(to_node_id)

    def add_event_listener(self, event_type: WorkflowEventType, listener: Callable):
        """添加事件监听器"""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(listener)

    def _emit_event(self, event: WorkflowEvent):
        """触发事件"""
        for listener in self._event_listeners.get(event.event_type, []):
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Event listener error: {e}")

    def get_all_nodes(self) -> list[BaseWorkflowNode]:
        """获取所有节点"""
        return list(self._nodes.values())

    def get_node_count(self) -> int:
        """获取节点数量"""
        return len(self._nodes)

    def to_dict(self) -> dict[str, Any]:
        """转为字典"""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "config": self.config.to_dict(),
            "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
            "start_node_id": self._start_node_id,
            "end_node_id": self._end_node_id,
            "status": self._status.value
        }

    def validate(self) -> tuple[bool, str]:
        """验证工作流"""
        # 检查是否有开始节点
        if not self._start_node_id:
            return False, "No start node found"

        # 检查是否有结束节点
        if not self._end_node_id:
            return False, "No end node found"

        # 检查所有节点是否可达
        reachable = set()
        queue = [self._start_node_id]
        while queue:
            node_id = queue.pop(0)
            if node_id in reachable:
                continue
            reachable.add(node_id)
            node = self._nodes.get(node_id)
            if node:
                for next_id in node._next_nodes:
                    if next_id not in reachable:
                        queue.append(next_id)

        # 检查是否有未连接的节点
        all_nodes = set(self._nodes.keys())
        unreachable = all_nodes - reachable
        if unreachable:
            return False, f"Unreachable nodes: {unreachable}"

        return True, "Valid"


# ============================================================
# 5. 工作流引擎
# ============================================================

class WorkflowEngine:
    """
    工作流引擎

    负责执行工作流并管理状态
    """

    def __init__(self, config: WorkflowConfig | None = None):
        self.config = config or WorkflowConfig()
        self._history: list[WorkflowHistory] = []
        self._running_workflows: dict[str, WorkflowResult] = {}

    async def execute(
        self,
        workflow: Workflow,
        variables: dict[str, Any] | None = None
    ) -> WorkflowResult:
        """
        执行工作流

        Args:
            workflow: 工作流实例
            variables: 初始变量

        Returns:
            工作流执行结果
        """
        run_id = str(uuid.uuid4())
        context = WorkflowContext(
            workflow_id=workflow.workflow_id,
            run_id=run_id,
            variables=variables or {}
        )

        result = WorkflowResult(
            workflow_id=workflow.workflow_id,
            run_id=run_id,
            status=WorkflowStatus.RUNNING,
            start_time=time.time(),
            context=context
        )

        self._running_workflows[run_id] = result

        # 触发开始事件
        workflow._emit_event(WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_STARTED,
            workflow_id=workflow.workflow_id,
            run_id=run_id
        ))

        try:
            # 验证工作流
            is_valid, message = workflow.validate()
            if not is_valid:
                raise ValueError(f"Invalid workflow: {message}")

            # 从开始节点执行（_execute_chain 沿链推进，ParallelNode 分支真并行）
            await self._execute_chain(
                workflow, context, result, workflow._start_node_id, set()
            )

            # 如果没有设置状态，设置为完成
            if result.status == WorkflowStatus.RUNNING:
                result.status = WorkflowStatus.COMPLETED

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            result.status = WorkflowStatus.FAILED
            result.error = str(e)

            # 触发失败事件
            workflow._emit_event(WorkflowEvent(
                event_type=WorkflowEventType.WORKFLOW_FAILED,
                workflow_id=workflow.workflow_id,
                run_id=run_id,
                data={"error": str(e)}
            ))

        finally:
            result.end_time = time.time()
            result.duration_ms = (result.end_time - result.start_time) * 1000
            self._running_workflows.pop(run_id, None)

            # 保存历史记录
            if self.config.enable_history:
                self._save_history(result, workflow)

            # 触发完成事件
            if result.status == WorkflowStatus.COMPLETED:
                workflow._emit_event(WorkflowEvent(
                    event_type=WorkflowEventType.WORKFLOW_COMPLETED,
                    workflow_id=workflow.workflow_id,
                    run_id=run_id,
                    data=result.to_dict()
                ))

        return result

    async def _execute_node(
        self,
        node: BaseWorkflowNode,
        context: WorkflowContext,
        workflow: Workflow
    ) -> NodeResult:
        """执行单个节点（含重试与超时，由 WorkflowConfig 控制）"""
        node_result = NodeResult(
            node_id=node.node_id,
            status=NodeStatus.RUNNING,
            start_time=time.time()
        )

        # 触发节点开始事件
        workflow._emit_event(WorkflowEvent(
            event_type=WorkflowEventType.NODE_STARTED,
            workflow_id=workflow.workflow_id,
            run_id=context.run_id,
            node_id=node.node_id
        ))

        try:
            # 设置节点状态
            node.status = NodeStatus.RUNNING

            # 执行节点（含重试与超时）
            output = await self._run_node_with_retry(node, context)

            # 设置节点状态
            node.status = NodeStatus.COMPLETED
            node_result.status = NodeStatus.COMPLETED
            node_result.output = output
            node_result.end_time = time.time()
            node_result.duration_ms = (node_result.end_time - node_result.start_time) * 1000

            # 触发节点完成事件
            workflow._emit_event(WorkflowEvent(
                event_type=WorkflowEventType.NODE_COMPLETED,
                workflow_id=workflow.workflow_id,
                run_id=context.run_id,
                node_id=node.node_id,
                data={"output": output}
            ))

        except TimeoutError:
            logger.error(f"Node {node.node_id} timed out after {self.config.timeout_seconds}s")
            node.status = NodeStatus.FAILED
            node_result.status = NodeStatus.FAILED
            node_result.error = (
                f"Node {node.node_id} timed out after {self.config.timeout_seconds}s"
            )
            node_result.end_time = time.time()
            node_result.duration_ms = (node_result.end_time - node_result.start_time) * 1000

            workflow._emit_event(WorkflowEvent(
                event_type=WorkflowEventType.NODE_FAILED,
                workflow_id=workflow.workflow_id,
                run_id=context.run_id,
                node_id=node.node_id,
                data={"error": node_result.error}
            ))

        except Exception as e:
            logger.error(f"Node {node.node_id} execution failed: {e}")
            node.status = NodeStatus.FAILED
            node_result.status = NodeStatus.FAILED
            node_result.error = str(e)
            node_result.end_time = time.time()
            node_result.duration_ms = (node_result.end_time - node_result.start_time) * 1000

            # 触发节点失败事件
            workflow._emit_event(WorkflowEvent(
                event_type=WorkflowEventType.NODE_FAILED,
                workflow_id=workflow.workflow_id,
                run_id=context.run_id,
                node_id=node.node_id,
                data={"error": str(e)}
            ))

        return node_result

    async def _run_node_with_retry(
        self,
        node: BaseWorkflowNode,
        context: WorkflowContext
    ) -> Any:
        """带重试与超时地执行节点。

        - 每次尝试受 WorkflowConfig.timeout_seconds 限制（asyncio.wait_for）。
        - 瞬时异常按 WorkflowConfig.max_retries 重试，退避 0.2s * attempt。
        - 超时不再重试（超时往往是稳态问题，重试只会拖长总时长）。
        """
        last_exc: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return await asyncio.wait_for(
                    node.execute(context),
                    timeout=self.config.timeout_seconds,
                )
            except TimeoutError:
                raise
            except Exception as e:  # noqa: BLE001 — 由 _execute_node 统一兜底
                last_exc = e
                logger.warning(
                    f"Node {node.node_id} attempt {attempt + 1} failed: {e}"
                )
                if attempt < self.config.max_retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    async def _execute_chain(
        self,
        workflow: Workflow,
        context: WorkflowContext,
        result: WorkflowResult,
        node_id: str,
        visited_nodes: set[str],
    ) -> bool:
        """沿单链推进节点，直到结束、失败或无后继。

        - visited_nodes 防止环形边（LoopNode 等）导致无限循环。
        - ParallelNode 的多出边作为独立分支并发执行（asyncio.gather）。
        - 其他节点的多出边保持向后兼容：仅沿第一条推进（ConditionNode /
          LoopNode 通过 get_next_nodes 已自行筛选出唯一后继，多个出边中
          后向边不应被当作并行分支执行）。

        Returns:
            True=本链正常结束；False=链上某节点失败。
        """
        while node_id:
            if node_id in visited_nodes:
                logger.warning(f"Node {node_id} already visited, skipping")
                break

            node = workflow.get_node(node_id)
            if not node:
                raise ValueError(f"Node {node_id} not found")

            # 执行节点
            node_result = await self._execute_node(node, context, workflow)
            result.node_results.append(node_result)

            # 检查节点是否成功
            if node_result.status == NodeStatus.FAILED:
                result.status = WorkflowStatus.FAILED
                result.error = node_result.error
                return False

            # 标记已访问
            visited_nodes.add(node_id)

            # 获取下一个节点
            next_node_ids = await node.get_next_nodes(context)

            if not next_node_ids:
                # 没有下一个节点，检查是否到达结束节点
                if node_id == workflow._end_node_id:
                    if result.status == WorkflowStatus.RUNNING:
                        result.status = WorkflowStatus.COMPLETED
                else:
                    if result.status != WorkflowStatus.FAILED:
                        result.status = WorkflowStatus.FAILED
                        result.error = f"Workflow ended at non-end node: {node_id}"
                    return False
                return True

            # ParallelNode：所有分支并发执行（修复原实现只取 next[0] 丢分支的 bug）
            if isinstance(node, ParallelNode) and len(next_node_ids) > 1:
                return await self._run_parallel_branches(
                    workflow, context, result, next_node_ids, visited_nodes
                )

            # 其余节点向后兼容：沿第一条推进
            node_id = next_node_ids[0]

        return True

    async def _run_parallel_branches(
        self,
        workflow: Workflow,
        context: WorkflowContext,
        result: WorkflowResult,
        branch_ids: list[str],
        visited_nodes: set[str],
    ) -> bool:
        """并发执行多个分支链，任一分支失败则整个工作流失败。"""
        async def run_branch(branch_id: str) -> bool:
            return await self._execute_chain(
                workflow, context, result, branch_id, set(visited_nodes)
            )

        outcomes = await asyncio.gather(
            *(run_branch(b) for b in branch_ids)
        )
        if any(o is False for o in outcomes):
            if result.status != WorkflowStatus.FAILED:
                result.status = WorkflowStatus.FAILED
                result.error = result.error or "One or more parallel branches failed"
            return False
        return True

    def _save_history(self, result: WorkflowResult, workflow: Workflow):
        """保存历史记录"""
        history = WorkflowHistory(
            run_id=result.run_id,
            workflow_id=result.workflow_id,
            status=result.status,
            start_time=result.start_time,
            end_time=result.end_time,
            duration_ms=result.duration_ms,
            node_results=result.node_results,
            error=result.error
        )

        self._history.append(history)

        # 限制历史记录数量
        if len(self._history) > self.config.max_history:
            self._history = self._history[-self.config.max_history:]

    def get_history(
        self,
        workflow_id: str | None = None
    ) -> list[WorkflowHistory]:
        """获取历史记录"""
        if workflow_id:
            return [h for h in self._history if h.workflow_id == workflow_id]
        return self._history.copy()

    def clear_history(self):
        """清除历史记录"""
        self._history.clear()


# ============================================================
# 6. 工作流构建器
# ============================================================

class WorkflowBuilder:
    """工作流构建器"""

    def __init__(self, workflow_id: str, name: str = "", description: str = ""):
        self.workflow = Workflow(workflow_id, name, description)
        self._node_counter = 0

    def _generate_node_id(self, prefix: str = "node") -> str:
        """生成节点ID"""
        self._node_counter += 1
        return f"{prefix}_{self._node_counter}"

    def add_start(self, node_id: str = "start", name: str = "开始") -> "WorkflowBuilder":
        """添加开始节点"""
        node = StartNode(node_id, name)
        self.workflow.add_node(node)
        return self

    def add_end(self, node_id: str = "end", name: str = "结束") -> "WorkflowBuilder":
        """添加结束节点"""
        node = EndNode(node_id, name)
        self.workflow.add_node(node)
        return self

    def add_task(
        self,
        task: Callable,
        node_id: str | None = None,
        name: str = "",
        **kwargs
    ) -> "WorkflowBuilder":
        """添加任务节点"""
        node_id = node_id or self._generate_node_id("task")
        node = TaskNode(node_id, task, name, **kwargs)
        self.workflow.add_node(node)
        return self

    def add_condition(
        self,
        condition: Callable,
        true_branch: str = "",
        false_branch: str = "",
        node_id: str | None = None,
        name: str = ""
    ) -> "WorkflowBuilder":
        """添加条件节点"""
        node_id = node_id or self._generate_node_id("cond")
        node = ConditionNode(node_id, condition, true_branch, false_branch, name)
        self.workflow.add_node(node)
        return self

    def add_parallel(
        self,
        branch_nodes: list[str],
        node_id: str | None = None,
        name: str = ""
    ) -> "WorkflowBuilder":
        """添加并行节点"""
        node_id = node_id or self._generate_node_id("parallel")
        node = ParallelNode(node_id, branch_nodes, name)
        self.workflow.add_node(node)
        return self

    def add_loop(
        self,
        loop_body: list[str],
        condition: Callable,
        max_iterations: int = 100,
        node_id: str | None = None,
        name: str = ""
    ) -> "WorkflowBuilder":
        """添加循环节点"""
        node_id = node_id or self._generate_node_id("loop")
        node = LoopNode(node_id, loop_body, condition, max_iterations, name)
        self.workflow.add_node(node)
        return self

    def add_merge(
        self,
        expected_inputs: int = 1,
        node_id: str | None = None,
        name: str = ""
    ) -> "WorkflowBuilder":
        """添加合并节点"""
        node_id = node_id or self._generate_node_id("merge")
        node = MergeNode(node_id, expected_inputs, name)
        self.workflow.add_node(node)
        return self

    def connect(self, from_node_id: str, to_node_id: str) -> "WorkflowBuilder":
        """连接节点"""
        self.workflow.add_edge(from_node_id, to_node_id)
        return self

    def build(self) -> Workflow:
        """构建工作流"""
        return self.workflow


# ============================================================
# 7. 工厂和全局实例
# ============================================================

class WorkflowFactory:
    """工作流工厂"""

    @staticmethod
    def create(
        workflow_id: str,
        name: str = "",
        description: str = "",
        config: WorkflowConfig | None = None
    ) -> Workflow:
        """创建工作流"""
        return Workflow(workflow_id, name, description, config)

    @staticmethod
    def create_engine(
        config: WorkflowConfig | None = None
    ) -> WorkflowEngine:
        """创建工作流引擎"""
        return WorkflowEngine(config)


# 全局实例
_workflow_engine: WorkflowEngine | None = None


def get_workflow_engine(
    config: WorkflowConfig | None = None
) -> WorkflowEngine:
    """
    获取全局工作流引擎实例

    Args:
        config: 工作流配置

    Returns:
        WorkflowEngine 实例
    """
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowFactory.create_engine(config)
    return _workflow_engine


def reset_workflow_engine():
    """重置全局工作流引擎实例（用于测试）"""
    global _workflow_engine
    if _workflow_engine:
        _workflow_engine.clear_history()
    _workflow_engine = None
