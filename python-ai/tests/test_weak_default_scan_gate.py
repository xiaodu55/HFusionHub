r"""检查 21 的门：弱默认值扫描器必须拦得住「照抄 `docker/.env.example` 就上线」。

第一百一十六批的取证链（本轮 A 段实测）：

  - 真机跑 `bash scripts/rotate-secrets.sh --check`（读 `docker/.env`）报
    `[ok] 未发现弱默认值`、退出码 0；逐键比对已入库的 `docker/.env.example`，
    13 个键里**没有一个等于示例占位值** ⇒ 本地这份确实轮换过。
  - 但把 `docker/.env.example` 原样复制成 `.env` 再喂给**同一个真脚本**，
    10 个占位键（8 个 `changeme-*` ＋ `minioadmin` ＋ `sk-replace-with-your-own-key`）
    它只点名 1 个（`minioadmin`），退出码**还是 0**。
  - 根因在 `scripts/rotate-secrets.sh` 的 `WEAK_PATTERNS`（改前在 :29）：里面写的是 `change-me`（带连字符），
    而自家示例文件用的是 `changeme`——**扫描器与它要保护的那份样例不同源**。

⇒ `docs/PRODUCTION_OPS.md:16` 当时那句「`--check` 可扫描弱默认值」原本只在有人手打
`admin`/`123456` 时成立，最常见的失效模式（照抄仓库里公开的示例）一路放行。
本批把那句口径改成"有一处门拦着"，代价是扫描器自己得先被拦一次：
判据是**行为**而不是把脚本里那份模式抄到 python 侧（抄过来只会把 bug 复述一遍）。

本文件钉住：真仓库绿 + 接线 + 适用面下界、负控/正控各跑真 bash、
恒 0 退出码红、漏点名红、一律红（正控失败）、示例文件失去占位符红、
脚本或示例缺失红、没有 bash 时不许默认绿，另加两条纯函数解析形态的判定。
"""

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "scripts" / "static-checks.py"
SCRIPT = REPO / "scripts" / "rotate-secrets.sh"
EXAMPLE = REPO / "docker" / ".env.example"

BASH = shutil.which("bash")
requires_bash = pytest.mark.skipif(BASH is None, reason="这条门判的是 bash 脚本的行为，本机没有 bash")


def _load_checker():
    spec = importlib.util.spec_from_file_location("hfusionhub_weak_default_scan_gate", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── 假扫描器：只用来造出各条红路径，不参与真仓库判定 ──────────────────────────

# 点名全部键但恒 0 —— 第一百一十六批改前的形态（退出码当不了门）
FAKE_NAMES_ALL_EXIT_ZERO = """#!/usr/bin/env bash
while IFS= read -r line; do
  case "$line" in \\#*|'') continue ;; esac
  [[ "$line" == *=* ]] || continue
  echo "  [!] ${line%%=*} 使用弱默认值，必须轮换"
done < "$ROTATE_SECRETS_ENV_FILE"
exit 0
"""

# 只点名第一个键、退出码 1 —— 漏点名（改前"1/10"的形状）
FAKE_NAMES_ONE = """#!/usr/bin/env bash
while IFS= read -r line; do
  case "$line" in \\#*|'') continue ;; esac
  [[ "$line" == *=* ]] || continue
  echo "  [!] ${line%%=*} 使用弱默认值，必须轮换"
  break
done < "$ROTATE_SECRETS_ENV_FILE"
exit 1
"""

# 一律红：连强随机值也拦 —— 会被绕过的门
FAKE_ALWAYS_RED = """#!/usr/bin/env bash
echo "  [!] ZZZ_NOT_FROM_INPUT 使用弱默认值，必须轮换"
exit 1
"""


def _fake(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake-rotate.sh"
    script.write_text(body, encoding="utf-8")
    return script


@pytest.fixture
def gate(tmp_path, monkeypatch):
    module = _load_checker()
    monkeypatch.setattr(module, "problems", [])
    return module


def _text(offenders) -> str:
    return "\n".join(offenders)


# ── 一、真仓库：绿 + 接线 + 适用面 ──────────────────────────────────────────


class TestRealRepo:
    @requires_bash
    def test_repo_is_green(self, gate):
        offenders, count = gate._weak_scan_offenders()
        assert offenders == [], _text(offenders)
        assert count == 10, f"负控的占位键数应当是 10，实际 {count}"

    @requires_bash
    def test_repo_prints_ok_line(self, gate, capsys):
        gate.problems.clear()
        gate.check_weak_default_scan()
        out = capsys.readouterr().out
        assert "弱默认值扫描器" in out and "10 个占位键" in out
        assert gate.problems == []

    def test_wired_into_default_full_run(self):
        """并入默认全跑档，否则只在显式传参时生效（第八十三批的接线哑火形态）。"""
        source = CHECKER.read_text(encoding="utf-8")
        main_body = source[source.index("def main()"):]
        assert "--weak-default-scan" in main_body
        all_mode = main_body[
            main_body.index("args = parser.parse_args()"): main_body.index("if args.tenant_columns:")
        ]
        assert all_mode.count("args.weak_default_scan") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_weak_default_scan()" in main_body

    def test_scanner_source_is_not_the_oracle(self, gate):
        """判据不许抄脚本里那份模式——抄过来只会把 bug 复述一遍。"""
        script_patterns = SCRIPT.read_text(encoding="utf-8")
        weak_line = [ln for ln in script_patterns.splitlines() if ln.startswith("WEAK_PATTERNS=")]
        assert weak_line, "脚本里那份弱模式被改名或删掉了，这条判定要跟它一起改"
        assert "changeme" not in weak_line[0], (
            f"占位符形态被并进了 WEAK_PATTERNS，oracle 与判据同源：{weak_line[0]}"
        )
        assert gate.PLACEHOLDER_MARKERS, "python 侧那份独立判据不能是空的"

    def test_lower_bound_matches_example(self, gate):
        """下界常量与示例文件实际占位键数同源（改一边不改另一边就是假绿/假红）。"""
        keys = gate._example_placeholder_keys()
        assert len(keys) == gate.PLACEHOLDER_KEYS_LOWER_BOUND, (
            f"示例里量到 {sorted(keys)}，"
            f"下界却钉在 {gate.PLACEHOLDER_KEYS_LOWER_BOUND}"
        )

    def test_every_changeme_key_is_in_the_negative_control(self, gate):
        """改前漏掉的那 9 个键现在必须在负控集合里（本轮取证的具体形状，防退化）。"""
        keys = gate._example_placeholder_keys()
        rows = dict(gate._env_rows(EXAMPLE))
        changeme = {k for k, v in rows.items() if v.lower().startswith("changeme")}
        assert len(changeme) == 8, f"示例里 `changeme-*` 应当是 8 个，实际 {sorted(changeme)}"
        assert changeme <= keys, f"漏了 {sorted(changeme - keys)}"
        assert {"MINIO_ROOT_USER", "DEEPSEEK_API_KEY"} <= keys


# ── 二、真脚本的两条行为契约（不经过检查器，直接跑 bash）─────────────────────


class TestRealScriptBehaviour:
    @requires_bash
    def test_example_input_now_fails_the_scan(self, tmp_path):
        env = dict(os.environ, ROTATE_SECRETS_ENV_FILE=str(EXAMPLE).replace("\\", "/"))
        result = subprocess.run(
            [BASH, str(SCRIPT), "--check"], capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, timeout=120,
        )
        assert result.returncode == 1, f"照抄示例必须判红，实际退出码 {result.returncode}"
        assert "未发现弱默认值" not in result.stdout

    @requires_bash
    def test_override_is_honoured(self, tmp_path):
        """`ROTATE_SECRETS_ENV_FILE` 不生效的话，负控其实是在扫本地真 `.env`——这条防它退回硬编码。"""
        weak = tmp_path / "custom.env"
        weak.write_text("MYSQL_PASSWORD=change\n", encoding="utf-8")
        env = dict(os.environ, ROTATE_SECRETS_ENV_FILE=str(weak).replace("\\", "/"))
        result = subprocess.run(
            [BASH, str(SCRIPT), "--check"], capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, timeout=120,
        )
        assert str(weak).replace("\\", "/") in result.stdout, result.stdout
        assert result.returncode == 1, f"自定义路径里的弱值必须判红，实际退出码 {result.returncode}"


# ── 三、各条红路径（假扫描器）──────────────────────────────────────────────


class TestRedPaths:
    @pytest.fixture
    def wired(self, gate, tmp_path):
        """把脚本换成假扫描器，示例文件仍是真的（判据形状要跟着真实占位键集合走）。"""
        example = tmp_path / ".env.example"
        example.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        gate.DOCKER_ENV_EXAMPLE = example
        gate.ROTATE_SCRIPT = _fake(tmp_path, FAKE_NAMES_ALL_EXIT_ZERO)
        return gate

    def test_exit_zero_never_counts_as_a_gate(self, wired):
        offenders, _ = wired._weak_scan_offenders()
        assert any("退出码 0" in o for o in offenders), offenders
        assert not any("没点名" in o for o in offenders), "这条假扫描器点名齐全，不该同时报漏点名"

    def test_missing_names_are_red(self, wired):
        wired.ROTATE_SCRIPT = _fake(wired.DOCKER_ENV_EXAMPLE.parent, FAKE_NAMES_ONE)
        offenders, count = wired._weak_scan_offenders()
        hit = [o for o in offenders if "没点名" in o]
        assert len(hit) == 1, offenders
        assert f"（{count - 1}/{count}）" in hit[0], hit[0]

    def test_always_red_fails_the_positive_control(self, wired):
        wired.ROTATE_SCRIPT = _fake(wired.DOCKER_ENV_EXAMPLE.parent, FAKE_ALWAYS_RED)
        offenders, _ = wired._weak_scan_offenders()
        assert any("正控不成立" in o for o in offenders), offenders

    def test_example_losing_placeholders_is_red(self, wired):
        wired.DOCKER_ENV_EXAMPLE.write_text(
            "MYSQL_PASSWORD=changeme-a\nREDIS_PASSWORD=changeme-b\n", encoding="utf-8"
        )
        offenders, count = wired._weak_scan_offenders()
        assert any("适用面缩小了" in o for o in offenders), offenders
        assert count == 2, f"应当只量到 2 个占位键，实际 {count}"

    def test_missing_script_is_red(self, wired):
        wired.ROTATE_SCRIPT = wired.DOCKER_ENV_EXAMPLE.parent / "nope.sh"
        offenders, _ = wired._weak_scan_offenders()
        assert any("扫描器本身不存在" in o for o in offenders), offenders

    def test_missing_example_is_red(self, wired):
        wired.DOCKER_ENV_EXAMPLE = wired.DOCKER_ENV_EXAMPLE.parent / "nope.example"
        offenders, _ = wired._weak_scan_offenders()
        assert any("占位符样例不存在" in o for o in offenders), offenders

    def test_no_bash_is_not_silently_green(self, wired, monkeypatch):
        monkeypatch.setattr(wired, "_find_bash", lambda: None)
        offenders, _ = wired._weak_scan_offenders()
        assert any("不能因为跑不了就当绿" in o for o in offenders), offenders


# ── 四、纯函数解析形态 ──────────────────────────────────────────────────────


class TestParsers:
    def test_named_key_line_shape(self, gate):
        stdout = (
            "── 检查 x 中的弱默认值 ──\n"
            "  [!] MYSQL_ROOT_PASSWORD 使用弱默认值，必须轮换\n"
            "\t[!] DEEPSEEK_API_KEY 使用弱默认值\n"
            "  [ok] 未发现弱默认值\n"
            "  普通行里有 [!] 但不带键名\n"
        )
        # 缩进可以变（tab / 空格），但 `[!]` 与键名之间的那个空格是脚本自己写死的
        # （现 rotate-secrets.sh:59）；真改没了就是改名，宁可判 0/10 红，不猜形状。
        assert gate._scan_named_keys(stdout) == {"MYSQL_ROOT_PASSWORD", "DEEPSEEK_API_KEY"}

    def test_env_rows_skips_comments_and_valueless_lines(self, gate, tmp_path):
        f = tmp_path / "x.env"
        f.write_text("# 注释\n\n  KEY_A =  v1 \nNOEQUALSIGN\nexport KEY_B=v2\n", encoding="utf-8")
        gate.DOCKER_ENV_EXAMPLE = f
        assert gate._env_rows(f) == [("KEY_A", "v1"), ("export KEY_B", "v2")]

    def test_positive_control_fixture_keeps_the_same_key_set(self, gate):
        """正控必须与负控同键集，否则"绿"只是因为少了要被扫的行。"""
        strong_keys = {line.split("=", 1)[0].strip()
                       for line in gate._strong_env_file_fixture().splitlines() if "=" in line}
        example_keys = {key for key, _ in gate._env_rows(EXAMPLE)}
        assert example_keys <= strong_keys, f"正控缺键 {sorted(example_keys - strong_keys)}"
        assert "MODEL_CREDENTIAL_ENCRYPTION_KEY" in strong_keys
