"""第九十二批：冻结摘要必须与行尾无关。

起因：CI 的四个 `Verify frozen suite integrity (SHA-256)` 步骤全红，报
`computed 15b0ea64… != pinned b02b9dd3…`，而同一命令在本地全绿。取数结果是
`cases.jsonl` 的 **git blob 是 LF（79,321 字节、0 个 CR）**，本地工作副本是
**CRLF（79,541 字节、220 个 CR = 每行一个）**：套件当年在 Windows 上由
`build_suite.py` 生成（`write_text` 默认按平台翻译换行），钉进 manifest 的是 CRLF
字节的摘要；`.gitattributes` 里没有 `*.jsonl` 规则，Linux runner 检出 blob 原文 ⇒
`read_bytes()` 摘要必然是另一个。也就是说**这条门禁在本地永远绿、在 CI 永远红**，
它测的是"这台机器的换行风格"，不是"用例被改过没有"。

判据分三层：钉住的值本身要写成行尾无关的形态（1、2）、实现要在任何形态下读出同一个
内容摘要（3、4、5、8）、生成侧要不再按平台翻译换行（6），最后是不把规则抄成四份
（7）。其中 6/8 在当前 Windows 工作副本上是红的、在 Linux 上是绿的——这正是它们要
钉住的东西：一条判据不该随检出平台变颜色。
"""

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path

import eval_baseline
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # python-ai/
REPO_ROOT = PROJECT_ROOT.parent
BASELINE_DIR = PROJECT_ROOT / "evaluation" / "baseline"

SUITE_DIRS = ["suite", "suite_bid", "suite_bid_it", "suite_bid_construction"]

# 基线 -> 它绑定哪个套件。offline/bid* 由 CI 的离线门禁消费，retrieval/runtime 由
# 运行时轨与纯检索直测消费；六份都钉同一个字段，所以一起判。
BASELINE_TO_SUITE = {
    "offline_baseline.json": "suite",
    "retrieval_baseline.json": "suite",
    "runtime_baseline.json": "suite",
    "bid_baseline.json": "suite_bid",
    "bid_it_baseline.json": "suite_bid_it",
    "bid_construction_baseline.json": "suite_bid_construction",
}


def canonical_lf_digest(data: bytes) -> str:
    """判据自己的独立实现：把 CRLF 折成 LF 再取 SHA-256。

    刻意不复用被测函数——否则"实现把规则写错"和"判据跟着一起错"就分不开了。
    """
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def _helper():
    helper = getattr(eval_baseline, "suite_content_digest", None)
    if helper is None:
        pytest.fail(
            "eval_baseline.suite_content_digest 不存在：冻结摘要没有单一规则，"
            "每个调用点各抄一遍 hashlib.sha256(read_bytes())"
        )
    return helper


class TestPinnedValuesAreLineEndingFree:
    @pytest.mark.parametrize("suite_dir", SUITE_DIRS)
    def test_suite_manifest_pin_is_not_platform_dependent(self, suite_dir: str):
        base = PROJECT_ROOT / "evaluation" / suite_dir
        raw = (base / "cases.jsonl").read_bytes()
        pinned = str(json.loads(
            (base / "suite_manifest.json").read_text(encoding="utf-8")
        )["cases_sha256"])
        expected = canonical_lf_digest(raw)
        cr_count = raw.count(b"\r")
        assert pinned == expected, (
            f"{suite_dir}: 钉的是 {pinned[:12]}…，而行尾无关摘要是 {expected[:12]}…；"
            f"工作副本含 {cr_count} 个 CR ⇒ Linux 检出读到的字节不同，CI 必然红"
        )

    @pytest.mark.parametrize(("baseline", "suite_dir"), sorted(BASELINE_TO_SUITE.items()))
    def test_baseline_binding_follows_the_suite_pin(self, baseline: str, suite_dir: str):
        base = PROJECT_ROOT / "evaluation" / suite_dir
        raw = (base / "cases.jsonl").read_bytes()
        digest = canonical_lf_digest(raw)
        bound = str(json.loads(
            (BASELINE_DIR / baseline).read_text(encoding="utf-8")
        )["suite_sha256"])
        assert bound == digest, (
            f"{baseline} 绑的是 {bound[:12]}…，应是行尾无关摘要 {digest[:12]}…"
        )


class TestDigestRuleIsSingleAndLineEndingFree:
    def test_crlf_and_lf_digests_are_the_same_content(self, _helper):
        cases = b'{"id": "a"}\n{"id": "b"}\n'
        crlf = cases.replace(b"\n", b"\r\n")
        assert _helper.__name__ == "suite_content_digest"
        assert _helper(crlf) == _helper(cases) == canonical_lf_digest(cases), (
            "摘要规则不是 CRLF→LF 规范化：换个检出平台就换哈希"
        )

    def test_verify_accepts_both_line_endings(self, tmp_path, _helper):
        """CI 拿到 LF、Windows 开发机拿到 CRLF，两者必须都过同一份 manifest。"""
        cases_lf = b'{"id": "a"}\n{"id": "b"}\n'
        manifest = tmp_path / "suite_manifest.json"
        cases_file = tmp_path / "cases.jsonl"
        manifest.write_text(
            json.dumps({"cases_sha256": canonical_lf_digest(cases_lf)}) + "\n", encoding="utf-8"
        )

        cases_file.write_bytes(cases_lf)
        eval_baseline.verify_suite_integrity(cases_file, manifest)

        cases_file.write_bytes(cases_lf.replace(b"\n", b"\r\n"))
        eval_baseline.verify_suite_integrity(cases_file, manifest)

    def test_verify_still_rejects_real_tampering(self, tmp_path):
        """规范化行尾不等于放弃篡改检测：内容变了必须还是红。"""
        cases_lf = b'{"id": "a"}\n{"id": "b"}\n'
        manifest = tmp_path / "suite_manifest.json"
        cases_file = tmp_path / "cases.jsonl"
        manifest.write_text(
            json.dumps({"cases_sha256": canonical_lf_digest(cases_lf)}) + "\n", encoding="utf-8"
        )
        cases_file.write_bytes(b'{"id": "a"}\n{"id": "c"}\n')
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            eval_baseline.verify_suite_integrity(cases_file, manifest)

    def test_real_suite_still_verifies_after_rebind(self):
        """真数据在真实现下要过——这条把上面几条合成判据钉在仓库实际状态上。"""
        for suite_dir in SUITE_DIRS:
            base = PROJECT_ROOT / "evaluation" / suite_dir
            eval_baseline.verify_suite_integrity(base / "cases.jsonl", base / "suite_manifest.json")


class TestGenerationSideStopsTranslatingNewlines:
    @pytest.mark.parametrize("suite_dir", SUITE_DIRS)
    def test_emit_cases_writes_lf_bytes(self, suite_dir: str, tmp_path):
        """`write_text` 默认 newline=None ⇒ Windows 写 CRLF、Linux 写 LF。

        生成侧一旦按平台翻译换行，同一个套件在两台机器上就是两份字节，冻结摘要也跟着分叉。
        """
        build_suite = _load_module(
            f"build_suite_{suite_dir}", PROJECT_ROOT / "evaluation" / suite_dir / "build_suite.py"
        )
        out = tmp_path / "emitted.jsonl"
        build_suite.emit_cases([{"id": "b"}, {"id": "a"}], out)
        data = out.read_bytes()
        cr_count = data.count(b"\r")
        assert b"\r" not in data, f"{suite_dir}: emit 写了平台换行（含 {cr_count} 个 CR）"

    @pytest.mark.parametrize("suite_dir", SUITE_DIRS)
    def test_pinned_suite_survives_a_crlf_checkout(self, suite_dir: str, tmp_path):
        """钉值换成 LF 形态之后，把真数据摆成 CRLF 也必须过——防"只改钉值、忘了改校验"。

        现在它红在 LF 那一轮（钉的是 CRLF 字节，这正是 CI 的形态）；改完实现两轮都要绿。
        """
        base = PROJECT_ROOT / "evaluation" / suite_dir
        raw = (base / "cases.jsonl").read_bytes()
        lf = raw.replace(b"\r\n", b"\n")
        for label, form in (("LF", lf), ("CRLF", lf.replace(b"\n", b"\r\n"))):
            cases_file = tmp_path / f"{suite_dir}-{label}.jsonl"
            cases_file.write_bytes(form)
            eval_baseline.verify_suite_integrity(cases_file, base / "suite_manifest.json")


class TestTheRuleIsNotCopiedAround:
    def test_retrieval_live_uses_the_shared_helper(self):
        src = (PROJECT_ROOT / "scripts" / "eval_retrieval_live.py").read_text(encoding="utf-8")
        assert "hashlib.sha256(Path(cases_path).read_bytes())" not in src, (
            "eval_retrieval_live 自己抄了一遍裸字节摘要：它会和 verify_suite_integrity 分叉"
        )
        assert "from eval_baseline import" in src and "suite_content_digest" in src, (
            "eval_retrieval_live 没有走共享摘要函数"
        )

    def test_verify_uses_the_shared_helper(self):
        src = inspect.getsource(eval_baseline.verify_suite_integrity)
        assert "suite_content_digest(" in src, "verify_suite_integrity 没有走共享摘要函数"
        assert "hashlib.sha256(" not in src, "verify_suite_integrity 自己又抄了一遍裸字节摘要"

    def test_jsonl_line_endings_are_declared_for_git(self):
        """`.gitattributes` 里必须有 `*.jsonl` 规则：没有它，检出侧的字节由
        开发者的 core.autocrlf 决定，冻结数据文件的 `git diff` 也就不可读。"""
        attrs = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
        rules = [line for line in attrs.splitlines() if line.strip() and not line.startswith("#")]
        matching = [line for line in rules if line.split()[0] == "*.jsonl"]
        assert matching, ".gitattributes 没有 *.jsonl 规则：blob 与工作副本的行尾可以不同"
        assert "eol=lf" in matching[0], f"*.jsonl 规则应钉成 LF：{matching[0]}"
