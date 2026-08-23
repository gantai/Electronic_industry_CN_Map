# -*- coding: utf-8 -*-
"""候选记录的中转格式:制表符分隔的 TSV。

之所以用 TSV 而不是 xlsx —— 它是纯文本,git diff 看得见改了哪一格,
Excel、Numbers、VS Code 乃至 Obsidian 都打得开。第一列 `keep` 是闸门:
留着 `?` 的行谁也进不了工作簿,改成 `y` 才放行,`n` 表示看过了、不要。
"""

import csv
import os


def write(path, rows, columns=None):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    if not rows:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write("\t".join(columns or ["keep"]) + "\n")
        return 0
    cols = columns or list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t",
                           extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    return len(rows)


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f, delimiter="\t")]


def kept(rows):
    """只放行明确写了 y / yes / 是 / 1 的行。"""
    ok = {"y", "yes", "是", "1", "true", "t"}
    return [r for r in rows if str(r.get("keep", "")).strip().lower() in ok]
