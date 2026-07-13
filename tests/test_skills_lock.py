"""skills.lock.json 结构语义(单一真相源:check_p1 与单测共用,防校验漂移)。

历史 bug:候选B 把引擎打包成本地 skill,skills.lock 出现 content-loop-local 这个
「本地 source」(workspace 原生,无 repo,sha='local'),但 check_p1 ② 硬性要求
每个 source 都有 repo 键 → AssertionError → check_p1 红。本测试锁住语义:
  本地 source(sha=='local')不要求 repo;远程 source 须有 repo + 40 位真 commit。
纯函数,零网络零文件依赖(真实 lock 只测结构不碰 local 路径)。
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchestrator import skills_lock  # noqa: E402

REMOTE = {"name": "r", "repo": "https://x/r.git", "local": "~/x", "ref": "main",
          "sha": "0" * 40, "skills": ["a"], "install": "symlink"}
LOCAL = {"name": "content-loop-local", "local": "/tmp/x", "ref": "workspace-native",
         "sha": "local", "skills": ["content-loop"], "install": "symlink"}


class TestSkillsLock(unittest.TestCase):
    def test_local_source_ok_without_repo(self):
        self.assertEqual(skills_lock.validate({"sources": [LOCAL]}), [])

    def test_remote_source_valid(self):
        self.assertEqual(skills_lock.validate({"sources": [REMOTE]}), [])

    def test_remote_missing_repo_flagged(self):
        s = dict(REMOTE); del s["repo"]
        errs = skills_lock.validate({"sources": [s]})
        self.assertTrue(any("repo" in e for e in errs), f"漏 repo 的远程 source 未被抓: {errs}")

    def test_remote_bad_sha_flagged(self):
        s = dict(REMOTE); s["sha"] = "deadbeef"
        errs = skills_lock.validate({"sources": [s]})
        self.assertTrue(any("40" in e for e in errs), f"非 40 位 sha 未被抓: {errs}")

    def test_missing_common_key_flagged(self):
        s = dict(LOCAL); del s["skills"]
        errs = skills_lock.validate({"sources": [s]})
        self.assertTrue(any("skills" in e for e in errs))

    def test_empty_sources_flagged(self):
        self.assertTrue(skills_lock.validate({"sources": []}))

    def test_is_local_source_by_sha_marker(self):
        self.assertTrue(skills_lock.is_local_source(LOCAL))
        self.assertFalse(skills_lock.is_local_source(REMOTE))

    def test_real_lock_schema_valid(self):
        lock = json.loads((ROOT / "skills.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(
            skills_lock.validate(lock), [],
            "真实 skills.lock.json 结构语义应合法(含 content-loop-local 本地 source)",
        )

    def test_drift_detects_head_mismatch(self):
        # 锁版漂移:安装现场实际 HEAD ≠ 锁定 sha → 抓;注入 head_of 免真 git
        errs = skills_lock.installed_drift({"sources": [REMOTE]}, lambda p: "f" * 40)
        self.assertTrue(any("漂移" in e for e in errs), f"HEAD 不符未被抓: {errs}")

    def test_drift_silent_when_head_matches(self):
        errs = skills_lock.installed_drift({"sources": [REMOTE]}, lambda p: REMOTE["sha"])
        self.assertEqual(errs, [])                        # HEAD==锁 → 无漂移

    def test_drift_skips_missing_repo_no_false_alarm(self):
        errs = skills_lock.installed_drift({"sources": [REMOTE]}, lambda p: None)
        self.assertEqual(errs, [])                        # 取不到 HEAD(路径缺/非git)→跳过不误报

    def test_drift_ignores_local_source(self):
        errs = skills_lock.installed_drift({"sources": [LOCAL]}, lambda p: "whatever")
        self.assertEqual(errs, [])                        # 本地 source(sha=local)无 commit 概念,不查

    def test_real_lock_head_aligned(self):
        # 真实 lock:远程源锁定 sha 应 == 本地仓库现 HEAD(漂了这条红,提醒重装/更锁)
        lock = json.loads((ROOT / "skills.lock.json").read_text(encoding="utf-8"))

        def head_of(local):
            p = Path(local).expanduser()
            if not p.exists():
                return None
            r = subprocess.run(["git", "-C", str(p), "rev-parse", "HEAD"],
                               capture_output=True, text=True)
            return r.stdout.strip() if r.returncode == 0 else None

        self.assertEqual(skills_lock.installed_drift(lock, head_of), [],
                         "远程技能源锁版应与安装现场 HEAD 对齐(漂移=源仓库变了没重装或锁没更)")

    def test_install_skills_does_not_warn_for_local_source_marker(self):
        p = subprocess.run(
            ["bash", "scripts/install_skills.sh"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("content-loop-local", p.stderr)
        self.assertNotIn("lock sha=local", p.stderr)


if __name__ == "__main__":
    unittest.main()
