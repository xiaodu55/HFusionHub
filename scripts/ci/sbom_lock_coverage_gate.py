#!/usr/bin/env python3
"""SBOM 与产品依赖锁的一致性判定门（第一百一十四批）。

判的对象：`cyclonedx-py environment` 生成的 SBOM 是否**覆盖了 `requirements.txt` 里
当前平台该装上的每一个 pin，且版本与锁一致**。

为什么要这条门（判据来自 runner 产物本体，run 38332373261 的 `sbom` artifact）：
`sbom-generation` 这个 job 从诞生起只 `pip install cyclonedx-bom==7.3.1`，从没装过产品
依赖，于是 `environment` 读到的解释器里只有那个工具＋它的闭包。产物打印过
`SBOM contains 35 components` 并退出 0，而同一条流水线的 `vulnerability-scan` 审的是锁的
78 个 pin（ubuntu 上按 marker 实装 76 个）。拆开看：按 ubuntu 侧适用的 76 个口径，门在这份
产物上报 **42 个缺失**（fastapi / uvicorn / httpx / numpy /
pandas / pymilvus / pypdf …）**＋ 9 个版本与锁不符**（lxml / packaging / rpds-py / setuptools /
tzdata / fqdn / idna / jsonpointer / pyparsing —— 那是工具自己拉的最新版本，不是钉的那一版）。
组件表为空时旧步骤只 `print('WARNING: SBOM has no components')`，退出码仍是 0 ⇒ 这条门在 CI
里没有任何一层会咬。

退出码契约：
  0 = 锁的每一个适用 pin 都在 SBOM 里且版本一致
  1 = 至少一个缺失或版本不符（逐个打印）
  2 = 读不出被描述的对象：文件打不开 / JSON 不认识 / `components` 缺失或为空 /
      锁里出现认不出的行形 / 同一个包被钉成两个版本 / 适用面为空。
      与 `vuln_report_gate.py` 同一条纪律：**读不出永远不当 0**。

`--sys-platform` 是给门的门的：不显式指定时按当前宿主算 marker，那会让同一份 fixture 在
Windows 开发和 ubuntu CI 上得出不同结论。本仓的锁里带 marker 的只有三条（pywin32、
win32-setctime 是 win32-only，uvloop 是非 win32），所以 ubuntu 上"要求 pywin32 出现在
SBOM 里"会是一条**天生红**的门——适用面必须算出来，不能写死名单。
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from packaging.markers import Marker, default_environment
from packaging.utils import canonicalize_name

_PIN_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*==\s*(?P<version>[^ ;]+)"
    r"(?:\s*;\s*(?P<marker>.+))?$"
)


class CannotRead(Exception):
    """读不出被描述的对象 —— 退出码 2，绝不能当成"覆盖良好"。"""


def _fail(reason: str) -> int:
    print(f"sbom_lock_coverage_gate: cannot read the described surface - {reason}", file=sys.stderr)
    return 2


def parse_lock(text: str, environment: dict[str, str]) -> dict[str, str]:
    """返回当前平台**适用**的 `{规范化包名: 版本}`。

    只认列 0 的 `name[extras]==version[ ; marker]`：pip-compile 的锁里缩进行是 `--hash=`
    续行和 `# via` 出处，`--index-url` 之类以 `-` 开头的是选项。认不出的一行按"读不出
    要描述的对象"处理，不静默跳过——静默跳过就是"少审一个包还报绿"。
    """
    pins: dict[str, str] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw[0] in " #-":
            continue
        line = raw.rstrip()
        if line.endswith("\\"):
            line = line[:-1].rstrip()
        if "#" in line:
            line = line.split("#", 1)[0].rstrip()
        match = _PIN_RE.match(line)
        if match is None:
            raise CannotRead(f"unrecognized requirement line: {raw[:100]!r}")
        name = match.group("name")
        try:
            key = canonicalize_name(name)
        except Exception as exc:
            raise CannotRead(f"invalid package name in {raw[:100]!r} ({exc})") from exc
        marker = match.group("marker")
        if marker is not None and not Marker(marker).evaluate(environment):
            continue
        previous = pins.get(key)
        if previous is not None and previous != match.group("version"):
            raise CannotRead(f"package {key} is pinned twice with different versions")
        pins[key] = match.group("version")
    return pins


def parse_sbom(path: str) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise CannotRead(f"SBOM cannot be opened ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise CannotRead(f"SBOM is not valid JSON ({exc})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("components"), list):
        got = type(data).__name__
        keys = sorted(data) if isinstance(data, dict) else []
        raise CannotRead(f"unrecognized SBOM shape: top level {got}, keys {keys}")
    components = data["components"]
    if not components:
        raise CannotRead("SBOM has no components - nothing is being described")
    surface: dict[str, str] = {}
    for entry in components:
        if not isinstance(entry, dict):
            raise CannotRead(f"unrecognized SBOM shape: component is {type(entry).__name__}")
        name = entry.get("name")
        version = entry.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise CannotRead(f"unrecognized SBOM shape: malformed component {entry!r:.120}")
        try:
            surface[canonicalize_name(name)] = version
        except Exception as exc:
            raise CannotRead(f"invalid component name {name!r} ({exc})") from exc
    return surface


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="sbom_lock_coverage_gate.py",
        description="judge whether an SBOM covers every applicable pinned package of a requirements lock",
    )
    parser.add_argument("sbom", help="path to the CycloneDX JSON SBOM")
    parser.add_argument("lock", help="path to the pinned requirements file")
    parser.add_argument(
        "--sys-platform",
        default=None,
        help="override sys_platform when evaluating environment markers (e.g. linux / win32)",
    )
    args = parser.parse_args(argv[1:])

    environment = dict(default_environment())
    if args.sys_platform:
        environment["sys_platform"] = args.sys_platform

    try:
        with open(args.lock, encoding="utf-8") as handle:
            lock_text = handle.read()
    except OSError as exc:
        return _fail(f"lock cannot be opened ({exc})")

    try:
        pins = parse_lock(lock_text, environment)
        surface = parse_sbom(args.sbom)
    except CannotRead as exc:
        return _fail(str(exc))

    if not pins:
        return _fail(f"zero applicable pins for sys_platform={environment.get('sys_platform')!r}")

    missing = sorted(name for name in pins if name not in surface)
    mismatched = sorted(
        (name, pins[name], surface[name]) for name in pins if name in surface and surface[name] != pins[name]
    )

    if missing or mismatched:
        print(
            f"SBOM does not describe the locked dependency surface: "
            f"{len(missing)} missing, {len(mismatched)} version-mismatched of {len(pins)} applicable pins"
        )
        for name in missing:
            print(f"  MISSING   {name}=={pins[name]} is not in the SBOM")
        for name, want, got in mismatched:
            print(f"  VERSION   {name}: lock pins {want}, SBOM reports {got}")
        return 1

    print(
        f"SBOM covers all {len(pins)} applicable locked packages "
        f"({len(surface)} components; extras describe the tool itself and are not judged)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
