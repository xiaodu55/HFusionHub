"""评测产物（runs / reports / scores / judge 缓存）的落点：必须可配，且在卷上。

三个落点此前都是模块级硬编码常量（`app/api/eval_harness.py:31`、
`app/core/eval_harness/runner.py:25`、`app/core/eval_harness/metrics/llm_judge.py:63`），
相对 `data/eval_harness/`；容器里 WORKDIR=/app ⇒ `/app/data`，而三档 shipped 拓扑
没有任何一档把卷挂在 `/app/data`（compose 只挂 `/data`，helm 连 `/data` 都不存在）。
后果不是"少一个优化"：`/score`、`/slides`、`/report`、`/diff` 四个端点按"文件还在"
读回产物（`eval_harness.py:211/220/236-237`），容器或 Pod 一重建就全部 404，helm 两副本
下 A 生成的报告对 B 根本不可见。

落点不能一把梭：runs/reports/scores 是"写一次、之后按文件名读回"⇒ 该上共享卷；
judge 缓存是整文件 read-modify-write ⇒ 上共享卷会让两副本互相覆盖，只能按 Pod 分。
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest
from deploy_surface import (
    CHART,
    DOCKERFILE_PYTHON,
    ROOT,
    covers,
    env_of,
    load_static_checker,
    mount_targets,
    python_workloads,
)

from app.utils.config import config

EVAL_API = ROOT / "python-ai" / "app" / "api" / "eval_harness.py"
EVAL_RUNNER = ROOT / "python-ai" / "app" / "core" / "eval_harness" / "runner.py"
LLM_JUDGE = ROOT / "python-ai" / "app" / "core" / "eval_harness" / "metrics" / "llm_judge.py"
CHECKPOINT_MODULE = ROOT / "python-ai" / "app" / "core" / "agent" / "checkpoint.py"
ENVIRONMENT_DOC = ROOT / "docs" / "ENVIRONMENT.md"

DATA_DIR_DEFAULT = "data/eval_harness"
CACHE_DEFAULT = "data/eval_harness/judge_cache.json"


class TestPathsAreConfigurable:
    def test_config_defines_the_data_dir_key(self):
        assert getattr(config, "EVAL_HARNESS_DATA_DIR", None) == DATA_DIR_DEFAULT, (
            "EVAL_HARNESS_DATA_DIR 必须存在且默认值保持今天的相对布局（宿主开发态不变）"
        )

    def test_config_defines_the_judge_cache_key(self):
        assert getattr(config, "EVAL_JUDGE_CACHE_PATH", None) == CACHE_DEFAULT

    def test_reports_dir_reads_the_config_key(self):
        text = EVAL_API.read_text(encoding="utf-8")
        assert re.search(r'REPORTS_DIR\s*=\s*Path\(config\.EVAL_HARNESS_DATA_DIR\)\s*/\s*"reports"',
                         text), "REPORTS_DIR 仍是硬编码常量，未走 EVAL_HARNESS_DATA_DIR"

    def test_runs_dir_reads_the_config_key(self):
        text = EVAL_RUNNER.read_text(encoding="utf-8")
        assert re.search(r'_RUNS_DIR\s*=\s*Path\(config\.EVAL_HARNESS_DATA_DIR\)\s*/\s*"runs"',
                         text), "_RUNS_DIR 仍是硬编码常量（record 阶段写它，读回的也是它）"

    def test_judge_cache_path_reads_the_config_key(self):
        text = LLM_JUDGE.read_text(encoding="utf-8")
        assert re.search(r"_CACHE_PATH\s*=\s*Path\(config\.EVAL_JUDGE_CACHE_PATH\)", text), (
            "judge 缓存落点仍硬编码：它必须与共享的 reports 分面，否则两副本互相覆盖"
        )


class TestDeploySurfacesPutArtifactsOnVolumes:
    def test_every_python_workload_sets_the_data_dir_on_a_volume(self):
        offenders = []
        for label, block in python_workloads().items():
            declared = env_of(block, "EVAL_HARNESS_DATA_DIR")
            if declared is None:
                offenders.append(f"{label} 未设 EVAL_HARNESS_DATA_DIR")
            elif not declared.startswith("/"):
                offenders.append(f"{label} 的 {declared} 不是绝对路径（容器里仍落镜像层）")
            elif not covers(mount_targets(block), declared):
                offenders.append(f"{label} 的 {declared} 不在任何挂载点上")
        assert not offenders, "评测产物仍会随容器/Pod 重建消失：\n    " + "\n    ".join(offenders)

    def test_every_python_workload_sets_an_isolated_judge_cache(self):
        offenders = []
        for label, block in python_workloads().items():
            cache = env_of(block, "EVAL_JUDGE_CACHE_PATH")
            data = env_of(block, "EVAL_HARNESS_DATA_DIR")
            if cache is None:
                offenders.append(f"{label} 未设 EVAL_JUDGE_CACHE_PATH")
            elif data and cache.startswith(data.rstrip("/") + "/") and "$(POD_NAME)" not in cache:
                offenders.append(
                    f"{label} 的缓存 {cache} 落在共享目录 {data} 下却没有按 Pod 分隔："
                    "整文件 read-modify-write 会在副本间互相覆盖"
                )
        assert not offenders, "judge 缓存与共享 reports 未分面：\n    " + "\n    ".join(offenders)

    def test_helm_gives_the_eval_artifacts_a_shared_rwx_pvc(self):
        text = (CHART / "templates" / "python.yaml").read_text(encoding="utf-8")
        assert "kind: PersistentVolumeClaim" in text, "helm 没为评测产物建 PVC"
        claims = re.findall(r"kind: PersistentVolumeClaim\n(?:.*\n)*?  accessModes:\n\s*- (\S+)", text)
        assert "ReadWriteMany" in claims, (
            f"评测产物的 PVC 必须是 RWX（副本 A 生成、副本 B 读回）：{claims}"
        )
        assert "/app/eval-harness" in mount_targets(text)

    def test_values_declares_the_eval_volume_size_key(self):
        text = (CHART / "values.yaml").read_text(encoding="utf-8")
        assert re.search(r"^\s+evalReportsSize:", text, re.MULTILINE), (
            "容量必须由 values 给出，而不是模板里写死一个数字"
        )

    def test_python_image_creates_every_helm_mount_point(self):
        """挂载点由模板说了算：加一块卷而镜像没建那个路径，空 PVC 就归 root（第八十四批）。

        从模板派生而不是列清单，所以下一批新增卷时这条会自己变红，不需要有人记得改它。
        """
        image = DOCKERFILE_PYTHON.read_text(encoding="utf-8")
        tpl = (CHART / "templates" / "python.yaml").read_text(encoding="utf-8")
        mounts = sorted(set(re.findall(r"^\s+mountPath:\s*(/\S+)\s*$", tpl, re.MULTILINE)))
        assert mounts, "python 模板里读不到任何挂载点，本条等于没跑"
        created = next((ln for ln in image.splitlines() if ln.startswith("RUN mkdir -p")), "")
        missing = [path for path in mounts if path not in created.split()]
        assert not missing, f"镜像没有创建这些挂载点，非 root 进程写不进去：{missing}"


class TestCheckpointClaimMatchesCallSurface:
    """`CHECKPOINT_DB_PATH` 的落点问题在接线之前没有适用对象——文档措辞要跟调用面一致。"""

    def _callers(self) -> list[str]:
        found = []
        for path in (ROOT / "python-ai" / "app").rglob("*.py"):
            if path == CHECKPOINT_MODULE or "__pycache__" in path.parts:
                continue
            if "get_checkpoint_manager" in path.read_text(encoding="utf-8"):
                found.append(path.name)
        return found

    def test_doc_claim_is_qualified_while_nothing_calls_it(self):
        callers = self._callers()
        row = next(
            (ln for ln in ENVIRONMENT_DOC.read_text(encoding="utf-8").splitlines()
             if ln.startswith("| `CHECKPOINT_DB_PATH`")),
            None,
        )
        assert row, "docs/ENVIRONMENT.md 不再列 CHECKPOINT_DB_PATH"
        if not callers:
            assert "无生产写点" in row, (
                "该库当前没有任何 app/ 调用方，文档必须先限定这一点，"
                "否则会诱导运维把它指向共享卷（第八十二批的假开关形态）"
            )
        else:
            assert "无生产写点" not in row, f"已接线（{callers}），文档的限定语要撤掉"


def _compose_fixture(tmp_path: Path, python_block: str) -> Path:
    path = tmp_path / "compose.yml"
    path.write_text(
        "services:\n"
        "  python-ai:\n"
        "    image: hfusionhub-python\n"
        + python_block
        + "\nvolumes:\n  python-data: {}\n",
        encoding="utf-8",
    )
    return path


def _point_gate_at_tmp(module, tmp_path: Path, dev: Path) -> None:
    blank = tmp_path / "helm.yaml"
    blank.write_text("kind: Deployment\n", encoding="utf-8")
    setattr(module, "COMPOSE_DEV", dev)
    setattr(module, "COMPOSE_PROD", dev)
    setattr(module, "HELM_PYTHON_TEMPLATE", blank)


class TestEvalHarnessStorageGate:
    def _run(self, module):
        module.problems.clear()
        module.check_eval_harness_storage()
        return list(module.problems)

    def test_gate_passes_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "static-checks.py"), "--eval-harness-storage"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_gate_is_in_the_default_all_mode(self):
        source = (ROOT / "scripts" / "static-checks.py").read_text(encoding="utf-8")
        main_body = source[source.index("def main()"):]
        assert "--eval-harness-storage" in main_body
        all_mode = main_body[main_body.index("args = parser.parse_args()"):
                             main_body.index("if args.tenant_columns:")]
        assert all_mode.count("args.eval_harness_storage") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_eval_harness_storage()" in main_body

    def test_gate_flags_an_rwo_eval_volume_in_helm(self, tmp_path):
        """2 副本读回彼此产物是 RWX 的唯一理由；RWO 会让 Pod 卡在多副本调度上。

        这条规则只有整行取名才测得出来：PVC 名 `{{ .Release.Name }}-eval-pvc` 含空格，
        `\\S+` 会把每个名字都读成 `{{`，所有 PVC 塌成一个键，访问模式互相顶包。
        """
        module = load_static_checker()
        helm = tmp_path / "python.yaml"
        helm.write_text(
            "kind: Deployment\n"
            "      containers:\n"
            "        - name: python-ai\n"
            "          env:\n"
            "            - name: EVAL_HARNESS_DATA_DIR\n"
            "              value: /app/eval-harness\n"
            "            - name: EVAL_JUDGE_CACHE_PATH\n"
            "              value: \"/app/eval-harness/$(POD_NAME)/judge_cache.json\"\n"
            "          volumeMounts:\n"
            "            - name: eval-harness\n"
            "              mountPath: /app/eval-harness\n"
            "      volumes:\n"
            "        - name: eval-harness\n"
            "          persistentVolumeClaim:\n"
            "            claimName: hf-eval-pvc\n"
            "---\n"
            "kind: PersistentVolumeClaim\n"
            "metadata:\n"
            "  name: hf-eval-pvc\n"
            "spec:\n"
            "  accessModes:\n"
            "    - ReadWriteOnce\n",
            encoding="utf-8",
        )
        setattr(module, "HELM_PYTHON_TEMPLATE", helm)
        problems = self._run(module)
        assert problems, "评测卷是 ReadWriteOnce 时必须报红（副本 A 的产物对副本 B 不可见）"
        assert "ReadWriteMany" in problems[0]

    def test_gate_flags_a_workload_that_sets_nothing(self, tmp_path):
        """第八十批的失效形态：键在全仓任何部署配置里都没出现过。"""
        module = load_static_checker()
        _point_gate_at_tmp(module, tmp_path, _compose_fixture(tmp_path, "    image: x\n"))
        problems = self._run(module)
        assert problems, "python 工作负载两把键都没设时必须报红"
        assert "EVAL_HARNESS_DATA_DIR" in problems[0]

    def test_gate_flags_a_data_dir_that_is_not_on_a_volume(self, tmp_path):
        module = load_static_checker()
        block = (
            "    environment:\n"
            "      EVAL_HARNESS_DATA_DIR: /app/data/eval-harness\n"
            "      EVAL_JUDGE_CACHE_PATH: /app/data/judge.json\n"
            "    volumes:\n"
            "      - python-data:/data\n"
        )
        _point_gate_at_tmp(module, tmp_path, _compose_fixture(tmp_path, block))
        problems = self._run(module)
        assert problems, "root 落在镜像层（/app/data）时必须报红"
        assert "/app/data/eval-harness" in problems[0]

    def test_gate_flags_a_shared_cache_without_pod_split(self, tmp_path):
        module = load_static_checker()
        block = (
            "    environment:\n"
            "      EVAL_HARNESS_DATA_DIR: /data/eval-harness\n"
            "      EVAL_JUDGE_CACHE_PATH: /data/eval-harness/judge_cache.json\n"
            "    volumes:\n"
            "      - python-data:/data\n"
        )
        _point_gate_at_tmp(module, tmp_path, _compose_fixture(tmp_path, block))
        problems = self._run(module)
        assert problems, "缓存与共享 reports 同目录且未按 Pod 分隔时必须报红"
        assert "POD_NAME" in problems[0] or "覆盖" in problems[0]

    def test_gate_allows_a_pod_scoped_cache_under_the_shared_dir(self, tmp_path):
        """helm 的合法形态：同一块 RWX 卷上按 $(POD_NAME) 分目录。"""
        module = load_static_checker()
        block = (
            "    environment:\n"
            "      EVAL_HARNESS_DATA_DIR: /data/eval-harness\n"
            "      EVAL_JUDGE_CACHE_PATH: /data/eval-harness/$(POD_NAME)/judge.json\n"
            "    volumes:\n"
            "      - python-data:/data\n"
        )
        _point_gate_at_tmp(module, tmp_path, _compose_fixture(tmp_path, block))
        assert self._run(module) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
