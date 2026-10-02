"""第九十五批：前端时间显示只有一个入口 —— 门禁 12 的判据与红→绿实测

门禁要防的不是某个页面写错一次，而是"三种互相矛盾的解析 theory 并存"回到仓库里：
utils/date.ts 曾注释断言"后端已存储北京时间（UTC+8）"并按本地墙钟解析，8 个页面直接
replace('T',' ') 截字面量，chat/Detail.vue 手工 +480 分钟。每条单独看都能解释服务端
的某一种写法，合起来必然让同一份数据在不同页面显示成不同时刻。

解析契约本身由 hfusionhub-frontend/src/utils/__tests__/date.spec.ts 覆盖（vitest）；
这里只覆盖门禁：它对真实仓库为绿、对两种字面写法为红、不被测试夹具误伤、且接进了默认全跑档。
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "static-checks.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("hfusionhub_static_checks", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_frontend(tmp_path):
    """把被扫描的 src 换到 tmp_path，三个根都建好，免得"根缺失"和"抓到违规"混在一条红里。"""
    module = _load_checker()
    for root in module.FRONTEND_TIME_ROOTS:
        (tmp_path / root).mkdir(parents=True, exist_ok=True)
    module.FRONTEND_SRC_DIR = tmp_path
    return module


class TestFrontendTimeGate:
    def test_time_gate_passes_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, str(GATE), "--frontend-time-entry"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_time_gate_is_in_the_default_all_mode(self):
        """并入默认全跑档，否则只在显式传参时才生效（第八十三批的接线哑火形态）。"""
        source = GATE.read_text(encoding="utf-8")
        main_body = source[source.index("def main()"):]
        assert "--frontend-time-entry" in main_body
        all_mode = main_body[main_body.index("args = parser.parse_args()"):
                             main_body.index("if args.tenant_columns:")]
        assert all_mode.count("args.frontend_time_entry") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_frontend_time_entry()" in main_body

    def test_gate_flags_literal_t_truncation(self, tmp_path):
        module = _fake_frontend(tmp_path)
        page = tmp_path / "pages" / "demo"
        page.mkdir(parents=True)
        (page / "List.vue").write_text(
            '<script setup lang="ts">\n'
            "const show = (v: string) => v.replace('T', ' ').slice(0, 16)\n"
            "</script>\n",
            encoding="utf-8",
        )
        module.problems.clear()
        module.check_frontend_time_entry()
        assert module.problems, "页面自行截 ISO 字面量时门禁必须报红"
        assert "List.vue:2" in module.problems[0]

    def test_gate_flags_manual_offset_math(self, tmp_path):
        module = _fake_frontend(tmp_path)
        (tmp_path / "api" / "time.ts").write_text(
            "export const toBeijing = (d: Date) =>\n"
            "  new Date(d.getTime() - d.getTimezoneOffset() * 60000 + 8 * 3600e3)\n",
            encoding="utf-8",
        )
        module.problems.clear()
        module.check_frontend_time_entry()
        assert module.problems, "手算偏移等于把某个国家的时区编进代码，门禁必须报红"
        assert "time.ts:2" in module.problems[0]
        assert "utils/date.ts" in module.problems[0], "报红要指回唯一入口，否则只会换个写法躲过去"

    def test_gate_ignores_test_fixtures(self, tmp_path):
        """__tests__ 下的夹具里出现禁字是常态（断言"旧写法不再回来"就得把它写出来）。"""
        module = _fake_frontend(tmp_path)
        tests = tmp_path / "components" / "__tests__"
        tests.mkdir(parents=True)
        (tests / "legacy.spec.ts").write_text(
            "it('不再截字面量', () => expect(src).not.toContain(\"replace('T',\"))\n",
            encoding="utf-8",
        )
        module.problems.clear()
        module.check_frontend_time_entry()
        assert module.problems == []

    def test_missing_root_is_a_problem_not_a_silent_pass(self, tmp_path):
        module = _fake_frontend(tmp_path)
        (tmp_path / "api").rmdir()
        module.problems.clear()
        module.check_frontend_time_entry()
        assert module.problems, "根目录不存在时不能报绿——那正是'扫了 0 个文件所以全对'的形态"
