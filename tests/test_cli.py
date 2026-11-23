"""命令行与报告渲染的自检。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dek import cli, report  # noqa: E402


class CliBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class TestCliExitCodes(CliBase):
    def test_verify_all_pass_exit_zero(self):
        self.write("Zhouruoying_proposal.md", "12345")
        self.write("dek.json", json.dumps({
            "project": "t",
            "claims": [{"id": "s", "kind": "file_size", "source": "Zhouruoying_proposal.md", "value": 5}],
            "deliverables": [{"pattern": "*proposal*", "required": True}],
        }))
        self.assertEqual(cli.main(["verify", "--root", str(self.root), "--no-repro"]), 0)

    def test_verify_failure_exit_one(self):
        self.write("dek.json", json.dumps({
            "claims": [{"id": "s", "kind": "file_size", "source": "nope.md", "value": 1}]
        }))
        self.assertEqual(cli.main(["verify", "--root", str(self.root), "--no-repro"]), 1)

    def test_bad_manifest_exit_two(self):
        self.write("dek.json", "{broken")
        self.assertEqual(cli.main(["verify", "--root", str(self.root)]), 2)

    def test_missing_manifest_exit_two(self):
        self.assertEqual(cli.main(["verify", "--root", str(self.root)]), 2)

    def test_root_not_dir_exit_two(self):
        self.assertEqual(cli.main(["verify", "--root", str(self.root / "ghost")]), 2)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(cli.main([]), 2)

    def test_init_writes_starter_and_refuses_overwrite(self):
        self.assertEqual(cli.main(["init", "--root", str(self.root)]), 0)
        self.assertTrue((self.root / "dek.json").exists())
        self.assertEqual(cli.main(["init", "--root", str(self.root)]), 2)
        self.assertEqual(cli.main(["init", "--root", str(self.root), "--force"]), 0)

    def test_verify_writes_json_and_html(self):
        self.write("Zhouruoying_proposal.md", "12345")
        self.write("dek.json", json.dumps({
            "claims": [{"id": "s", "kind": "file_size", "source": "Zhouruoying_proposal.md", "value": 5}],
            "deliverables": [{"pattern": "*proposal*", "required": True}],
        }))
        out_json = str(self.root / "out" / "r.json")
        out_html = str(self.root / "out" / "r.html")
        (self.root / "out").mkdir()
        rc = cli.main(["verify", "--root", str(self.root), "--no-repro",
                       "--json", out_json, "--html", out_html])
        self.assertEqual(rc, 0)
        data = json.loads(Path(out_json).read_text(encoding="utf-8"))
        self.assertEqual(data["verdict"], "PASS")
        self.assertIn("DEK 交付核验报告", Path(out_html).read_text(encoding="utf-8"))

    def test_inventory_writes_file(self):
        self.write("a.md", "12345")
        out = str(self.root / "inv.json")
        self.assertEqual(cli.main(["inventory", "--root", str(self.root), "--out", out]), 0)
        data = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["bytes"], 5)


class TestRender(CliBase):
    def _sample(self, verdict="PASS"):
        return {
            "project": "demo",
            "root": "/tmp/demo",
            "verdict": verdict,
            "summary": {"total": 2, "pass": 2 if verdict == "PASS" else 1, "fail": 0 if verdict == "PASS" else 1, "skip": 0,
                        "claims": 1, "deliverables": 1, "repro": 0},
            "claims": [{"id": "c1", "kind": "file_size", "source": "a.md", "expected": 5,
                        "actual": 5 if verdict == "PASS" else 6, "status": verdict, "detail": ""}],
            "deliverables": [{"id": "*proposal*", "pattern": "*proposal*", "required": True,
                              "matched": ["a.md"], "status": "PASS", "detail": ""}],
            "repro": [],
        }

    def test_html_contains_verdict_and_no_external_assets(self):
        html = report.render_html(self._sample("PASS"))
        self.assertIn("VERDICT = PASS", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_html_escapes_injection(self):
        data = self._sample()
        data["claims"][0]["source"] = "<script>alert(1)</script>"
        html = report.render_html(data)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_render_cli_from_json(self):
        p = self.root / "r.json"
        p.write_text(json.dumps(self._sample(), ensure_ascii=False), encoding="utf-8")
        out = self.root / "r.html"
        self.assertEqual(cli.main(["render", "--report", str(p), "--html", str(out)]), 0)
        self.assertIn("VERDICT = PASS", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
