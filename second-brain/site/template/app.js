const $ = s => document.querySelector(s);
const byId = Object.fromEntries(BRAIN.pages.map(p => [p.slug, p]));
const FOLDERS = ["sources", "projects", "decisions", "concepts", "root"];
const FLABEL = { sources: "Sources", projects: "Projects", decisions: "Decisions", concepts: "Concepts", root: "Wiki root" };
const FVAR = { sources: "--cat-1", projects: "--cat-4", decisions: "--cat-3", concepts: "--cat-2", root: "--cat-other" };
let cfg = JSON.parse(JSON.stringify(BRAIN.config));
let db = null, sample = null, downloads = null, current = null, query = "";

const edges = []; const seen = new Set();
for (const p of BRAIN.pages) for (const l of p.links) {
  if (!byId[l]) continue;
  const k = [p.slug, l].sort().join("|");
  if (!seen.has(k)) { seen.add(k); edges.push({ a: p.slug, b: l }); }
}
const deg = {};
for (const e of edges) { deg[e.a] = (deg[e.a] || 0) + 1; deg[e.b] = (deg[e.b] || 0) + 1; }
$("#nPages").textContent = BRAIN.pages.length;
$("#nLinks").textContent = edges.length;
$("#nSrc").textContent = BRAIN.pointers.length;
$("#nCommit").textContent = BRAIN.commit;

/* ---------- navigation ---------- */
const VIEWS = { home: "vHome", explore: "vExplore", employees: "vEmployees", page: "vPage", ask: "vAsk", capture: "vCapture", settings: "vSettings" };
function go(name) {
  if (!$("#" + VIEWS[name])) name = "home";
  for (const id of Object.values(VIEWS)) { const el = $("#" + id); if (el) el.classList.toggle("on", id === VIEWS[name]); }
  document.querySelectorAll(".nl").forEach(b => {
    const active = b.dataset.view === name || (name === "page" && b.dataset.view === "explore");
    b.setAttribute("aria-current", active ? "page" : "false");
  });
  scrollTo({ top: 0, behavior: "instant" });
  if (name === "explore") { resize(); alpha = Math.max(alpha, .55); }
}
document.addEventListener("click", e => {
  const v = e.target.closest("[data-view]");
  if (v) { go(v.dataset.view); return; }
  const g = e.target.closest("[data-go]");
  if (g) { e.preventDefault(); openPage(g.dataset.go); }
});
$("#backBtn").onclick = () => go("explore");
$("#themeBtn").onclick = () => {
  const cur = document.documentElement.getAttribute("data-theme");
  const dark = cur ? cur === "dark" : matchMedia("(prefers-color-scheme:dark)").matches;
  document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
  readColors(); paintFigure(); draw();
};

/* ---------- home diagram ---------- */
function paintFigure() {
  const cs = getComputedStyle(document.documentElement);
  const c = k => cs.getPropertyValue(k).trim();
  const docs = [["PLAN.md", 70], ["ROADMAP.md", 20], ["CLAUDE.md", 20], ["README.md", 3]];
  let g = "";
  docs.forEach((d, i) => {
    const y = 26 + i * 40;
    g += '<rect x="8" y="' + y + '" width="132" height="30" rx="6" fill="' + c("--surface") + '" stroke="' + c("--line") + '"/>' +
      '<text x="22" y="' + (y + 19) + '" font-family="Noto Sans Mono,monospace" font-size="11.5" fill="' + c("--text") + '">' + d[0] + "</text>" +
      '<text x="126" y="' + (y + 19) + '" text-anchor="end" font-family="Noto Sans Mono,monospace" font-size="9.5" fill="' + c("--text-faint") + '">' + d[1] + "K</text>";
  });
  $("#figDocs").innerHTML = g;

  let f = "";
  docs.forEach((d, i) => {
    const y = 41 + i * 40;
    f += '<path d="M146 ' + y + " C 210 " + y + ", 250 100, 300 100" + '" fill="none" stroke="' + c("--accent") +
      '" stroke-width="1.3" opacity=".5" class="dash" style="animation-delay:' + (i * .32) + 's"/>';
  });
  $("#figFlow").innerHTML = f;

  $("#figHub").innerHTML =
    '<circle cx="330" cy="100" r="30" fill="' + c("--accent-soft") + '" stroke="' + c("--accent") + '" stroke-width="1.4"/>' +
    '<text x="330" y="96" text-anchor="middle" font-family="Fraunces,serif" font-size="13" fill="' + c("--accent") + '">ingest</text>' +
    '<text x="330" y="110" text-anchor="middle" font-family="Noto Sans Mono,monospace" font-size="8" fill="' + c("--text-faint") + '">compile</text>';

  const pts = [[470,44],[540,26],[610,52],[680,32],[745,60],[500,96],[575,86],[650,100],[720,92],[790,72],
               [478,148],[548,158],[618,140],[688,156],[756,136],[812,110],[530,124],[608,170],[700,124],[770,168]];
  const cols = [c("--cat-1"), c("--cat-4"), c("--cat-3"), c("--cat-2")];
  let w = "";
  for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
    const dx = pts[i][0] - pts[j][0], dy = pts[i][1] - pts[j][1];
    if (Math.hypot(dx, dy) < 88) w += '<line x1="' + pts[i][0] + '" y1="' + pts[i][1] + '" x2="' + pts[j][0] +
      '" y2="' + pts[j][1] + '" stroke="' + c("--line") + '" stroke-width="1"/>';
  }
  pts.forEach((p, i) => { w += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="' + (3.4 + (i % 4)) + '" fill="' + cols[i % 4] + '"/>'; });
  w += '<path d="M366 100 L 452 100" fill="none" stroke="' + c("--accent") + '" stroke-width="1.3" opacity=".5" class="dash"/>';
  w += '<text x="640" y="196" text-anchor="middle" font-family="Noto Serif,serif" font-size="10.5" letter-spacing="1.6" fill="' + c("--text-faint") + '">40 CROSS-LINKED PAGES</text>';
  w += '<text x="74" y="196" text-anchor="middle" font-family="Noto Serif,serif" font-size="10.5" letter-spacing="1.6" fill="' + c("--text-faint") + '">YOUR SOURCES</text>';
  $("#figWiki").innerHTML = w;
}

/* ---------- markdown ---------- */
const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
function inline(s) {
  return s
    .replace(/`([^`]+)`/g, (m, c) => "<code>" + c + "</code>")
    .replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (m, slug, alias) => {
      const t = (alias || slug).replace(/-/g, " ");
      return byId[slug] ? '<a class="wl" data-go="' + slug + '">' + t + "</a>" : '<span style="color:var(--text-faint)">' + t + "</span>";
    })
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");
}
function md(src) {
  const lines = src.split("\n"); const out = []; let i = 0; let para = [];
  const flush = () => { if (para.length) { out.push("<p>" + inline(para.join(" ")) + "</p>"); para = []; } };
  while (i < lines.length) {
    const L = lines[i];
    if (L.startsWith("```")) {
      flush(); const code = []; i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i++; out.push("<pre><code>" + code.join("\n") + "</code></pre>"); continue;
    }
    if (/^\|/.test(L) && /^\|[\s:|-]+\|$/.test(lines[i + 1] || "")) {
      flush();
      const cells = r => r.split("|").slice(1, -1).map(c => c.trim());
      let h = "<div class='tw'><table><thead><tr>" + cells(L).map(c => "<th>" + inline(c) + "</th>").join("") + "</tr></thead><tbody>";
      i += 2;
      while (i < lines.length && /^\|/.test(lines[i])) { h += "<tr>" + cells(lines[i]).map(c => "<td>" + inline(c) + "</td>").join("") + "</tr>"; i++; }
      out.push(h + "</tbody></table></div>"); continue;
    }
    let m;
    if ((m = L.match(/^(#{2,4})\s+(.*)$/))) { flush(); const n = m[1].length; out.push("<h" + n + ">" + inline(m[2]) + "</h" + n + ">"); i++; continue; }
    if (/^[-*]\s+/.test(L) || /^\d+\.\s+/.test(L)) {
      flush();
      const ord = /^\d+\.\s+/.test(L), tag = ord ? "ol" : "ul";
      const re = ord ? /^\d+\.\s+/ : /^[-*]\s+/;
      let h = "<" + tag + ">";
      while (i < lines.length && re.test(lines[i])) {
        let t = lines[i].replace(re, ""); i++;
        while (i < lines.length && /^\s{2,}\S/.test(lines[i])) { t += " " + lines[i].trim(); i++; }
        h += "<li>" + inline(t) + "</li>";
      }
      out.push(h + "</" + tag + ">"); continue;
    }
    if (/^(&gt;|>)\s?/.test(L)) {
      flush(); const q = [];
      while (i < lines.length && /^(&gt;|>)\s?/.test(lines[i])) { q.push(lines[i].replace(/^(&gt;|>)\s?/, "")); i++; }
      out.push("<blockquote>" + inline(q.join(" ")) + "</blockquote>"); continue;
    }
    if (/^---+$/.test(L)) { flush(); i++; continue; }
    if (!L.trim()) { flush(); i++; continue; }
    para.push(L.trim()); i++;
  }
  flush();
  return out.join("");
}

/* ---------- reader ---------- */
function openPage(slug) {
  const p = byId[slug]; if (!p) return;
  current = slug;
  const nb = new Set();
  for (const e of edges) { if (e.a === slug) nb.add(e.b); if (e.b === slug) nb.add(e.a); }
  const rel = [...nb].map(s => '<button data-go="' + s + '">' + byId[s].title + "</button>").join("");
  $("#doc").innerHTML =
    '<div class="kick"><span class="badge">' + p.type + '</span><span class="meta">' + p.path +
    '</span><span class="meta">' + p.words + " words · " + (deg[slug] || 0) + " links</span></div>" +
    "<h1>" + esc(p.title) + "</h1>" + md(esc(p.body)) +
    (rel ? '<div class="rel"><h4>Links out to</h4><div>' + rel + "</div></div>" : "");
  go("page"); pulse(slug); draw();
}

/* ---------- explore ---------- */
function matches(p) {
  if (!query) return true;
  const q = query.toLowerCase();
  return p.title.toLowerCase().includes(q) || p.slug.includes(q) || p.body.toLowerCase().includes(q);
}
function renderRows() {
  const el = $("#rows"); el.innerHTML = "";
  let n = 0;
  for (const f of FOLDERS) {
    const items = BRAIN.pages.filter(p => p.folder === f && matches(p));
    if (!items.length) continue;
    n += items.length;
    const h = document.createElement("div"); h.className = "grp"; h.textContent = FLABEL[f];
    el.appendChild(h);
    for (const p of items) {
      const b = document.createElement("button");
      b.className = "row2";
      const first = p.body.split("\n").find(l => l.trim() && !l.startsWith("#") && !l.startsWith("|")) || "";
      b.innerHTML = "<b></b><em></em><span></span>";
      b.children[0].textContent = p.title;
      b.children[1].textContent = first.replace(/[*`\[\]]/g, "").slice(0, 90);
      b.children[2].textContent = (deg[p.slug] || 0) + " links";
      b.onclick = () => openPage(p.slug);
      el.appendChild(b);
    }
  }
  if (!n) el.innerHTML = '<div class="grp">No page matches that</div>';
}
/* ---------- employees ---------- */
const SHOWN = 3;

function runRow(r, doing) {
  const row = document.createElement("div");
  row.className = "run" + (doing ? " doing" : "");
  row.innerHTML = "<em></em><span></span>";
  row.children[0].textContent = r.date;
  row.children[1].textContent = r.what;
  row.children[1].title = r.what + (r.ref ? "  (" + r.ref + ")" : "");
  return row;
}

function renderStaff() {
  const el = $("#staff");
  el.innerHTML = "";
  for (const m of BRAIN.employees) {
    const card = document.createElement("div");
    card.className = "emp";
    card.innerHTML =
      '<header><div class="av"></div><div><h3></h3><span class="kind"></span></div></header>' +
      '<p class="role"></p><div class="chips"></div>' +
      '<div class="work"><div class="st"><i></i><b></b></div><div class="runs"></div></div>';
    card.querySelector(".av").textContent = m.icon;
    card.querySelector("h3").textContent = m.invoke;
    card.querySelector(".kind").textContent = m.kind;

    const role = card.querySelector(".role");
    role.textContent = m.role || "No definition in this repository — known only by the commits it signs.";
    if (!m.role) role.classList.add("none");

    // Only the facts the definition actually carries. A command has no model
    // of its own because it runs in whatever session invokes it, so an empty
    // chip row is correct rather than something to fill.
    const chips = card.querySelector(".chips");
    const add = (text, cls) => {
      const c = document.createElement("span");
      c.className = "chip" + (cls ? " " + cls : "");
      c.textContent = text;
      chips.appendChild(c);
    };
    if (m.model) add(m.model);
    if (m.effort) add("effort " + m.effort);
    if (m.can.length) add(m.can.length + " tools");
    if (m.cannot.length) add("cannot write", "no");

    const live = m.doing.length > 0;
    const st = card.querySelector(".st");
    st.classList.add(live ? "live" : m.done.length ? "idle" : "never");
    st.querySelector("b").textContent = live
      ? "Working — " + m.doing.length + " unmerged"
      : m.done.length ? "Idle" : "Never run";

    const runs = card.querySelector(".runs");
    for (const r of m.doing) runs.appendChild(runRow(r, true));
    const rest = m.done.slice(0, Math.max(0, SHOWN - m.doing.length));
    for (const r of rest) runs.appendChild(runRow(r, false));

    if (m.done.length > rest.length) {
      const more = document.createElement("button");
      more.className = "more";
      more.textContent = "Show all " + m.done.length;
      more.onclick = () => {
        more.remove();
        for (const r of m.done.slice(rest.length)) runs.appendChild(runRow(r, false));
        card.classList.add("on");
      };
      card.querySelector(".work").appendChild(more);
    }

    if (!m.done.length && !live) {
      const why = document.createElement("div");
      why.className = "run";
      why.innerHTML = "<span></span>";
      why.children[0].textContent = !m.defined ? "No signed commits."
        : BRAIN.logHeld ? "Its record is in the activity log, which this build holds back."
        : "Defined, but no run recorded against it yet.";
      runs.appendChild(why);
    }

    // A commit and a ledger row each prove the employee ran. A log entry that
    // names it is only evidence it was involved — the entry recording that the
    // brain commands were built names all four of them. Counting those with
    // the rest would read as four runs that never happened, so the tally keeps
    // the three sources apart.
    const foot = document.createElement("footer");
    const tally = [["run", "runs"], ["commit", "commits"], ["log mention", "log mentions"]]
      .map(([one, many], i) => {
        const n = m.done.filter(r => r.via === ["run", "commit", "log"][i]).length;
        return n ? n + " " + (n === 1 ? one : many) : "";
      })
      .filter(Boolean);
    foot.textContent = [
      tally.join(" · ") || "nothing recorded",
      m.last ? "last " + m.last : "",
      m.defined,
    ].filter(Boolean).join("  ·  ");
    card.querySelector(".work").appendChild(foot);
    el.appendChild(card);
  }

  const never = BRAIN.employees.filter(m => !m.done.length && !m.doing.length && m.defined);
  $("#staffNote").textContent =
    "Roles come from the definition files under .claude/. Work comes from three places: commits " +
    "on main, which attribute a bot by its author and Claude by its Co-Authored-By trailer; the " +
    "run ledger at .claude/runs.tsv, written by whatever invoked an agent that cannot write for " +
    "itself; and " +
    (BRAIN.logHeld
      ? "the wiki's activity log, which this build holds back — so anything whose only trace is a " +
        "log entry reads as never run here."
      : "dated entries in the wiki's activity log, which name an employee without proving it ran.") +
    (never.length && !BRAIN.logHeld
      ? " " + never.map(m => m.invoke).join(" and ") + " show nothing because no run has been " +
        "recorded against them yet."
      : "");
}

$("#q").oninput = e => { query = e.target.value.trim(); renderRows(); draw(); };
$("#segMap").onclick = () => setMode(true);
$("#segList").onclick = () => setMode(false);
function setMode(map) {
  $("#segMap").setAttribute("aria-pressed", String(map));
  $("#segList").setAttribute("aria-pressed", String(!map));
  $("#gwrap").classList.toggle("hid", !map);
  $("#rows").classList.toggle("hid", map);
  if (map) { resize(); alpha = Math.max(alpha, .5); } else renderRows();
}

/* ---------- graph ---------- */
const cv = $("#cv"), ctx = cv.getContext("2d");
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const nodes = BRAIN.pages.map((p, i) => {
  const a = (i / BRAIN.pages.length) * Math.PI * 2;
  return { id: p.slug, p, x: Math.cos(a) * 10, y: Math.sin(a) * 10, vx: 0, vy: 0, r: 4 + Math.min(9, (deg[p.slug] || 0) * .72) };
});
const nOf = Object.fromEntries(nodes.map(n => [n.id, n]));
let W = 0, H = 0, alpha = 1, hover = null, drag = null, pulses = [], COL = {};
function readColors() {
  const cs = getComputedStyle(document.documentElement);
  COL = { line: cs.getPropertyValue("--line").trim(), text: cs.getPropertyValue("--text").trim(),
          dim: cs.getPropertyValue("--text-muted").trim(), accent: cs.getPropertyValue("--accent").trim() };
  for (const f of FOLDERS) COL[f] = cs.getPropertyValue(FVAR[f]).trim();
}
function resize() {
  const r = $("#gwrap").getBoundingClientRect();
  if (!r.width || !r.height) return;
  W = r.width; H = r.height;
  const dpr = Math.min(2, devicePixelRatio || 1);
  cv.width = W * dpr; cv.height = H * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
function tick() {
  const cx = W / 2, cy = H / 2;
  for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
    const a = nodes[i], b = nodes[j];
    const dx = b.x - a.x, dy = b.y - a.y; let d2 = dx * dx + dy * dy || .01;
    if (d2 > 96000) continue;
    const d = Math.sqrt(d2), f = 2800 / d2;
    a.vx -= dx / d * f; a.vy -= dy / d * f; b.vx += dx / d * f; b.vy += dy / d * f;
  }
  for (const e of edges) {
    const a = nOf[e.a], b = nOf[e.b];
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || .01;
    const f = (d - 122) * .011;
    a.vx += dx / d * f; a.vy += dy / d * f; b.vx -= dx / d * f; b.vy -= dy / d * f;
  }
  for (const n of nodes) {
    n.vx += (cx - n.x) * .0022; n.vy += (cy - n.y) * .0022;
    if (drag === n) { n.vx = n.vy = 0; continue; }
    n.vx *= .86; n.vy *= .86;
    n.x += n.vx * alpha; n.y += n.vy * alpha;
    n.x = Math.max(n.r + 18, Math.min(W - n.r - 18, n.x));
    n.y = Math.max(n.r + 18, Math.min(H - n.r - 30, n.y));
  }
  alpha = Math.max(.15, alpha * .992);
}
function nbrs(id) { const s = new Set([id]); for (const e of edges) { if (e.a === id) s.add(e.b); if (e.b === id) s.add(e.a); } return s; }
function draw() {
  if (!W) return;
  ctx.clearRect(0, 0, W, H);
  const focus = hover || current, near = focus ? nbrs(focus) : null;
  const found = query ? new Set(BRAIN.pages.filter(matches).map(p => p.slug)) : null;
  ctx.lineWidth = 1;
  for (const e of edges) {
    const a = nOf[e.a], b = nOf[e.b], hot = near && near.has(e.a) && near.has(e.b);
    ctx.strokeStyle = hot ? COL.accent : COL.line;
    ctx.globalAlpha = hot ? .8 : (near ? .14 : .4);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
  ctx.globalAlpha = 1;
  for (const p of pulses) {
    const a = nOf[p.a], b = nOf[p.b];
    ctx.globalAlpha = 1 - p.t; ctx.fillStyle = COL.accent;
    ctx.beginPath(); ctx.arc(a.x + (b.x - a.x) * p.t, a.y + (b.y - a.y) * p.t, 2.6, 0, 7); ctx.fill();
  }
  ctx.globalAlpha = 1;
  for (const n of nodes) {
    const on = (!near || near.has(n.id)) && (!found || found.has(n.id));
    ctx.globalAlpha = on ? 1 : .15;
    ctx.fillStyle = COL[n.p.folder] || COL.dim;
    ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 7); ctx.fill();
    if (n.id === current) {
      ctx.strokeStyle = COL.accent; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 5, 0, 7); ctx.stroke(); ctx.lineWidth = 1;
    }
    if ((deg[n.id] || 0) >= 6 || (near && near.has(n.id))) {
      ctx.globalAlpha = on ? .92 : .1;
      ctx.fillStyle = near && near.has(n.id) ? COL.text : COL.dim;
      ctx.font = '500 10px "Noto Serif",Georgia,serif'; ctx.textAlign = "center";
      const t = n.p.title.length > 24 ? n.p.title.slice(0, 22) + "…" : n.p.title;
      ctx.fillText(t, n.x, n.y + n.r + 12);
    }
  }
  ctx.globalAlpha = 1;
}
function frame() { if (!REDUCED) { tick(); pulses = pulses.filter(p => (p.t += .022) < 1); } draw(); requestAnimationFrame(frame); }
function pulse(id) {
  if (REDUCED) return;
  pulses = edges.filter(e => e.a === id || e.b === id).map(e => ({ a: id, b: e.a === id ? e.b : e.a, t: 0 }));
}
function at(ev) {
  const r = cv.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
  let best = null, bd = 1e9;
  for (const n of nodes) { const d = Math.hypot(n.x - x, n.y - y); if (d < n.r + 10 && d < bd) { bd = d; best = n; } }
  return { x, y, n: best };
}
cv.addEventListener("mousemove", ev => {
  const { x, y, n } = at(ev);
  if (drag) { drag.x = x; drag.y = y; alpha = Math.max(alpha, .45); return; }
  hover = n ? n.id : null;
  const tip = $("#tip");
  if (n) {
    tip.style.opacity = "1";
    tip.style.left = Math.min(W - 250, x + 15) + "px"; tip.style.top = (y + 15) + "px";
    tip.innerHTML = "<strong>" + esc(n.p.title) + "</strong><br><span style='color:var(--text-faint);font-family:var(--font-mono);font-size:10.5px'>" +
      n.p.type + " · " + (deg[n.id] || 0) + " links</span>";
  } else tip.style.opacity = "0";
});
cv.addEventListener("mousedown", ev => { const { n } = at(ev); if (n) drag = n; });
addEventListener("mouseup", () => { drag = null; });
cv.addEventListener("mouseleave", () => { hover = null; $("#tip").style.opacity = "0"; });
cv.addEventListener("click", ev => { const { n } = at(ev); if (n) openPage(n.id); });
addEventListener("resize", () => { resize(); alpha = Math.max(alpha, .4); });
$("#legend").innerHTML = FOLDERS.map(f => '<span class="lg"><s style="background:var(' + FVAR[f] + ')"></s>' + FLABEL[f] + "</span>").join("");

/* ---------- toast ---------- */
let tt; const toast = m => { const t = $("#toast"); t.textContent = m; t.classList.add("on"); clearTimeout(tt); tt = setTimeout(() => t.classList.remove("on"), 2800); };

/* ---------- adapters ---------- */
// The three panels below run in both builds. All that differs is where a
// setting, a note or a question goes: the Claude viewer hands us db, sample
// and downloads at runtime, and the hosted site has localStorage, a real file
// download, and an endpoint at the edge. Everything past this block calls
// these five functions and never learns which build it is in.
//
// Each one either returns the line to show the reader or throws with a message
// worth reading. Nothing here swallows a failure and reports success.

/*IF:caps*/
async function saveConfig(next) {
  if (!db) throw new Error("Settings can't be stored here — download the file instead");
  await db.doc("config/current").set({ config: next, savedAt: new Date().toISOString() });
  return "Settings saved";
}
async function saveFile(name, data) {
  if (!downloads) throw new Error("Downloads aren't available in this view");
  await downloads.save({ filename: name, data });
  return "Saved " + name;
}
async function captureNote(text) {
  if (!db) throw new Error("Inbox unavailable — paste the note into /brain:log instead");
  await db.collection("inbox").add({ text, created: new Date().toISOString(), status: "pending" });
  return "Captured — /brain:log will file it";
}
function watchNotes(render) {
  if (!db) return;
  db.collection("inbox").orderBy("created", "desc").limit(8)
    .onSnapshot(s => render(s.docs.map(d => d.data())), () => {});
}
function refreshNotes() {}   // the snapshot listener above already redraws
async function askModel(payload, onText) {
  if (!sample) throw new Error("Asking Claude isn't available in this view.");
  const res = await sample(payload.input, {
    modelTier: "default", onText: ({ text }) => onText(text),
  });
  return res.text;
}
const NOTE_HINT = "Notes wait in the inbox until /brain:log files them.";
/*ENDIF*/

/*IF:static*/
// Everything the hosted site keeps goes to D1 behind the worker, not to the
// browser: a note captured on a phone has to be there when /brain:log drains
// the inbox from a laptop, and a setting has to outlive cleared site data.
// Cloudflare Access is the authentication - the endpoints refuse without it -
// so there is no token or session for this code to hold.
async function api(path, init) {
  const res = await fetch(path, {
    ...init,
    headers: init?.body ? { "content-type": "application/json" } : undefined,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "The site could not reach its own storage.");
  }
  return res.json();
}
async function saveConfig(next) {
  const { saved } = await api("/api/config", { method: "PUT", body: JSON.stringify({ config: next }) });
  return `Saved ${saved} settings \u2014 download the file to put them in front of the commands`;
}
async function saveFile(name, data) {
  const url = URL.createObjectURL(new Blob([data], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url; link.download = name;
  link.click();
  URL.revokeObjectURL(url);
  return "Downloaded " + name;
}
async function captureNote(text) {
  await api("/api/notes", { method: "POST", body: JSON.stringify({ text }) });
  return "Captured \u2014 /brain:log will file it";
}
async function watchNotes(render) {
  try {
    const { notes } = await api("/api/notes");
    render(notes.map(n => ({ text: n.text, status: n.filed_at ? "filed" : "pending" })));
  } catch (e) {
    $("#noteHint").textContent = e.message;
  }
}
function refreshNotes() { watchNotes(renderNotes); }
async function askModel(payload, onText) {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question: payload.question, context: payload.context, cite: payload.cite }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "That couldn't be answered here.");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let out = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    out += decoder.decode(value, { stream: true });
    onText(out);
  }
  if (!out.trim()) throw new Error("The model returned nothing. Try asking again.");
  return out;
}
const NOTE_HINT = "Notes wait in the inbox until /brain:log files them.";
/*ENDIF*/

/* ---------- settings ---------- */
const CHECKS = { brokenLinks: "Broken links", orphans: "Orphan pages", indexDrift: "Index drift",
  frontmatter: "Missing frontmatter", uncitedClaims: "Uncited claims", sourceDrift: "Source drift",
  staleness: "Stale pages", contradictions: "Contradictions" };
$("#checks").innerHTML = Object.entries(CHECKS).map(([k, l]) =>
  '<div class="set"><label>' + l + '</label><button class="sw" role="switch" data-chk="' + k + '"></button></div>').join("");
$("#moreChecks").onclick = e => {
  const hid = $("#checks").classList.toggle("hid");
  e.target.textContent = hid ? "Show the eight checks" : "Hide the checks";
};
const sw = (el, v) => el.setAttribute("aria-checked", String(!!v));
function bind(el, get, set) { sw(el, get()); el.onclick = () => { set(!get()); sw(el, get()); }; }
function paint() {
  $("#cBatch").value = cfg.ingest.batchSize;
  $("#cStale").value = cfg.lint.staleAfterDays;
  $("#cCite").value = cfg.style.citationStrictness;
  $("#cWords").value = cfg.style.maxPageWords;
  $("#cMaxP").value = cfg.query.maxPagesRead;
  sw($("#cReing"), cfg.ingest.reingestChangedDocs);
  sw($("#cContra"), cfg.style.recordContradictions);
  sw($("#cPropose"), cfg.query.proposeUpdates);
  sw($("#cLinked"), cfg.log.updateLinkedPages);
  document.querySelectorAll("[data-chk]").forEach(b => sw(b, cfg.lint.checks[b.dataset.chk]));
}
bind($("#cReing"), () => cfg.ingest.reingestChangedDocs, v => cfg.ingest.reingestChangedDocs = v);
bind($("#cContra"), () => cfg.style.recordContradictions, v => cfg.style.recordContradictions = v);
bind($("#cPropose"), () => cfg.query.proposeUpdates, v => cfg.query.proposeUpdates = v);
bind($("#cLinked"), () => cfg.log.updateLinkedPages, v => cfg.log.updateLinkedPages = v);
document.querySelectorAll("[data-chk]").forEach(b => bind(b, () => cfg.lint.checks[b.dataset.chk], v => cfg.lint.checks[b.dataset.chk] = v));
$("#cBatch").oninput = e => cfg.ingest.batchSize = +e.target.value;
$("#cStale").oninput = e => cfg.lint.staleAfterDays = +e.target.value;
$("#cCite").onchange = e => cfg.style.citationStrictness = e.target.value;
$("#cWords").oninput = e => cfg.style.maxPageWords = +e.target.value;
$("#cMaxP").oninput = e => cfg.query.maxPagesRead = +e.target.value;
paint();
$("#saveCfg").onclick = async () => {
  try { toast(await saveConfig(cfg)); }
  catch (e) { toast(e.code === "invalid_argument"
    ? "You have read access here \u2014 download the file instead"
    : e.message || "Could not save settings"); }
};
$("#dlCfg").onclick = async () => {
  try { toast(await saveFile("brain.config.json", JSON.stringify(cfg, null, 2) + "\n")); }
  catch (e) { if (e.code !== "declined") toast(e.message || "Download failed"); }
};

/* ---------- capture ---------- */
function renderNotes(docs) {
  $("#noteWrap").innerHTML = docs.length
    ? "<h4>Waiting in the inbox</h4>" + docs.map(d =>
      '<div class="rec"><span>' + esc(d.text.slice(0, 120)) + (d.text.length > 120 ? "…" : "") + "</span><em>" + d.status + "</em></div>").join("")
    : "";
}
$("#noteBtn").onclick = async () => {
  const text = $("#noteIn").value.trim(); if (!text) return;
  try {
    const said = await captureNote(text);
    $("#noteIn").value = ""; toast(said); refreshNotes();
  } catch (e) {
    toast(e.code === "quota_exceeded" ? "Inbox is full \u2014 drain it with /brain:log"
      : e.code === "invalid_argument" ? "You have read access here \u2014 only editors can capture notes"
      : e.message || "Could not capture that note");
  }
};

/* ---------- ask ---------- */
const SUGS = ["What is blocking the catalog from hitting its targets?",
  "Where do the plan and the running system disagree?",
  "Why is the evaluation harness built before the stylist agent?",
  "What has to be true before the enterprise studio starts?"];
$("#sugs").innerHTML = SUGS.map(s => '<button class="sug">' + s + "</button>").join("");
document.querySelectorAll(".sug").forEach(b => b.onclick = () => { $("#askIn").value = b.textContent; ask(); });
$("#askBtn").onclick = ask;
function context(question) {
  const words = question.toLowerCase().match(/[a-z]{4,}/g) || [];
  return BRAIN.pages.map(p => {
    const hay = (p.title + " " + p.slug + " " + p.body).toLowerCase();
    let s = 0;
    for (const w of words) { if (hay.includes(w)) s += 1; if (p.title.toLowerCase().includes(w)) s += 3; }
    return { p, s };
  }).sort((a, b) => b.s - a.s).slice(0, Math.min(cfg.query.maxPagesRead || 8, 10))
    .filter(x => x.s > 0)
    .map(x => "<<page slug=" + x.p.slug + ">>\n# " + x.p.title + "\n" + x.p.body.slice(0, 2200) + "\n<</page>>").join("\n\n");
}
async function ask() {
  const question = $("#askIn").value.trim(); if (!question) return;
  const out = $("#askOut");
  const ctxText = context(question);
  if (!ctxText) { out.innerHTML = '<div class="note">Nothing in the wiki matches that. Try different words, or run <code>/brain:ingest</code> if the source is new.</div>'; return; }
  $("#askBtn").disabled = true;
  out.innerHTML = '<div class="pending"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span>Reading the wiki…</span></div>';
  const cite = cfg.query.citeEveryClaim
    ? "Cite every claim with its page slug in double brackets, like [[catalog-supply]]. If a claim has no page, say the wiki does not cover it."
    : "Cite the main pages you used with the page slug in double brackets.";
  const input = "You are answering from a compiled engineering wiki about Genesis, an AI fashion platform. Use ONLY the pages below. " +
    cite + " If pages disagree, present both and name them; never average them into one confident answer. " +
    "Answer in plain prose, at most 200 words, no preamble.\n\n" + ctxText + "\n\nQuestion: " + question;
  try {
    const answer = await askModel({ question, context: ctxText, cite, input }, text => {
      out.innerHTML = '<div class="ans"></div>'; out.firstChild.innerHTML = inline(esc(text));
    });
    out.innerHTML = '<div class="ans"></div>'; out.firstChild.innerHTML = inline(esc(answer));
  } catch (e) {
    out.innerHTML = '<div class="note">' + (e.code === "rate_limited" ? "Rate limited — wait a moment and ask again."
      : e.code === "not_granted" ? "You declined that request."
      : esc(e.message || "That couldn't be answered here. Try /brain:query in Claude Code.")) + "</div>";
  } finally { $("#askBtn").disabled = false; }
}

/*ENDIF*/
/* ---------- boot ---------- */
readColors(); paintFigure(); renderRows(); renderStaff(); resize();
if (REDUCED) { for (let i = 0; i < 420; i++) tick(); alpha = .15; draw(); }
else requestAnimationFrame(frame);
matchMedia("(prefers-color-scheme:dark)").addEventListener("change", () => { readColors(); paintFigure(); draw(); });
setTimeout(() => { resize(); draw(); }, 90);
if (document.fonts) document.fonts.ready.then(() => { resize(); paintFigure(); draw(); });

$("#noteHint").textContent = NOTE_HINT;

/*IF:caps*/
(async () => {
  if (!window.claude || !claude.use) { $("#noteHint").textContent = "Inbox unavailable in this view"; return; }
  db = await claude.use("db").catch(() => null);
  sample = await claude.use("sample").catch(() => null);
  downloads = await claude.use("downloads").catch(() => null);
  if (!downloads) $("#dlCfg").disabled = true;
  if (!sample) $("#askBtn").disabled = true;
  if (!db) { $("#saveCfg").disabled = true; $("#noteHint").textContent = "Inbox unavailable in this view"; return; }
  try {
    const snap = await db.doc("config/current").get();
    if (snap.exists && snap.data().config) { cfg = Object.assign(cfg, snap.data().config); paint(); }
  } catch (e) {}
  watchNotes(renderNotes);
})();
/*ENDIF*/

/*IF:static*/
// Stored settings outrank the ones compiled into the page, so a change made
// here survives a rebuild until the file is downloaded and put in front of the
// commands. Both of these reach the network, so neither blocks first paint.
(async () => {
  try {
    const { config } = await api("/api/config");
    if (config && Object.keys(config).length) { cfg = Object.assign(cfg, config); paint(); }
  } catch (e) { $("#noteHint").textContent = e.message; }
  await watchNotes(renderNotes);
})();
/*ENDIF*/
