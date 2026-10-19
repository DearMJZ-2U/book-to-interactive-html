# Splitting a book into fragments, and writing them without losing facts

Two independent problems that get confused:

1. **How many fragments, and where does each one start?** — a *source* question.
2. **How do you get that much prose written without dropping facts or running out
   of context?** — an *authoring* question.

Getting (1) wrong means a chapter is split mid-argument. Getting (2) wrong means
the fragments are complete but hollow.

---

## 1. Where to cut

### Prefer the book's own boundaries

A book's chapter list is the only defensible cut, because the author already
decided where an argument ends. Use the source's own structure whenever it has
one: EPUB spine, DOCX Heading 1, PDF outline, or the 目录 page of a scan.

### What to merge and what to drop

| Source section | Decision | Why |
|---|---|---|
| 推荐序 / 序 / foreword by someone else | **drop** by default | not the author's argument; ask if unsure |
| 前言 / preface **by the author** | **keep as its own section** | it usually states the thesis and the frame |
| 目录 | drop | the reader's TOC replaces it |
| 版权页 / CIP | drop | |
| 参考文献 / bibliography | **drop unless asked** | user's standing preference in this pipeline |
| 注释 / endnotes | **keep every one** | they carry real content, not just citations |
| 后记 / afterword | **keep, but read it** | often contains the most honest or most speculative material |

《缠斗》's front matter was 10 pages of three separate 推荐序 (by 黄奇帆, 乐玉成,
王一鸣) plus a 20-page 前言 by the authors. The three prefaces were dropped; the
前言 became its own section because it hands the reader the book's two analysis
threads ("权" and "钱") that every later chapter uses.

### The guide section is not optional

Every book in this pipeline gets a **导读 / guide** fragment before the first
real chapter, and it is written by *you*, marked `class="ed"`:

- one-sentence thesis of the whole book
- the chapter chain, as a diagram — what each chapter is *for* in the argument
- key-concept glossary (6–8 entries)
- 2–3 reading routes with time estimates
- three cautions about how to read this particular author

This is the single highest-value section per word. It is also the one a
delegated subagent should never write, because it requires having read the whole
book.

---

## 2. Writing at scale without losing facts

### The failure modes, in the order they bite

**B1 — the subagent invents.** You hand it a pack and it "helpfully" adds
context it knows from elsewhere. Its output reads *better* than a faithful one,
which is why it survives review.

**B2 — the subagent drops.** It writes 4 000 characters instead of 9 000 and the
validator catches it, but the missing part is usually the mechanism, not the
summary.

**B3 — it silently fails.** ~25% of dispatches in this pipeline have produced no
file at all. You must verify the file exists and grows.

**B4 — it duplicates a note marker**, so `notechk` passes on count but the
linkage is wrong.

### What actually works

**Give the pack path, not the facts.** Never paraphrase the book's numbers into
the prompt. A paraphrased number is an invitation to elaborate on it (B3 in
pitfalls). The instruction is: *"the pack is the only legal source; if a fact is
not in it, omit it — do not fill the gap."*

**Give an exact output path and an exact checklist.** "Write
`build/frag/ch07.html`; it must have exactly 5 `<svg class="chart">`, ≥8 cards,
5 quiz questions, `sup.nb` count == `li` count, ≥9 000 readable characters."
Vague briefs produce vague files.

**Tell it the validator command and to iterate until its own row says OK.**
`python validate.py` prints one line per fragment; the subagent only has to make
its own line green. This converts an open-ended quality question into a closed
loop it can actually run.

**Never ask it to judge an image.** There is no image input. Give it the caption
text from `figs.json` and let `check_captions.py` verify the result.

**Serialize.** A dozen parallel writers will exhaust whatever concurrency the
provider allows and the tail of the batch dies. Batches of ≤6, verify each batch
before dispatching the next.

### When delegation is not working, generate instead

In the 《缠斗》 run **every** delegated writer failed (provider quota), and the
book still shipped. What made that possible was splitting the fragment into
*repetitive* and *authored* parts:

- Repetitive: `<figure>` blocks, notes list, quiz wrapper, pager, stat blocks →
  one shortcut line each, expanded by `scripts/expand.py`.
- Authored: prose + hand-drawn SVG → written directly.

A 600-line fragment is then ~450 lines of shortcuts and ~150 lines of real
writing, which is small enough to author directly at high quality. **Do this even
when delegation works** — it removes the transcription errors in caption text,
which is the one thing the checker compares verbatim.

### Verify, don't trust

After every writer (human or agent), independently:

```bash
python validate.py        # per-fragment quotas
python notechk.py         # marker <-> note one-to-one, no duplicates
python check_captions.py  # every caption traces to figs.json
```

And check the *file* changed:

```bash
python metrics.py ch07    # lines / charts / figures / notes / chars
```

A fragment that exists but did not grow is the failure mode that costs the most
time, because it looks like success in a directory listing.

---

## 3. Quota table that worked

For a 300-page Chinese non-fiction chapter (tier A):

| Metric | Target | Why this number |
|---|---|---|
| readable characters | ≥9 000 | below this the "详解" is a summary, not an explanation |
| `<svg class="chart">` | 5 | one per major mechanism; more becomes decoration |
| `.card` | ≥8 (≥3 `.card bad`) | misconceptions are the highest-value cards |
| `.case` | ≥3 | concrete instances, not more abstractions |
| `.cmp` / `.tbl` | ≥2 | structure the reader can scan |
| `.stats` | ≥2 | numbers deserve their own block |
| `.numline` | exactly 3 | chapter-opening headline figures |
| quiz questions | exactly 5 | concept / mechanism / data / counter-intuitive / boundary |
| `.tldr` | exactly 3 | |
| `.quote` | exactly 1 | one verbatim passage, not a wall of them |

Short sections (preface, afterword) take a lighter tier: ≥5 200 chars, 3 charts,
5 cards, 2 cases.

`validate.py` enforces these as *floors*, and the numbers came from what a good
chapter actually needed — not the other way round.
