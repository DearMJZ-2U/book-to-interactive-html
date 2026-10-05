# Auditing a book in headless Chrome

You usually cannot see the rendered page. So **measure it**. Every claim
("nothing overlaps", "the text is readable", "no knowledge points lost")
should come from geometry or counts, never from impression.

## The pattern

Inject a JS auditor before `</body>`. It measures real geometry with
`getBoundingClientRect()` / `getComputedStyle()`, then **replaces the document
with a tiny payload** so `--dump-dom` returns something small:

```js
document.documentElement.innerHTML = "<body><pre id='__audit'></pre></body>";
document.getElementById("__audit").textContent = JSON.stringify(report);
```

`scripts/chrome_probe.py` wraps this.

## Running it

```python
subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-sandbox",
                "--user-data-dir=" + os.path.join(BLD, "cprof"),
                "--window-size=1440,1200",
                "--virtual-time-budget=30000",
                "--dump-dom", "file:///" + tmp.replace("\\", "/")],
               stdout=open(out, "w", encoding="utf-8"),
               stderr=subprocess.DEVNULL, timeout=600)
```

Always go through Python — see pitfalls D1, D10, D11, D13.

## Determinism (do this every single run)

```python
pre = ('<style>*,*::before,*::after{transition:none!important;animation:none!important}'
       'html{scroll-behavior:auto!important}</style>\n'
       '<script>try{localStorage.removeItem("hbj:pos");'
       'localStorage.setItem("hbj:theme",JSON.stringify("%s"));}catch(e){}</script>\n' % theme)
html = html.replace("</head>", pre + "</head>", 1)
```

`--user-data-dir` persists `localStorage` between runs. Without this, a dark
run poisons the next light run and both report confident, wrong numbers.

## What to measure

### Charts
| Check | How |
|---|---|
| rendered scale | `(rect.width - padding - border) / viewBox.width` — **content box** (D7) |
| smallest label | min over text of `fontSize × scale`; threshold ~11 px |
| text × text overlap | pairwise bbox intersection of `<text>` boxes |
| escaping the viewBox | `getBoundingClientRect()` in **screen space** (D3) |
| unreadable | WCAG ratio vs. the resolved, opacity-composited backdrop (D4, D6) |
| hidden | covering shape swallows ≥90 % of the text bbox, `fillOpacity ≥ 0.5` (D5) |

Contrast:
```js
function lum(rgb){var m=String(rgb).match(/[\d.]+/g).map(Number);
  var f=function(v){v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);};
  return 0.2126*f(m[0])+0.7152*f(m[1])+0.0722*f(m[2]);}
function contrast(a,b){var x=lum(a),y=lum(b);if(x===null||y===null)return null;
  return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05);}
```

Backdrop resolution — paint order plus alpha, both mandatory:
```js
var order = new Map();
document.querySelectorAll("*").forEach(function(e,i){order.set(e,i);});
// ... pick the shape with the greatest order < text's order ...
var alpha = fillOpacity * opacity;
var backdrop = alpha >= 0.99 ? rawFill : over(rawFill, cardBg, alpha);
```

### Blocks
Measure L/R/T/B separately and flag only **negative** values (D9). Compute
`ownText` from direct child text nodes and skip layout-only containers (D8).

### Page
`document.documentElement.scrollWidth - clientWidth` must be 0. A single
`white-space: nowrap` in a flex topbar is enough to add hundreds of px of
horizontal scroll.

## Interaction probes

Test behaviour, not just layout. A probe that clicks, types and asserts:

```js
tocBtn.click();
ck("TOC panel opens", q("#tocmenu").hidden === false);
var target = document.getElementById("ch11");
var want = target.getBoundingClientRect().top + window.pageYOffset;
list.children[3].click();
ck("TOC entry scrolls to its chapter", Math.abs(window.pageYOffset - want) < 40);
```

Assertions must match the **real contract**. An early version asserted
"an inline `<mark>` appears"; the first hit was inside a chart, where HTML
markup is impossible and an outline is the correct fallback. The test was
wrong. Assert `inlineMarks + outlines > 0`, and add a *second* check with a
prose-only term that genuinely must wrap.

Chain async steps with nested `setTimeout`, and make sure the closing
brackets line up — an unbalanced chain fails silently as "no report".

## Pre-seed state for load-time behaviour

To test "restore last position on open", inject **before** the page's own
script so it runs first:

```python
html = html.replace("<script>\n", PRE + "<script>\n", 1)
```

and remember the value must be `JSON.stringify`'d exactly as the app writes
it (pitfall E5).

## The gate

`check_all.py` runs, in order:

1. structure — tag balance, duplicate SVG def ids, one `</html>`
2. fragment metrics
3. note marker ↔ note item linkage, **including duplicates**
4. caption traceability to the source text
5. chart legibility at 1440 / 1024 / 768 / 430
6. card & block layout at the same widths
7. **the same chart audit under the night palette**
8. reader controls end to end

Exit 0 only if every check passes. Rebuild first — audits read the built
file. Steps 5–8 are 16 Chrome launches; run it in the background.

## Honest reporting

If a check cannot run, say so. A gate that reports "all passed" because a
sub-step silently produced no report is worse than no gate — print the report
byte count and fail loudly when it is missing:

```python
if not m:
    print("!! auditor produced no report; dom size", len(dom)); sys.exit(1)
```