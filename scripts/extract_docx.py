#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract a .docx into the same build layout as the epub/pdf extractors.

    python extract_docx.py <book.docx> [-o build]

DOCX has a real heading structure (the outline pane works), so chapters come
from Heading 1/2 styles in document order. Images come from inline shapes
plus any relationship that is an image.

Traps handled (references/pitfalls.md):
  H8   python-docx walks paragraphs and tables SEPARATELY and in the wrong
       order if you just iterate twice; the body must be walked once through
       the XML so paragraphs and tables interleave correctly.
  H9   heading styles are localised ("Heading 1" vs "标题 1"); match on the
       outline level property rather than the style name string.
  H10  never shadow an output-path variable with paragraph text.
  H11  a heading must START a new chapter, not merge into the current one.
"""
import argparse, json, os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("-o", "--out", default="docx-build")
    a = ap.parse_args()

    try:
        import docx
        from docx.oxml.ns import qn
    except ImportError:
        sys.exit("!! python-docx not installed:  pip install python-docx")

    if not os.path.exists(a.docx):
        sys.exit("no such file: " + a.docx)
    d = docx.Document(a.docx)

    out = os.path.abspath(a.out)
    raw = os.path.join(out, "raw")
    txt = os.path.join(raw, "text")
    img = os.path.join(out, "images")
    for p in (txt, img):
        os.makedirs(p, exist_ok=True)

    # ---- images from relationships ----
    images = []
    for i, rel in enumerate(d.part.rels.values()):
        if "image" not in rel.reltype:
            continue
        ext = os.path.splitext(rel.target_ref)[1] or ".png"
        fn = "img%04d%s" % (i, ext)
        with open(os.path.join(img, fn), "wb") as f:
            f.write(rel.target_part.blob)
        images.append({"file": fn, "bytes": len(rel.target_part.blob)})
    print("images:", len(images))

    # ---- walk the body ONCE so paragraphs and tables interleave (H8) ----
    def is_heading(p, lvl):
        # H9: match the outline level, not the localised style name
        pPr = p._p.find(qn("w:pPr"))
        if pPr is None:
            return None
        ol = pPr.find(qn("w:outlineLvl"))
        if ol is not None:
            try:
                v = int(ol.get(qn("w:val")))
                return v + 1 == lvl
            except (TypeError, ValueError):
                return None
        name = (p.style.name or "").lower()
        if name in ("heading %d" % lvl, "标题 %d" % lvl):
            return True
        # the level may live on the style rather than the paragraph (H9)
        try:
            st = p.style.element.find(qn("w:pPr"))
            ol = st.find(qn("w:outlineLvl")) if st is not None else None
            return ol is not None and int(ol.get(qn("w:val"))) + 1 == lvl
        except (AttributeError, TypeError, ValueError):
            return False

    chapters, cur = [], None

    def new_chapter(title):
        nonlocal cur
        cur = {"n": len(chapters) + 1, "title": title, "parts": []}
        chapters.append(cur)
        return cur

    def ensure(title):
        # H11: a Heading 1 must START a new chapter, not merge into the current
        return cur if cur is not None else new_chapter(title)

    for child in d.element.body.iterchildren():
        if child.tag == qn("w:p"):
            p = next((x for x in d.paragraphs if x._p is child), None)
            if p is None:
                continue
            line = p.text.strip()          # not `txt` - that is the output dir (H10)
            if is_heading(p, 1):
                new_chapter(line or "untitled")
            elif line:
                ensure(cur["title"] if cur else "untitled")["parts"].append(line)
        elif child.tag == qn("w:tbl"):
            t = next((x for x in d.tables if x._tbl is child), None)
            if t is None:
                continue
            rows = [" | ".join(c.text.strip() for c in r.cells) for r in t.rows]
            ensure(cur["title"] if cur else "untitled")["parts"].append(
                "[table]\n" + "\n".join(rows))

    if not chapters:
        sys.exit("!! no text found")
    for c in chapters:
        body = "\n\n".join(c["parts"])
        name = "ch%02d.txt" % c["n"]
        open(os.path.join(txt, name), "w", encoding="utf-8").write(body)
        c["file"], c["chars"] = name, len(body)
    print("chapters:", len(chapters))
    for c in chapters:
        print("  %-10s %7d chars  %s" % (c["file"], c["chars"], c["title"][:50]))

    json.dump({"chapters": chapters, "images": images},
              open(os.path.join(out, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nwrote", os.path.join(out, "meta.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())