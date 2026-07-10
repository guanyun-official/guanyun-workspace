import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import account_kernel, config  # noqa: E402


class TestAccountKernel(unittest.TestCase):
    def setUp(self):
        self._orig = config.WORKSPACE
        self.root = Path(tempfile.mkdtemp())
        (self.root / "brands" / "观云" / "accounts").mkdir(parents=True)
        config.WORKSPACE = self.root

    def tearDown(self):
        config.WORKSPACE = self._orig

    def write_account(self, name: str, frontmatter: str, body: str = "# 画像\n已拆解"):
        (self.root / "brands" / "观云" / "accounts" / f"{name}.md").write_text(
            f"---\n{frontmatter}\n---\n\n{body}",
            encoding="utf-8",
        )

    def test_account_identity_drift_is_fail(self):
        self.write_account(
            "科普号",
            '{"account":"科普号","content_types":["文物对照"],"cadence":{"posts_per_day":1}}',
        )
        base = [
            {"record_id": "acc-1", "fields": {"账号名": "图文号1", "小红书号": "1"}},
        ]
        ctypes = [{"record_id": "ct-1", "fields": {"内容类型名": "文物对照", "所属账号": []}}]

        audit = account_kernel.build_audit(
            list_records=lambda table: {"账号表": base, "内容类型表": ctypes}[table],
        )
        statuses = {c["name"]: c for c in audit["checks"]}

        self.assertEqual(statuses["account_identity"]["status"], "FAIL")
        self.assertIn("图文号1", statuses["account_identity"]["detail"])
        self.assertIn("科普号", statuses["account_identity"]["detail"])

    def test_active_workspace_content_type_missing_is_fail(self):
        self.write_account(
            "图文号1",
            '{"account":"图文号1","content_types":["新类型"],"cadence":{"posts_per_day":1}}',
        )
        base = [{"record_id": "acc-1", "fields": {"账号名": "图文号1"}}]
        ctypes = [{"record_id": "ct-1", "fields": {"内容类型名": "旧类型"}}]

        audit = account_kernel.build_audit(
            list_records=lambda table: {"账号表": base, "内容类型表": ctypes}[table],
        )
        status = {c["name"]: c for c in audit["checks"]}["content_types_declared"]

        self.assertEqual(status["status"], "FAIL")
        self.assertIn("新类型", status["detail"])

    def test_inactive_workspace_content_type_missing_is_only_reported(self):
        self.write_account(
            "官号",
            '{"account":"官号","content_types":["品牌叙事"],"launched":false,"cadence":{"posts_per_day":0}}',
        )
        base = [{"record_id": "acc-1", "fields": {"账号名": "官号"}}]
        ctypes = []

        audit = account_kernel.build_audit(
            list_records=lambda table: {"账号表": base, "内容类型表": ctypes}[table],
        )
        status = {c["name"]: c for c in audit["checks"]}["content_types_declared"]

        self.assertEqual(status["status"], "PASS")
        self.assertIn("品牌叙事", status["detail"])

    def test_content_type_without_account_link_is_warn(self):
        self.write_account(
            "图文号1",
            '{"account":"图文号1","content_types":["文物对照"],"cadence":{"posts_per_day":1}}',
        )
        base = [{"record_id": "acc-1", "fields": {"账号名": "图文号1"}}]
        ctypes = [{"record_id": "ct-1", "fields": {"内容类型名": "文物对照", "所属账号": []}}]

        audit = account_kernel.build_audit(
            list_records=lambda table: {"账号表": base, "内容类型表": ctypes}[table],
        )
        status = {c["name"]: c for c in audit["checks"]}["content_type_account_links"]

        self.assertEqual(status["status"], "WARN")
        self.assertIn("文物对照", status["detail"])

    def test_placeholder_profile_is_warn(self):
        self.write_account(
            "图文号1",
            '{"account":"图文号1","cadence":{"posts_per_day":1},'
            '"playbooks":[{"id":"考据","content_type":"文物对照","weight":1.0,"view":"考据"}]}',
            body="# 画像\n> 待 account-teardown 对该号近~20篇总结填充",
        )
        base = [{"record_id": "acc-1", "fields": {"账号名": "图文号1"}}]
        ctypes = [{"record_id": "ct-1", "fields": {"内容类型名": "文物对照", "所属账号": [{"record_ids": ["acc-1"]}]}}]

        audit = account_kernel.build_audit(
            list_records=lambda table: {"账号表": base, "内容类型表": ctypes}[table],
        )
        status = {c["name"]: c for c in audit["checks"]}["account_profiles"]

        self.assertEqual(status["status"], "WARN")
        self.assertIn("图文号1", status["detail"])

    def test_base_content_type_knowhow_is_fail_because_workspace_owns_it(self):
        self.write_account(
            "图文号1",
            '{"account":"图文号1","cadence":{"posts_per_day":1},'
            '"playbooks":[{"id":"考据","content_type":"文物对照","weight":1.0,"view":"考据",'
            '"focus":"文物出处","title_formula":"孤品钩子"}]}',
        )
        base = [{"record_id": "acc-1", "fields": {"账号名": "图文号1"}}]
        ctypes = [{
            "record_id": "ct-1",
            "fields": {
                "内容类型名": "文物对照",
                "所属账号": [{"record_ids": ["acc-1"]}],
                "取数字段·切面": "文物出处",
                "文案元模版": "孤品钩子",
            },
        }]

        audit = account_kernel.build_audit(
            list_records=lambda table: {"账号表": base, "内容类型表": ctypes}[table],
        )
        status = {c["name"]: c for c in audit["checks"]}["source_owner_content_type_knowhow"]

        self.assertEqual(status["status"], "FAIL")
        self.assertIn("文物对照", status["detail"])

    def test_launched_account_without_explicit_playbooks_is_fail(self):
        self.write_account(
            "图文号1",
            '{"account":"图文号1","content_types":["文物对照"],"cadence":{"posts_per_day":1}}',
        )
        base = [{"record_id": "acc-1", "fields": {"账号名": "图文号1"}}]
        ctypes = [{"record_id": "ct-1", "fields": {"内容类型名": "文物对照", "所属账号": [{"record_ids": ["acc-1"]}]}}]

        audit = account_kernel.build_audit(
            list_records=lambda table: {"账号表": base, "内容类型表": ctypes}[table],
        )
        status = {c["name"]: c for c in audit["checks"]}["source_owner_playbooks"]

        self.assertEqual(status["status"], "FAIL")
        self.assertIn("图文号1", status["detail"])


if __name__ == "__main__":
    unittest.main()
