"""容器运行身份必须钉死，且镜像 / helm / compose 三处对同一身份的写法必须一致。

卷能不能写，取决于"进程的 uid/gid"与"卷的属主"这两件事是否在同一处约定过。
第八十三批渲染核实：8 个工作负载里只有 plugin-runner 带 securityContext，
python/java 的 pod 与容器层全空；而两个应用镜像分别用 `useradd -r`（Debian 系统
uid 池 100–999）与 `adduser -S`（Alpine 同类）建用户 —— uid 随构建时基镜像里已
占了哪些号而变，重建镜像就可能换号。于是非 root 进程 + 无 fsGroup + 卷属主由
provisioner 决定 ⇒ /app/uploads 与 /app/audit-queue 的可写性在仓库里没有任何
声明过。本文件把身份钉死成三处同源的一个常量，并要求镜像自己拥有它要挂载的目录。
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "hfusionhub"
DOCKERFILE_PYTHON = ROOT / "deploy" / "Dockerfile.python"
DOCKERFILE_JAVA = ROOT / "deploy" / "Dockerfile.java"


def _pod_security_from_values() -> dict[str, int]:
    """取 values.yaml 里 podSecurity 段的三个身份键（必须是整数）。"""
    text = (CHART / "values.yaml").read_text(encoding="utf-8")
    block = re.search(r"^podSecurity:\n((?:[ \t]+\S.*\n)+)", text, re.MULTILINE)
    assert block, "values.yaml 没有 podSecurity 段"
    found: dict[str, int] = {}
    for key, value in re.findall(r"^\s+(runAsUser|runAsGroup|fsGroup):\s*(\d+)\s*$",
                                 block.group(1), re.MULTILINE):
        found[key] = int(value)
    return found


def _user_ids(dockerfile: Path) -> tuple[int, int]:
    """从 Dockerfile 的用户创建行取 (uid, gid)，未钉死则报错。"""
    text = dockerfile.read_text(encoding="utf-8")
    create = [
        line for line in text.splitlines()
        if not line.lstrip().startswith("#")
        and re.search(r"\b(useradd|adduser|groupadd|addgroup)\b", line)
    ]
    assert create, f"{dockerfile.name} 没有创建用户的行"
    uid = re.findall(r"\b(?:useradd|adduser)\b[^\n&]*? -u\s+(\d+)", "\n".join(create))
    gid = re.findall(r"\b(?:groupadd|addgroup)\b[^\n&]*? -g\s+(\d+)", "\n".join(create))
    assert len(uid) == 1, f"{dockerfile.name} 的用户必须用 -u 钉死 uid，实际找到 {len(uid)} 处"
    assert len(gid) == 1, f"{dockerfile.name} 的组必须用 -g 钉死 gid，实际找到 {len(gid)} 处"
    return int(uid[0]), int(gid[0])


class TestContainerIdentityIsPinned:
    def test_values_declares_the_pod_security_triple(self):
        found = _pod_security_from_values()
        assert set(found) == {"runAsUser", "runAsGroup", "fsGroup"}, f"podSecurity 键不全：{found}"
        # fsGroup 与主组同号：kubelet 会把卷 chown 给这个组并加进进程的补充组，
        # java 与 python 才能在同一块 RWX 卷上互写。
        assert found["runAsGroup"] == found["fsGroup"]

    def test_python_image_pins_uid_and_gid(self):
        uid, gid = _user_ids(DOCKERFILE_PYTHON)
        assert uid >= 10000, f"钉的 uid {uid} 仍在系统池里，基镜像占号变化就会撞"
        assert gid == uid, f"gid({gid}) 应与 uid({uid}) 同号，便于三处书写一致"

    def test_java_image_pins_uid_and_gid(self):
        uid, gid = _user_ids(DOCKERFILE_JAVA)
        assert uid >= 10000, f"钉的 uid {uid} 仍在系统池里，基镜像占号变化就会撞"
        assert gid == uid

    def test_the_three_surfaces_agree_on_one_identity(self):
        """镜像里的号和 helm 声明的号必须是同一个常量。

        这正是第八十三批那类笔误（模板读了一个不存在的键）的兄弟形态：两处各写
        一遍而无人核对。这里做三方比对，static-checks 的 --container-uid 门禁在
        CI 里跑同一件事。
        """
        py_uid, py_gid = _user_ids(DOCKERFILE_PYTHON)
        java_uid, java_gid = _user_ids(DOCKERFILE_JAVA)
        values = _pod_security_from_values()
        assert py_uid == java_uid == values["runAsUser"], (
            f"uid 三处不一致：python={py_uid} java={java_uid} values={values['runAsUser']}"
        )
        assert py_gid == java_gid == values["runAsGroup"] == values["fsGroup"], (
            f"gid 三处不一致：python={py_gid} java={java_gid} values={values}"
        )


class TestImagesOwnTheirMountPoints:
    """空命名卷/空 PVC 的属主来自镜像在该路径上的内容；路径不存在就以 root 建。

    java 挂载 /app/uploads 却从未在镜像里创建它，compose 上写
    uploads/documents 的第一步 mkdir 就会 AccessDenied —— 这不是 helm 独有的缺口。
    """

    @staticmethod
    def _owns(text: str, path: str) -> None:
        """镜像里该路径要在 mkdir 行上出现，且之后有 chown 覆盖它或它的父目录。"""
        mkdir_line = next(
            (ln for ln in text.splitlines() if "mkdir" in ln and path in ln),
            None,
        )
        assert mkdir_line is not None, f"镜像没有创建挂载点 {path}"
        after = text[text.index(mkdir_line):]
        chown_line = next((ln for ln in after.splitlines() if "chown" in ln), None)
        assert chown_line is not None, f"{path} 创建后没有 chown 给运行用户"
        parts = chown_line.split()
        targets = [p for p in parts if p.startswith("/")]
        assert any(path == t or path.startswith(t.rstrip("/") + "/") for t in targets), (
            f"chown 未覆盖 {path}：{chown_line!r}"
        )

    def test_java_image_creates_and_owns_the_uploads_dir(self):
        text = DOCKERFILE_JAVA.read_text(encoding="utf-8")
        self._owns(text, "/app/uploads")
        user_at = text.find("\nUSER ")
        assert user_at > text.index("/app/uploads"), "chown 必须发生在切换到非 root 用户之前"

    def test_python_image_creates_and_owns_both_app_mount_points(self):
        text = DOCKERFILE_PYTHON.read_text(encoding="utf-8")
        for path in ("/app/uploads", "/app/audit-queue"):
            self._owns(text, path)
        # 审计卷在 helm 里按 $(POD_NAME) 分子目录，子目录由进程运行期创建，
        # 所以镜像必须把根目录本身交出来。


class TestHelmDeclaresTheIdentity:
    def test_app_workloads_run_non_root_with_fs_group(self):
        for rel in ("templates/python.yaml", "templates/java.yaml"):
            text = (CHART / rel).read_text(encoding="utf-8")
            spec = text.split("\n    spec:\n", 1)[1].split("\n      containers:", 1)[0]
            assert "securityContext:" in spec, f"{rel} 的 pod 层没有 securityContext"
            for key in ("runAsNonRoot: true", "runAsUser", "runAsGroup", "fsGroup"):
                assert key in spec, f"{rel} 的 pod securityContext 缺 {key}"
            assert "| default" not in spec, f"{rel} 用了 default：nil 父键照样渲染失败（第八十三批）"
            assert ".Values.podSecurity." in spec, f"{rel} 没有从 values 取身份"

    def test_pod_security_root_is_referenced_not_invented(self):
        """.Values.podSecurity 必须在 values.yaml 顶层存在（检查 7 的同一口径）。"""
        values = (CHART / "values.yaml").read_text(encoding="utf-8")
        assert re.search(r"^podSecurity:", values, re.MULTILINE)

    def test_our_own_non_root_workloads_all_declare_an_fs_group(self):
        """凡是"我们的镜像 + 挂卷"的工作负载，都得有 fsGroup 且与 runAsGroup 同号。

        空 PVC 的属主由 provisioner 决定，镜像里的 chown 在挂载后被卷内容取代；没有
        fsGroup 就没有任何机制将卷交给这个组。mysql/etcd/milvus/redis 不在此列：那是
        上游镜像，默认以 root 起、入口脚本自己 chown 数据目录，改它属于另一件事。
        """
        for rel in ("templates/python.yaml", "templates/java.yaml", "templates/plugin-runner.yaml"):
            text = (CHART / rel).read_text(encoding="utf-8")
            assert "fsGroup" in text, f"{rel} 挂了卷却没有 fsGroup"
            group = re.search(r"runAsGroup:\s*(\S+)", text)
            fsgroup = re.search(r"fsGroup:\s*(\S+)", text)
            assert group and fsgroup, f"{rel} 的 runAsGroup/fsGroup 不成对"
            assert group.group(1) == fsgroup.group(1), (
                f"{rel} runAsGroup={group.group(1)} 与 fsGroup={fsgroup.group(1)} 不同号"
            )


class TestUidGate:
    def _load_checker(self):
        spec = importlib.util.spec_from_file_location(
            "hfusionhub_static_checks", ROOT / "scripts" / "static-checks.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_container_uid_gate_passes_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "static-checks.py"), "--container-uid"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_container_uid_gate_is_in_the_default_all_mode(self):
        """并入默认全跑档，否则只在显式传参时才生效（第八十三批的接线哑火形态）。

        全跑档由两处构成：`if not (...)` 的条件里要有这个 flag，下面的默认赋值链里
        也要有——只接一处就会出现"单独传参报红、裸跑却全绿"。
        """
        source = (ROOT / "scripts" / "static-checks.py").read_text(encoding="utf-8")
        main_body = source[source.index("def main()"):]
        assert "--container-uid" in main_body
        all_mode = main_body[main_body.index("args = parser.parse_args()"):
                             main_body.index("if args.tenant_columns:")]
        assert all_mode.count("args.container_uid") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_container_uid_consistency()" in main_body

    def test_gate_flags_a_uid_that_only_matches_one_image(self, tmp_path):
        module = self._load_checker()
        for name in ("DOCKERFILE_PYTHON", "DOCKERFILE_JAVA", "HELM_VALUES"):
            setattr(module, name, tmp_path / name)
        (tmp_path / "DOCKERFILE_PYTHON").write_text(
            "RUN groupadd -r -g 10001 a && useradd -r -u 10001 -g 10001 a\n", encoding="utf-8"
        )
        (tmp_path / "DOCKERFILE_JAVA").write_text(
            "RUN addgroup -S -g 10002 a && adduser -S -u 10002 -G a a\n", encoding="utf-8"
        )
        (tmp_path / "HELM_VALUES").write_text(
            "podSecurity:\n  runAsUser: 10001\n  runAsGroup: 10001\n  fsGroup: 10001\n",
            encoding="utf-8",
        )
        module.problems.clear()
        module.check_container_uid_consistency()
        assert module.problems, "java 镜像的号与 helm/python 不一致时门禁必须报红"
        assert "10002" in module.problems[0]

    def test_gate_flags_an_unpinned_system_user(self, tmp_path):
        module = self._load_checker()
        for name in ("DOCKERFILE_PYTHON", "DOCKERFILE_JAVA", "HELM_VALUES"):
            setattr(module, name, tmp_path / name)
        (tmp_path / "DOCKERFILE_PYTHON").write_text(
            "RUN groupadd -r hfusionhub && useradd -r -g hfusionhub -d /app hfusionhub\n",
            encoding="utf-8",
        )
        (tmp_path / "DOCKERFILE_JAVA").write_text(
            "RUN addgroup -S -g 10001 a && adduser -S -u 10001 -G a a\n", encoding="utf-8"
        )
        (tmp_path / "HELM_VALUES").write_text(
            "podSecurity:\n  runAsUser: 10001\n  runAsGroup: 10001\n  fsGroup: 10001\n",
            encoding="utf-8",
        )
        module.problems.clear()
        module.check_container_uid_consistency()
        assert module.problems, "`useradd -r` 不钉 -u 必须被判为未钉身份"
