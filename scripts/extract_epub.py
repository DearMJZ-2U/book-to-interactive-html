#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract an EPUB into raw/, plain chapter text and an image manifest.

    python extract_epub.py <book.epub> [-o build_dir]

Writes:
    raw/                 unzipped epub
    raw/text/chNN.txt    one plain-text file per spine document
    images.json          filename -> {path, bytes, media_type}
    meta.json            title/creator/publisher + the spine in reading order

Print the spine before doing anything else - the file order on disk is not
the reading order, and chapter numbering must follow the spine.

Traps handled here (see references/pitfalls.md):
  A1  re.match returns None on non-matching filenames
  A2  assert the manifest is non-empty instead of silently writing {}
"""
import argparse, html, json, os, re, shutil, sys, zipfile
from xml.etree import ElementTree as ET

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
TAG = re.compile(r"<[^>]+>")


def clean(x: str) -> str:
    x = re.sub(r"(?is)<(script|style).*?</\1>", " ", x)
    x = re.sub(r"(?i)<br\s*/?>", "\n", x)
    x = re.sub(r"(?i)</(p|div|h1|h2|h3|h4|li|tr|figcaption)>", "\n", x)
    x = re.sub(r"(?i)<(h1|h2|h3|h4)[^>]*>", "\n\n", x)
    x = re.sub(r"(?i)<li[^>]*>", "\n  - ", x)
    x = TAG.sub("", x)
    x = html.unescape(x).replace("\u00a0", " ").replace("\ufeff", "")
    x = re.sub(r"[ \t\u3000]+", " ", x)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", x).strip()


def find(root: str, name: str):
    """content.opf is not always at the archive root (pitfall A1)."""
    for dirpath, _dirs, files in os.walk(root):
        if name in files:
            return os.path.join(dirpath, name)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("epub")
    ap.add_argument("-o", "--out", default="epub-build")
    a = ap.parse_args()

    if not os.path.exists(a.epub):
        sys.exit("no such file: " + a.epub)
    out = os.path.abspath(a.out)
    raw, txt = os.path.join(out, "raw"), os.path.join(out, "raw", "text")
    if os.path.isdir(raw):
        shutil.rmtree(raw)
    os.makedirs(txt, exist_ok=True)

    with zipfile.ZipFile(a.epub) as z:
        z.extractall(raw)

    opf_path = find(raw, "content.opf")
    if not opf_path:
        sys.exit("!! content.opf not found - is this really an EPUB?")
    opf_dir = os.path.dirname(opf_path)
    opf = ET.parse(opf_path).getroot()
    ns = {"opf": OPF_NS, "dc": DC_NS}

    meta = {}
    for t in ("title", "creator", "publisher", "language", "date", "identifier"):
        e = opf.find("dc:" + t, ns)
        if e is not None and e.text:
            meta[t] = e.text.strip()

    manifest = {it.get("id"): it.get("href") for it in opf.find("opf:manifest", ns)}
    spine = []
    sp = opf.find("opf:spine", ns)
    if sp is not None:
        for item in sp:
            href = manifest.get(item.get("idref"))
            if href:
                spine.append(href)

    # ---- plain text, keyed by spine position ----
    chapters = []
    for i, href in enumerate(spine, 1):
        path = os.path.normpath(os.path.join(opf_dir, href))
        if not os.path.exists(path):
            print("  !! spine target missing:", href); continue
        body = clean(open(path, encoding="utf-8", errors="replace").read())
        name = "ch%02d.txt" % i
        open(os.path.join(txt, name), "w", encoding="utf-8").write(body)
        m = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", open(path, encoding="utf-8",
                                                           errors="replace").read(), re.S)
        title = re.sub(r"<[^>]+>", " ", m.group(1)).strip() if m else ""
        chapters.append({"n": i, "src": href, "file": name,
                         "chars": len(body), "title": title})
    # A1: never let an empty result pass quietly (A2).
    if not chapters:
        sys.exit("!! produced no chapters - check the spine parsing")
    print("chapters extracted:", len(chapters))

    # ---- images ----
    images = {}
    for dirpath, _d, files in os.walk(raw):
        for f in files:
            if re.search(r"\.(jpe?g|png|gif|svg|webp)$", f, re.I):
                full = os.path.join(dirpath, f)
                images[f] = {"path": full,
                             "bytes": os.path.getsize(full),
                             "media": "image/" + f.rsplit(".", 1)[-1].lower()}
    if not images:
        print("  !! no images found")
    print("images found     :", len(images))

    # ---- toc.ncx is advisory; the spine is authoritative ----
    nav = []
    ncx_path = find(raw, "toc.ncx")
    if ncx_path:
        try:
            for np_ in ET.parse(ncx_path).getroot().iter("{%s}navPoint" % NCX_NS):
                lab = np_.find("{%s}navLabel/{%s}text" % (NCX_NS, NCX_NS))
                con = np_.find("{%s}content" % NCX_NS)
                if lab is not None:
                    nav.append({"label": (lab.text or "").strip(),
                                "src": con.get("src") if con is not None else ""})
        except ET.ParseError as e:
            print("  !! toc.ncx unparsable:", e)
    print("toc entries      :", len(nav))

    json.dump({"meta": meta, "chapters": chapters, "nav": nav, "images": images},
              open(os.path.join(out, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("\n=== spine (reading order) ===")
    for c in chapters:
        print("  %2d  %-28s %7d chars  %s" % (c["n"], c["file"], c["chars"], c["title"][:40]))
    print("\nwrote", os.path.join(out, "meta.json"))


if __name__ == "__main__":
    main()