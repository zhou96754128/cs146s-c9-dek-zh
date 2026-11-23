"""DEK 核验核心：三类断言。

claim       —— 文档里的数字必须等于来源文件里的数字（防"文档写 226315、盘上 523426"）
deliverable —— 必交物必须按文件名通配命中真实文件（防"URL 只写在 README 正文里"）
repro       —— 复现命令必须真跑且退出码/标记符合预期（防"入口脚本从没真跑过"）
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .scan import match_deliverables, read_text, sha256_file

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

DEFAULT_TIMEOUT = 300


class ManifestError(ValueError):
    """清单本身不合法（不是核验失败，是配置错误）。"""


def load_manifest(path):
    p = Path(path)
    if not p.exists():
        raise ManifestError("清单不存在: %s" % p)
    try:
        data = json.loads(read_text(p))
    except json.JSONDecodeError as exc:
        raise ManifestError("清单不是合法 JSON: %s" % exc) from exc
    if not isinstance(data, dict):
        raise ManifestError("清单根节点必须是对象")
    for key in ("claims", "deliverables", "repro"):
        if key in data and not isinstance(data[key], list):
            raise ManifestError("'%s' 必须是数组" % key)
    return data


def _pointer(obj, ptr):
    cur = obj
    if ptr in ("", None):
        return cur
    for part in str(ptr).split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(str(ptr))
            cur = cur[part]
        else:
            raise KeyError(str(ptr))
    return cur


BOOL_KINDS = {"contains", "not_contains", "file_exists"}


def actual_value(claim, root):
    """按 kind 从来源文件里取出真实值。取不到就抛异常，由调用方记为 FAIL。"""
    kind = claim.get("kind", "json")
    src = Path(root) / str(claim["source"])
    if kind == "file_exists":
        return src.exists()
    if not src.exists():
        raise FileNotFoundError(str(claim["source"]))
    if kind == "file_size":
        return src.stat().st_size
    if kind == "sha256":
        return sha256_file(src)
    if kind == "sha256_prefix":
        return sha256_file(src)[: int(claim.get("length", 16))]
    if kind == "line_count":
        return len(read_text(src).splitlines())
    if kind == "contains":
        return str(claim["value"]) in read_text(src)
    if kind == "not_contains":
        return str(claim["value"]) not in read_text(src)
    return _pointer(json.loads(read_text(src)), claim.get("pointer", ""))


def compare(claim, actual):
    expected = claim["value"]
    kind = claim.get("kind", "json")
    if kind in BOOL_KINDS:
        return bool(actual) is True
    if isinstance(expected, bool):
        return bool(actual) == expected
    if isinstance(expected, (int, float)):
        tol = float(claim.get("tolerance", 0))
        try:
            return abs(float(actual) - float(expected)) <= tol
        except (TypeError, ValueError):
            return False
    if kind == "sha256_prefix":
        return str(actual).startswith(str(expected))
    return str(actual) == str(expected)


def check_claim(claim, root):
    cid = str(claim.get("id") or claim.get("source") or "claim")
    base = {
        "id": cid,
        "kind": claim.get("kind", "json"),
        "source": claim.get("source"),
        "expected": claim.get("value"),
        "note": claim.get("note", ""),
    }
    if not claim.get("source") or "value" not in claim:
        base.update(status=FAIL, actual=None, detail="缺少 source 或 value")
        return base
    try:
        actual = actual_value(claim, root)
    except Exception as exc:  # noqa: BLE001 - 任何取数失败都算这条断言失败
        base.update(status=FAIL, actual=None, detail="取数失败: %s: %s" % (type(exc).__name__, exc))
        return base
    ok = compare(claim, actual)
    base.update(status=PASS if ok else FAIL, actual=actual, detail="" if ok else "期望 %r，实际 %r" % (claim.get("value"), actual))
    return base


def check_deliverables(root, entries):
    patterns = [e["pattern"] for e in entries if isinstance(e, dict) and e.get("pattern")]
    hits = match_deliverables(root, patterns)
    results = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("pattern"):
            continue
        pattern = entry["pattern"]
        matched = hits.get(pattern, [])
        required = entry.get("required", True)
        if matched:
            status = PASS
        elif required:
            status = FAIL
        else:
            status = SKIP
        results.append({
            "id": pattern,
            "pattern": pattern,
            "required": required,
            "matched": matched,
            "status": status,
            "detail": "" if matched else ("未命中任何文件" if required else "可选，未提供"),
        })
    return results


def run_repro(entry, root, timeout=None):
    rid = str(entry.get("id") or entry.get("cmd") or "repro")
    cmd = entry.get("cmd")
    if not cmd:
        return {"id": rid, "status": FAIL, "detail": "缺少 cmd", "exit": None, "stdout": "", "stderr": ""}
    limit = int(entry.get("timeout", timeout or DEFAULT_TIMEOUT))
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=limit,
        )
    except subprocess.TimeoutExpired:
        return {"id": rid, "cmd": cmd, "status": FAIL, "detail": "超时 %ss" % limit, "exit": None, "stdout": "", "stderr": ""}
    expect_exit = int(entry.get("expect_exit", 0))
    marker = entry.get("expect_stdout")
    ok = proc.returncode == expect_exit
    detail = ""
    if not ok:
        detail = "退出码 %s != 期望 %s" % (proc.returncode, expect_exit)
    if marker and marker not in proc.stdout:
        ok = False
        detail = (detail + "; " if detail else "") + "stdout 缺少标记 %r" % marker
    return {
        "id": rid,
        "cmd": cmd,
        "status": PASS if ok else FAIL,
        "detail": detail,
        "exit": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-2000:],
        "timeout": limit,
    }


def run_manifest(root, manifest, run_repros=True):
    claims = [check_claim(c, root) for c in manifest.get("claims", [])]
    deliverables = check_deliverables(root, manifest.get("deliverables", []))
    repros = [run_repro(r, root) for r in manifest.get("repro", [])] if run_repros else []

    rows = claims + deliverables + repros
    counts = {PASS: 0, FAIL: 0, SKIP: 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "project": manifest.get("project", ""),
        "root": str(root),
        "verdict": FAIL if counts[FAIL] else PASS,
        "summary": {
            "total": len(rows),
            "pass": counts[PASS],
            "fail": counts[FAIL],
            "skip": counts[SKIP],
            "claims": len(claims),
            "deliverables": len(deliverables),
            "repro": len(repros),
        },
        "claims": claims,
        "deliverables": deliverables,
        "repro": repros,
    }
