"""requirements.txt 里的 Windows-only 锁必须带平台 marker，否则 Linux 装不上（第八十八批）。

红因是本机第一次真跑 `docker build -f deploy/Dockerfile.python`（第八十四批把"首次构建即是
它的验收"留在 docs/PRODUCTION_OPS.md §10.2）——pip 在 linux/amd64 上死于：

    ERROR: Could not find a version that satisfies the requirement pywin32==312
           (from versions: none)

锁由 Windows 开发机的 pip-compile 生成（`requirements.txt:5` 记录的命令行没有钉
`--python-platform`），于是 `docker` SDK 在 Windows 分支上的传递依赖 `pywin32` 以**无
marker** 的形式进了锁；而 PyPI 上 pywin32 312 只有 21 个 win32 wheel、没有 sdist ⇒ Linux
无解。宿主是 Windows，pip 解析得动，所以这条缺陷在开发机上完全不可见，CI 里 docker-build /
eval-nightly 又都死于同一行（本地看到的最新 main push 是 2026-09-22 起跑即败）。

同一次构建修完 marker 之后撞到的第二条（`--require-hashes` 是 pip 在"任一条目带哈希"时
**自动**开启的，锁尾手工追加的三条 opentelemetry 没有哈希，于是 collect 完才整体报错）
不限平台，CI 的 `pip install -r requirements.txt` 与镜像构建一起中招。它的修法是把 OTel
从锁尾拿掉、改由 `deploy/Dockerfile.python` 显式钉版安装（与 arq 同一先例），因此本文件
既钉"锁的可安装面"，也钉"OTel 只有一个声明处"。

本文件钉的是两件事：凡上游只在 Windows 上需要的包，锁里必须带 sys_platform marker；
而一旦这份锁采用哈希锁定，每一条 pin 都必须带哈希。
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "python-ai" / "requirements.txt"

# 两份锁都要过同一套口径：`requirements.txt` 是镜像装的，`requirements-dev.txt` 是 CI 的
# python job 与开发态装的（ci.yml:155/178/215、plugin-security.yml:21、eval-nightly.yml:168
# 都在 ubuntu-latest 上 `pip install -r requirements-dev.txt`）。它们出自同一次
# 单平台 pip-compile，所以同一个 marker 缺陷是**两份锁一起坏的**——只修镜像那份，CI 照旧死。
LOCKS = [REQUIREMENTS, ROOT / "python-ai" / "requirements-dev.txt"]

# 上游声明就是 Windows-only 的包（pywin32 由 docker SDK 引入，win32-setctime 由 loguru 引入）。
# 两者在锁里都应当带 `sys_platform == "win32"`；缺 marker 时 pywin32 让 Linux 解析直接失败，
# win32-setctime 虽然能装上（纯 Python wheel），但会在非 Windows 上装进一个用不到的包。
WINDOWS_ONLY_PACKAGES = {"pywin32", "win32-setctime"}

# 反过来：只在**非** Windows 上才需要的包。uvicorn 0.27.0 的 `standard` extra 声明是
# `uvloop!=0.15.0,!=0.15.1,>=0.14.0; (sys_platform != 'win32') and (platform_python_implementation != 'PyPy')`
# （PyPI 的 requires_dist 原文），pip-compile 在 Windows 宿主上按 marker 为假直接不写它 ⇒
# 锁里既没有 uvloop 也没有它的哈希。Linux 侧 marker 为真，pip 只好拿 extra 自带的 `>=` 规格去
# 解析，而 `--require-hashes` 不接受非 `==` 的传递依赖：
#   2582.1 ERROR: In --require-hashes mode, all requirements must have their versions
#                pinned with ==. These do not: uvloop!=0.15.0,!=0.15.1,>=0.14.0
# 与 pywin32 同根（单平台编译的锁对另一个平台是瞎的），只是方向相反。
NON_WINDOWS_ONLY_PACKAGES = {"uvloop"}

# uvloop 必须至少把镜像与 CI 会用到的那些文件钉上；cp311/manylinux_x86_64 是
# `python:3.11-slim` 里 pip 实际挑中的那个 wheel（构建日志的报错行给了它的 sha256）。
UVLOOP_SHA256_FOR_IMAGE_PYTHON = "ab17b3a8aa754be0de0e397f7b95f13b14e56f077a4c6ae295e3d4afd199b325"

# 门禁的反向口径现在也吃 tmp_path 里的临时锁：凡"这条锁是干净的"用例都要自带一条合规的
# uvloop，否则它会在与本条无关的规则上判红。写法照真实锁（marker 排除 win32、带哈希）。
UVLOOP_OK = (
    'uvloop==0.23.0 ; sys_platform != "win32" and sys_platform != "cygwin" '
    'and platform_python_implementation != "PyPy" \\\n'
    f"    --hash=sha256:{UVLOOP_SHA256_FOR_IMAGE_PYTHON}\n"
    "    # via uvicorn[standard]\n"
)


def _parse_lock(text: str) -> list[dict]:
    """独立实现一遍锁解析（与 static-checks.py 的那份刻意分开写）。

    条目形态：首行 `name==version [; marker] \\`，随后若干 `--hash=...` 续行，最后一行
    `# via ...`。只认首行的 marker——把 marker 从续行里找回来是本项目不会犯的错，但从
    首行漏读恰恰会让"有 marker"与"没 marker"看起来一样。
    """
    entries: list[dict] = []
    pending: dict | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if pending is not None:
            if line.strip().startswith("--hash="):
                pending["hashes"].append(line.strip())
                continue
            pending = None
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("--"):
            continue
        head = stripped.split(" \\")[0].strip()
        match = re.match(
            r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?==([^;\s]+)(?:\s*;\s*(.*))?$",
            head,
        )
        if not match:
            continue
        name, version, marker = match.group(1), match.group(2), match.group(3)
        entries.append(
            {
                "name": name.lower().replace("_", "-"),
                "version": version,
                "marker": marker or "",
                "hashes": [],
                "line": lineno,
            }
        )
        pending = entries[-1]
    return entries


class TestLockIsInstallableOnLinux:
    @pytest.mark.parametrize("lock", LOCKS, ids=lambda p: p.name)
    def test_parser_finds_the_windows_only_pins(self, lock):
        """解析器本身要先能看见这两个包，否则后面的断言是空转。"""
        names = {entry["name"] for entry in _parse_lock(lock.read_text(encoding="utf-8"))}
        missing = WINDOWS_ONLY_PACKAGES - names
        assert not missing, f"{lock.name} 里找不到 {missing}，解析器或包名归一化错了"

    def test_parser_reads_a_marker_from_the_entry_head(self):
        entries = _parse_lock(
            'pywin32==312 ; sys_platform == "win32" \\\n'
            "    --hash=sha256:deadbeef\n"
            "    # via docker\n"
            "setuptools==83.0.0 \\\n"
            "    --hash=sha256:cafe\n"
        )
        by_name = {entry["name"]: entry for entry in entries}
        assert by_name["pywin32"]["marker"].startswith("sys_platform")
        assert by_name["setuptools"]["marker"] == ""
        assert by_name["pywin32"]["hashes"] == ["--hash=sha256:deadbeef"]
        assert by_name["setuptools"]["hashes"] == ["--hash=sha256:cafe"]

    def test_windows_only_pins_carry_a_win32_marker(self):
        bad = [
            entry
            for entry in _parse_lock(REQUIREMENTS.read_text(encoding="utf-8"))
            if entry["name"] in WINDOWS_ONLY_PACKAGES and "win32" not in entry["marker"]
        ]
        assert not bad, "锁里的 Windows-only 包没有 marker，Linux 装不上：\n" + "\n".join(
            f"  requirements.txt:{e['line']} {e['name']}=={e['version']}（marker={e['marker'] or '无'}）" for e in bad
        )

    def test_no_pin_in_the_lock_is_left_unmarked_by_accident(self):
        """整份锁今天一个 marker 都没有 ⇒ 它是在单一平台上编译的，不是跨平台锁。

        这条不要求每个条目都有 marker，只要求"一旦出现了 Windows-only 包就必须带"，
        所以它在跨平台重编译之前也应当是绿的（与上一条同因，但分开写以免常量清单
        更新后这里静默失去意义）。
        """
        text = REQUIREMENTS.read_text(encoding="utf-8")
        marked = [e for e in _parse_lock(text) if e["marker"]]
        unmarked_windows = [e for e in _parse_lock(text) if e["name"] in WINDOWS_ONLY_PACKAGES and not marked]
        assert not unmarked_windows, (
            f"锁内没有任何 marker（{len(marked)} 条有），而 Windows-only 的 "
            f"{[e['name'] for e in unmarked_windows]} 全靠裸奔——说明它是单平台编译产物"
        )


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("hfusionhub_static_checks", ROOT / "scripts" / "static-checks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestLockSeesItsOwnExtrasEntries:
    """`name[extra]==ver` 形态的条目必须被解析器认出来，否则它对哈希口径隐形。

    锁里确有这种形态（`uvicorn[standard]==0.27.0`、`jsonschema[format-nongpl]==4.26.0`、
    `cyclonedx-python-lib[validation]==11.12.0`），而两套解析器的包名正则都不含 `[` ⇒
    这些条目从计数里直接消失。本类的用例把"解析器看得见她"钉住：一个手工追加的
    `foo[bar]==1.2.3`（无哈希）正好落在测试与门禁共同的盲点上。
    """

    @pytest.mark.parametrize("lock", LOCKS, ids=lambda p: p.name)
    def test_extras_entries_are_parsed(self, lock):
        text = lock.read_text(encoding="utf-8")
        head_lines = [
            line
            for line in text.splitlines()
            if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[^\]]+\])?==\S+", line)
        ]
        with_extras = [line for line in head_lines if "[" in line]
        assert with_extras, f"{lock.name} 里没有 extras 形态条目，本条的核对对象消失了"
        parsed = _parse_lock(text)
        assert len(parsed) == len(head_lines), (
            f"{lock.name}：{len(with_extras)} 条 extras 形态里，解析器只认出 "
            f"{len(parsed)} / {len(head_lines)} 条 pin"
        )

    @pytest.mark.parametrize("lock", LOCKS, ids=lambda p: p.name)
    def test_gate_parser_agrees_on_the_count(self, lock):
        """两套解析器对同一份锁的条目数必须一致（口径分叉等于两份锁两套真相）。"""
        module = _load_gate_module()
        text = lock.read_text(encoding="utf-8")
        assert len(module._lock_pins(text)) == len(_parse_lock(text)), (
            f"{lock.name}：门禁解析出 {len(module._lock_pins(text))} 条，测试解析出 {len(_parse_lock(text))} 条"
        )


class TestNonWindowsExtraClosureIsPinned:
    """`uvicorn[standard]` 的非 Windows 依赖要在锁里，且要带反向 marker。

    只在 Dockerfile 上把 extra 去掉（`sed 's/uvicorn\\[standard\\]/uvicorn/g'`，即 3cd5303
    当年的绕法，今天仍活在 `docker/Dockerfile.plugin-runner:12`）能让构建变绿，但代价是
    生产镜像从此没有 uvloop/httptools，且镜像装的与 `requirements.in:5` 声明的
    `uvicorn[standard]>=0.27.0` 分叉——那是本批 `TestBuildWorkaroundsAreRefused` 拒绝的形状。
    """

    @pytest.mark.parametrize("lock", LOCKS, ids=lambda p: p.name)
    def test_the_non_windows_only_package_is_pinned(self, lock):
        names = {entry["name"] for entry in _parse_lock(lock.read_text(encoding="utf-8"))}
        missing = NON_WINDOWS_ONLY_PACKAGES - names
        assert not missing, f"{lock.name} 里没有 {sorted(missing)}：Linux 会去解析 extra 自带的 >= 规格，哈希模式当场拒绝"

    @pytest.mark.parametrize("lock", LOCKS, ids=lambda p: p.name)
    def test_it_carves_windows_out_by_marker(self, lock):
        """marker 必须是"排除 win32"而不是没有 marker——生成锁的宿主是 Windows，无 marker 的 pin 会被它自己拒装。"""
        entries = [e for e in _parse_lock(lock.read_text(encoding="utf-8")) if e["name"] in NON_WINDOWS_ONLY_PACKAGES]
        assert entries
        for entry in entries:
            assert "win32" in entry["marker"], (
                f"{lock.name}:{entry['line']} {entry['name']}=={entry['version']} 没有 marker，"
                f"Windows 宿主（生成这份锁的 pip-compile 与本地开发态）会装不上它"
            )
            assert "!=" in entry["marker"], f"marker 要排除 win32 而不是选中它：{entry['marker']}"

    def test_the_hash_set_covers_the_wheel_the_image_installs(self):
        entries = [e for e in _parse_lock(REQUIREMENTS.read_text(encoding="utf-8")) if e["name"] == "uvloop"]
        assert entries
        hashes = {h for e in entries for h in e["hashes"]}
        assert any(UVLOOP_SHA256_FOR_IMAGE_PYTHON in h for h in hashes), (
            "锁里 uvloop 的哈希集不含 cp311/manylinux_x86_64 wheel，"
            f"python:3.11-slim 上 pip 挑中的那个文件会因为对不上哈希被拒：{sorted(hashes)[:2]}"
        )

    def test_the_pinned_version_satisfies_the_extras_own_spec(self):
        """钉的版本必须落在 uvicorn 自己声明的 `!=0.15.0,!=0.15.1,>=0.14.0` 里，否则 pip 仍要回溯解析。"""
        entries = [e for e in _parse_lock(REQUIREMENTS.read_text(encoding="utf-8")) if e["name"] == "uvloop"]
        assert entries
        versions = {tuple(int(p) for p in e["version"].split(".")) for e in entries}
        assert len(versions) == 1, f"uvloop 在锁里出现多个版本：{versions}"
        (version,) = versions
        assert version >= (0, 14, 0) and version not in {(0, 15, 0), (0, 15, 1)}, (
            f"uvloop {'.'.join(map(str, version))} 不满足 uvicorn extra 的 !=0.15.0,!=0.15.1,>=0.14.0"
        )


class TestLockIsTamperProof:
    """锁里混合"带哈希"与"不带哈希"的条目时，pip 会整体拒绝安装（任何平台）。

    `--require-hashes` 不是谁显式开的：只要**任一**条目带 `--hash=`，pip 就自动进入该模式，
    于是没有哈希的条目 collect 完才报 "Hashes are required in --require-hashes mode"。
    `65b3ef8b`（2026-09-04）手工往 pip-compile 生成的锁尾追加了三条 opentelemetry pin
    （`requirements.in` 里并没有它们），三条都没有哈希 ⇒ 镜像构建在 pywin32 之后必然撞到这里。
    """

    def test_the_lock_knows_which_kind_of_lock_it_is(self):
        """要么全带哈希，要么全不带——混合形态本身就是缺陷，先把它断言出来。"""
        entries = _parse_lock(REQUIREMENTS.read_text(encoding="utf-8"))
        hashed = [e for e in entries if e["hashes"]]
        assert hashed, "锁里一条哈希都没有，本类的口径需要重新设计（pip 不会开 require-hashes）"
        mixed = len(hashed) != len(entries)
        assert not mixed, (
            f"{len(hashed)}/{len(entries)} 带哈希：混合锁会让 pip 自动进入 --require-hashes 并拒绝其余条目"
        )

    def test_every_pin_carries_at_least_one_hash(self):
        entries = _parse_lock(REQUIREMENTS.read_text(encoding="utf-8"))
        bare = [e for e in entries if not e["hashes"]]
        assert not bare, "这些 pin 没有哈希，pip install -r 会整体失败：\n" + "\n".join(
            f"  requirements.txt:{e['line']} {e['name']}=={e['version']}" for e in bare
        )


class TestOpentelemetryHasExactlyOneOwner:
    """opentelemetry 只能由一处声明：锁（带哈希）或 Dockerfile（显式钉版）。

    第六十五批起 `app/utils/telemetry.py` 用 OTel 做追踪，`65b3ef8b` 把三条裸 pin 手工
    追加到 pip-compile 的哈希锁尾（`requirements.in` 里没有它们）。形状后果在
    第八十八批的构建日志里：pip 自动进入 `--require-hashes`，collect 完 1706 秒后整体
    拒绝（`Hashes are required ... opentelemetry-api==1.29.0`）。补哈希又要求它的
    closure（`opentelemetry-proto`/`-semantic-conventions`/`-exporter-otlp-proto-common`/
    `googleapis-common-protos`/`deprecated`）全部进锁，而那要把 arq/redis 的归属一起
    决定下来——是一次独立的重编译，不是本批的规模。

    版本也不能停在 1.29.0：`opentelemetry-proto 1.29.0` 要 `protobuf<6.0`，锁里的
    `protobuf==7.35.1`（`# via pymilvus`）与之冲突，装它会把 protobuf 往下拖，而
    pymilvus 在锁上认的是 7.x。1.39 起放宽到 `<7.0`、1.45 起 `<8.0`，因此下限取 1.39，
    并按锁里的 protobuf 主版本核对。
    """

    OTEL_PACKAGES = {
        "opentelemetry-api",
        "opentelemetry-sdk",
        "opentelemetry-exporter-otlp-proto-http",
    }
    OTEL_MIN_WITHOUT_PROTOBUF6_CAP = (1, 39)

    def _dockerfile_otel_pins(self) -> dict[str, str]:
        source = (ROOT / "deploy" / "Dockerfile.python").read_text(encoding="utf-8")
        run_stmts = re.findall(r"RUN\s+(.*?)(?:\n[A-Z#]|\n(?=\S)|\Z)", source, re.S)
        pins: dict[str, str] = {}
        for stmt in run_stmts:
            if "pip install" not in stmt:
                continue
            for name, version in re.findall(r'"([a-z0-9._-]+)==([^"\s]+)"', stmt):
                pins[name.lower()] = version
        return {k: v for k, v in pins.items() if k in self.OTEL_PACKAGES}

    def test_lock_and_dockerfile_do_not_both_declare_opentelemetry(self):
        in_lock = {
            e["name"] for e in _parse_lock(REQUIREMENTS.read_text(encoding="utf-8")) if e["name"] in self.OTEL_PACKAGES
        }
        in_dockerfile = set(self._dockerfile_otel_pins())
        both = in_lock & in_dockerfile
        assert not both, f"OTel 同时声明在锁与 Dockerfile，两处版本会各自漂：{sorted(both)}"

    def test_opentelemetry_is_declared_somewhere(self):
        """不许两处都没有——那等于追踪在镜像里静默关闭（telemetry.py 会降级成 no-op）。"""
        in_lock = {
            e["name"] for e in _parse_lock(REQUIREMENTS.read_text(encoding="utf-8")) if e["name"] in self.OTEL_PACKAGES
        }
        missing = self.OTEL_PACKAGES - in_lock - set(self._dockerfile_otel_pins())
        assert not missing, f"这些 OTel 包在锁和 Dockerfile 里都找不到：{sorted(missing)}"

    def test_dockerfile_otel_pins_clear_the_locks_protobuf(self):
        pins = self._dockerfile_otel_pins()
        assert pins, "Dockerfile 没有钉 opentelemetry 版本（不许裸装 latest）"
        assert set(pins) == self.OTEL_PACKAGES, f"三条要一起钉，缺 {sorted(self.OTEL_PACKAGES - set(pins))}"
        versions = {tuple(int(p) for p in v.split(".")[:2]) for v in pins.values()}
        assert len(versions) == 1, f"三条版本必须同号：{pins}"
        (otel_pair,) = versions
        assert otel_pair >= self.OTEL_MIN_WITHOUT_PROTOBUF6_CAP, (
            f"opentelemetry {'.'.join(map(str, otel_pair))} 的 opentelemetry-proto 还要 protobuf<6.0，"
            f"与锁里的 protobuf 冲突"
        )
        lock_protobuf = {
            e["version"] for e in _parse_lock(REQUIREMENTS.read_text(encoding="utf-8")) if e["name"] == "protobuf"
        }
        assert lock_protobuf, "锁里找不到 protobuf，本条的核对对象消失了"
        (protobuf_major,) = {int(v.split(".")[0]) for v in lock_protobuf}
        assert protobuf_major < 8, f"锁里 protobuf {lock_protobuf} 已超出 OTel 的 <8.0 上限，需重查"


class TestCiOnlySeesTheDevLock:
    """OTel 不在 dev 锁里 ⇒ CI 上任何直接 import 它的用例都必须自带前提守卫。

    CI 的 python job 装的是 `requirements-dev.txt`（ci.yml:155/178、plugin-security.yml:21、
    eval-nightly.yml:168），而 OTel 只由 `deploy/Dockerfile.python` 装进镜像。所以
    `from opentelemetry import ...` 在 CI 上是 ModuleNotFoundError 而不是代码缺陷——本批把
    dev 锁的 marker 修好之后，CI 第一次能走到 pytest，撞到的就是这个。
    守卫写的是"环境不具备则 skip"，真跑这条覆盖的位置是镜像内。
    """

    def test_every_test_that_imports_opentelemetry_declares_it_optional(self):
        users = []
        for path in sorted((ROOT / "python-ai" / "tests").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if not re.search(r"^\s*(from opentelemetry|import opentelemetry)", text, re.M):
                continue
            assert "importorskip" in text, (
                f"{path.relative_to(ROOT).as_posix()} 裸 import 了可选依赖，CI（只装 dev 锁）会红在这里而不是跳过"
            )
            users.append(path.name)
        assert users, "没有任何用例依赖 OTel——本条的核对对象消失了，需要重新决定它保护什么"


class TestBuildWorkaroundsAreRefused:
    def test_dockerfile_does_not_edit_the_lock_at_build_time(self):
        """不许用 `grep -v pywin32` 这类构建期删行来绕过锁。

        修 lock 与改 Dockerfile 是两种形状：后者让"镜像装的依赖"与"锁声明的依赖"分叉，
        而锁同时被 CI 的 python job 与宿主开发态使用，分叉会一路传到评测与SBOM。
        """
        source = (ROOT / "deploy" / "Dockerfile.python").read_text(encoding="utf-8")
        for line in source.splitlines():
            if line.lstrip().startswith("#"):
                continue
            assert not re.search(r"\b(grep|sed|awk)\b[^\n]*pywin32", line), (
                f"Dockerfile.python 在构建期过滤依赖，锁与镜像将不再同源：{line!r}"
            )


class TestRequirementsMarkerGate:
    def _load_checker(self):
        return _load_gate_module()

    def test_gate_passes_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "static-checks.py"), "--requirements-markers"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            cwd=ROOT,
        )
        assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")

    def test_gate_is_wired_into_the_default_all_mode(self):
        source = (ROOT / "scripts" / "static-checks.py").read_text(encoding="utf-8")
        main_body = source[source.index("def main()") :]
        assert "--requirements-markers" in main_body
        all_mode = main_body[main_body.index("args = parser.parse_args()") : main_body.index("if args.tenant_columns:")]
        assert all_mode.count("args.requirements_markers") >= 2, f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        assert "check_requirements_platform_markers()" in main_body

    def test_gate_flags_a_pin_without_hashes(self, tmp_path):
        """与 marker 同一条门禁的第二种坏形状：混合锁。"""
        module = self._load_checker()
        lock = tmp_path / "requirements.txt"
        lock.write_text(
            "fastapi==0.141.1 \\\n    --hash=sha256:aaa\n    # via -r requirements.in\nopentelemetry-api==1.29.0\n",
            encoding="utf-8",
        )
        module.LOCK_FILES = (lock,)
        module.problems.clear()
        module.check_requirements_platform_markers()
        assert module.problems, "混合锁必须判红"
        assert "opentelemetry-api" in module.problems[0]

    def test_gate_passes_when_every_pin_is_hashed(self, tmp_path):
        module = self._load_checker()
        lock = tmp_path / "requirements.txt"
        lock.write_text(
            "fastapi==0.141.1 \\\n"
            "    --hash=sha256:aaa\n"
            "    # via -r requirements.in\n"
            "opentelemetry-api==1.29.0 \\\n"
            "    --hash=sha256:bbb\n"
            "    # via -r requirements.in\n" + UVLOOP_OK,
            encoding="utf-8",
        )
        module.LOCK_FILES = (lock,)
        module.problems.clear()
        module.check_requirements_platform_markers()
        assert not module.problems, module.problems

    def test_gate_flags_an_unmarked_windows_pin(self, tmp_path):
        module = self._load_checker()
        lock = tmp_path / "requirements.txt"
        lock.write_text(
            "pywin32==312 \\\n    --hash=sha256:deadbeef\n    # via docker\n",
            encoding="utf-8",
        )
        module.LOCK_FILES = (lock,)
        module.problems.clear()
        module.check_requirements_platform_markers()
        assert module.problems, "无 marker 的 pywin32 必须判红"
        assert "pywin32" in module.problems[0]

    def test_gate_passes_when_the_pin_is_marked(self, tmp_path):
        module = self._load_checker()
        lock = tmp_path / "requirements.txt"
        lock.write_text(
            'pywin32==312 ; sys_platform == "win32" \\\n'
            "    --hash=sha256:deadbeef\n"
            "    # via docker\n"
            'win32-setctime==1.2.0 ; sys_platform == "win32" \\\n'
            "    --hash=sha256:cafe\n"
            "    # via loguru\n" + UVLOOP_OK,
            encoding="utf-8",
        )
        module.LOCK_FILES = (lock,)
        module.problems.clear()
        module.check_requirements_platform_markers()
        assert not module.problems, module.problems

    def test_gate_ignores_comment_lines(self, tmp_path):
        """锁里 `# via docker` / 说明性注释提到包名不算声明。"""
        module = self._load_checker()
        lock = tmp_path / "requirements.txt"
        lock.write_text(
            "# pywin32==312 曾被无 marker 地写进锁里\n" + UVLOOP_OK, encoding="utf-8"
        )
        module.LOCK_FILES = (lock,)
        module.problems.clear()
        module.check_requirements_platform_markers()
        assert not module.problems, module.problems

    def test_gate_flags_a_missing_linux_only_pin(self, tmp_path):
        """uvloop 整条不在锁里——本批真实构建撞到的就是这一种，门禁必须单独报出来。"""
        module = self._load_checker()
        lock = tmp_path / "requirements.txt"
        lock.write_text(
            "uvicorn[standard]==0.27.0 \\\n    --hash=sha256:aaa\n    # via -r requirements.in\n",
            encoding="utf-8",
        )
        module.LOCK_FILES = (lock,)
        module.problems.clear()
        module.check_requirements_platform_markers()
        assert module.problems, "extra 的非 Windows 依赖没进锁必须判红"
        assert "uvloop" in module.problems[0], module.problems[0]

    def test_gate_flags_a_linux_only_pin_without_a_marker(self, tmp_path):
        """反向 marker 也要核：无 marker 时 Windows 宿主（生成锁的那台）自己装不上。"""
        module = self._load_checker()
        lock = tmp_path / "requirements.txt"
        lock.write_text(
            "uvloop==0.23.0 \\\n    --hash=sha256:aaa\n    # via uvicorn\n",
            encoding="utf-8",
        )
        module.LOCK_FILES = (lock,)
        module.problems.clear()
        module.check_requirements_platform_markers()
        assert module.problems, "uvloop 没有 marker 必须判红"
        assert "uvloop" in module.problems[0], module.problems[0]

    def test_gate_passes_when_the_linux_only_pin_is_marked(self, tmp_path):
        module = self._load_checker()
        lock = tmp_path / "requirements.txt"
        lock.write_text(
            'uvloop==0.23.0 ; sys_platform != "win32" \\\n'
            "    --hash=sha256:aaa\n"
            "    # via uvicorn\n",
            encoding="utf-8",
        )
        module.LOCK_FILES = (lock,)
        module.problems.clear()
        module.check_requirements_platform_markers()
        assert not module.problems, module.problems

    def test_gate_reaches_every_lock_the_repo_ships(self):
        """门禁的文件清单必须真的包含两份锁，且两份里都能看见那两个 Windows-only 包。

        否则"核了两份锁"这句话只是注释：CI 装的是 dev 锁，镜像装的是 prod 锁，
        漏掉任一份就等于那条安装路径仍然没有人核过。
        """
        module = self._load_checker()
        names = {lock.name for lock in module.LOCK_FILES}
        assert {"requirements.txt", "requirements-dev.txt"} <= names, names
        assert set(module.NON_WINDOWS_ONLY_PINS) == NON_WINDOWS_ONLY_PACKAGES, (
            f"门禁的反向清单与测试的清单分叉：{sorted(module.NON_WINDOWS_ONLY_PINS)}"
        )
        for lock in module.LOCK_FILES:
            found = {name for name, _, _, _ in module._lock_pins(lock.read_text(encoding="utf-8"))}
            missing = set(module.WINDOWS_ONLY_PINS) - found
            assert not missing, f"{lock.name} 里解析不到 {missing}，门禁对该文件是空转"
            absent = set(module.NON_WINDOWS_ONLY_PINS) - found
            assert not absent, f"{lock.name} 里解析不到 {absent}，反向口径是空转"

    def test_gate_reports_which_lock_is_broken(self, tmp_path):
        """两份锁里坏一份，消息里必须带出是哪一份——只说"锁不可安装"会逼人再去查两遍。"""
        module = self._load_checker()
        good = tmp_path / "requirements.txt"
        good.write_text("fastapi==0.141.1 \\\n    --hash=sha256:aaa\n" + UVLOOP_OK, encoding="utf-8")
        broken = tmp_path / "requirements-dev.txt"
        broken.write_text("pywin32==312 \\\n    --hash=sha256:bbb\n    # via docker\n", encoding="utf-8")
        module.LOCK_FILES = (good, broken)
        module.problems.clear()
        module.check_requirements_platform_markers()
        assert len(module.problems) == 1, module.problems
        assert "requirements-dev.txt" in module.problems[0], module.problems[0]
