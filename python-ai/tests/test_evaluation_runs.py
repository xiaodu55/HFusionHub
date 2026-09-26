from app.core.rag.evaluation_runs import EvaluationRunStore


def _report(recall: float = 1.0):
    return {
        "summary": {
            "top_k": 5,
            "case_count": 2,
            "precision_at_k": 0.8,
            "recall_at_k": recall,
            "mean_reciprocal_rank": 0.75,
        },
        "cases": [
            {"case_id": "pass", "recall_at_k": 1.0, "query": "do not persist me"},
            {"case_id": "miss", "recall_at_k": recall, "query": "nor me"},
        ],
    }


def test_evaluation_run_store_persists_sanitized_history(tmp_path):
    database_path = tmp_path / "evaluation-runs.db"
    store = EvaluationRunStore(str(database_path))

    recorded = store.record(_report(recall=0.0), knowledge_base_id=8, label="release candidate")
    reloaded = EvaluationRunStore(str(database_path)).list(knowledge_base_id=8)

    assert recorded.failed_case_ids == ["miss"]
    assert len(reloaded) == 1
    assert reloaded[0]["label"] == "release candidate"
    assert reloaded[0]["failed_case_ids"] == ["miss"]
    assert "query" not in reloaded[0]


def test_evaluation_run_store_filters_by_knowledge_base(tmp_path):
    store = EvaluationRunStore(str(tmp_path / "evaluation-runs.db"))
    store.record(_report(), knowledge_base_id=1)
    store.record(_report(), knowledge_base_id=2)

    assert len(store.list(knowledge_base_id=1)) == 1
    assert store.list(knowledge_base_id=1)[0]["knowledge_base_id"] == 1


class TestEvaluationHistoryPersistenceConfigured:
    """评测历史是控制台的读面，落点必须显式配置，否则三套拓扑里都在镜像层。

    默认值 ./data/rag_evaluation_runs.db 在容器里解析成 /app/data（WORKDIR=/app），
    而卷只挂在 /data（compose）与 /app/uploads、/app/audit-queue（helm）——
    evaluation_runs.py 顶部"Durable"与 rag.py:233"durable metric history"
    两句声称在 shipped 拓扑里本就不成立。helm 侧是另一回事：见下面的测试。
    """

    @staticmethod
    def _compose_env(rel: str) -> dict:
        import pathlib

        import yaml

        root = pathlib.Path(__file__).resolve().parents[2]
        doc = yaml.safe_load((root / rel).read_text(encoding="utf-8"))
        return doc["services"]["python-ai"]["environment"]

    def test_compose_files_set_the_evaluation_history_path(self):
        import pathlib

        for rel in ("docker/docker-compose.yml", "deploy/docker-compose.prod.yml"):
            env = self._compose_env(rel)
            assert "RAG_EVALUATION_DB_PATH" in env, f"{rel} 未配置评测历史落点"
            path = pathlib.PurePosixPath(env["RAG_EVALUATION_DB_PATH"])
            assert path.parent == pathlib.PurePosixPath("/data"), (
                f"{rel} 的评测历史必须直接落在已挂载的 /data 上：{path}"
            )
            # store 只接文件路径（evaluation_runs.py:67 拿 parent 建目录），
            # 给个目录会静默造出一个打不开的库，故这里钉死后缀
            assert path.suffix == ".db", f"{rel} 的落点不是 SQLite 文件：{path}"

    def test_helm_does_not_share_the_evaluation_sqlite_across_replicas(self):
        """helm 是 2 副本（values.yaml pythonAi.replicas），共享单个 SQLite 文件会互踩锁。

        本批刻意不给它配落点，并把原因写进 values.yaml——按 Pod 分目录会让"最近评测"
        面板只看到应答副本的历史，读面语义不如持久性先解决。
        """
        import pathlib
        import re

        chart = pathlib.Path(__file__).resolve().parents[2] / "deploy/helm/hfusionhub"
        text = (chart / "templates/python.yaml").read_text(encoding="utf-8")
        env_names = set(re.findall(r"^ *- name: (\S+)$", text, re.MULTILINE))
        assert "RAG_EVALUATION_DB_PATH" not in env_names, (
            "helm 不该把评测历史指向共享卷：2 副本共写一个 SQLite 文件"
        )

        values = (chart / "values.yaml").read_text(encoding="utf-8")
        assert "RAG_EVALUATION_DB_PATH" in values, (
            "values.yaml 必须按变量名记下这个刻意不配的决策，否则下一个人会当遗漏补上"
        )


def test_evaluation_run_store_honours_the_config_key(tmp_path, monkeypatch):
    from app.core.rag import evaluation_runs as er_mod
    from app.utils.config import config

    monkeypatch.setattr(config, "RAG_EVALUATION_DB_PATH", str(tmp_path / "cfg.db"))
    er_mod.reset_evaluation_run_store()
    try:
        assert er_mod.get_evaluation_run_store()._path == tmp_path / "cfg.db"
    finally:
        er_mod.reset_evaluation_run_store()
