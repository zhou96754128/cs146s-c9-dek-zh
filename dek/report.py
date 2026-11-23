"""报告渲染：单文件 HTML（无外链、无 CDN，可直接归档或贴进 Pages）。"""

from __future__ import annotations

import json
from html import escape

CSS = """
:root{--bg:#0f1115;--panel:#171a21;--line:#262b36;--fg:#e6e9ef;--dim:#9aa4b2;
--ok:#3ecf8e;--bad:#ff6b6b;--skip:#c9a227}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.6 -apple-system,"PingFang SC","Helvetica Neue",Arial,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--dim);font-size:13px;margin-bottom:20px;word-break:break-all}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.kpi .n{font-size:24px;font-weight:600}
.kpi .l{color:var(--dim);font-size:12px;margin-top:2px}
.verdict{border-radius:10px;padding:12px 14px;margin-bottom:22px;font-weight:600}
.verdict.pass{background:rgba(62,207,142,.12);border:1px solid var(--ok);color:var(--ok)}
.verdict.fail{background:rgba(255,107,107,.12);border:1px solid var(--bad);color:var(--bad)}
h2{font-size:15px;margin:26px 0 10px;color:var(--dim);text-transform:none;letter-spacing:.02em}
table{width:100%;border-collapse:collapse;background:var(--panel);
border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line);
vertical-align:top;font-size:13px}
th{color:var(--dim);font-weight:500;background:#141821}
tr:last-child td{border-bottom:none}
code{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#c8d3e0}
.pass{color:var(--ok)} .fail{color:var(--bad)} .skip{color:var(--skip)}
.tag{font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid currentColor}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px;word-break:break-all;color:#c8d3e0}
.detail{color:var(--dim);font-size:12px;margin-top:3px}
pre{background:#0b0d11;border:1px solid var(--line);border-radius:8px;padding:10px;
overflow:auto;font-size:12px;max-height:260px}
footer{margin-top:32px;color:var(--dim);font-size:12px}
"""


def _tag(status):
    cls = {"PASS": "pass", "FAIL": "fail", "SKIP": "skip"}.get(status, "skip")
    return '<span class="tag %s">%s</span>' % (cls, escape(status))


def _table(headers, rows):
    head = "".join("<th>%s</th>" % escape(h) for h in headers)
    body = []
    for row in rows:
        cells = "".join("<td>%s</td>" % c for c in row)
        body.append("<tr>%s</tr>" % cells)
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (head, "".join(body))


def render_html(report):
    s = report["summary"]
    verdict_cls = "pass" if report["verdict"] == "PASS" else "fail"
    parts = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>DEK 交付核验报告 · %s</title>" % escape(report.get("project") or "delivery"),
        "<style>%s</style></head><body><div class='wrap'>" % CSS,
        "<h1>DEK 交付核验报告</h1>",
        "<div class='sub'>project=%s · root=%s</div>"
        % (escape(report.get("project") or "-"), escape(report.get("root") or "-")),
        "<div class='kpis'>",
    ]
    for label, value, tone in (
        ("断言总数", s["total"], ""),
        ("PASS", s["pass"], "ok"),
        ("FAIL", s["fail"], "bad"),
        ("SKIP", s["skip"], "sub"),
    ):
        color = {"ok": "var(--ok)", "bad": "var(--bad)", "sub": "var(--dim)"}.get(tone, "var(--fg)")
        parts.append(
            "<div class='kpi'><div class='n' style='color:%s'>%s</div><div class='l'>%s</div></div>"
            % (color, value, escape(label))
        )
    parts.append("</div>")
    parts.append(
        "<div class='verdict %s'>VERDICT = %s</div>" % (verdict_cls, escape(report["verdict"]))
    )

    if report["claims"]:
        rows = []
        for c in report["claims"]:
            rows.append([
                "<code>%s</code>" % escape(str(c["id"])),
                "<code>%s</code>" % escape(str(c.get("kind") or "json")),
                "<code>%s</code>" % escape(str(c.get("source"))),
                "<code>%s</code>" % escape(json.dumps(c.get("expected"), ensure_ascii=False)),
                "<code>%s</code>" % escape(json.dumps(c.get("actual"), ensure_ascii=False)),
                _tag(c["status"]) + ("<div class='detail'>%s</div>" % escape(c["detail"]) if c.get("detail") else ""),
            ])
        parts.append("<h2>① claim · 数字与来源一致（%d）</h2>" % len(rows))
        parts.append(_table(["断言", "类型", "来源", "期望", "实际", "结果"], rows))

    if report["deliverables"]:
        rows = []
        for d in report["deliverables"]:
            hits = "<br>".join("<code>%s</code>" % escape(h) for h in d["matched"]) or "<span class='detail'>无</span>"
            rows.append([
                "<code>%s</code>" % escape(d["pattern"]),
                "必须" if d["required"] else "可选",
                hits,
                _tag(d["status"]),
            ])
        parts.append("<h2>② deliverable · 必交物按文件名通配命中（%d）</h2>" % len(rows))
        parts.append(_table(["通配符", "要求", "命中文件", "结果"], rows))

    if report["repro"]:
        rows = []
        for r in report["repro"]:
            out = ""
            if r.get("stdout") or r.get("stderr"):
                out = "<pre>%s</pre>" % escape((r.get("stdout") or "") + (r.get("stderr") or ""))
            rows.append([
                "<code>%s</code>" % escape(str(r["id"])),
                "<code>%s</code>" % escape(str(r.get("cmd"))),
                escape(str(r.get("exit"))),
                _tag(r["status"]) + ("<div class='detail'>%s</div>" % escape(r["detail"]) if r.get("detail") else "") + out,
            ])
        parts.append("<h2>③ repro · 复现命令真跑（%d）</h2>" % len(rows))
        parts.append(_table(["断言", "命令", "退出码", "结果"], rows))

    parts.append(
        "<footer>由 DEK（Delivery Evidence Kit）生成 · 断言 %d 条 · 失败 %d 条 · 报告中不包含任何人工填写的结果</footer>"
        % (s["total"], s["fail"])
    )
    parts.append("</div></body></html>")
    return "".join(parts)


def write_outputs(report, json_path=None, html_path=None):
    written = []
    if json_path:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        written.append(json_path)
    if html_path:
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(render_html(report))
        written.append(html_path)
    return written
