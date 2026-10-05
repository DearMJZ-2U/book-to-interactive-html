# book-to-interactive-html

把任意电子书转成**一个**自包含、可离线打开的交互式 HTML 书——逐章讲解、手绘动效图表、点击放大的插图、完整注释，外加目录、全文搜索、夜间阅读模式和阅读位置记忆。

Turn any book — **EPUB / PDF / 扫描版 PDF / DOCX / HTML** — into **one**
self-contained interactive HTML book, verified by a headless-Chrome geometry
audit instead of by eyeballing screenshots.

---

## 它解决什么问题

一本 23 万字的书，转成 HTML 后最常见的三个失败：

1. **知识点丢了** —— 注释、图注、表格在转换过程中被悄悄吃掉，没人发现。
2. **图表看不清** —— SVG 缩到手机上字只有 6px，文字压在色块上，两两重叠。
3. **没法验证** —— "我觉得还行"不是检查。改完只能靠肉眼看，改一处坏三处。

这个 skill 的核心立场：**成品是生成物，不是手写文件**；**版式必须用真实几何数据量，不能靠看**。

## 支持的输入格式

| 输入 | 提取器 | 章节边界 |
|---|---|---|
| `.epub` | `scripts/extract_epub.py` | 自动 —— spine 就是章节表 |
| `.pdf`（数字版） | `scripts/extract_pdf.py` | 有 outline 就用，没有就自己推 |
| `.pdf`（扫描版） | `scripts/extract_pdf.py --ocr` | **必须手工定页码区间**（没有机器可读的目录） |
| `.docx` | `scripts/extract_docx.py` | 自动 —— Heading 1 大纲 |

所有格式在第 2 步之后完全汇流到同一套 `pack/<CID>.md` + `frag/<CID>.html`，后续流程不关心书是从哪来的。

## 成品包含什么

- **逐章讲解** —— 不是摘要，是把原书的论证结构讲清楚
- **手绘 SVG 图表** —— 逐个手写、带入场动画、按章节配色
- **原书插图原位保留**，点击放大人眼看不清的细节
- **完整尾注**，双链回正文
- **目录 / 全文搜索 / 夜间模式 / 阅读位置记忆**

一次真实产出：**13.8 MB 单文件**，15 个 section、83 张图表、46 个图、47 张内嵌图、289 条尾注、18 张表格；`check_all.py` 在 1440 / 1024 / 768 / 430 四种宽度、日间与夜间两种模式下全部退出 0，所有几何计数器为 0。

## 安装

把整个目录放进你的 skills 目录：

```bash
# Claude Code
git clone https://github.com/DearMJZ-2U/book-to-interactive-html.git \
    ~/.claude/skills/book-to-interactive-html

# 或直接拷贝
cp -r book-to-interactive-html ~/.agents/skills/
```

依赖：`python`（`pymupdf`、`rapidocr-onnxruntime`、`python-docx`、`pyyaml`，按需）、`node`（可选，用于语法检查）。**提取脚本本身不装任何东西也能跑**，缺库会明确报错。

## 用法

装好之后直接跟 agent 说：

```
把《人类文明的自然大历史》.epub 做成一个详解图 HTML
帮我把这本 PDF 转成网页书，保留图片和注释
```

## 目录结构

```
SKILL.md                     入口：构建约定 + 8 阶段流程 + 硬规则
references/
  source-formats.md          四种格式怎么提取，各自的坑
  pitfalls.md          ★    49 条真实失败记录：症状 → 原因 → 修法
  auditing.md                几何审计方法论
  charts.md                  手写 SVG 图表规则
  reader-features.md         目录/搜索/夜间/位置 的做法与各自的坑
scripts/
  extract_epub.py            EPUB → raw/ text/ meta.json
  extract_pdf.py             PDF（数字版 + OCR 扫描版）
  extract_docx.py            DOCX
  chrome_probe.py            通用 headless Chrome 审计器
  validate_skill.py          自检 frontmatter（改完 SKILL.md 跑一下）
assets/
  reader.css / reader.js     四个阅读控件的可用实现
```

## 关于 `references/pitfalls.md`

这份文件是这个 skill 里最有价值的部分。49 条坑全部来自真实构建，每条都是「**症状 → 原因 → 修法**」。

举几个能让你少走几天的：

- **★ 对比度审计漏算透明度**：面板 `fill="#6E7B2E" opacity=".14"` 铺在米色纸上，真实底色是很淡的 wash。审计读的是原始填充色，报出「对比度 1.0」，于是把标签改成白色——**白字压在浅色 wash 上，白天模式反而看不见了**。是工具在撒谎。
- **★ 正则里的空格破坏了回溯**：字符类写成 `[a-z0-9 _-]`，其中的空格让整段回溯失效，脚本**一次都没匹配上**，却正常退出、正常打印「0 个问题」。
- **★ 字符集删多了一位**：`key = f[:-6]` 应该是 `[:-5]`，整张颜色映射表变成一个**合法的空 JSON `{}`**，后面的「没有需要转换的颜色」也一并成立。
- **★ skill 的 description 里一个「冒号+空格」**：YAML 解析直接失败，skill 静默不加载，**任何地方都不报错**，唯一症状就是「技能从列表里消失了」。
- **测试自己的错**：播种 `localStorage.setItem(k, "dark")`，代码存的是 `JSON.stringify("dark")`，`JSON.parse` 抛异常被 catch 吞掉，表现为「主题没记住」——其实是我测试写错了。

贯穿全篇的一条教训：

> **先造测量工具。** 上面前三个 bug，工具都给出了自信的 0，而按它的建议改会让页面更糟。每个假零都是靠**交叉验证**才抓到的——独立计数、打开真实源码、切换配色重测、**或者干脆拿真实文件跑一遍**。
>
> 一个永远只会通过的检查，不是检查。

## 核心理念

> **绝不手改成品 HTML。** 只改 `frag/*.html`、`style.css`、`app.js`，然后重新 build。

成品是 14 MB 的生成物。直接编辑它，意味着下次 build 会静默丢弃你的改动，而且你无法 diff 出到底变了什么。

## License

MIT — 见 [LICENSE](LICENSE)。