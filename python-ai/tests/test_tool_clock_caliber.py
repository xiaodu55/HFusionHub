"""内置时间工具的钟面口径（第一百零二批）。

`get_current_time` 此前返回 `datetime.now()` 的**裸本地墙钟**，输出里没有任何口径标签：
四档 python 工作负载都没声明 `TZ`（第一百零二批实测：`docker/`、`deploy/`、`helm/` 下
`TZ` 声明为 0 处），所以这个值实际等于"镜像默认的时区"——一旦有人给容器加了 `TZ`，
同一句"现在几点"就会静默平移 N 小时，而调用方（模型）无从分辨。

本批把它并入仓库已有口径（写侧判定读库的 UTC 钟，见 `scripts/static-checks.py` 检查 13）：
取带 tzinfo 的 UTC 瞬时，并把口径写在返回值里。
"""

import datetime as _dt
import io
import re
import time
import tokenize
from pathlib import Path

import pytest

from app.core.tools.time_tool import TimeTool

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# 裸本地墙钟的三种写法：datetime.now() / datetime.utcnow() / date.today()
# （utcnow 在 3.12 起被弃用且返回 naive 值，同样不声明口径，一并禁）
_NAIVE_PATTERNS = (
    re.compile(r"datetime\.now\(\s*\)"),
    re.compile(r"datetime\.utcnow\(\s*\)"),
    re.compile(r"(?<!\.)\bdate\.today\(\s*\)"),
)


def _code_surface(text: str) -> str:
    """把注释与字符串常量的内容涂白（保留行号与列位置），只剩可执行代码的表面。

    time_tool.py 的模块 docstring 里就在解释"此前用的是 `datetime.now()`"——按原文扫的
    正则会在自己的说明文字上判红，那种红只会教人去删注释。检查 15 用 ast 达到同一目的，
    这里故意换一个 oracle（token 流），两边同时看错同一形状的概率才低。
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text  # 解析不了就按原文扫：宁可多报，不可漏报
    lines = [list(line) for line in text.splitlines(keepends=True)]
    ignored = {tokenize.COMMENT, tokenize.STRING}
    ignored.update(
        getattr(tokenize, name)
        for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END")
        if hasattr(tokenize, name)
    )
    for tok in tokens:
        if tok.type not in ignored:
            continue
        (sr, sc), (er, ec) = tok.start, tok.end
        for row in range(sr, er + 1):
            if row - 1 >= len(lines):
                break
            chars = lines[row - 1]
            lo = sc if row == sr else 0
            hi = ec if row == er else len(chars)
            for col in range(lo, min(hi, len(chars))):
                if chars[col] not in "\n\r":
                    chars[col] = " "
    return "".join("".join(chars) for chars in lines)


@pytest.mark.asyncio
async def test_time_tool_output_declares_utc_caliber():
    """返回值必须显式带 UTC 口径，且数值就是本次调用的 UTC 瞬时（秒级）。"""
    before = _dt.datetime.now(_dt.UTC)
    result = await TimeTool().execute()
    after = _dt.datetime.now(_dt.UTC)

    assert result.get("caliber") == "UTC", f"输出没有声明口径：{result}"
    iso = result.get("iso8601") or ""
    assert iso.endswith("+00:00"), f"iso8601 没有带 UTC 偏移：{iso!r}"

    parsed = _dt.datetime.strptime(result["datetime"], "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=_dt.UTC
    )
    # 工具的 datetime 字段截到秒，比较的两端必须同样截，否则同一瞬间也会判成"早于 before"
    assert before.replace(microsecond=0) <= parsed <= after.replace(microsecond=0), (
        f"datetime 不在本次调用的 UTC 区间内：{result['datetime']} "
        f"（before={before}，after={after}）"
    )
    # 分片字段必须与同一个瞬时一致，不能一半本地一半 UTC
    assert result["date"] == parsed.strftime("%Y-%m-%d")
    assert result["time"] == parsed.strftime("%H:%M:%S")
    assert (result["year"], result["month"], result["day"]) == (parsed.year, parsed.month, parsed.day)
    assert result["weekday"] == ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][
        parsed.weekday()
    ]


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="tzset 是 POSIX 专有，Windows 上无法翻转进程时区")
@pytest.mark.asyncio
async def test_time_tool_is_immune_to_process_timezone():
    """把进程时区挪到 +08：裸墙钟会跟着走，口径值必须不动。"""
    import os

    original_tz = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "Asia/Shanghai"
        time.tzset()

        naive_local = _dt.datetime.now()
        utc_now = _dt.datetime.now(_dt.UTC)
        assert naive_local.strftime("%m-%d %H:%M") != utc_now.strftime("%m-%d %H:%M"), (
            f"进程时区没真的翻转（naive={naive_local} 与 UTC={utc_now} 同值），"
            "本用例的免疫断言不成立"
        )

        result = await TimeTool().execute()
        parsed = _dt.datetime.strptime(result["datetime"], "%Y-%m-%d %H:%M:%S")
        assert parsed.strftime("%Y-%m-%d %H:%M") == utc_now.strftime("%Y-%m-%d %H:%M"), (
            f"输出跟着进程时区走了：拿到 {result['datetime']}，"
            f"UTC 应为 {utc_now.strftime('%Y-%m-%d %H:%M:%S')}（裸本地墙钟是 {naive_local}）"
        )
    finally:
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        time.tzset()


def test_app_has_no_bare_naive_wall_clock_reads():
    """`app/` 下不得再有裸 `datetime.now()` / `utcnow()` / `date.today()`。

    口径要能核对才有意义：显式 `datetime.now(UTC)` 与 `time.gmtime()` 都不依赖进程时区，
    裸写法依赖，而容器从未声明 `TZ`。这条与 static-checks 的 python 钟面检查同面，
    差别在于本用例管"写法"，门禁管"写法 + 部署面是否声明 TZ"。
    """
    offenders: list[str] = []
    for py in sorted(APP_DIR.rglob("*.py")):
        text = _code_surface(py.read_text(encoding="utf-8"))
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            for pattern in _NAIVE_PATTERNS:
                if pattern.search(line):
                    offenders.append(f"{py.relative_to(APP_DIR.parent)}:{lineno}: {line.strip()}")
    assert not offenders, "app/ 里还有不声明口径的墙钟读法：\n" + "\n".join(offenders)
