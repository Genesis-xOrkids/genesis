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
  if (name === "employees") startGems();
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
  readColors(); paintFigure(); draw(); repaintGems();
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

// The mark on each card is a gem, and its cut says the kind. styles.css owns each
// kind's material and the stone's float; this section owns the solid, the light
// and the turn.
//
// Each cut is one outline: the stone's girdle seen from above. The solid is a
// stack of rings, each that outline scaled about its centre at a height, from the
// top of the stone to its base, and its facets are the bands between neighbouring
// rings. A ring with a half-step twist sits on the outline's edge midpoints, so
// the bands either side of it break into triangles - the star and bezel facets of
// a brilliant - while untwisted neighbours give long flat faces, like a shard's.
// Every solid is convex, so it is exactly the space inside all of its facets'
// planes, which is what lets each pixel be ray-traced through it cheaply.
const CUTS = {
  agent: Array.from({ length: 8 }, (_, i) => {
    const a = Math.PI * (i / 4 + 1 / 8);
    return [20 + 17.5 * Math.cos(a), 20 + 17.5 * Math.sin(a)];
  }),
  command: [[6, 18], [15, 8], [29, 9], [35, 20], [27, 31], [12, 30]],
  service: [[17, 4], [23, 4], [37, 29], [34, 35], [6, 35], [3, 29]],
};
// [scale, height, twist, x, z] from the top down, as fractions of the outline's
// radius; a scale of 0 is a point, set off the axis by x and z. Agents are round
// brilliants and services trillions, with crowns and pavilions near a real
// stone's. Commands are not cut at all: each is a shard of crystal, broken off
// to a long point at one end and a shorter one at the other.
const RINGS = {
  agent: [[.55, .3, 0], [.9, .2, 1], [1, 0, 0], [0, -.86, 0]],
  command: [[0, 1.35, 0, .08, 0], [.58, .38, 0], [.72, 0, 0], [.55, -.42, 0], [0, -1, 0, -.07, .03]],
  service: [[.5, .26, 0], [.82, .18, 1], [1, 0, 0], [0, -.62, 0]],
};
// How far each kind leans in the picture, in radians. A shard turns about its own
// length on a diagonal; the cut stones stand upright.
const TILT = { agent: 0, command: -.6, service: 0 };
const MAX_FACETS = 48;  // the shader's fixed loop bound
function solid(kind) {
  const outline = CUTS[kind], n = outline.length;
  const cx = outline.reduce((s, p) => s + p[0], 0) / n;
  const cz = outline.reduce((s, p) => s + p[1], 0) / n;
  const flat = outline.map(([x, z]) => [x - cx, z - cz]);
  const radius = Math.max(...flat.map(([x, z]) => Math.hypot(x, z)));
  const verts = [];
  const rings = RINGS[kind].map(([scale, height, twist, x = 0, z = 0]) => {
    if (!scale) return [verts.push([x, height, z]) - 1];
    return flat.map(([x, z], k) => {
      const [x1, z1] = flat[(k + 1) % n];
      const [qx, qz] = twist ? [(x + x1) / 2, (z + z1) / 2] : [x, z];
      return verts.push([qx / radius * scale, height, qz / radius * scale]) - 1;
    });
  });
  const faces = rings[0].length > 1 ? [rings[0]] : [];  // a table, unless the top is a point
  for (let j = 1; j < rings.length; j++) {
    const up = rings[j - 1], lo = rings[j];
    for (let k = 0; k < n; k++) {
      const next = (k + 1) % n, prev = (k + n - 1) % n;
      if (up.length === 1) faces.push([up[0], lo[next], lo[k]]);
      else if (lo.length === 1) faces.push([up[k], up[next], lo[0]]);
      else if (RINGS[kind][j][2]) faces.push([up[k], up[next], lo[k]], [up[k], lo[k], lo[prev]]);
      else if (RINGS[kind][j - 1][2]) faces.push([up[k], lo[k], lo[next]], [lo[k], up[prev], up[k]]);
      else faces.push([up[k], up[next], lo[next], lo[k]]);
    }
  }
  const centre = [0, 1, 2].map(axis => verts.reduce((s, v) => s + v[axis], 0) / verts.length);
  const heights = verts.map(v => v[1]);
  if (faces.length > MAX_FACETS) throw new Error(kind + " has more facets than the gem shader reads");
  const facets = faces.map(ids => {
    // Newell's normal, turned outward if the winding left it facing in.
    const normal = [0, 0, 0], at = [0, 0, 0];
    ids.forEach((id, k) => {
      const a = verts[id], b = verts[ids[(k + 1) % ids.length]];
      normal[0] += (a[1] - b[1]) * (a[2] + b[2]);
      normal[1] += (a[2] - b[2]) * (a[0] + b[0]);
      normal[2] += (a[0] - b[0]) * (a[1] + b[1]);
      for (let axis = 0; axis < 3; axis++) at[axis] += a[axis] / ids.length;
    });
    const outward = normal.reduce((s, v, axis) => s + v * (at[axis] - centre[axis]), 0) < 0 ? -1 : 1;
    const length = Math.hypot(...normal) * outward;
    return { ids, normal: normal.map(v => v / length) };
  });
  // Each facet's plane as its outward normal and its distance from the centre.
  const planes = new Float32Array(4 * MAX_FACETS);
  facets.forEach(({ ids, normal }, k) => {
    const v = verts[ids[0]];
    planes.set([...normal, normal[0] * v[0] + normal[1] * v[1] + normal[2] * v[2]], 4 * k);
  });
  return { verts, mid: (Math.max(...heights) + Math.min(...heights)) / 2, faces: facets, planes };
}
const SOLIDS = Object.fromEntries(Object.keys(CUTS).map(kind => [kind, solid(kind)]));

// Colour. A stone's body colour is worked in OKLCH, then brought into sRGB by
// giving up chroma at constant lightness and hue; clipped channel by channel
// instead, a light blue bends into aqua.
const linear = v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
const gamma = v => v <= .0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - .055;
function oklch(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error("A gem colour must be a hex token, not " + JSON.stringify(hex));
  const [r, g, b] = [0, 2, 4].map(i => linear(parseInt(m[1].slice(i, i + 2), 16) / 255));
  const long = Math.cbrt(.4122214708 * r + .5363325363 * g + .0514459929 * b);
  const medium = Math.cbrt(.2119034982 * r + .6806995451 * g + .1073969566 * b);
  const short = Math.cbrt(.0883024619 * r + .2817188376 * g + .6299787005 * b);
  const a = 1.9779984951 * long - 2.4285922050 * medium + .4505937099 * short;
  const bb = .0259040371 * long + .7827717662 * medium - .8086757660 * short;
  return [.2104542553 * long + .7936177850 * medium - .0040720468 * short, Math.hypot(a, bb),
    Math.atan2(bb, a) * 180 / Math.PI];
}
function inGamut(l, c, h) {  // linear sRGB
  l = Math.min(1, Math.max(0, l));
  const channels = chroma => {
    const a = chroma * Math.cos(h * Math.PI / 180), b = chroma * Math.sin(h * Math.PI / 180);
    const long = (l + .3963377774 * a + .2158037573 * b) ** 3;
    const medium = (l - .1055613458 * a - .0638541728 * b) ** 3;
    const short = (l - .0894841775 * a - 1.2914855480 * b) ** 3;
    return [4.0767416621 * long - 3.3077115913 * medium + .2309699292 * short,
      -1.2684380046 * long + 2.6097574011 * medium - .3413193965 * short,
      -.0041960863 * long - .7034186147 * medium + 1.7076147010 * short];
  };
  const fits = chroma => channels(chroma).every(v => v > -1e-6 && v < 1 + 1e-6);
  let inside = fits(c) ? c : 0, outside = c;
  if (inside !== c) for (let i = 0; i < 16; i++) {
    const mid = (inside + outside) / 2;
    if (fits(mid)) inside = mid; else outside = mid;
  }
  return channels(inside).map(v => Math.min(1, Math.max(0, v)));
}
const css = rgb => "rgb(" + rgb.map(v => Math.round(255 * gamma(v))).join(",") + ")";

// A stone's material, read off its card. The kind's colour is lifted to the
// lightness floor styles.css sets and becomes the stone's body. Light crossing the
// stone is absorbed in proportion to how far it travels, so thin edges run pale
// and long paths run deep - the way a cut stone takes its colour.
const DEPTH = .75;
function material(card, state) {
  const style = getComputedStyle(card);
  const read = name => style.getPropertyValue(name).trim();
  const need = name => {
    const v = parseFloat(read(name));
    if (Number.isNaN(v)) throw new Error("styles.css gives the gem no " + name);
    return v;
  };
  const live = state === "live";
  const [gemL, gemC, gemH] = oklch(read("--gem"));
  const l = Math.max(gemL, need("--stone-l"), need("--kind-l")) + (live ? .05 : 0);
  // Commands pin their own chroma and hue; the other kinds boost the token's.
  const c = read("--chroma") ? need("--chroma") : gemC * (live ? 1.6 : 1.5);
  const h = read("--hue") ? need("--hue") : gemH;
  const body = inGamut(l, c, h);
  const fire = name => { const [fl, fc, fh] = oklch(read(name)); return inGamut(fl + .1, fc * 1.5, fh); };
  return {
    stone: css(body), absorb: body.map(v => -Math.log(Math.max(v, .02)) * DEPTH),
    fireA: fire("--fire-a"), fireB: fire("--fire-b"),
  };
}

// Light. Every pixel of a stone is ray-traced on the GPU. A ray from the eye splits
// at the surface: some reflects the studio around the stone, the rest refracts in,
// bounces off the insides of the facets - mostly by total internal reflection,
// which is what makes a cut stone bright - and leaves through another facet, bent
// a little differently for red, green and blue. That split is fire. The studio is
// a dim floor under a pale sky, a broad fill behind the eye, a large softbox at the
// top left where the flat marks were always lit from, a strip light to the right,
// a bright horizon, and two small panels in the stone's fire hues. It stays still
// while the stone turns, so the facets flash as they catch it.
const GEM_SHADER = `
precision highp float;
uniform vec4 planes[${MAX_FACETS}];
uniform int count;
uniform mat3 turn, back;
uniform vec3 absorb, fireA, fireB;
uniform vec4 sparks[3];
uniform vec2 centre;
uniform float size, unit;
const float IOR = 2.2;
const float SPREAD = .07;

vec3 studio(vec3 d) {
  vec3 light = mix(vec3(.08, .08, .09), vec3(.62, .63, .67), smoothstep(-.6, .6, d.y));
  light += 1.1 * smoothstep(.2, .9, dot(d, vec3(0., .2, .98)));
  light += 8. * smoothstep(.85, .96, dot(d, normalize(vec3(-.55, .7, .45))));
  light += 3. * smoothstep(.93, .99, dot(d, normalize(vec3(.8, .3, .5))));
  light += 1.6 * exp(-pow((d.y - .1) * 10., 2.));
  light += 2.5 * fireA * smoothstep(.92, .98, dot(d, normalize(vec3(-.75, -.3, .6))));
  light += 2.5 * fireB * smoothstep(.92, .98, dot(d, normalize(vec3(.7, -.4, .6))));
  return light;
}
float fresnel(float cosine) { return .1 + .9 * pow(1. - clamp(cosine, 0., 1.), 5.); }

vec4 stone(vec2 p) {
  vec3 origin = back * vec3(p + centre, 4.), ray = back * vec3(0., 0., -1.);
  float entry = -1e9, depth = 1e9;
  vec3 normal = vec3(0., 0., 1.);
  for (int i = 0; i < ${MAX_FACETS}; i++) {
    if (i >= count) break;
    float facing = dot(planes[i].xyz, ray), gap = planes[i].w - dot(planes[i].xyz, origin);
    if (abs(facing) < 1e-6) { if (gap < 0.) depth = -1e9; continue; }
    float t = gap / facing;
    if (facing < 0.) { if (t > entry) { entry = t; normal = planes[i].xyz; } }
    else depth = min(depth, t);
  }
  float chord = depth - entry;
  if (chord <= 0.) return vec4(0.);

  float f = fresnel(-dot(ray, normal));
  vec3 light = f * studio(turn * reflect(ray, normal));
  vec3 at = origin + ray * entry, dir = refract(ray, normal, 1. / IOR), carried = vec3(1. - f);
  for (int bounce = 0; bounce < 5; bounce++) {
    float leave = 1e9;
    vec3 exit = vec3(0., 1., 0.);
    for (int i = 0; i < ${MAX_FACETS}; i++) {
      if (i >= count) break;
      float facing = dot(planes[i].xyz, dir);
      if (facing > 1e-6) {
        float t = (planes[i].w - dot(planes[i].xyz, at)) / facing;
        if (t < leave) { leave = t; exit = planes[i].xyz; }
      }
    }
    at += dir * leave;
    carried *= exp(-absorb * leave);
    vec3 red = refract(dir, -exit, IOR - SPREAD), green = refract(dir, -exit, IOR), blue = refract(dir, -exit, IOR + SPREAD);
    vec3 passes = vec3(step(1e-4, dot(red, red)), step(1e-4, dot(green, green)), step(1e-4, dot(blue, blue)));
    vec3 outside = vec3(studio(turn * red).r, studio(turn * green).g, studio(turn * blue).b);
    float kept = fresnel(dot(dir, exit));
    light += carried * (1. - kept) * passes * outside;
    carried *= mix(vec3(1.), vec3(kept), passes);
    dir = reflect(dir, -exit);
  }
  light += .5 * carried * studio(turn * dir);
  float edge = clamp(chord / (unit * 3.), 0., 1.);  // soften the outline where the stone is thinnest
  return vec4(pow(1. - exp(-1.5 * light), vec3(1. / 2.2)) * edge, edge);
}

// A sparkle: a soft bloom crossed by two thin rays, turning as it lives.
float sparkle(vec2 frag) {
  float light = 0.;
  for (int i = 0; i < 3; i++) {
    if (sparks[i].z <= 0.) continue;
    vec2 d = frag - sparks[i].xy;
    float c = cos(sparks[i].w), s = sin(sparks[i].w);
    d = vec2(c * d.x - s * d.y, s * d.x + c * d.y) / sparks[i].z;
    light += .9 * exp(-6. * dot(d, d)) + max(0., 1. - abs(d.x) * 14. - abs(d.y)) + max(0., 1. - abs(d.y) * 14. - abs(d.x));
  }
  return min(light, 1.);
}

void main() {
  vec4 base = stone((gl_FragCoord.xy - size * .5) * unit);
  float glint = sparkle(gl_FragCoord.xy);
  gl_FragColor = vec4(min(base.rgb + glint, 1.), max(base.a, glint));
}`;
// Sparkles are born where a facet facing the eye catches the softbox head on, and
// live about half a second.
const unit = v => { const length = Math.hypot(...v); return v.map(x => x / length); };
const GLARE = unit([-.55, .7, 1.45]);
// The canvas is the 52px stone box with 10px either side for the turning outline
// and its sparkles. The stone is seen from 28 degrees above its girdle, so the
// table and the pavilion both show as it turns.
const GEM_BOX = 72, GEM_RADIUS = 24, PITCH = .49, REST = .35, TURN = 2 * Math.PI;
const SPARK_MS = 520;
const gems = new Map();

// One WebGL canvas, off the page, draws every stone in turn and hands each frame to
// its card's canvas as a bitmap. A page may hold only a handful of WebGL contexts
// and there is a card per employee; handing over a bitmap moves the frame without
// reading its pixels back off the GPU, which copying into a 2D canvas would. Frames
// render at twice the card's device pixels and are shown at its size, so the edges
// come out antialiased. Without WebGL the stones stay unpainted and the cards read
// the same.
const STUDIO_SIZE = GEM_BOX * Math.min(2, devicePixelRatio || 1) * 2;
let studio;
function makeStudio() {
  if (typeof OffscreenCanvas === "undefined") return null;
  const canvas = new OffscreenCanvas(STUDIO_SIZE, STUDIO_SIZE);
  const gl = canvas.getContext("webgl", { antialias: false });
  if (!gl) return null;
  const shader = (type, source) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, source);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error("gem shader: " + gl.getShaderInfoLog(s));
    return s;
  };
  const program = gl.createProgram();
  gl.attachShader(program, shader(gl.VERTEX_SHADER, "attribute vec2 corner; void main() { gl_Position = vec4(corner, 0., 1.); }"));
  gl.attachShader(program, shader(gl.FRAGMENT_SHADER, GEM_SHADER));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error("gem shader: " + gl.getProgramInfoLog(program));
  gl.useProgram(program);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const corner = gl.getAttribLocation(program, "corner");
  gl.enableVertexAttribArray(corner);
  gl.vertexAttribPointer(corner, 2, gl.FLOAT, false, 0, 0);
  gl.viewport(0, 0, STUDIO_SIZE, STUDIO_SIZE);
  const at = name => gl.getUniformLocation(program, name);
  gl.uniform1f(at("size"), STUDIO_SIZE);
  gl.uniform1f(at("unit"), GEM_BOX / GEM_RADIUS / STUDIO_SIZE);
  return {
    canvas, gl, planes: at("planes"), count: at("count"), turn: at("turn"), back: at("back"), centre: at("centre"),
    absorb: at("absorb"), fireA: at("fireA"), fireB: at("fireB"), sparks: at("sparks"),
  };
}

function gem(badge) {
  return '<span class="float" aria-hidden="true"><canvas class="gem"></canvas>' +
    '<i class="motes"><b></b><b></b><b></b></i>' + badge + "</span>";
}
function paintGem(card, state) {
  const stone = material(card, state);
  card.style.setProperty("--stone", stone.stone);
  return stone;
}
function makeGem(card, kind, state, i) {
  if (studio === undefined) studio = makeStudio();
  const canvas = card.querySelector(".gem");
  canvas.width = canvas.height = STUDIO_SIZE;
  const shape = SOLIDS[kind];
  return {
    card, frame: canvas.getContext("bitmaprenderer"), state, i, shape, tilt: TILT[kind], material: paintGem(card, state),
    screen: new Float32Array(shape.verts.length * 2), glare: new Float32Array(shape.faces.length), sparks: [],
    yaw: REST + i * 1.1, pitch: PITCH, roll: 0, speed: 0,
    hover: false, px: 0, py: 0, steerX: 0, steerY: 0,
  };
}
function repaintGems() {
  for (const g of gems.values()) { g.material = paintGem(g.card, g.state); drawGem(g, performance.now()); }
}

// Every stone turns and sways whatever its record - the status line says whether
// it has run - and a working one turns fastest. The stone under the pointer turns
// faster still and leans toward it.
function stepGem(g, dt, t) {
  const ease = rate => 1 - Math.exp(-dt * rate);
  const spin = g.state === "live" ? TURN / 3.5 : TURN / 9, sway = g.state === "live" ? 1.6 : 1;
  g.speed += ((g.hover ? spin * 2.5 : spin) - g.speed) * ease(2.5);
  g.yaw += g.speed * dt;
  g.steerX += ((g.hover ? g.px : 0) - g.steerX) * ease(6);
  g.steerY += ((g.hover ? g.py : 0) - g.steerY) * ease(6);
  g.pitch = PITCH + sway * .08 * Math.sin(t * .9 + g.i) + g.steerY * .6;
  g.roll = g.tilt + sway * .06 * Math.sin(t * .63 + g.i * 1.7) - g.steerX * .25;
}
function drawGem(g, now) {
  const { shape, material: stone, screen } = g;
  const yaw = g.yaw + g.steerX * .9;
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(g.pitch), sp = Math.sin(g.pitch);
  const cr = Math.cos(g.roll), sr = Math.sin(g.roll);
  const turn = ([x, y, z]) => {
    const x1 = x * cy + z * sy, z1 = z * cy - x * sy;
    const y1 = y * cp - z1 * sp, z2 = y * sp + z1 * cp;
    return [x1 * cr - y1 * sr, x1 * sr + y1 * cr, z2];
  };
  // The stone's middle stays at the middle of its box however it is turned.
  const [centreX, centreY] = turn([0, shape.mid, 0]);
  shape.verts.forEach((v, k) => {
    const [x, y] = turn(v);
    screen[2 * k] = GEM_BOX / 2 + (x - centreX) * GEM_RADIUS;
    screen[2 * k + 1] = GEM_BOX / 2 + (centreY - y) * GEM_RADIUS;
  });
  shape.faces.forEach((face, k) => {
    const n = turn(face.normal);
    const glare = n[2] > 0 ? Math.max(0, n[0] * GLARE[0] + n[1] * GLARE[1] + n[2] * GLARE[2]) ** 40 : 0;
    if (glare > .7 && g.glare[k] <= .7 && g.sparks.length < 3) {
      const top = face.ids.reduce((best, id) => screen[2 * id + 1] < screen[2 * best + 1] ? id : best);
      g.sparks.push({ x: screen[2 * top], y: screen[2 * top + 1], born: now });
    }
    g.glare[k] = glare;
  });
  g.sparks = g.sparks.filter(spark => now - spark.born < SPARK_MS);
  if (!studio) return;
  const { gl } = studio, pixel = STUDIO_SIZE / GEM_BOX;
  const sparks = new Float32Array(12);
  g.sparks.forEach((spark, k) => {
    const age = (now - spark.born) / SPARK_MS;
    sparks.set([spark.x * pixel, (GEM_BOX - spark.y) * pixel, 8 * Math.sin(Math.PI * age) * pixel, age * Math.PI / 4], 4 * k);
  });
  const columns = [turn([1, 0, 0]), turn([0, 1, 0]), turn([0, 0, 1])];
  gl.uniform4fv(studio.planes, shape.planes);
  gl.uniform1i(studio.count, shape.faces.length);
  gl.uniformMatrix3fv(studio.turn, false, columns.flat());
  gl.uniformMatrix3fv(studio.back, false, [0, 1, 2].flatMap(row => columns.map(column => column[row])));
  gl.uniform2f(studio.centre, centreX, centreY);
  gl.uniform3fv(studio.absorb, stone.absorb);
  gl.uniform3fv(studio.fireA, stone.fireA);
  gl.uniform3fv(studio.fireB, stone.fireB);
  gl.uniform4fv(studio.sparks, sparks);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  g.frame.transferFromImageBitmap(studio.canvas.transferToImageBitmap());
}

// One loop turns every stone, and only while the Employees view is showing. Under
// a reduced-motion preference it never starts: each stone keeps the still frame
// renderStaff drew.
let gemsTurning = false, gemsLast = 0;
function gemFrame(now) {
  if (!$("#vEmployees").classList.contains("on")) { gemsTurning = false; return; }
  const dt = Math.min(.05, (now - gemsLast) / 1000);
  gemsLast = now;
  for (const g of gems.values()) { stepGem(g, dt, now / 1000); drawGem(g, now); }
  requestAnimationFrame(gemFrame);
}
function startGems() {
  if (REDUCED || gemsTurning) return;
  gemsTurning = true;
  gemsLast = performance.now();
  requestAnimationFrame(gemFrame);
}
const CHECK = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.6l3 3 6-6.6"/></svg>';
const SEAL = '<svg class="ok" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7"/><path d="M4.8 8.4l2.2 2.2 4.3-4.6"/></svg>';

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
  gems.clear();
  for (const [n, m] of BRAIN.employees.entries()) {
    const live = m.doing.length > 0;
    const state = live ? "live" : m.done.length ? "done" : "never";
    const card = document.createElement("div");
    card.className = "emp " + state;
    card.dataset.kind = m.kind;
    // Each card's motion runs on its own phase, so a row of gems drifts rather
    // than marching in step.
    card.style.setProperty("--i", n);
    card.innerHTML =
      '<header><div class="av">' + gem(state === "done" ? SEAL : "") + "</div>" +
      '<div><h3></h3><span class="kind"></span></div></header>' +
      '<p class="role"></p><div class="chips"></div>' +
      '<div class="work"><div class="st">' + (state === "done" ? CHECK : "<i></i>") + "<b></b></div>" +
      '<div class="runs"></div></div>';
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

    card.querySelector(".st b").textContent = live
      ? "Working — " + m.doing.length + " unmerged"
      : state === "done" ? "Finished" : "Never run";

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
    const g = makeGem(card, m.kind, state, n);
    gems.set(card, g);
    drawGem(g, 0);
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

// The gem under the pointer wakes and leans toward it, as if the card were a stone
// turned under a lamp. Fine pointers only, since a touch has no hover to end it,
// and never under a reduced-motion preference.
const tilts = matchMedia("(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)");
let hovered = null;
$("#staff").addEventListener("pointermove", e => {
  const card = tilts.matches && e.target.closest(".emp");
  const g = card ? gems.get(card) : null;
  if (hovered && hovered !== g) hovered.hover = false;
  hovered = g;
  if (!g) return;
  const r = card.getBoundingClientRect();
  g.hover = true;
  g.px = (e.clientX - r.left) / r.width - .5;
  g.py = (e.clientY - r.top) / r.height - .5;
});
$("#staff").addEventListener("pointerleave", () => {
  if (hovered) hovered.hover = false;
  hovered = null;
});

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
matchMedia("(prefers-color-scheme:dark)").addEventListener("change", () => { readColors(); paintFigure(); draw(); repaintGems(); });
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
