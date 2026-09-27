"""评测产物的保留口径（第八十七批）：按数量淘汰最旧的 run 及其派生报告。

第 86 批把 runs/reports 搬到卷上之后，失效模式从"会不会丢"换成"会不会写满"：
一次 `POST /run` 落 3 个文件（`runs/<stem>.jsonl` + `reports/<stem>_scores.json` +
`<stem>_report.md`，`POST /score` 再加 `<stem>_slides.html`），而 jsonl 逐样本存
`EvalRecord.contexts`（`app/core/eval_harness/schemas.py:44`，每 case 最多 top_k 篇召回
原文全文）。2Gi 的 eval PVC 上没有 TTL、没有归档、也没有清理入口时，涨到写不下的是
**整块 RWX 卷**，同卷的其它写者一起失败。

口径选"数量"、且只在 `/run` 之后就地触发。理由是本仓的清理惯例已经被证伪过一次：
`checkpoint.prune`（`app/core/agent/checkpoint.py:220`）与
`approval_store.cleanup_expired`（`app/core/agent/approval_store.py:153`）都是
**零调用方**的死函数，全仓唯一真在跑的清理是 `audit.py:315/337` 那种"在自己的写路径
上顺手收"。把保留做成一个等人调用的端点，大概率只是第 3 个死函数。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from deploy_surface import ROOT
from fastapi.testclient import TestClient

from app.utils.config import config

EVAL_API = ROOT / "python-ai" / "app" / "api" / "eval_harness.py"
ENVIRONMENT_DOC = ROOT / "docs" / "ENVIRONMENT.md"
OPS_DOC = ROOT / "docs" / "PRODUCTION_OPS.md"
ENV_EXAMPLE = ROOT / "python-ai" / ".env.example"

AUTH_HEADERS = {"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"}

SUFFIXES = ("_scores.json", "_report.md", "_slides.html")


def _retention():
    from app.core.eval_harness import retention

    return retention


def _mk_run(runs_dir: Path, name: str, *, mtime: float) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / name
    path.write_text(json.dumps({"query_id": "q1"}) + "\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _mk_artifacts(reports_dir: Path, stem: str, *, mtime: float) -> list[Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for suffix in SUFFIXES:
        path = reports_dir / f"{stem}{suffix}"
        path.write_text("x", encoding="utf-8")
        os.utime(path, (mtime, mtime))
        out.append(path)
    return out


def _names(root: Path, subdir: str) -> set[str]:
    directory = root / subdir
    return {p.name for p in directory.iterdir()} if directory.exists() else set()


class TestKeepCountIsConfigurable:
    def test_config_defines_the_keep_count(self):
        assert getattr(config, "EVAL_RETENTION_KEEP", None) == 50, (
            "EVAL_RETENTION_KEEP 必须存在，默认 50 组 run（宿主与容器同一默认，"
            "三档部署面都不必再配这个键）"
        )

    def test_env_override_is_honoured(self):
        """键必须真的从环境读：否则运维把卷调大之后无从放宽保留。

        子进程而不是 importlib.reload：reload 会把模块属性 `config` 换成新类，而 app 代码
        在导入期就绑死了旧类 —— 之后任何测试再 `from app.utils.config import config` 都会
        拿到另一个对象，钉住的就不是生产代码真正读的那一份了。
        """
        import subprocess
        import sys

        probe = "from app.utils.config import config; print(config.EVAL_RETENTION_KEEP)"
        env = {**os.environ, "EVAL_RETENTION_KEEP": "7"}
        completed = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                                   text=True, env=env,
                                   cwd=str(Path(__file__).resolve().parent.parent), check=True)
        assert completed.stdout.strip() == "7"


class TestPruneRuns:
    def test_deletes_oldest_beyond_keep_and_their_derived_artifacts(self, tmp_path):
        runs, reports = tmp_path / "runs", tmp_path / "reports"
        base = 1_600_000_000.0
        for i in range(5):
            name = f"r{i}_2026100{i}_000000.jsonl"
            _mk_run(runs, name, mtime=base + i)
            _mk_artifacts(reports, name[: -len(".jsonl")], mtime=base + i)

        result = _retention().prune_runs(runs, reports, keep=2)

        # keep=2 ⇒ 最新两组留下（/runs 给控制台的顺序就是 mtime 倒序），其余整组删
        assert _names(tmp_path, "runs") == {"r4_20261004_000000.jsonl",
                                           "r3_20261003_000000.jsonl"}
        for i in range(3):
            stem = f"r{i}_2026100{i}_000000"
            assert not (reports / f"{stem}_scores.json").exists()
            assert not (reports / f"{stem}_report.md").exists()
            assert not (reports / f"{stem}_slides.html").exists()
        assert sorted(result["deleted_run_files"]) == [
            "r0_20261000_000000.jsonl", "r1_20261001_000000.jsonl",
            "r2_20261002_000000.jsonl"]
        assert result["keep"] == 2

    def test_kept_runs_keep_all_four_artifact_kinds(self, tmp_path):
        runs, reports = tmp_path / "runs", tmp_path / "reports"
        _mk_run(runs, "old_20261001_000000.jsonl", mtime=1_600_000_000.0)
        _mk_artifacts(reports, "old_20261001_000000", mtime=1_600_000_000.0)
        _mk_run(runs, "new_20261002_000000.jsonl", mtime=1_700_000_000.0)
        _mk_artifacts(reports, "new_20261002_000000", mtime=1_700_000_000.0)

        result = _retention().prune_runs(runs, reports, keep=1)

        assert result["deleted_run_files"] == ["old_20261001_000000.jsonl"]
        assert _names(tmp_path, "reports") == {
            f"new_20261002_000000{suffix}" for suffix in SUFFIXES}

    def test_protected_run_never_dies_even_with_keep_zero(self, tmp_path):
        """keep=0 的含义是"只保留本次"，不是"把刚写完的这条也删掉"。"""
        runs, reports = tmp_path / "runs", tmp_path / "reports"
        _mk_run(runs, "cur_20261008_000000.jsonl", mtime=1_700_000_000.0)
        _mk_artifacts(reports, "cur_20261008_000000", mtime=1_700_000_000.0)
        _mk_run(runs, "prev_20261007_000000.jsonl", mtime=1_600_000_000.0)
        _mk_artifacts(reports, "prev_20261007_000000", mtime=1_600_000_000.0)

        result = _retention().prune_runs(runs, reports, keep=0,
                                         protect="cur_20261008_000000.jsonl")

        assert _names(tmp_path, "runs") == {"cur_20261008_000000.jsonl"}
        assert result["deleted_run_files"] == ["prev_20261007_000000.jsonl"]
        assert _names(tmp_path, "reports") == {
            f"cur_20261008_000000{suffix}" for suffix in SUFFIXES}

    def test_protect_is_extra_to_keep(self, tmp_path):
        """keep 约束的是旧的留几条，本次那条另算 ⇒ 盘上最多 keep+1 组。"""
        runs = tmp_path / "runs"
        for i in range(4):
            _mk_run(runs, f"r{i}_2026100{i}_000000.jsonl", mtime=1_600_000_000.0 + i)

        _retention().prune_runs(runs, tmp_path / "reports", keep=2,
                                protect="r3_20261003_000000.jsonl")

        assert _names(tmp_path, "runs") == {"r3_20261003_000000.jsonl",
                                           "r2_20261002_000000.jsonl",
                                           "r1_20261001_000000.jsonl"}

    def test_orphan_artifacts_go_even_when_the_run_is_gone(self, tmp_path):
        """对旧 run 手动 POST /score 会重建派生产物；没有孤儿规则就永远清不掉。"""
        runs, reports = tmp_path / "runs", tmp_path / "reports"
        _mk_run(runs, "kept_20261008_000000.jsonl", mtime=1_700_000_000.0)
        _mk_artifacts(reports, "orphan_20261001_000000", mtime=1_700_000_000.0)

        result = _retention().prune_runs(runs, reports, keep=50)

        assert set(result["deleted_artifacts"]) == {
            f"orphan_20261001_000000{suffix}" for suffix in SUFFIXES}
        assert _names(tmp_path, "reports") == set()
        assert result["deleted_run_files"] == []

    def test_files_that_are_not_eval_artifacts_are_untouched(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        (reports / "notes.json").write_text("{}", encoding="utf-8")
        (reports / "keepme.txt").write_text("x", encoding="utf-8")
        _mk_artifacts(reports, "orphan_20261001_000000", mtime=1_700_000_000.0)

        _retention().prune_runs(tmp_path / "runs", reports, keep=50)

        assert _names(tmp_path, "reports") == {"notes.json", "keepme.txt"}

    def test_missing_dirs_are_a_noop_and_are_not_created(self, tmp_path):
        result = _retention().prune_runs(tmp_path / "nope-runs", tmp_path / "nope-reports",
                                         keep=1)

        assert result["deleted_run_files"] == []
        assert result["deleted_artifacts"] == []
        assert not (tmp_path / "nope-runs").exists(), (
            "清扫不该建目录：挂载点由镜像负责（第 84 批），运行时建出来的目录属主不可控"
        )

    def test_order_comes_from_the_console_listing(self, tmp_path, monkeypatch):
        """淘汰顺序必须与 /runs 给控制台的顺序同源，否则删掉的会是界面认为还在的那条。"""
        retention = _retention()
        runs = tmp_path / "runs"
        # 真实 mtime：old 更早、new 更晚；伪装 listing 却把 old 排在前面
        old = _mk_run(runs, "old_20261001_000000.jsonl", mtime=1_600_000_000.0)
        new = _mk_run(runs, "new_20261008_000000.jsonl", mtime=1_900_000_000.0)
        monkeypatch.setattr(retention.runner, "list_run_files",
                            lambda directory: [{"file": old.name}, {"file": new.name}])

        result = retention.prune_runs(runs, tmp_path / "reports", keep=1)

        assert result["deleted_run_files"] == [new.name]
        assert old.exists() and not new.exists()

    def test_file_already_removed_by_another_pod_is_not_an_error(self, tmp_path, monkeypatch):
        """helm 两副本会在同一块 RWX 卷上并发清扫：对手抢先删掉不是故障。"""
        retention = _retention()
        runs = tmp_path / "runs"
        _mk_run(runs, "n_20261008_000000.jsonl", mtime=1_700_000_000.0)
        ghost = "g_20261001_000000.jsonl"
        monkeypatch.setattr(retention.runner, "list_run_files",
                            lambda directory: [{"file": "n_20261008_000000.jsonl"},
                                               {"file": ghost}])

        result = retention.prune_runs(runs, tmp_path / "reports", keep=1)

        assert result["deleted_run_files"] == [], "别人删的不该记在自己名下"
        assert result["skipped"] == []

    def test_unlink_failure_is_recorded_and_does_not_raise(self, tmp_path, monkeypatch):
        """卷写不下/权限不对时清扫要如实上报，而不是把一次已完成的评估带崩。"""
        retention = _retention()
        runs = tmp_path / "runs"
        _mk_run(runs, "n_20261008_000000.jsonl", mtime=1_700_000_000.0)
        victim = _mk_run(runs, "d_20261001_000000.jsonl", mtime=1_600_000_000.0)

        real_remove = retention._remove

        def flaky(path: Path) -> bool:
            if path.name.endswith(".jsonl"):
                raise OSError("Input/output error")
            return real_remove(path)

        monkeypatch.setattr(retention, "_remove", flaky)
        result = retention.prune_runs(runs, tmp_path / "reports", keep=1)

        assert result["skipped"] == ["d_20261001_000000.jsonl"]
        assert victim.exists()

    def test_keep_defaults_to_the_config_value(self, tmp_path, monkeypatch):
        retention = _retention()
        runs = tmp_path / "runs"
        for i in range(3):
            _mk_run(runs, f"r{i}_2026100{i}_000000.jsonl", mtime=1_600_000_000.0 + i)
        monkeypatch.setattr(config, "EVAL_RETENTION_KEEP", 1)

        result = retention.prune_runs(runs, tmp_path / "reports")

        assert result["keep"] == 1
        assert _names(tmp_path, "runs") == {"r2_20261002_000000.jsonl"}


EVAL_BASE = "/api/eval-harness"
RUN_NAME = "batch87_20261008_000000.jsonl"


class _RecordingHttpClient:
    def __init__(self, posts, order):
        self._posts = posts
        self._order = order

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, *, json, headers):
        self._posts.append(url)
        self._order.append("java_record")
        return SimpleNamespace(status_code=200, text="ok")


@pytest.fixture
def eval_dirs(monkeypatch, tmp_path):
    """REPORTS_DIR / DATASET_DIR / runner._RUNS_DIR 都是模块级量：不 patch 就写真目录。"""
    import app.api.eval_harness as eval_api
    from app.core.eval_harness import runner as runner_mod

    reports = tmp_path / "reports"
    runs = tmp_path / "runs"
    monkeypatch.setattr(eval_api, "REPORTS_DIR", reports)
    monkeypatch.setattr(eval_api, "DATASET_DIR", tmp_path / "eval_sets")
    monkeypatch.setattr(runner_mod, "_RUNS_DIR", runs)
    return SimpleNamespace(reports=reports, runs=runs, root=tmp_path)


@pytest.fixture
def client():
    from app.main import create_app

    return TestClient(create_app(), headers=AUTH_HEADERS)


@pytest.fixture
def eval_prune_calls(monkeypatch, eval_run_fakes):
    calls: list[dict] = []
    import app.core.eval_harness.retention as retention_mod

    def fake_prune(*args, **kwargs):
        eval_run_fakes.order.append("prune_runs")
        calls.append({"args": args, "kwargs": kwargs})
        return {"keep": 50, "deleted_run_files": [], "deleted_artifacts": [], "skipped": []}

    monkeypatch.setattr(retention_mod, "prune_runs", fake_prune)
    return calls


@pytest.fixture
def eval_run_fakes(monkeypatch, eval_dirs):
    """把 /run 的四步（record → score → report → Java 回调）换成记录顺序的替身。"""
    from app.core.eval_harness import report as report_mod
    from app.core.eval_harness import runner as runner_mod
    from app.core.eval_harness import score as score_mod
    from app.core.eval_harness.schemas import MetricResult

    order: list[str] = []
    posts: list[str] = []

    def fake_run_dataset(*args, **kwargs):
        order.append("run_dataset")
        eval_dirs.runs.mkdir(parents=True, exist_ok=True)
        path = eval_dirs.runs / RUN_NAME
        path.write_text("", encoding="utf-8")
        return path

    async def fake_score_run(run_file, **kwargs):
        order.append("score_run")
        return MetricResult(run_file=run_file, overall={"retrieval_hit@5": 1.0},
                            meta={"record_count": 1})

    def fake_save_report(result, reports_dir, title=""):
        order.append("save_report")
        return Path(reports_dir) / "x_report.md"

    monkeypatch.setattr(runner_mod, "run_dataset", fake_run_dataset)
    monkeypatch.setattr(score_mod, "score_run", fake_score_run)
    monkeypatch.setattr(report_mod, "save_report", fake_save_report)
    monkeypatch.setattr(config, "JAVA_BACKEND_URL", "http://java:8080/api")
    monkeypatch.setattr("httpx.Client", lambda **kwargs: _RecordingHttpClient(posts, order))
    return SimpleNamespace(order=order, posts=posts)


def _run_payload() -> dict:
    return {"label": "batch87", "knowledge_base_id": 1,
            "samples": [{"query_id": "q1", "query": "问题", "expected_document_ids": ["1"]}]}


class TestRunEndpointTriggersRetention:
    def test_run_prunes_after_its_own_artifacts_are_written(
            self, client, eval_dirs, eval_run_fakes, eval_prune_calls):
        resp = client.post(f"{EVAL_BASE}/run", json=_run_payload())
        assert resp.status_code == 200, resp.text

        order = eval_run_fakes.order
        assert order[:3] == ["run_dataset", "score_run", "save_report"], (
            "评估自身的三步顺序不该被本批改动"
        )
        assert order.index("prune_runs") > order.index("save_report"), (
            "本次产物还没写齐就清扫，会把它们当孤儿删掉"
        )
        assert len(eval_prune_calls) == 1, "/run 写完产物必须就地清扫一次"

        call = eval_prune_calls[0]
        assert [Path(p).resolve() for p in call["args"]] == [
            eval_dirs.runs.resolve(), eval_dirs.reports.resolve()], (
            "清扫对象必须是 runner 的 runs 目录与 API 的 REPORTS_DIR——不能自己再推一遍路径"
        )
        assert call["kwargs"].get("protect") == RUN_NAME, (
            "刚写完的这条要显式保护：时间戳是秒级，同秒的两条里它未必排在前面"
        )
        assert "keep" not in call["kwargs"], (
            "keep 不在端点里写死，留给 EVAL_RETENTION_KEEP"
        )

    def test_run_does_not_await_the_sweep_on_the_event_loop(self):
        """同步 file IO（网络卷上的 stat+unlink）不许压在事件循环上——沿用第 54/81 批口径。"""
        text = EVAL_API.read_text(encoding="utf-8")
        assert re.search(r"to_thread\(\s*\n?\s*retention\.prune_runs", text), (
            "/run 的清扫没走 asyncio.to_thread"
        )

    def test_sweep_and_java_callback_both_happen(self, client, eval_dirs, eval_run_fakes,
                                                 eval_prune_calls):
        resp = client.post(f"{EVAL_BASE}/run", json=_run_payload())
        assert resp.status_code == 200
        assert eval_run_fakes.posts == ["http://java:8080/api/internal/eval-harness/record"]
        assert len(eval_prune_calls) == 1

    def test_prune_failure_does_not_fail_a_completed_run(self, client, eval_dirs,
                                                         eval_run_fakes, monkeypatch):
        import app.core.eval_harness.retention as retention_mod

        def boom(*args, **kwargs):
            raise RuntimeError("volume not writable")

        monkeypatch.setattr(retention_mod, "prune_runs", boom)
        resp = client.post(f"{EVAL_BASE}/run", json=_run_payload())
        assert resp.status_code == 200, "结果已落盘，清扫失败不能把评估判失败"

    def test_response_shape_is_unchanged(self, client, eval_dirs, eval_run_fakes,
                                         eval_prune_calls):
        """保留结果只进日志：不给 /run 的响应体加键，api.md 与前端类型都不必跟改。"""
        resp = client.post(f"{EVAL_BASE}/run", json=_run_payload())
        assert set(resp.json().keys()) == {"run_file", "summary", "meta"}


class TestDocsRecordThePolicy:
    def test_environment_doc_lists_the_key(self):
        text = ENVIRONMENT_DOC.read_text(encoding="utf-8")
        assert "EVAL_RETENTION_KEEP" in text, (
            "给运维的变量表里没有这一行，等于保留口径只写在代码注释里"
        )

    def test_env_example_carries_the_key(self):
        assert "EVAL_RETENTION_KEEP" in ENV_EXAMPLE.read_text(encoding="utf-8")

    def test_ops_doc_records_the_choice_and_the_leftovers(self):
        text = OPS_DOC.read_text(encoding="utf-8")
        assert "EVAL_RETENTION_KEEP" in text
        assert "prune_runs" in text, "文档要指名清理函数，否则运维无从核对它在被调用"
        # 并发清扫（helm 两副本共用一块 RWX 卷）
        assert re.search(r"清扫[^。\n]*副本|副本[^。\n]*清扫", text), (
            "两副本在同一卷上并发清扫的行为必须写下来"
        )
        # judge 缓存不归这个口径管
        assert re.search(r"judge 缓存[^。\n]*(不在|不受|保留)", text), (
            "数量口径只管 runs/reports，judge 缓存的生长必须显式说明不在其内"
        )
        # Java 摘要行不删，且会活得比明细久
        assert re.search(r"eval_harness_runs[^。\n]*(不删|保留|活)", text), (
            "删了 Python 侧文件后 eval_harness_runs 的行仍在，这是口径的已知代价"
        )
