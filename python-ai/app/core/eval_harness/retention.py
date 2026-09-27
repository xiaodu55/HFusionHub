"""按数量保留评测产物：一次 `/run` 收尾时淘汰最旧的 run 及其派生报告。

第 86 批把 runs/reports 搬到卷上之后，失效方式从"产物不见了"换成"卷被写满"：一个 run
的 JSONL 逐样本存 `EvalRecord.contexts`（召回全文），单次最多 500 条样本，而 2Gi 的
eval PVC 一旦被写满，同卷的其它写者会一起失败。

口径是"组"：`<label>_<ts>.jsonl` 与它派生的 `_scores.json`/`_report.md`/`_slides.html`
同生共死（命名见 score.save_scores、report.save_report、slides.save_slides）。淘汰顺序
复用 `runner.list_run_files`，即 `/runs` 给控制台的顺序——删谁与界面列谁同源。

只在写路径末尾被调用，不做后台任务，也不留一个等运维点的端点：本仓已有
`checkpoint.prune` 与 `approval_store.cleanup_expired` 两个零调用方的清理函数。
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...utils.config import config
from . import runner

logger = logging.getLogger(__name__)

# 派生产物后缀，与 save_scores / save_report / save_slides 的命名一一对应
_ARTIFACT_SUFFIXES = ("_scores.json", "_report.md", "_slides.html")


def _remove(path: Path) -> bool:
    """删一个文件；不存在时按 Python 语义抛 FileNotFoundError，由 _try_remove 归成"不是我删的"。"""
    path.unlink()
    return True


def _try_remove(path: Path, skipped: list[str]) -> bool:
    try:
        removed = _remove(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("[eval-harness] retention: cannot remove %s: %s", path.name, exc)
        skipped.append(path.name)
        return False
    return removed


def _stem(run_file_name: str) -> str:
    return run_file_name[: -len(".jsonl")] if run_file_name.endswith(".jsonl") else run_file_name


def prune_runs(runs_dir: Path, reports_dir: Path, keep: int | None = None,
               protect: str | None = None) -> dict:
    """runs_dir 里超出 keep 的旧 run 连派生产物一起删，无主的派生产物也删。

    本函数不抛：单个文件的 OSError 记进 skipped，一次已完成的评估不该因清扫失败而失败。
    keep 省略时取 `EVAL_RETENTION_KEEP`；protect（本次刚写完的那条）永远不删，且不占
    keep 的名额 ⇒ 盘上最多 keep+1 组。
    """
    if keep is None:
        keep = config.EVAL_RETENTION_KEEP
    deleted_runs: list[str] = []
    deleted_artifacts: list[str] = []
    skipped: list[str] = []

    ordered = [entry["file"] for entry in runner.list_run_files(runs_dir)]
    for name in [n for n in ordered if n != protect][max(keep, 0):]:
        if _try_remove(runs_dir / name, skipped):
            deleted_runs.append(name)
        stem = _stem(name)
        for suffix in _ARTIFACT_SUFFIXES:
            artifact = reports_dir / f"{stem}{suffix}"
            if _try_remove(artifact, skipped):
                deleted_artifacts.append(artifact.name)

    if reports_dir.exists():
        for path in sorted(reports_dir.iterdir()):
            suffix = next((s for s in _ARTIFACT_SUFFIXES if path.name.endswith(s)), None)
            if suffix is None or not path.is_file():
                continue
            if (runs_dir / f"{path.name[: -len(suffix)]}.jsonl").exists():
                continue  # 还活着的 run 的报告，由 keep 决定去留
            if _try_remove(path, skipped):
                deleted_artifacts.append(path.name)

    result = {"keep": keep, "deleted_run_files": deleted_runs,
              "deleted_artifacts": deleted_artifacts, "skipped": skipped}
    if deleted_runs or deleted_artifacts or skipped:
        logger.info("[eval-harness] retention keep=%s runs=%d artifacts=%d skipped=%d dir=%s",
                    keep, len(deleted_runs), len(deleted_artifacts), len(skipped), runs_dir)
    return result
