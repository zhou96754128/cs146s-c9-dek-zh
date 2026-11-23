"""DEK 命令行入口。

用法：
  dek verify    --root DIR [--manifest dek.json] [--json out.json] [--html out.html] [--no-repro]
  dek inventory --root DIR [--out inventory.json] [--pattern '*.md']
  dek init      --root DIR [--force]

退出码：0 全部通过 / 1 存在失败断言 / 2 清单或参数不合法
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .report import render_html, write_outputs
from .scan import inventory
from .verify import ManifestError, load_manifest, run_manifest

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def _print_table(report):
    rows = []
    for c in report["claims"]:
        rows.append((c["status"], "claim", str(c["id"]), c.get("detail", "")))
    for d in report["deliverables"]:
        rows.append((d["status"], "deliv", d["pattern"], ",".join(d["matched"][:2]) or d.get("detail", "")))
    for r in report["repro"]:
        rows.append((r["status"], "repro", str(r["id"]), r.get("detail", "") or ("exit=%s" % r.get("exit"))))
    width = max([len(r[2]) for r in rows] + [10])
    for status, kind, name, detail in rows:
        line = "%-4s %-6s %-*s %s" % (status, kind, width, name, detail)
        print(line.rstrip())
    s = report["summary"]
    print("")
    print("VERDICT=%s  total=%d  pass=%d  fail=%d  skip=%d" % (
        report["verdict"], s["total"], s["pass"], s["fail"], s["skip"]))


def cmd_verify(args):
    root = Path(args.root).resolve()
    if not root.is_dir():
        print("root 不是目录: %s" % root, file=sys.stderr)
        return EXIT_USAGE
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    try:
        manifest = load_manifest(manifest_path)
    except ManifestError as exc:
        print("清单错误: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    report = run_manifest(root, manifest, run_repros=not args.no_repro)
    _print_table(report)
    written = write_outputs(report, args.json, args.html)
    for path in written:
        print("已写出: %s" % path)
    return EXIT_FAIL if report["verdict"] != "PASS" else EXIT_PASS


def cmd_inventory(args):
    root = Path(args.root).resolve()
    patterns = [args.pattern] if args.pattern else None
    items = inventory(root, patterns)
    total = sum(i["bytes"] for i in items)
    payload = {"root": str(root), "count": len(items), "bytes": total, "items": items}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print("已写出: %s" % args.out)
    else:
        print(text)
    print("files=%d bytes=%d" % (len(items), total), file=sys.stderr)
    return EXIT_PASS


STARTER = {
    "project": "my-delivery",
    "claims": [
        {"id": "示例_文件字节", "kind": "file_size", "source": "README.md", "value": 1, "note": "改成真实值"},
        {"id": "示例_JSON字段", "kind": "json", "source": "summary.json", "pointer": "n_items", "value": 0},
    ],
    "deliverables": [
        {"pattern": "*proposal*", "required": True},
        {"pattern": "*AI日志*", "required": True},
    ],
    "repro": [
        {"id": "示例_自检", "cmd": "python3 -m unittest discover -s tests", "expect_exit": 0, "expect_stdout": "OK"}
    ],
}


def cmd_init(args):
    root = Path(args.root).resolve()
    target = root / "dek.json"
    if target.exists() and not args.force:
        print("已存在，未覆盖: %s（加 --force 覆盖）" % target, file=sys.stderr)
        return EXIT_USAGE
    root.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(STARTER, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("已生成: %s" % target)
    return EXIT_PASS


def cmd_render(args):
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    Path(args.html).write_text(render_html(report), encoding="utf-8")
    print("已写出: %s" % args.html)
    return EXIT_PASS


def build_parser():
    ap = argparse.ArgumentParser(prog="dek", description="Delivery Evidence Kit — 让每个交付数字都可复核")
    ap.add_argument("--version", action="version", version="dek " + __version__)
    sub = ap.add_subparsers(dest="command")

    p = sub.add_parser("verify", help="按清单核验 claim/deliverable/repro")
    p.add_argument("--root", default=".")
    p.add_argument("--manifest", default="dek.json")
    p.add_argument("--json", default="")
    p.add_argument("--html", default="")
    p.add_argument("--no-repro", action="store_true", help="跳过 repro（只读核验）")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("inventory", help="输出文件指纹清单")
    p.add_argument("--root", default=".")
    p.add_argument("--out", default="")
    p.add_argument("--pattern", default="")
    p.set_defaults(func=cmd_inventory)

    p = sub.add_parser("init", help="生成一份起步 dek.json")
    p.add_argument("--root", default=".")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("render", help="由已生成的 JSON 报告重渲染 HTML")
    p.add_argument("--report", required=True)
    p.add_argument("--html", required=True)
    p.set_defaults(func=cmd_render)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return EXIT_USAGE
    return args.func(args)
