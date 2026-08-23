# -*- coding: utf-8 -*-
"""扫描件 → 逐页纯文本。

一本志动辄七八百页,所以这一步做成**可断可续**的:每页一个 `pages/pNNNN.txt`,
已经有了就跳过(`--force` 才重做)。中途断电、关机、换台机器接着跑都不要紧。

三条取字路径,按开销从小到大:

  1. **原生文本层** —— 不少 PDF(书同文、超星、国图数字方志)本身带字,
     直接取出即可,又快又准,连 OCR 都不必。逐页判断,有字的页走这条。
  2. **PaddleOCR** —— 中文识别的首选,简繁横排都好。
  3. **Tesseract** (`chi_sim+chi_tra`) —— 装起来省事,准头略逊,作备胎。

哪一页由哪条路径得来,记在 `meta.json` 里,后面 Markdown 的页首注里也照录 ——
识别来路不同,可信度不同,不该混作一谈。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

PAGE_RE = re.compile(r"^p(\d{4,})\.txt$")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")

# 一页里有这么多汉字,就认为原生文本层是可用的,不必再 OCR
TEXT_LAYER_MIN_CHARS = 40


# ---------------------------------------------------------------- 环境自检

def _has(cmd):
    return shutil.which(cmd) is not None


def _import(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


def check():
    """报一遍本机装了什么,缺什么该怎么装。"""
    rows = [
        ("PyMuPDF (fitz)", _import("fitz"), "pip install pymupdf",
         "PDF 翻页、渲染、取文本层;没有它就退回 poppler 命令行"),
        ("poppler (pdftotext/pdftoppm)", _has("pdftotext") and _has("pdftoppm"),
         "apt install poppler-utils / brew install poppler", "PyMuPDF 的替代品"),
        ("PaddleOCR", _import("paddleocr"), "pip install paddleocr paddlepaddle",
         "中文 OCR 首选"),
        ("Tesseract", _has("tesseract"), "apt install tesseract-ocr tesseract-ocr-chi-sim "
         "tesseract-ocr-chi-tra / brew install tesseract tesseract-lang", "OCR 备胎"),
        ("openpyxl", _import("openpyxl"), "pip install openpyxl", "回写 xlsx 用"),
    ]
    langs = ""
    if _has("tesseract"):
        try:
            out = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                                 text=True, timeout=30).stdout
            langs = " ".join(l for l in out.split() if l.startswith("chi"))
        except Exception:
            pass
    return rows, langs


# ---------------------------------------------------------------- PDF 读写

class Pdf:
    """把 PyMuPDF 与 poppler 两条路子包成一个样子。"""

    def __init__(self, path):
        self.path = str(path)
        self.doc = None
        if _import("fitz"):
            import fitz
            self.doc = fitz.open(self.path)
            self.n = self.doc.page_count
        elif _has("pdfinfo"):
            out = subprocess.run(["pdfinfo", self.path], capture_output=True, text=True).stdout
            m = re.search(r"Pages:\s+(\d+)", out)
            self.n = int(m.group(1)) if m else 0
        else:
            raise RuntimeError("既没有 PyMuPDF 也没有 poppler,无法读 PDF。先跑 `gaz check`。")

    def text(self, i):
        """第 i 页(从 1 起)的原生文本层,没有就返回空串。"""
        if self.doc is not None:
            return self.doc[i - 1].get_text("text") or ""
        out = subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), "-layout", self.path, "-"],
                             capture_output=True, text=True)
        return out.stdout or ""

    def render(self, i, out_png, dpi=300):
        """把第 i 页渲染成图,交给 OCR。"""
        if self.doc is not None:
            import fitz
            pix = self.doc[i - 1].get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0))
            pix.save(out_png)
            return out_png
        stem = out_png[:-4] if out_png.endswith(".png") else out_png
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(i), "-l", str(i),
                        self.path, stem], check=True)
        for cand in (out_png, "%s-%d.png" % (stem, i), "%s-%03d.png" % (stem, i),
                     "%s-%02d.png" % (stem, i)):
            if os.path.exists(cand):
                if cand != out_png:
                    os.replace(cand, out_png)
                return out_png
        raise RuntimeError("pdftoppm 没能渲染第 %d 页" % i)


# ---------------------------------------------------------------- OCR 引擎

_PADDLE = None


def _paddle_engine(lang="ch"):
    global _PADDLE
    if _PADDLE is None:
        from paddleocr import PaddleOCR
        try:
            _PADDLE = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        except TypeError:      # 新版去掉了 show_log / use_angle_cls
            _PADDLE = PaddleOCR(lang=lang)
    return _PADDLE


def ocr_paddle(png, lang="ch"):
    eng = _paddle_engine(lang)
    try:
        res = eng.ocr(png, cls=True)
    except TypeError:
        res = eng.ocr(png)
    lines = []
    for block in (res or []):
        for item in (block or []):
            # 旧版:[box, (text, score)];新版:{'rec_texts': [...]}
            if isinstance(item, dict):
                lines.extend(item.get("rec_texts", []))
            elif len(item) >= 2 and isinstance(item[1], (list, tuple)):
                lines.append(item[1][0])
    return "\n".join(lines)


def ocr_tesseract(png, langs="chi_sim+chi_tra", psm="6"):
    out = subprocess.run(["tesseract", png, "stdout", "-l", langs, "--psm", psm],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("tesseract 出错:%s" % out.stderr.strip()[:300])
    return out.stdout


# ---------------------------------------------------------------- 主流程

def run(src, outdir, engine="auto", dpi=300, first=1, last=None, force=False,
        keep_images=False, lang="ch", log=print):
    """src 可以是一个 PDF,也可以是一个装着页图的目录。"""
    src = str(src)
    pages_dir = os.path.join(outdir, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    meta_path = os.path.join(outdir, "meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    meta.setdefault("source", os.path.abspath(src))
    meta.setdefault("pages", {})

    if os.path.isdir(src):
        imgs = sorted(f for f in os.listdir(src) if f.lower().endswith(IMAGE_EXT))
        total = len(imgs)
        pdf = None
    else:
        pdf = Pdf(src)
        total = pdf.n
        imgs = None
    last = min(last or total, total)
    log("共 %d 页,处理 %d–%d" % (total, first, last))

    tmp = tempfile.mkdtemp(prefix="gaz-")
    done = skipped = 0
    try:
        for i in range(first, last + 1):
            txt_path = os.path.join(pages_dir, "p%04d.txt" % i)
            if os.path.exists(txt_path) and not force:
                skipped += 1
                continue

            text, how = "", ""
            if pdf is not None and engine in ("auto", "text"):
                text = pdf.text(i)
                if engine == "text":
                    # 明说了只走文本层,就照单全收 —— 汉字多寡不该由我来判
                    how = "text-layer" if text.strip() else ""
                elif len(re.findall(r"[一-鿿]", text)) >= TEXT_LAYER_MIN_CHARS:
                    how = "text-layer"
                elif text.strip() and not (_import("paddleocr") or _has("tesseract")):
                    # 汉字不够本该改走 OCR,可本机一个引擎都没有 ——
                    # 与其写出一页空白,不如把文本层原样留下,并注明成色存疑
                    how = "text-layer-thin"
                else:
                    text = ""

            if not text and engine != "text":
                png = os.path.join(tmp, "p%04d.png" % i)
                if pdf is not None:
                    pdf.render(i, png, dpi=dpi)
                else:
                    png = os.path.join(src, imgs[i - 1])
                try:
                    if engine in ("auto", "paddle") and _import("paddleocr"):
                        text, how = ocr_paddle(png, lang=lang), "paddleocr"
                    elif engine in ("auto", "tesseract") and _has("tesseract"):
                        text, how = ocr_tesseract(png), "tesseract"
                    elif engine == "paddle":
                        raise RuntimeError("没装 PaddleOCR")
                    elif engine == "tesseract":
                        raise RuntimeError("没装 Tesseract")
                    else:
                        raise RuntimeError("没有可用的 OCR 引擎,先跑 `gaz check`")
                finally:
                    if pdf is not None and not keep_images and os.path.exists(png):
                        os.remove(png)

            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            meta["pages"][str(i)] = {"how": how, "chars": len(text.strip())}
            done += 1
            if done % 10 == 0 or i == last:
                log("  已识别 %d 页(跳过 %d 页已有的)" % (done, skipped))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)

    empty = [k for k, v in meta["pages"].items() if not v.get("chars")]
    log("完成:新识别 %d 页,沿用 %d 页,页文本在 %s" % (done, skipped, pages_dir))
    if empty:
        log("注意:%d 页没取到任何文字(%s%s)。"
            % (len(empty), "、".join("p." + k for k in empty[:8]),
               " 等" if len(empty) > 8 else ""))
        log("     多半是插图页或空白页;若整本都是空的,八成是没装 OCR 引擎 ——"
            " 跑一遍 `gaz check`。")
    thin = sum(1 for v in meta["pages"].values() if v.get("how") == "text-layer-thin")
    if thin:
        log("注意:%d 页的文本层汉字偏少,本机又无 OCR 引擎,已照原样留下,成色待查。" % thin)
    return meta


def load_pages(outdir):
    """把 pages/ 读回来,返回 [(页码, 文本), ...],按页码排好。"""
    pages_dir = os.path.join(outdir, "pages")
    out = []
    for fn in sorted(os.listdir(pages_dir)):
        m = PAGE_RE.match(fn)
        if not m:
            continue
        with open(os.path.join(pages_dir, fn), encoding="utf-8") as f:
            out.append((int(m.group(1)), f.read()))
    return out
