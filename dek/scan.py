"""文件扫描、证据指纹与必交物匹配。

三条硬规则（都来自真实事故）：
1. 只返回**文件**，目录永不参与匹配 —— 目录式条目在真实平台永远匹配不上。
2. 匹配既看相对路径也看 basename，通配符 `*repo链接*` 能命中 `docs/repo链接.md`。
3. 指纹一律流式 sha256，不把大文件读进内存。
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", ".mypy_cache"}

CHUNK = 256 * 1024


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def read_text(path) -> str:
    """按 utf-8 -> gb18030 -> latin-1 的顺序尝试解码，绝不静默丢内容。"""
    data = Path(path).read_bytes()
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def walk_files(root):
    """稳定顺序遍历目录下的所有文件（跳过缓存/版本控制目录）。"""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            yield Path(dirpath) / name


def inventory(root, patterns=None):
    root = Path(root)
    items = []
    for path in walk_files(root):
        rel = path.relative_to(root).as_posix()
        if patterns and not any(fnmatch.fnmatch(rel, pat) for pat in patterns):
            continue
        st = path.stat()
        items.append({"path": rel, "bytes": st.st_size, "sha256": sha256_file(path)})
    return items


def match_deliverables(root, patterns):
    """把每个通配符展开成命中的**文件相对路径**列表。

    目录永远不会出现在结果里：这是刻意的，因为按目录匹配在真实平台上必然失败。
    """
    root = Path(root)
    names = [p.relative_to(root).as_posix() for p in walk_files(root)]
    matched = {}
    for pattern in patterns:
        hits = []
        for name in names:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(Path(name).name, pattern):
                hits.append(name)
        matched[pattern] = hits
    return matched
