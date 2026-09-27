"""部署面文本核对的共用解析器（compose / k8s 模板）。

这些不是测试，是测试的读数工具：`test_upload_path_contract.py` 与
`test_eval_harness_storage.py` 都要按服务读 env 与挂载点。刻意与
`scripts/static-checks.py` 里的解析**各写一遍**——两边同时看错同一个形状的概率
远低于一方自证；compose 侧另有 PyYAML 读回做第三方对照。
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "hfusionhub"
COMPOSE_DEV = ROOT / "docker" / "docker-compose.yml"
COMPOSE_PROD = ROOT / "deploy" / "docker-compose.prod.yml"
DOCKERFILE_PYTHON = ROOT / "deploy" / "Dockerfile.python"
DOCKERFILE_JAVA = ROOT / "deploy" / "Dockerfile.java"


def compose_services(text: str) -> dict[str, str]:
    """compose `services:` 段按两空格缩进切成 {服务名: 服务块文本}。"""
    blocks: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    inside = False
    for line in text.splitlines():
        if not inside:
            inside = line.rstrip() == "services:"
            continue
        if line and not line.startswith((" ", "\t", "#")):
            break
        named = re.match(r"^  ([A-Za-z0-9_.-]+):\s*(#.*)?$", line)
        if named:
            if current is not None:
                blocks[current] = "\n".join(buf)
            current, buf = named.group(1), []
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        blocks[current] = "\n".join(buf)
    return blocks


def python_workloads() -> dict[str, str]:
    """三档 shipped 拓扑里所有 python 工作负载，键为可读的面向标签。"""
    found: dict[str, str] = {}
    for label, path in (
        ("dev compose", COMPOSE_DEV),
        ("prod compose", COMPOSE_PROD),
    ):
        services = compose_services(path.read_text(encoding="utf-8"))
        for name, block in services.items():
            if name.startswith("python"):
                found[f"{label}:{name}"] = block
    helm_python = CHART / "templates" / "python.yaml"
    found["helm:python.yaml"] = helm_python.read_text(encoding="utf-8")
    return found


def without_comments(block: str) -> str:
    return "\n".join(ln for ln in block.splitlines() if not ln.lstrip().startswith("#"))


def flat_env(block: str, key: str) -> str | None:
    """compose 的 `KEY: value` 形态。"""
    found = re.search(rf"^\s*{re.escape(key)}:\s*'?\"?([^\n\"']+)\"?'?\s*$",
                      without_comments(block), re.MULTILINE)
    return found.group(1).strip() if found else None


def k8s_env(block: str, name: str) -> str | None:
    """k8s 的 `- name: X` + `value: Y` 形态。"""
    found = re.search(
        rf'- name: {re.escape(name)}\n\s+value:\s*"?([^\n"]+)"?\s*$',
        without_comments(block),
        re.MULTILINE,
    )
    return found.group(1).strip() if found else None


def env_of(block: str, key: str) -> str | None:
    """两种写法都试一遍——运维面里同一个键的形态取决于它是哪一档拓扑。"""
    return flat_env(block, key) or k8s_env(block, key)


def mount_targets(block: str) -> list[str]:
    """块内出现的所有挂载目标（compose 的 `src:dst[:ro]` 与 k8s 的 mountPath）。"""
    text = without_comments(block)
    targets = re.findall(r"^\s*-\s+\S+:(/\S+?)(?::\S+)?\s*$", text, re.MULTILINE)
    targets += re.findall(r"^\s*mountPath:\s*(/\S+)\s*$", text, re.MULTILINE)
    return [t.rstrip("/") for t in targets]


def covers(targets: list[str], path: str) -> bool:
    """path 本身或其祖先挂到了卷上 ⇒ 它在容器里落在卷内。"""
    return any(path == t or path.startswith(t + "/") for t in targets)


def load_static_checker():
    """按文件加载 scripts/static-checks.py（名字里有连字符，不能 import）。"""
    spec = importlib.util.spec_from_file_location(
        "hfusionhub_static_checks", ROOT / "scripts" / "static-checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
