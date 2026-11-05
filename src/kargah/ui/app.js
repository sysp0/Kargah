// devchain web viewer: polls `./dev web` and draws one run. Read-only. Every value from the run goes into the page
// through textContent, never as HTML: logs and prompts hold arbitrary text.
"use strict";

const TONE = {
  done: "ok", commit: "ok", failed: "bad", heavy: "bad", blocked: "warn", needs_decision: "warn",
  app_bug: "mag", triage: "mag", running: "run", codex: "run", resume: "run", accept: "run", tests: "run",
  build_ui: "run", playwright: "run", review: "rev", planfix: "plan", gate: "warn",
  approved: "ok", skipped: "warn", "waiting for test": "warn", "QA running": "run", building: "run",
  fixed: "ok", fixing: "run", closed: "ok", question: "mag", "needs-info": "mag", decide: "bad",
};
const PART_ICON = { done: "✔", approved: "✔", skipped: "⏭", "waiting for test": "⏸", "QA running": "⏸",
  building: "⚙", "not started": "○" };
const MAX_LINES = 3000;
const S = {
  runs: [], runId: null, run: null, seq: 0, pkg: null, pkgKey: "", rowsKey: "", skew: 0, poll: 2000,
  timer: null, busy: false, again: false, fail: 0,
};
const $ = (id) => document.getElementById(id);
const enc = encodeURIComponent;

// ---- small helpers ----------------------------------------------------------------------------------------------
function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "text") node.textContent = String(value);
    else if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const kid of kids) if (kid !== null && kid !== undefined && kid !== false) node.append(kid);
  return node;
}
const pad = (n) => String(n).padStart(2, "0");
function dur(sec) {
  sec = Math.max(0, Math.floor(sec));
  const hours = Math.floor(sec / 3600), minutes = Math.floor((sec % 3600) / 60), seconds = sec % 60;
  return hours ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`;
}
function short(n) {
  n = n || 0;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${Math.round(n / 1e3)}k`;
  return String(n);
}
const usd = (x) => `$${(x || 0).toFixed(2)}`;
function clock(ts) {
  const d = new Date(ts * 1000);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
function size(n) {
  if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}
const serverNow = () => Date.now() / 1000 - S.skew;
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : null);
const claudeCost = (p) => ((p.usage || {}).claude || {}).cost_usd || 0;

async function api(path) {
  const res = await fetch(path, { cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `${res.status} ${path}`);
  return body;
}

function readHash() {
  const q = new URLSearchParams(location.hash.slice(1));
  return { run: q.get("run"), pkg: q.get("pkg") };
}
function writeHash() {
  const q = new URLSearchParams();
  if (S.runId) q.set("run", S.runId);
  if (S.pkg) q.set("pkg", S.pkg);
  history.replaceState(null, "", `#${q}`);
}

function badge(state, active) {
  return h("span", { class: "badge", "data-tone": TONE[state] || null },
    active ? h("span", { class: "live-dot" }) : null, state);
}

// ---- polling ------------------------------------------------------------------------------------------------------
async function refresh() {
  clearTimeout(S.timer);
  if (S.busy) {
    S.again = true;
    return;
  }
  S.busy = true;
  try {
    const list = await api("/api/runs");
    S.poll = list.poll_ms || 2000;
    S.runs = list.runs || [];
    if (!S.runs.some((r) => r.id === S.runId)) {
      if (S.runId) S.pkg = null;   // a link to a run that is gone; a link with only #pkg= keeps the package
      S.runId = S.runs.length ? S.runs[0].id : null;
      resetRun();
      writeHash();
    }
    drawRuns();
    if (!S.runId) {
      drawNoRuns();
    } else {
      const id = S.runId;
      const d = await api(`/api/runs/${enc(id)}?since=${S.seq}`);
      if (id === S.runId) {
        S.skew = Date.now() / 1000 - d.now;
        if (d.live_reset) clearLog();
        S.run = d;
        appendLines(d.live);
        S.seq = d.live_seq;
        S.fail = 0;
        drawRun();
        await refreshPackage();
      }
    }
    S.fail = 0;
  } catch (err) {
    S.fail += 1;
    console.warn("devchain web:", err);
    drawBanner();
  } finally {
    S.busy = false;
    S.timer = setTimeout(refresh, S.again ? 0 : S.poll);
    S.again = false;
  }
}

function resetRun() {
  S.seq = 0;
  S.run = null;
  S.pkgKey = "";
  S.rowsKey = "";
  clearLog();
  drawDetailEmpty();
}

// ---- header, banner, table, usage ---------------------------------------------------------------------------------
function drawRuns() {
  const select = $("run");
  const key = S.runs.map((r) => `${r.id}|${r.status}|${r.done}|${r.packages}`).join(",");
  if (select.dataset.key !== key) {
    select.replaceChildren(...S.runs.map((r) =>
      h("option", { value: r.id, text: `${r.id} · ${r.status} · ${r.done}/${r.packages}` })));
    select.dataset.key = key;
  }
  select.value = S.runId || "";
}

function drawNoRuns() {
  S.run = null;
  $("status").replaceChildren();
  $("stage").textContent = "";
  $("count").textContent = "";
  $("elapsed").textContent = "";
  $("cost").textContent = "";
  $("bar").style.width = "0";
  document.querySelector("#pkgs tbody").replaceChildren();
  $("empty").hidden = false;
  $("usage").replaceChildren();
  drawBanner();
}

function drawRun() {
  const d = S.run;
  const pill = $("status");
  pill.replaceChildren(d.status === "running" ? h("span", { class: "live-dot" }) : "", d.status);
  pill.dataset.tone = TONE[d.status] || "";
  $("stage").textContent = [d.kind, d.stage].filter(Boolean).join(" · ");
  const done = d.packages.filter((p) => p.state === "done").length;
  $("count").textContent = `${done}/${d.packages.length} done`;
  $("bar").style.width = d.packages.length ? `${(100 * done) / d.packages.length}%` : "0";
  $("cost").textContent = `Claude ${usd((d.totals.claude || {}).cost_usd)}`;
  $("empty").hidden = true;
  document.title = `${d.status} ${done}/${d.packages.length} · devchain`;
  drawCurrent();
  drawTable();
  drawUsage();
  tick();
}

function bannerOf(d) {
  if (S.fail) return { tone: "bad", title: "Connection lost", text: "the page cannot reach ./dev web; retrying." };
  if (!d) return null;
  const now = serverNow();
  if (d.waiting_until && !d.finished && d.waiting_until > now) {
    return { tone: "warn", title: "Usage limit",
      text: `waiting; continues in ${dur(d.waiting_until - now)} (at ${clock(d.waiting_until)}).` };
  }
  if (d.status === "blocked" || d.status === "failed") {
    const p = [...d.packages].reverse().find((x) => x.state === d.status);
    return { tone: d.status === "failed" ? "bad" : "warn",
      title: `${d.status === "failed" ? "Failed" : "Blocked"}${p ? ` at ${p.name}` : ""}`,
      text: (p && p.message) || d.outcome_message || "",
      hint: p && p.note && !(p.message || "").includes(p.note) ? `note ${p.note}` : "./dev resume continues the run after the fix." };
  }
  if (d.status === "stopped") {
    const byHand = d.outcome === "stopped";
    return { tone: "", title: byHand ? "Stopped" : "Not running",
      text: byHand ? "stopped by hand (Ctrl+C or ./dev stop)." : "the runner ended without an outcome (killed or crashed).",
      hint: "./dev resume continues it." };
  }
  if (d.status === "gate") {
    return { tone: "warn", title: "Waiting for your test", text: d.outcome_message || "",
      hint: "./dev approve <part> or ./dev skip <part>, then ./dev resume" };
  }
  if (d.status === "done") return { tone: "ok", title: "Done", text: "every package of this run is done." };
  return null;
}

function drawBanner() {
  const el = $("banner");
  const b = bannerOf(S.run);
  if (!b) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  el.dataset.tone = b.tone || "";
  el.replaceChildren(h("b", { text: b.title }), h("span", { text: b.text || "" }),
    ...(b.hint ? [h("span", { class: "hint", text: b.hint })] : []));   // replaceChildren prints a null as "null"
}

function drawCurrent() {
  const d = S.run;
  const p = d.packages.find((x) => x.name === d.current);
  const el = $("current");
  if (d.status !== "running" || !p || !p.active) {
    el.replaceChildren();
    return;
  }
  el.replaceChildren(`now ${p.name} · ${p.state}${p.round !== null ? ` (round ${p.round})` : ""} · `,
    h("span", { class: "mono", "data-start": p.step_started ?? "" }));
}

function treeRow(node, running) {
  const p = node.pkg;
  const pad = { style: `padding-left: ${8 + node.depth * 18}px` };
  if (node.kind === "part" || node.kind === "group") {
    return h("tr", { class: "part" },
      h("td", { class: "name", colspan: 2 }, `${PART_ICON[node.state] || "▾"} ${node.label}`,
        h("span", { class: "muted", text: `  ${node.title}` })),
      h("td", { colspan: 2 }, node.state ? badge(node.state, node.state === "building" && running) : ""),
      h("td", { class: "num", text: node.detail }),
      h("td", { colspan: 2, text: node.counts }));
  }
  if (node.kind === "issue") {
    const issue = node.issue;
    const select = p ? () => selectPkg(p.name) : null;
    return h("tr", { class: [p && p.name === S.pkg ? "selected" : "", "issue"].join(" ").trim(),
      "data-pkg": p ? p.name : null, onclick: select },
      h("td", { class: "name", ...pad }, `${node.icon} `,
        h("a", { href: safeUrl(issue.url), target: "_blank", rel: "noopener", text: node.label,
          onclick: (e) => e.stopPropagation() })),
      h("td", {}, badge(node.state, p && p.active && running)),
      h("td", { class: "num", text: p && p.round !== null ? p.round : "" }),
      h("td", { class: "num mono", "data-start": p ? p.started ?? "" : "", "data-end": p ? p.finished ?? "" : "" }),
      h("td", { text: node.detail }),
      h("td", { class: "num", text: p && claudeCost(p) ? usd(claudeCost(p)) : "" }),
      h("td", { class: "more", text: node.title, title: node.title }));
  }
  const cost = claudeCost(p);
  const detail = p.pr
    ? h("a", { href: safeUrl(p.pr), target: "_blank", rel: "noopener", text: `${p.commit || ""} PR`.trim(),
      onclick: (e) => e.stopPropagation() })
    : [node.title, p.commit].filter(Boolean).join(" · ");
  const cls = [p.name === S.pkg ? "selected" : "", p.state === "waiting" ? "waiting" : ""].join(" ").trim();
  return h("tr", { class: cls || null, "data-pkg": p.name, onclick: () => selectPkg(p.name) },
    h("td", { class: "name", ...pad, text: p.name }),
    h("td", {}, badge(p.state, p.active && running)),
    h("td", { class: "num", text: p.round ?? "" }),
    h("td", { class: "num mono", "data-start": p.started ?? "", "data-end": p.finished ?? "" }),
    h("td", { text: p.last_result || node.counts || "" }),
    h("td", { class: "num", text: cost ? usd(cost) : "" }),
    h("td", { class: "more", title: p.message || node.title || null }, detail));
}

function drawTable() {
  const d = S.run;
  const key = JSON.stringify([S.pkg, d.status, d.tree, d.packages.map((p) =>
    [p.name, p.state, p.round, p.last_result, p.commit, p.pr, p.message, p.started, p.finished, claudeCost(p)])]);
  if (key === S.rowsKey) return;
  S.rowsKey = key;
  if (d.tree && d.tree.length) {
    const running = d.status === "running";
    document.querySelector("#pkgs tbody").replaceChildren(...d.tree.map((node) => treeRow(node, running)));
    return;
  }
  const rows = d.packages.map((p) => {
    const cost = claudeCost(p);
    const detail = p.pr
      ? h("a", { href: safeUrl(p.pr), target: "_blank", rel: "noopener", text: `${p.commit || ""} PR`.trim(),
        onclick: (e) => e.stopPropagation() })
      : (p.commit || p.message || "");
    const cls = [p.name === S.pkg ? "selected" : "", p.state === "waiting" ? "waiting" : ""].join(" ").trim();
    return h("tr", { class: cls || null, "data-pkg": p.name, onclick: () => selectPkg(p.name) },
      h("td", { class: "name", text: p.name }),
      h("td", {}, badge(p.state, p.active && d.status === "running")),
      h("td", { class: "num", text: p.round ?? "" }),
      h("td", { class: "num mono", "data-start": p.started ?? "", "data-end": p.finished ?? "" }),
      h("td", { text: p.last_result || "" }),
      h("td", { class: "num", text: cost ? usd(cost) : "" }),
      h("td", { class: "more", title: p.message || null }, detail));
  });
  document.querySelector("#pkgs tbody").replaceChildren(...rows);
}

function usageRows(pairs) {
  return h("table", {}, h("tbody", {}, ...pairs.map(([k, v]) =>
    h("tr", {}, h("td", { text: k }), h("td", { class: "mono", text: v })))));
}

function drawUsage() {
  const d = S.run;
  const codex = d.totals.codex || {};
  const claude = d.totals.claude || {};
  const pct = codex.cache_pct === null || codex.cache_pct === undefined ? "" : ` (${Math.round(codex.cache_pct)}%)`;
  const models = Object.entries(d.models || {}).filter(([k]) => k.startsWith("claude "))
    .map(([k, u]) => [k.slice(7), `${u.calls} calls · ${usd(u.cost_usd)}`]);
  $("usage").replaceChildren(
    h("h4", { text: "Codex" }),
    usageRows([["calls", String(codex.calls || 0)], ["input", short(codex.input)],
      ["cached", short(codex.cached) + pct], ["output", short(codex.output)], ["reasoning", short(codex.reasoning)]]),
    h("h4", { text: "Claude", style: "margin-top: 12px" }),
    usageRows([["calls", String(claude.calls || 0)], ["cost", usd(claude.cost_usd)], ...models]),
    h("div", { class: "folder", text: `Run folder ${d.dir}` }));
}

function tick() {
  const d = S.run;
  if (!d) return;
  // a run that is not running stops the clocks at its last event
  const now = d.status === "running" ? serverNow() : (d.finished || d.last_ts || serverNow());
  for (const cell of document.querySelectorAll("[data-start]")) {
    const start = parseFloat(cell.dataset.start);
    const end = parseFloat(cell.dataset.end);
    cell.textContent = Number.isFinite(start) ? dur((Number.isFinite(end) ? end : now) - start) : "";
  }
  $("elapsed").textContent = d.started ? dur((d.finished || now) - d.started) : "";
  drawBanner();
}

// ---- package detail and files -------------------------------------------------------------------------------------
function drawDetailEmpty() {
  $("detail").replaceChildren(h("p", { class: "muted",
    text: "Select a package to see its message, findings, plan note and files." }));
}

function selectPkg(name) {
  S.pkg = name;
  S.pkgKey = "";
  S.rowsKey = "";
  writeHash();
  $("only-name").textContent = name;
  if (S.run) drawTable();
  filterLog();
  refreshPackage().catch((err) => console.warn("devchain web:", err));
}

async function refreshPackage() {
  const d = S.run;
  if (!d || !S.pkg) return;
  const p = d.packages.find((x) => x.name === S.pkg);
  if (!p) {
    S.pkg = null;
    drawDetailEmpty();
    return;
  }
  const key = JSON.stringify([d.id, d.status, p.state, p.round, p.last_result, p.message, p.step_started,
    p.finished, p.note]);
  if (key === S.pkgKey) return;
  const id = d.id;
  const name = p.name;
  const data = await api(`/api/runs/${enc(id)}/pkg/${enc(name)}`);
  if (id === S.runId && name === S.pkg) {
    S.pkgKey = key;
    drawDetail(data);
  }
}

function block(label, ...kids) {
  return h("div", { class: "block" }, h("div", { class: "label", text: label }), ...kids);
}

function drawDetail(data) {
  const p = data.row;
  const running = S.run && S.run.status === "running";
  const kids = [h("h3", {}, p.name, badge(p.state, p.active && running),
    p.round !== null ? h("span", { class: "muted", text: `round ${p.round}` }) : null)];
  const facts = [["time", h("span", { class: "mono", "data-start": p.started ?? "", "data-end": p.finished ?? "" })],
    ["last step", p.last_result || "-"]];
  if (p.branch) facts.push(["branch", p.branch]);
  if (p.commit) facts.push(["commit", p.commit]);
  if (p.pr) {
    facts.push(["PR", h("a", { href: safeUrl(p.pr), target: "_blank", rel: "noopener",
      text: p.pr.replace(/^https:\/\/github\.com\//, "") })]);
  }
  const xu = (p.usage || {}).codex || {};
  const cu = (p.usage || {}).claude || {};
  facts.push(["Codex", `${xu.calls || 0} calls · in ${short(xu.input)} · cached ${short(xu.cached)} · out ${short(xu.output)}`]);
  facts.push(["Claude", `${cu.calls || 0} calls · ${usd(cu.cost_usd)}`]);
  kids.push(h("dl", { class: "facts" }, ...facts.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", {}, v)])));
  if (p.message) kids.push(block("Message", h("div", { class: "message", text: p.message })));
  if (data.note) {
    kids.push(block(`Plan note · ${data.note.path}`,
      h("pre", { text: data.note.text ?? "(the note is not in the working tree any more)" })));
  }
  if (data.findings.length) {
    const last = data.findings.length - 1;
    kids.push(block("Findings", ...data.findings.map((f, i) =>
      h("details", { open: i === last }, h("summary", { text: `round ${f.round ?? "-"}` }), h("pre", { text: f.text })))));
  }
  if (data.files.length) {
    kids.push(block("Files of this package (newest first)", h("ul", { class: "files" }, ...[...data.files].reverse()
      .map((f) => h("li", {}, h("button", { type: "button", text: f.path, onclick: () => openFile(data.name, f.path) }),
        h("span", { class: "size", text: `${size(f.size)} · ${clock(f.mtime)}` }))))));
  }
  $("detail").replaceChildren(...kids);
  tick();
}

async function openFile(pkg, path) {
  const dialog = $("viewer");
  const body = $("viewer-body");
  $("viewer-title").textContent = `${pkg}/${path}`;
  body.textContent = "loading…";
  if (!dialog.open) dialog.showModal();
  try {
    const f = await api(`/api/runs/${enc(S.runId)}/pkg/${enc(pkg)}/file?path=${enc(path)}`);
    $("viewer-title").textContent = `${pkg}/${f.path} · ${size(f.size)}${f.truncated ? " · only its end" : ""}`;
    body.textContent = f.text || "(empty)";
    body.scrollTop = /\.(log|txt)$/.test(f.path) ? body.scrollHeight : 0;   // the end of a log matters most
  } catch (err) {
    body.textContent = String(err.message || err);
  }
}

// ---- live log -----------------------------------------------------------------------------------------------------
function clearLog() {
  $("log").replaceChildren();
}

function hiddenLine(pkg) {
  return $("only").checked && S.pkg !== null && (pkg || "-") !== S.pkg;
}

function appendLines(lines) {
  if (!lines || !lines.length) return;
  const log = $("log");
  const frag = document.createDocumentFragment();
  for (const line of lines) {
    const row = h("div", { class: "line", "data-pkg": line.pkg || "-" },
      h("span", { class: "t", text: clock(line.ts) }),
      h("span", { class: "p", text: line.pkg || "-", onclick: () => line.pkg && selectPkg(line.pkg) }),
      h("span", { class: `s st-${line.step}`, text: line.step }),
      h("span", { class: line.step === "state" ? "x st-state" : "x", text: line.text }));
    row.hidden = hiddenLine(line.pkg);
    row.line = line;   // what Copy JSON copies
    frag.append(row);
  }
  log.append(frag);
  while (log.childElementCount > MAX_LINES) log.firstElementChild.remove();
  if ($("follow").checked) log.scrollTop = log.scrollHeight;
}

function filterLog() {
  for (const row of $("log").children) row.hidden = hiddenLine(row.dataset.pkg === "-" ? null : row.dataset.pkg);
  if ($("follow").checked) $("log").scrollTop = $("log").scrollHeight;
}

async function copyLog() {
  const lines = [...$("log").children].filter((row) => !row.hidden && row.line).map(({ line }) =>
    ({ time: clock(line.ts), pkg: line.pkg || null, step: line.step, text: line.text }));
  const text = JSON.stringify({ run: S.runId, stage: S.run ? S.run.stage : null,
    package: $("only").checked ? S.pkg : null, lines }, null, 2);
  const button = $("copy");
  let ok = false;
  try {
    await navigator.clipboard.writeText(text);
    ok = true;
  } catch {   // no clipboard API on plain http from another host: copy through a hidden textarea
    const area = h("textarea", { style: "position: fixed; opacity: 0" });
    area.value = text;
    document.body.append(area);
    area.select();
    ok = document.execCommand("copy");
    area.remove();
  }
  button.textContent = ok ? `Copied ${lines.length} lines` : "Copy failed";
  button.dataset.tone = ok ? "ok" : "bad";
  clearTimeout(button.timer);
  button.timer = setTimeout(() => {
    button.textContent = "Copy JSON";
    delete button.dataset.tone;
  }, 1800);
}

// ---- events -------------------------------------------------------------------------------------------------------
$("run").addEventListener("change", (e) => {
  S.runId = e.target.value;
  S.pkg = null;
  $("only-name").textContent = "the selected package";
  resetRun();
  writeHash();
  refresh();
});
$("only").addEventListener("change", filterLog);
$("copy").addEventListener("click", copyLog);
$("follow").addEventListener("change", () => {
  if ($("follow").checked) $("log").scrollTop = $("log").scrollHeight;
});
$("log").addEventListener("scroll", () => {
  const log = $("log");
  $("follow").checked = log.scrollTop + log.clientHeight >= log.scrollHeight - 24;
});
$("viewer-close").addEventListener("click", () => $("viewer").close());
$("viewer").addEventListener("click", (e) => {
  if (e.target === $("viewer")) $("viewer").close();   // a click on the backdrop
});
document.addEventListener("keydown", (e) => {
  if ($("viewer").open || !S.run || !["ArrowDown", "ArrowUp", "j", "k"].includes(e.key)) return;
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  const names = S.run.packages.map((p) => p.name);
  if (!names.length) return;
  const at = names.indexOf(S.pkg);
  const step = e.key === "ArrowDown" || e.key === "j" ? 1 : -1;
  const next = names[Math.min(names.length - 1, Math.max(0, at < 0 ? 0 : at + step))];
  e.preventDefault();
  selectPkg(next);
  const row = document.querySelector(`#pkgs tr[data-pkg="${CSS.escape(next)}"]`);
  if (row) row.scrollIntoView({ block: "nearest" });
});

const first = readHash();
S.runId = first.run;
S.pkg = first.pkg;
if (S.pkg) $("only-name").textContent = S.pkg;
setInterval(tick, 1000);
refresh();
