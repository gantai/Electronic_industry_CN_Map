# -*- coding: utf-8 -*-
"""往屏幕上写字这一头的事 —— 专治 Windows 上接了管道就炸。

`python … | Select-String 隶属` 这么一接,Python 就不再按控制台的编码写,
改按系统的编码写;简体中文 Windows 上那是 GBK,而 GBK 里**没有「✓」**。
于是第一行还没打完就抛 UnicodeEncodeError,整场跑断在第一条上 ——
看着倒像是代码坏了,其实一个字符也没算错。

(`run_out` 那头治的是反过来的毛病:读别人吐出来的 UTF-8。同一件事的两面。)

两手都要,缺一不可:

* **编码错误不许致命** —— 为一个记号丢掉整场输出,不值当;
* **记号挑写得出的那一套** —— GBK 有「√」「×」,没有「✓」「✗」。
  只做头一件,✓ 会写成一个「?」,满屏问号,照样看不成。
"""

import sys

#: 由好到次,挑头一对写得出的。末一对是 ASCII,哪儿都写得出。
MARK_SETS = [("✓", "✗"), ("√", "×"), ("+", "!")]


def writable(text, stream=None):
    """这段字,这个流写得出去吗?"""
    enc = getattr(stream or sys.stdout, "encoding", None)
    if not enc:
        return False
    try:
        text.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def marks(stream=None):
    """回一对 (对号, 叉号) —— 这个流写得出去的那一对。"""
    for tick, cross in MARK_SETS:
        if writable(tick + cross, stream):
            return tick, cross
    return MARK_SETS[-1]


def init(stream=None):
    """把编码错误设成不致命,回一对写得出的记号。

    进程一起头就调一次。回值拿去打勾打叉,别再把「✓」写死在格式串里。"""
    stream = stream or sys.stdout
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(errors="replace")
        except (ValueError, OSError):
            # 流被人换过(测试里常有),换不动就算了 —— 底下挑记号那一步
            # 照样管用,不至于炸。
            pass
    return marks(stream)
