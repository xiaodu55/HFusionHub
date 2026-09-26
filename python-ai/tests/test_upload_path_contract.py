"""Java 与 python 必须"同一个绝对路径看见同一个文件"，三档部署面都得成立。

Java 存进 `document.file_path` 的是它**自己容器内**的绝对路径
（`DocumentServiceImpl.java:529` 的 `Paths.get(System.getProperty("user.dir"), UPLOAD_DIR)`，
而 `Dockerfile.java` 的 WORKDIR=/app），`VectorizationServiceImpl.java:737` 把它原样发给
python 的 `/api/parse`；python 侧 `validators.py:87-103` 要求这个路径在**自己的容器里**
真实存在、且落在 `DOCUMENT_STORAGE_ROOT` 之下。反向同样成立：`/api/ingest/url` 返回的
`file_path` 由 Java 持久化并回写。⇒ 两服务共用 uploads 卷、挂载点与 root 同号，是契约
本身而不是冗余配置。

第八十四批登记这条时把方向写反了（说成"prod compose 给 python 挂了它从不写的卷"）。
真正缺配置的是 dev compose 的 fullstack 档：`python-ai` 与 `python-ai-worker` 既没挂
uploads 卷也没设 root，于是容器化一键启动下每个文档解析都 400（code 10001）。
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "hfusionhub"
COMPOSE_DEV = ROOT / "docker" / "docker-compose.yml"
COMPOSE_PROD = ROOT / "deploy" / "docker-compose.prod.yml"
HELM_PYTHON = CHART / "templates" / "python.yaml"
DOCKERFILE_JAVA = ROOT / "deploy" / "Dockerfile.java"
JAVA_DOCUMENT_SERVICE = (
    ROOT / "java-backend" / "src" / "main" / "java" / "com" / "hfusionhub"
    / "service" / "impl" / "DocumentServiceImpl.java"
)
JAVA_VECTORIZATION_SERVICE = (
    ROOT / "java-backend" / "src" / "main" / "java" / "com" / "hfusionhub"
    / "service" / "impl" / "VectorizationServiceImpl.java"
)
PYTHON_VALIDATORS = ROOT / "python-ai" / "app" / "utils" / "validators.py"


def _compose_services(text: str) -> dict[str, str]:
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
            if current:
                blocks[current] = "\n".join(buf)
            current = named.group(1)
            buf = []
            continue
        if current is not None:
            buf.append(line)
    if current:
        blocks[current] = "\n".join(buf)
    return blocks


def _flat_env(block: str, key: str) -> str | None:
    """compose 的 `KEY: value` 形态。"""
    found = re.search(rf"^\s*{re.escape(key)}:\s*'?\"?([^\n\"']+)\"?'?\s*$", block, re.MULTILINE)
    return found.group(1).strip() if found else None


def _k8s_env(block: str, name: str) -> str | None:
    """k8s 的 `- name: X` + `value: Y` 形态。"""
    found = re.search(
        rf'- name: {re.escape(name)}\n\s+value:\s*"?([^\n"]+)"?\s*$', block, re.MULTILINE
    )
    return found.group(1).strip() if found else None


def _mount_targets(block: str) -> list[str]:
    """一个服务块里出现的所有挂载目标（compose 的 `src:dst[:ro]` 与 k8s 的 mountPath）。"""
    targets = re.findall(r"^\s*-\s+\S+:(/\S+?)(?::\S+)?\s*$", block, re.MULTILINE)
    targets += re.findall(r"^\s*mountPath:\s*(/\S+)\s*$", block, re.MULTILINE)
    return [t.rstrip("/") for t in targets]


def _covers(targets: list[str], root: str) -> bool:
    """root 本身或其祖先挂到了卷上 ⇒ 该 root 在容器里落在卷内。"""
    return any(root == t or root.startswith(t + "/") for t in targets)


def _java_document_root() -> str:
    """由 java 侧两个锚点派生 python 必须配的路径，避免测试与门禁各自硬编码。"""
    stages = re.split(r"^FROM\b", DOCKERFILE_JAVA.read_text(encoding="utf-8"),
                      flags=re.MULTILINE)[1:]
    assert stages, "Dockerfile.java 没有 FROM 阶段"
    workdirs = re.findall(r"^WORKDIR\s+(/\S+)\s*$", stages[-1], re.MULTILINE)
    assert len(workdirs) == 1, f"运行阶段的 WORKDIR 不唯一，派生值有歧义：{workdirs}"
    upload_dir = re.search(
        r'static\s+final\s+String\s+UPLOAD_DIR\s*=\s*"([^"]+)"',
        JAVA_DOCUMENT_SERVICE.read_text(encoding="utf-8"),
        re.IGNORECASE,
    )
    assert upload_dir, "DocumentServiceImpl.java 里找不到 UPLOAD_DIR 常量"
    return f"{workdirs[0].rstrip('/')}/{upload_dir.group(1).strip('/')}"


EXPECTED_ROOT = _java_document_root()


class TestContractPremises:
    """契约两端仍是"按路径互见"，否则本文件的门禁会悄悄失去意义。"""

    def test_java_sends_its_own_absolute_path_to_python(self):
        text = JAVA_VECTORIZATION_SERVICE.read_text(encoding="utf-8")
        assert re.search(r'Map\.entry\(\s*"file_path",\s*document\.getFilePath\(\)\s*\)', text), (
            "java 不再把 document.file_path 发给 python /api/parse，本批前提需重新评估"
        )

    def test_python_requires_the_path_to_exist_under_its_root(self):
        text = PYTHON_VALIDATORS.read_text(encoding="utf-8")
        assert "resolve(strict=True)" in text and "relative_to(storage_root)" in text, (
            "validate_file_path 不再按 DOCUMENT_STORAGE_ROOT 围栏并要求文件真实存在"
        )

    def test_derived_root_is_the_absolute_upload_documents_dir(self):
        assert EXPECTED_ROOT == "/app/uploads/documents", f"派生结果异常：{EXPECTED_ROOT}"


class TestDevComposeCarriesTheContract:
    """fullstack 档此前两个 python 服务都缺配置：解析必然 400 code 10001。"""

    def _python(self, name: str) -> str:
        services = _compose_services(COMPOSE_DEV.read_text(encoding="utf-8"))
        assert name in services, f"docker/docker-compose.yml 缺服务 {name}"
        return services[name]

    def test_python_ai_mounts_the_shared_uploads_volume(self):
        assert _covers(_mount_targets(self._python("python-ai")), EXPECTED_ROOT), (
            f"python-ai 没把 uploads 卷挂到 {EXPECTED_ROOT} 的祖先路径，"
            "Java 传来的绝对路径在它容器里不存在"
        )

    def test_python_ai_declares_the_document_storage_root(self):
        assert _flat_env(self._python("python-ai"), "DOCUMENT_STORAGE_ROOT") == EXPECTED_ROOT

    def test_worker_mounts_the_shared_uploads_volume(self):
        assert _covers(_mount_targets(self._python("python-ai-worker")), EXPECTED_ROOT), (
            "arq worker 同样要读到 Java 的文件，缺一处挂载就只是把失败挪到 worker"
        )

    def test_worker_declares_the_document_storage_root(self):
        assert _flat_env(self._python("python-ai-worker"), "DOCUMENT_STORAGE_ROOT") == EXPECTED_ROOT


class TestShippedSurfacesStayAligned:
    def test_prod_compose_python_pairs_mount_and_root(self):
        block = _compose_services(COMPOSE_PROD.read_text(encoding="utf-8"))["python-ai"]
        assert _covers(_mount_targets(block), EXPECTED_ROOT)
        assert _flat_env(block, "DOCUMENT_STORAGE_ROOT") == EXPECTED_ROOT

    def test_helm_python_pairs_mount_and_root(self):
        text = HELM_PYTHON.read_text(encoding="utf-8")
        assert _covers(_mount_targets(text), EXPECTED_ROOT)
        assert _k8s_env(text, "DOCUMENT_STORAGE_ROOT") == EXPECTED_ROOT

    def test_every_python_workload_uses_the_same_root(self):
        roots = [
            _flat_env(_compose_services(COMPOSE_DEV.read_text(encoding="utf-8"))["python-ai"],
                      "DOCUMENT_STORAGE_ROOT"),
            _flat_env(_compose_services(COMPOSE_DEV.read_text(encoding="utf-8"))["python-ai-worker"],
                      "DOCUMENT_STORAGE_ROOT"),
            _flat_env(_compose_services(COMPOSE_PROD.read_text(encoding="utf-8"))["python-ai"],
                      "DOCUMENT_STORAGE_ROOT"),
            _k8s_env(HELM_PYTHON.read_text(encoding="utf-8"), "DOCUMENT_STORAGE_ROOT"),
        ]
        assert set(roots) == {EXPECTED_ROOT}, f"同一契约在四处部署面写出不同值：{roots}"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "hfusionhub_static_checks", ROOT / "scripts" / "static-checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compose_fixture(tmp_path: Path, python_block: str) -> Path:
    path = tmp_path / "compose.yml"
    path.write_text(
        "services:\n"
        "  java-backend:\n"
        "    image: hfusionhub-java\n"
        "    volumes:\n"
        "      - uploads-data:/app/uploads\n"
        + python_block
        + "\nvolumes:\n  uploads-data: {}\n",
        encoding="utf-8",
    )
    return path


def _surfaces_to_tmp(module, dev: Path, helm: Path) -> None:
    """把三个部署面指到临时文件；java 侧两个锚点仍读仓库，派生值保持真实。"""
    for name, path in (
        ("COMPOSE_DEV", dev),
        ("COMPOSE_PROD", dev),
        ("HELM_PYTHON_TEMPLATE", helm),
    ):
        setattr(module, name, path)


class TestDocumentStorageRootGate:
    def _run(self, module):
        module.problems.clear()
        module.check_document_storage_root_contract()
        return list(module.problems)

    def test_gate_passes_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "static-checks.py"),
             "--document-storage-root"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_gate_is_in_the_default_all_mode(self):
        """只接显式传参不并入全跑档 = 门禁在自己的缺陷上报绿（第八十三批的哑火形态）。"""
        source = (ROOT / "scripts" / "static-checks.py").read_text(encoding="utf-8")
        main_body = source[source.index("def main()"):]
        assert "--document-storage-root" in main_body
        all_mode = main_body[main_body.index("args = parser.parse_args()"):
                             main_body.index("if args.tenant_columns:")]
        assert all_mode.count("args.document_storage_root") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_document_storage_root_contract()" in main_body

    def test_gate_flags_a_python_service_with_mount_but_no_root(self, tmp_path):
        """本批修掉的真实缺陷形态：挂了卷却不设 root，root 落到镜像默认值上。"""
        module = _load_checker()
        dev = _compose_fixture(tmp_path, (
            "  python-ai:\n"
            "    image: hfusionhub-python\n"
            "    volumes:\n"
            "      - uploads-data:/app/uploads\n"
        ))
        helm = tmp_path / "helm.yaml"
        helm.write_text("kind: Deployment\n", encoding="utf-8")
        _surfaces_to_tmp(module, dev, helm)
        problems = self._run(module)
        assert problems, "挂载与 root 不成对时门禁必须报红"
        assert "DOCUMENT_STORAGE_ROOT" in problems[0] and "python-ai" in problems[0]

    def test_gate_flags_a_root_that_is_not_on_a_volume(self, tmp_path):
        """设了 root 却没把卷挂在它（或它的祖先）上 ⇒ 写进去的数据随容器重建消失。"""
        module = _load_checker()
        dev = _compose_fixture(tmp_path, (
            "  python-ai:\n"
            "    image: hfusionhub-python\n"
            "    environment:\n"
            f"      DOCUMENT_STORAGE_ROOT: {EXPECTED_ROOT}\n"
            "    volumes:\n"
            "      - python-data:/data\n"
        ))
        helm = tmp_path / "helm.yaml"
        helm.write_text("kind: Deployment\n", encoding="utf-8")
        _surfaces_to_tmp(module, dev, helm)
        problems = self._run(module)
        assert problems, "root 不在任何挂载点上时必须报红"
        assert "/app/uploads" in problems[0]

    def test_gate_flags_a_root_that_disagrees_with_java(self, tmp_path):
        module = _load_checker()
        dev = _compose_fixture(tmp_path, (
            "  python-ai:\n"
            "    image: hfusionhub-python\n"
            "    environment:\n"
            "      DOCUMENT_STORAGE_ROOT: /data/uploads/documents\n"
            "    volumes:\n"
            "      - uploads-data:/data/uploads\n"
        ))
        helm = tmp_path / "helm.yaml"
        helm.write_text("kind: Deployment\n", encoding="utf-8")
        _surfaces_to_tmp(module, dev, helm)
        problems = self._run(module)
        assert problems, "python 的 root 与 java 的上传目录不同号时必须报红"
        assert "/data/uploads/documents" in problems[0] and EXPECTED_ROOT in problems[0]
