"""核心核验逻辑的自检（标准库 unittest，零依赖）。"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dek import scan, verify  # noqa: E402


class TempProject(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text, encoding="utf-8"):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        return path


class TestScan(TempProject):
    def test_sha256_matches_hashlib(self):
        import hashlib

        p = self.write("a.txt", "hello")
        self.assertEqual(scan.sha256_file(p), hashlib.sha256(b"hello").hexdigest())

    def test_walk_skips_git_and_pycache(self):
        self.write("keep.txt", "x")
        self.write(".git/config", "x")
        self.write("__pycache__/m.pyc", "x")
        rels = [p.name for p in scan.walk_files(self.root)]
        self.assertEqual(rels, ["keep.txt"])

    def test_inventory_reports_bytes(self):
        self.write("a.txt", "12345")
        items = scan.inventory(self.root)
        self.assertEqual(items[0]["bytes"], 5)

    def test_inventory_pattern_filter(self):
        self.write("a.md", "x")
        self.write("b.txt", "x")
        items = scan.inventory(self.root, ["*.md"])
        self.assertEqual([i["path"] for i in items], ["a.md"])

    def test_read_text_falls_back_to_gb18030(self):
        p = self.root / "cn.txt"
        p.write_bytes("中文内容".encode("gb18030"))
        self.assertEqual(scan.read_text(p), "中文内容")

    def test_directory_never_matches_deliverable(self):
        """目录式条目必须永远匹配不上 —— 真实平台就是这么判的。"""
        (self.root / "screenshots").mkdir()
        (self.root / "screenshots" / "01.png").write_bytes(b"png")
        hits = scan.match_deliverables(self.root, ["*.png"])
        self.assertEqual(hits["*.png"], ["screenshots/01.png"])
        hits_dir = scan.match_deliverables(self.root, ["screenshots/"])
        self.assertEqual(hits_dir["screenshots/"], [])

    def test_wildcard_matches_basename_under_subdir(self):
        self.write("docs/repo链接.md", "x")
        hits = scan.match_deliverables(self.root, ["*repo链接*"])
        self.assertEqual(hits["*repo链接*"], ["docs/repo链接.md"])

    def test_wildcard_multiple_hits_sorted(self):
        self.write("b_AAR_W2.md", "x")
        self.write("a_AAR_W1.md", "x")
        hits = scan.match_deliverables(self.root, ["*AAR_W*"])
        self.assertEqual(hits["*AAR_W*"], ["a_AAR_W1.md", "b_AAR_W2.md"])


class TestClaims(TempProject):
    def test_file_size_claim_pass(self):
        self.write("a.md", "12345")
        res = verify.check_claim({"id": "s", "kind": "file_size", "source": "a.md", "value": 5}, self.root)
        self.assertEqual(res["status"], verify.PASS)

    def test_file_size_claim_fail(self):
        self.write("a.md", "12345")
        res = verify.check_claim({"id": "s", "kind": "file_size", "source": "a.md", "value": 6}, self.root)
        self.assertEqual(res["status"], verify.FAIL)
        self.assertIn("期望", res["detail"])

    def test_json_pointer_pass(self):
        self.write("s.json", json.dumps({"run": {"n_solved": 11}}))
        res = verify.check_claim(
            {"id": "n", "source": "s.json", "pointer": "run.n_solved", "value": 11}, self.root
        )
        self.assertEqual(res["status"], verify.PASS)

    def test_json_pointer_missing_key_fails_not_crashes(self):
        self.write("s.json", json.dumps({"run": {}}))
        res = verify.check_claim(
            {"id": "n", "source": "s.json", "pointer": "run.nope", "value": 1}, self.root
        )
        self.assertEqual(res["status"], verify.FAIL)
        self.assertIn("取数失败", res["detail"])

    def test_numeric_tolerance(self):
        self.write("s.json", json.dumps({"bp": 1.2244}))
        ok = verify.check_claim(
            {"id": "b", "source": "s.json", "pointer": "bp", "value": 1.2245, "tolerance": 0.001},
            self.root,
        )
        self.assertEqual(ok["status"], verify.PASS)
        bad = verify.check_claim(
            {"id": "b", "source": "s.json", "pointer": "bp", "value": 1.3, "tolerance": 0.001},
            self.root,
        )
        self.assertEqual(bad["status"], verify.FAIL)

    def test_sha256_prefix_pass(self):
        self.write("a.md", "hello")
        full = scan.sha256_file(self.root / "a.md")
        res = verify.check_claim(
            {"id": "h", "kind": "sha256_prefix", "source": "a.md", "value": full[:16], "length": 16},
            self.root,
        )
        self.assertEqual(res["status"], verify.PASS)

    def test_sha256_prefix_mismatch_fails(self):
        self.write("a.md", "hello")
        res = verify.check_claim(
            {"id": "h", "kind": "sha256_prefix", "source": "a.md", "value": "deadbeefdeadbeef"},
            self.root,
        )
        self.assertEqual(res["status"], verify.FAIL)

    def test_contains_and_not_contains(self):
        self.write("d.md", "多次实测区间约 76–95")
        ok = verify.check_claim(
            {"id": "c", "kind": "contains", "source": "d.md", "value": "76–95"}, self.root
        )
        self.assertEqual(ok["status"], verify.PASS)
        bad = verify.check_claim(
            {"id": "c", "kind": "not_contains", "source": "d.md", "value": "76–95"}, self.root
        )
        self.assertEqual(bad["status"], verify.FAIL)

    def test_line_count(self):
        self.write("a.md", "1\n2\n3\n")
        res = verify.check_claim({"id": "l", "kind": "line_count", "source": "a.md", "value": 3}, self.root)
        self.assertEqual(res["status"], verify.PASS)

    def test_missing_source_fails(self):
        res = verify.check_claim({"id": "x", "kind": "file_size", "source": "nope.md", "value": 1}, self.root)
        self.assertEqual(res["status"], verify.FAIL)

    def test_missing_value_or_source_is_fail(self):
        self.assertEqual(verify.check_claim({"id": "x"}, self.root)["status"], verify.FAIL)

    def test_file_exists_claim(self):
        self.write("a.md", "x")
        ok = verify.check_claim({"id": "e", "kind": "file_exists", "source": "a.md", "value": True}, self.root)
        self.assertEqual(ok["status"], verify.PASS)


class TestDeliverables(TempProject):
    def test_required_hit_pass(self):
        self.write("Zhouruoying_proposal.md", "x")
        rows = verify.check_deliverables(self.root, [{"pattern": "*proposal*", "required": True}])
        self.assertEqual(rows[0]["status"], verify.PASS)

    def test_required_miss_fail(self):
        rows = verify.check_deliverables(self.root, [{"pattern": "*proposal*", "required": True}])
        self.assertEqual(rows[0]["status"], verify.FAIL)
        self.assertEqual(rows[0]["detail"], "未命中任何文件")

    def test_optional_miss_is_skip(self):
        rows = verify.check_deliverables(self.root, [{"pattern": "*demo*", "required": False}])
        self.assertEqual(rows[0]["status"], verify.SKIP)


class TestRepro(TempProject):
    def test_exit_zero_pass(self):
        res = verify.run_repro({"id": "ok", "cmd": "python3 -c \"print('fine')\""}, self.root)
        self.assertEqual(res["status"], verify.PASS)
        self.assertEqual(res["exit"], 0)

    def test_nonzero_exit_fails(self):
        res = verify.run_repro({"id": "bad", "cmd": "python3 -c \"raise SystemExit(3)\""}, self.root)
        self.assertEqual(res["status"], verify.FAIL)
        self.assertIn("退出码 3", res["detail"])

    def test_expected_stdout_marker(self):
        ok = verify.run_repro(
            {"id": "m", "cmd": "python3 -c \"print('OK 12')\"", "expect_stdout": "OK"}, self.root
        )
        self.assertEqual(ok["status"], verify.PASS)
        bad = verify.run_repro(
            {"id": "m", "cmd": "python3 -c \"print('no')\"", "expect_stdout": "OK"}, self.root
        )
        self.assertEqual(bad["status"], verify.FAIL)

    def test_missing_cmd_fails(self):
        self.assertEqual(verify.run_repro({"id": "x"}, self.root)["status"], verify.FAIL)

    def test_cwd_is_root(self):
        self.write("marker.txt", "here")
        res = verify.run_repro(
            {"id": "cwd", "cmd": "python3 -c \"print(open('marker.txt').read())\"", "expect_stdout": "here"},
            self.root,
        )
        self.assertEqual(res["status"], verify.PASS)


class TestManifest(TempProject):
    def test_load_rejects_non_json(self):
        self.write("dek.json", "not json")
        with self.assertRaises(verify.ManifestError):
            verify.load_manifest(self.root / "dek.json")

    def test_load_rejects_wrong_type(self):
        self.write("dek.json", json.dumps({"claims": {}}))
        with self.assertRaises(verify.ManifestError):
            verify.load_manifest(self.root / "dek.json")

    def test_load_missing_file(self):
        with self.assertRaises(verify.ManifestError):
            verify.load_manifest(self.root / "absent.json")

    def test_run_manifest_verdict_and_counts(self):
        self.write("proposal.md", "12345")
        manifest = {
            "project": "t",
            "claims": [{"id": "s", "kind": "file_size", "source": "proposal.md", "value": 5}],
            "deliverables": [{"pattern": "*proposal*", "required": True}],
            "repro": [],
        }
        report = verify.run_manifest(self.root, manifest)
        self.assertEqual(report["verdict"], verify.PASS)
        self.assertEqual(report["summary"]["pass"], 2)
        self.assertEqual(report["summary"]["fail"], 0)

    def test_run_manifest_verdict_fail(self):
        manifest = {"claims": [{"id": "s", "kind": "file_size", "source": "x.md", "value": 1}]}
        report = verify.run_manifest(self.root, manifest)
        self.assertEqual(report["verdict"], verify.FAIL)
        self.assertEqual(report["summary"]["fail"], 1)


if __name__ == "__main__":
    unittest.main()
