#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run a JS auditor inside a built HTML file with headless Chrome.

    python chrome_probe.py <built.html> <probe.js> [--width 1440] [--json out.json]

The probe script runs before </body>. It measures whatever it likes and then
shrinks the document to a single <pre id="__probe"> carrying a JSON report,
so --dump-dom returns kilobytes instead of the whole book.

Every trap in references/auditing.md is handled here:
  D1   output goes through Python subprocess, never shell redirection
  D10  stdout is reconfigured for UTF-8 so Chinese and emoji survive
  D11  theme is pinned and saved state cleared on EVERY run
  D13  transitions/animations disabled so nothing is sampled mid-flight
  D12  a missing report is a hard failure, not a silent pass
"""
import argparse, json, os, re, subprocess, sys

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
]
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def find_chrome():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("!! Chrome not found; set CHROME env var")


DETERMINISM = (
    "<style>*,*::before,*::after{transition:none!important;animation:none!important}"
    "html{scroll-behavior:auto!important}</style>\n"
    "<script>try{var k=Object.keys(localStorage);for(var i=0;i<k.length;i++){"
    "if(k[i].indexOf('hbj:')===0)localStorage.removeItem(k[i]);}}catch(e){}</script>\n"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("probe")
    ap.add_argument("--width", default="1440")
    ap.add_argument("--height", default="1200")
    ap.add_argument("--budget", default="30000")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--workdir", default=None,
                    help="scratch dir for the temp html and chrome profile")
    a = ap.parse_args()

    work = a.workdir or os.path.join(os.path.dirname(os.path.abspath(a.html)), "_probe")
    os.makedirs(work, exist_ok=True)
    tmp = os.path.join(work, "probe.html")
    dump = os.path.join(work, "probe.dump")
    profile = os.path.join(work, "cprof")

    html = open(a.html, encoding="utf-8").read()
    probe = open(a.probe, encoding="utf-8").read()
    html = html.replace("</head>", DETERMINISM + "</head>", 1)
    html = html.replace("</body>", "<script>\n" + probe + "\n</script>\n</body>")
    open(tmp, "w", encoding="utf-8").write(html)

    subprocess.run(
        [find_chrome(), "--headless", "--disable-gpu", "--no-sandbox",
         "--user-data-dir=" + profile,
         "--window-size=%s,%s" % (a.width, a.height),
         "--virtual-time-budget=" + a.budget,
         "--dump-dom", "file:///" + tmp.replace("\\", "/")],
        stdout=open(dump, "w", encoding="utf-8"),
        stderr=subprocess.DEVNULL, timeout=1800)

    dom = open(dump, encoding="utf-8").read()
    m = re.search(r"<pre id=[\"']__probe[\"']>([\s\S]*?)</pre>", dom)
    if not m:
        # D12: a probe that produced nothing must fail loudly, never pass.
        raise SystemExit("!! probe produced no report (dom %d bytes) - "
                         "the probe threw before writing #__probe" % len(dom))
    payload = (m.group(1).replace("&amp;", "&").replace("&lt;", "<")
               .replace("&gt;", ">").replace("&quot;", '"'))
    data = json.loads(payload)
    if isinstance(data, dict) and "fatal" in data:
        raise SystemExit("!! probe failed: " + str(data["fatal"]))

    if a.json_out:
        json.dump(data, open(a.json_out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print(json.dumps(data, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())