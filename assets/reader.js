/* Reader runtime: TOC · full-text search · night mode · reading position.
   Drop into app.js inside the existing IIFE.

   Required markup (see references/reader-features.md):
     <div class="topbar"> ... <div class="tb-tools">
        <button class="tb-btn" id="tocbtn" aria-expanded="false"><span class="ico">☰</span><span id="tocnow">目录</span></button>
        <button class="tb-btn" id="srchbtn" aria-expanded="false"><span class="ico">🔍</span>搜索</button>
        <button class="tb-btn" id="themebtn" aria-pressed="false"><span class="ico">🌙</span></button>
     </div></div>
     <div class="panel" id="tocmenu" hidden><div class="panel-h">目录</div><nav id="toclist"></nav></div>
     <div class="panel" id="srchpanel" hidden><div class="panel-h">全文搜索</div>
       <input id="srchin" type="search"><div id="srchmeta"></div><div id="srchlist"></div></div>
     <div id="resume" hidden><span>上次读到 <b id="resumeAt"></b> · <span id="resumePct"></span></span>
       <button id="resumeGo">继续阅读</button><button id="resumeNo">从头开始</button></div>

   Required on each section (emitted by assemble.py - never parse these from h1):
     <section class="chapter" id="ch05" data-toc="第一章" data-tt="合作的生命" style="--accent:#2E7D8C">
*/
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $ = function (s) { return document.querySelector(s); };

  /* ---------- storage: file:// can block localStorage ---------- */
  var LS = (function () {
    var mem = {}, ok = true;
    try { window.localStorage.setItem("__t", "1"); window.localStorage.removeItem("__t"); }
    catch (e) { ok = false; }
    return {
      get: function (k, d) {
        try { var v = ok ? window.localStorage.getItem("hbj:" + k) : mem[k];
              return v == null ? d : JSON.parse(v); } catch (e) { return d; }
      },
      set: function (k, v) {
        try { var s = JSON.stringify(v);
              if (ok) window.localStorage.setItem("hbj:" + k, s); else mem[k] = s; }
        catch (e) {}
      }
    };
  })();

  /* ---------- scrolling: glide for short hops, land instantly for long ones ---------- */
  function scrollToEl(el) {
    if (!el) return;
    var top = Math.max(0, el.getBoundingClientRect().top + window.pageYOffset - 12);
    if (!reduce && Math.abs(top - window.pageYOffset) < 2400) {
      window.scrollTo({ top: top, behavior: "smooth" });
      return;
    }
    var prev = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = "auto";
    window.scrollTo({ top: top, behavior: "instant" });
    document.documentElement.style.scrollBehavior = prev;
  }

  /* ---------- 1. table of contents ---------- */
  var CH = Array.prototype.map.call(
    document.querySelectorAll("section.chapter"),
    function (sec) {
      return {
        id: sec.id, el: sec,
        num: sec.getAttribute("data-toc") || "",
        rest: sec.getAttribute("data-tt") || sec.id
      };
    }).filter(function (c) { return c.num; });
  if (!CH.length) return;                       // nothing to drive; bail quietly

  var tocBtn = $("#tocbtn"), tocMenu = $("#tocmenu"),
      tocList = $("#toclist"), tocNow = $("#tocnow");
  var srchBtn = $("#srchbtn"), srchPanel = $("#srchpanel"),
      srchIn = $("#srchin"), srchMeta = $("#srchmeta"), srchList = $("#srchlist");

  function closePanels() {
    [tocMenu, srchPanel].forEach(function (p) { if (p) p.hidden = true; });
    if (tocBtn) tocBtn.setAttribute("aria-expanded", "false");
    if (srchBtn) srchBtn.setAttribute("aria-expanded", "false");
  }
  function currentChapter() {
    var y = window.pageYOffset + 120, found = CH[0];
    for (var i = 0; i < CH.length; i++) {
      if (CH[i].el.getBoundingClientRect().top + window.pageYOffset <= y) found = CH[i];
      else break;
    }
    if (window.pageYOffset + window.innerHeight >= document.documentElement.scrollHeight - 4)
      found = CH[CH.length - 1];
    return found;
  }

  CH.forEach(function (c) {
    var b = document.createElement("button");
    b.type = "button"; b.setAttribute("data-id", c.id);
    var n = document.createElement("span"); n.className = "n"; n.textContent = c.num;
    var t = document.createElement("span"); t.className = "t"; t.textContent = c.rest;
    var p = document.createElement("span"); p.className = "pct";
    b.appendChild(n); b.appendChild(t); b.appendChild(p);
    b.addEventListener("click", function () {
      closePanels(); scrollToEl(c.el); markNow(); savePos();
    });
    tocList.appendChild(b);
  });
  var tocBtns = Array.prototype.slice.call(tocList.children);

  function markNow() {
    var c = currentChapter();
    if (!c) return;
    if (tocNow) tocNow.textContent = c.num;        // never blank (pitfall E1)
    var ci = CH.indexOf(c);
    tocBtns.forEach(function (btn, i) {
      var on = btn.getAttribute("data-id") === c.id;
      btn.classList.toggle("now", on);
      var mk = btn.querySelector(".pct");
      if (mk) mk.textContent = on ? "●" : (i < ci ? "✓" : "");
    });
  }

  /* ---------- 2. night mode ---------- */
  var DARKCACHE = {};
  function hexToHsl(hex) {
    var r, g, b;
    if (hex.length === 4) { r = hex[1]+hex[1]; g = hex[2]+hex[2]; b = hex[3]+hex[3]; }
    else { r = hex.substr(1,2); g = hex.substr(3,2); b = hex.substr(5,2); }
    r = parseInt(r,16)/255; g = parseInt(g,16)/255; b = parseInt(b,16)/255;
    var mx = Math.max(r,g,b), mn = Math.min(r,g,b), l = (mx+mn)/2, s = 0, h = 0;
    if (mx !== mn) {
      var d = mx - mn;
      s = l > 0.5 ? d/(2-mx-mn) : d/(mx+mn);
      h = mx === r ? (g-b)/d + (g<b?6:0) : mx === g ? (b-r)/d+2 : (r-g)/d+4;
      h /= 6;
    }
    return [h, s, l];
  }
  function hslToHex(h, s, l) {
    function f(p,q,t){ if(t<0)t+=1; if(t>1)t-=1;
      if(t<1/6)return p+(q-p)*6*t; if(t<1/2)return q; if(t<2/3)return p+(q-p)*(2/3-t)*6; return p; }
    var r,g,b;
    if (s === 0) { r = g = b = l; }
    else { var q = l<0.5 ? l*(1+s) : l+s-l*s, p = 2*l-q;
           r=f(p,q,h+1/3); g=f(p,q,h); b=f(p,q,h-1/3); }
    function h2(v){ var s2 = Math.round(Math.max(0,Math.min(1,v))*255).toString(16);
                     return s2.length === 1 ? "0"+s2 : s2; }
    return "#" + h2(r) + h2(g) + h2(b);
  }
  function mapDark(hex) {          // S-curve keeps near-mid pairs separated (F2)
    var c = hexToHsl(hex), L = c[2];
    var nl = (1 - L) * 0.92 + 0.04;
    nl = Math.max(0.03, Math.min(0.97, 0.5 + (nl - 0.5) * 1.18));
    return hslToHex(c[0], c[1] * (L > 0.85 ? 0.5 : 0.88), nl);
  }
  function mapDarkStyle(s) {
    return s.replace(/(--(?:accent|c)\s*:\s*)(#[0-9a-fA-F]{3,6})/g, function (m, key, hex) {
      return key + (DARKCACHE[hex] || (DARKCACHE[hex] = mapDark(hex)));
    });
  }

  var paintNodes = null, accentNodes = null;
  function collectPaint() {
    paintNodes = []; accentNodes = [];
    // matches a parent <g fill> too, so inherited label colours get remapped (F3)
    Array.prototype.forEach.call(document.querySelectorAll("svg [fill], svg [stroke]"), function (el) {
      ["fill", "stroke"].forEach(function (a) {
        var v = el.getAttribute(a);
        if (!v || v === "none" || v.charAt(0) !== "#") return;
        paintNodes.push([el, a, v]);
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll('[style*="--accent"],[style*="--c"]'), function (el) {
      el._ostyle = el.getAttribute("style") || "";
      accentNodes.push(el);
    });
  }
  function applyThemeColors(dark) {
    if (!paintNodes) collectPaint();
    if (dark) {
      paintNodes.forEach(function (p) {
        p[0].setAttribute(p[1], DARKCACHE[p[2]] || (DARKCACHE[p[2]] = mapDark(p[2])));
      });
      accentNodes.forEach(function (el) {
        if (!el._dstyle) el._dstyle = mapDarkStyle(el._ostyle);
        el.setAttribute("style", el._dstyle);
      });
    } else {
      paintNodes.forEach(function (p) { p[0].setAttribute(p[1], p[2]); });
      accentNodes.forEach(function (el) { el.setAttribute("style", el._ostyle); });
    }
  }

  var themeBtn = $("#themebtn");
  function setTheme(dark, persist) {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    applyThemeColors(dark);
    if (themeBtn) {
      themeBtn.setAttribute("aria-pressed", dark ? "true" : "false");
      themeBtn.title = dark ? "切换回日间模式" : "切换夜间阅读模式";
      var i = themeBtn.querySelector(".ico");
      if (i) i.textContent = dark ? "☀" : "🌙";
    }
    if (persist) LS.set("theme", dark ? "dark" : "light");
  }
  if (themeBtn) themeBtn.addEventListener("click", function () {
    setTheme(document.documentElement.getAttribute("data-theme") !== "dark", true);
  });
  var savedTheme = LS.get("theme", null);
  if (!savedTheme && window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches) savedTheme = "dark";
  setTheme(savedTheme === "dark", false);

  /* ---------- 3. full-text search ---------- */
  var INDEX = null;
  function buildIndex() {
    if (INDEX) return;
    INDEX = [];
    var SEL = "p, li, td, th, h1, h2, h3, figcaption, cite, .chart-cap, text";
    CH.forEach(function (c) {
      Array.prototype.forEach.call(c.el.querySelectorAll(SEL), function (el) {
        var own = false;                      // own text only: avoids parent/child double count
        for (var i = 0; i < el.childNodes.length; i++) {
          var nd = el.childNodes[i];
          if (nd.nodeType === 3 && nd.nodeValue.replace(/\s+/g, "")) { own = true; break; }
        }
        if (!own) return;
        var t = (el.textContent || "").replace(/\s+/g, " ").trim();
        if (t.length < 2) return;
        INDEX.push({ el: el, t: t, lc: t.toLowerCase(), ch: c });
      });
    });
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m];
    });
  }
  function clearMarks() {
    Array.prototype.forEach.call(document.querySelectorAll("mark.sh"), function (m) {
      var p = m.parentNode;
      while (m.firstChild) p.insertBefore(m.firstChild, m);
      p.removeChild(m); p.normalize();
    });
    Array.prototype.forEach.call(document.querySelectorAll(".hit-box"), function (e) {
      e.classList.remove("hit-box");
    });
  }
  function markIn(el, q) {
    if (el.ownerSVGElement) { el.classList.add("hit-box"); return false; }   // E4
    // one flat string across all text nodes: the query may be split by <b>/<br> (E3)
    var nodes = [], text = "";
    var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null), n;
    while ((n = w.nextNode())) { nodes.push({ node: n, start: text.length }); text += n.nodeValue; }
    var i = text.toLowerCase().indexOf(q);
    if (i < 0) return false;
    function locate(pos) {
      for (var k = 0; k < nodes.length; k++) {
        var end = nodes[k].start + nodes[k].node.nodeValue.length;
        if (pos < end || (pos === end && k === nodes.length - 1))
          return { node: nodes[k].node, off: pos - nodes[k].start };
      }
      var last = nodes[nodes.length - 1];
      return { node: last.node, off: last.node.nodeValue.length };
    }
    var a = locate(i), b2 = locate(i + q.length);
    var r = document.createRange();
    try { r.setStart(a.node, a.off); r.setEnd(b2.node, b2.off); }
    catch (e) { return false; }
    var m = document.createElement("mark"); m.className = "sh";
    try { r.surroundContents(m); return true; } catch (e) { return false; }
  }
  function revealAncestors(el) {          // a collapsed <details> swallows the jump
    var p = el.parentElement;
    while (p && p !== document.body) { if (p.tagName === "DETAILS") p.open = true; p = p.parentElement; }
  }

  var results = [], cur = -1, searchTimer = null;
  function gotoRes(i) {
    if (!results.length) return;
    cur = (i === undefined ? cur + 1 : i);
    if (cur < 0) cur = results.length - 1;
    if (cur >= results.length) cur = 0;
    var r = results[cur];
    Array.prototype.forEach.call(srchList.querySelectorAll(".sres"), function (b, k) {
      b.classList.toggle("on", k === cur);
    });
    var active = srchList.children[cur];
    if (active && active.scrollIntoView) active.scrollIntoView({ block: "nearest" });
    clearMarks();
    revealAncestors(r.el);
    markIn(r.el, r.q);
    r.el.classList.remove("sh-flash"); void r.el.offsetWidth; r.el.classList.add("sh-flash");
    setTimeout(function () { r.el.classList.remove("sh-flash"); }, 1600);
    scrollToEl(r.el);
    markNow();
  }
  function doSearch() {
    var q = (srchIn.value || "").trim().toLowerCase();
    clearMarks();
    srchList.innerHTML = "";
    results = []; cur = -1;
    if (!q) { srchMeta.textContent = "支持中文与英文，回车跳到下一处"; return; }
    buildIndex();
    var hits = 0;
    for (var i = 0; i < INDEX.length; i++) {
      var at = INDEX[i].lc.indexOf(q);
      if (at < 0) continue;
      hits++;
      if (results.length >= 80) continue;
      results.push({ el: INDEX[i].el, ch: INDEX[i].ch, q: q });
      var b = document.createElement("button");
      b.type = "button"; b.className = "sres";
      var ch = document.createElement("span"); ch.className = "ch";
      ch.textContent = INDEX[i].ch.num + " · " + INDEX[i].ch.rest;
      var tx = document.createElement("span"); tx.className = "tx";
      var a = Math.max(0, at - 34), z = Math.min(INDEX[i].t.length, at + q.length + 46);
      tx.innerHTML = (a > 0 ? "…" : "") + esc(INDEX[i].t.slice(a, at)) +
                     "<mark>" + esc(INDEX[i].t.substr(at, q.length)) + "</mark>" +
                     esc(INDEX[i].t.slice(at + q.length, z)) + (z < INDEX[i].t.length ? "…" : "");
      b.appendChild(ch); b.appendChild(tx);
      b.addEventListener("click", function (e) { gotoRes(results.indexOf(e.currentTarget._r)); });
      b._r = results[results.length - 1];
      srchList.appendChild(b);
    }
    if (!hits) {
      var e2 = document.createElement("div");
      e2.className = "sres-empty";
      e2.textContent = "没有找到「" + srchIn.value.trim() + "」。正文、卡片、注释与图表文字都在检索范围内。";
      srchList.appendChild(e2);
      srchMeta.textContent = "0 处";
      return;
    }
    srchMeta.textContent = hits + " 处命中" + (hits > 80 ? "（显示前 80 条）" : "") + " · 回车跳到下一处";
    gotoRes(0);
  }
  if (srchIn) {
    srchIn.addEventListener("input", function () {
      clearTimeout(searchTimer); searchTimer = setTimeout(doSearch, 180);
    });
    srchIn.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); gotoRes(cur + (e.shiftKey ? -1 : 1)); }
      else if (e.key === "Escape") { closePanels(); }
    });
  }

  /* ---------- panels ---------- */
  if (tocBtn) tocBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    var open = tocMenu.hidden;
    closePanels(); tocMenu.hidden = !open;
    tocBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) markNow();
  });
  if (srchBtn) srchBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    var open = srchPanel.hidden;
    closePanels(); srchPanel.hidden = !open;
    srchBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) { buildIndex(); srchIn.focus(); srchIn.select(); }
  });
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t.closest && (t.closest("#tocmenu") || t.closest("#srchpanel") ||
                      t.closest("#tocbtn") || t.closest("#srchbtn"))) return;
    if ((!tocMenu || !tocMenu.hidden) || (srchPanel && !srchPanel.hidden)) closePanels();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closePanels();
    if ((e.ctrlKey || e.metaKey) && e.key === "f" && srchBtn) { e.preventDefault(); srchBtn.click(); }
  });

  /* ---------- 4. reading position ---------- */
  var resumeBox = $("#resume"), savedPos = LS.get("pos", null);
  function readPct() {
    var h = document.documentElement.scrollHeight - window.innerHeight;
    return h > 0 ? Math.round((window.pageYOffset / h) * 100) : 0;
  }
  function savePos() {
    var c = currentChapter();
    var y = window.pageYOffset;
    var top = c ? c.el.getBoundingClientRect().top + y : 0;
    LS.set("pos", { id: c ? c.id : "", off: Math.round(y - top), y: Math.round(y),
                    pct: readPct(), at: Date.now() });
  }
  function jumpToPos(p) {
    var sec = p.id ? document.getElementById(p.id) : null;
    var topY = sec ? sec.getBoundingClientRect().top + window.pageYOffset : 0;
    var prev = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = "auto";      // must be instant (E6)
    window.scrollTo({ top: Math.max(0, topY + (p.off || 0)), behavior: "instant" });
    document.documentElement.style.scrollBehavior = prev;
  }
  var posTimer = null;
  function onScroll() {
    if (posTimer) return;
    posTimer = setTimeout(function () { posTimer = null; markNow(); savePos(); }, 250);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("beforeunload", savePos);
  document.addEventListener("visibilitychange", function () { if (document.hidden) savePos(); });

  // guard on max(y, off): a layout change can zero y while off is still deep (E7)
  var depth = savedPos ? Math.max(savedPos.y || 0, savedPos.off || 0) : 0;
  if (resumeBox && savedPos && depth > 400) {
    var at = $("#resumeAt"), pc = $("#resumePct"), found = null;
    for (var i = 0; i < CH.length; i++) if (CH[i].id === savedPos.id) found = CH[i];
    if (at) at.textContent = found ? found.num + " · " + found.rest : "上次的位置";
    if (pc) pc.textContent = (savedPos.pct || 0) + "%";
    resumeBox.hidden = false;
    jumpToPos(savedPos);
    markNow();
    var go = $("#resumeGo"), no = $("#resumeNo");
    if (go) go.addEventListener("click", function () {
      jumpToPos(savedPos); resumeBox.hidden = true; savePos();
    });
    if (no) no.addEventListener("click", function () {   // otherwise the reader is trapped
      LS.set("pos", null); resumeBox.hidden = true;
      scrollToEl(CH[0].el); savePos();
    });
  } else if (resumeBox) {
    resumeBox.hidden = true;
  }

  markNow();
})();