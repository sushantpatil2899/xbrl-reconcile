// Queries the published Parquet in the reader's browser. No server is involved.
//
// DuckDB compiled to WebAssembly fetches the Parquet over HTTP range requests, so a
// filtered query reads a few kilobytes out of a 700 KB file rather than downloading
// it. That is why this works as a static page at no cost: the host serves files it
// never interprets, and the reader's machine does the work.
//
// Freshness is the one thing a static page gets wrong by default. The data is not
// baked in, so a new publish is picked up on the next load, but a browser or CDN
// cache can quietly serve last week's file with nothing on screen to say so. The fix
// is to treat _index.json as the version marker: it is about a kilobyte, it already
// carries published_at, and it is fetched with no-store so that one request always
// reaches the server. Each Parquet is then requested with ?v=<published_at>, so a new
// publish is a new cache key and an unchanged one is served from cache instantly.
//
// Nothing on this page is a hardcoded figure. The hero's counters, the confidence
// bar, every table and the count in the "what to distrust" heading are all read from
// the marts on load, so the page cannot drift from the data it is describing.

import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm";

const R = matchMedia("(prefers-reduced-motion: reduce)").matches;
const NS = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat("en-US");
const money = (v) =>
  v === null || v === undefined
    ? '<span class="muted">no value</span>'
    : (v < 0 ? "(" : "") + fmt.format(Math.round(Math.abs(v))) + (v < 0 ? ")" : "");

let connection = null;
let CONCEPTS = [];
let RESOLVE = [];
const settled = {};
let timers = [];

// ---------------------------------------------------------------- boot

async function boot() {
  const index = await (await fetch("_index.json", { cache: "no-store" })).json();
  const version = (index.published_at || "0").replace(/[^0-9A-Za-z]/g, "");
  $("fa").textContent = index.published_at;

  const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
  const workerUrl = URL.createObjectURL(
    new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }),
  );
  const worker = new Worker(workerUrl);
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(workerUrl);

  // Registered under the plain name, fetched with the version. Queries stay readable
  // and the stable URL keeps working for anyone pointing their own DuckDB at it.
  // The fetch URL must be absolute: DuckDB runs in a worker created from a blob, so
  // a relative path has no page to resolve against and fails with "Invalid URL".
  for (const mart of index.marts) {
    await db.registerFileURL(
      `${mart.name}.parquet`,
      new URL(`${mart.name}.parquet?v=${version}`, location.href).href,
      duckdb.DuckDBDataProtocol.HTTP,
      false,
    );
  }
  connection = await db.connect();

  await heroData(index);
  await Promise.all([fillPickers(), showDistrust(), showBuild()]);
  await Promise.all([showCompare(), showCompany()]);
}

async function query(sql, params = []) {
  const prepared = await connection.prepare(sql);
  const result = await prepared.query(...params);
  await prepared.close();
  return result.toArray().map((row) => row.toJSON());
}

// ---------------------------------------------------------------- hero

async function heroData(index) {
  const [tags] = await query(
    `select count(distinct tag) as distinct_tags,
            round(100.0 * sum(case when peers_using_same_name <= 1 then 1 else 0 end)
                  / count(*), 0) as one_filer_pct
     from 'mart_custom_tags.parquet'`,
  );

  const conf = await query(
    `select confidence, count(*) as n from 'mart_financials.parquet'
     group by 1 order by n desc`,
  );
  const total = conf.reduce((a, r) => a + Number(r.n), 0);
  const by = Object.fromEntries(conf.map((r) => [r.confidence, Number(r.n)]));

  // The concepts shown are whichever carry the most published values, so the hero
  // describes the data rather than a list someone typed a year ago.
  CONCEPTS = (
    await query(
      `select concept, count(*) as n from 'mart_financials.parquet'
       where concept is not null group by 1 order by n desc limit 3`,
    )
  ).map((r) => r.concept);

  RESOLVE = await query(
    `select source_tag, concept,
            count(distinct ticker) as filers, count(*) as n,
            any_value(confidence) as confidence
     from 'mart_financials.parquet'
     where source_tag is not null and source_tag not like 'derived:%'
       and concept in (?, ?, ?)
     group by 1, 2 order by n desc limit 7`,
    CONCEPTS,
  );

  buildHero();
  runHero({
    tags: Number(tags.distinct_tags),
    pct: Number(tags.one_filer_pct),
    total,
    conf: by,
    order: conf.map((r) => r.confidence),
    publishedAt: index.published_at,
  });
}

function buildHero() {
  const tagsEl = $("tags");
  const cpsEl = $("cps");
  tagsEl.innerHTML = "";
  cpsEl.innerHTML = "";

  RESOLVE.forEach((r, n) => {
    const li = document.createElement("li");
    li.className = { high: "c-high", medium: "c-med", derived: "c-drv" }[r.confidence] || "c-med";
    li.id = "row" + n;
    const filers = Number(r.filers);
    li.innerHTML =
      `<span class="t">${r.source_tag}</span>` +
      `<span class="co">${filers} ${filers === 1 ? "filer" : "filers"}</span>`;
    li.addEventListener("mouseenter", () => pulse(n));
    tagsEl.appendChild(li);
  });

  CONCEPTS.forEach((c, n) => {
    const li = document.createElement("li");
    li.id = "cp" + n;
    li.innerHTML =
      `<span class="nm">${c.replace(/_/g, " ")}</span>` +
      `<span class="v"><b id="kn${n}">0</b><span>values</span></span>`;
    cpsEl.appendChild(li);
  });
  relayout();
}

function wires() {
  const bench = $("bench");
  const svg = $("svg");
  if (!bench.clientWidth || !RESOLVE.length) return;
  svg.innerHTML = "";
  const bb = bench.getBoundingClientRect();
  RESOLVE.forEach((r, n) => {
    const row = $("row" + n);
    const cp = $("cp" + CONCEPTS.indexOf(r.concept));
    if (!row || !cp) return;
    const a = row.getBoundingClientRect();
    const c = cp.getBoundingClientRect();
    const x1 = a.right - bb.left - 3;
    const y1 = a.top + a.height / 2 - bb.top;
    const x2 = c.left - bb.left;
    const y2 = c.top + c.height / 2 - bb.top;
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", `M${x1},${y1} C${x1 + 58},${y1} ${x2 - 58},${y2} ${x2},${y2}`);
    p.setAttribute("class", "wire");
    p.id = "w" + n;
    if (settled[n]) p.classList.add("lit");
    svg.appendChild(p);
  });
}

function pulse(n) {
  const w = $("w" + n);
  if (!w || R) return;
  const d = document.createElementNS(NS, "circle");
  d.setAttribute("r", "3.5");
  d.setAttribute("class", "pulse");
  $("svg").appendChild(d);
  const L = w.getTotalLength();
  let t0 = null;
  requestAnimationFrame(function step(ts) {
    if (t0 === null) t0 = ts;
    const k = Math.min((ts - t0) / 1150, 1);
    const e = 1 - Math.pow(1 - k, 2.2);
    const pt = w.getPointAtLength(L * e);
    d.setAttribute("cx", pt.x);
    d.setAttribute("cy", pt.y);
    d.setAttribute("opacity", k < 0.18 ? k / 0.18 : k > 0.82 ? (1 - k) / 0.18 : 1);
    if (k < 1) requestAnimationFrame(step);
    else d.remove();
  });
}

function count(el, to, ms, suffix = "") {
  if (!el) return;
  if (R) {
    el.textContent = fmt.format(to) + suffix;
    return;
  }
  const from = parseInt(String(el.textContent).replace(/[^0-9-]/g, ""), 10) || 0;
  let t0 = null;
  requestAnimationFrame(function step(ts) {
    if (t0 === null) t0 = ts;
    const k = Math.min((ts - t0) / ms, 1);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt.format(Math.round(from + (to - from) * e)) + suffix;
    if (k < 1) requestAnimationFrame(step);
  });
}

// The load sequence is the animation: each row lands as its result is read, a pulse
// travels the wire, and the concept's running total goes up. The page has nothing to
// show before the data arrives, so the wait is the thing worth watching.
function runHero(d) {
  timers.forEach(clearTimeout);
  timers = [];
  count($("hc"), d.tags, 1500);

  const share = $("hs");
  if (R) share.textContent = d.pct + "%";
  else {
    let t0 = null;
    requestAnimationFrame(function step(ts) {
      if (t0 === null) t0 = ts;
      const k = Math.min((ts - t0) / 1500, 1);
      share.textContent = Math.round(d.pct * (1 - Math.pow(1 - k, 3))) + "%";
      if (k < 1) requestAnimationFrame(step);
    });
  }

  const totals = CONCEPTS.map(() => 0);
  let t = R ? 0 : 500;
  RESOLVE.forEach((r, n) => {
    const delay = R ? 0 : t;
    t += 280 + (n % 3) * 60;
    timers.push(
      setTimeout(() => {
        $("row" + n).classList.add("in");
        pulse(n);
        timers.push(
          setTimeout(() => {
            $("row" + n).classList.add("on");
            settled[n] = 1;
            const w = $("w" + n);
            if (w) w.classList.add("lit");
            const ci = CONCEPTS.indexOf(r.concept);
            const cp = $("cp" + ci);
            if (cp) cp.classList.add("on");
            totals[ci] += Number(r.n);
            count($("kn" + ci), totals[ci], 750);
          }, R ? 0 : 920),
        );
      }, delay),
    );
  });

  timers.push(
    setTimeout(
      () => {
        $("pip").classList.add("ok");
        $("stat").textContent =
          `${fmt.format(d.total)} values, published ${d.publishedAt.slice(0, 10)}`;

        const slots = ["high", "derived", "medium"];
        const bar = $("pb");
        slots.forEach((k, i) => {
          const el = bar.children[i];
          if (el) el.style.width = ((d.conf[k] || 0) / d.total) * 100 + "%";
        });
        count($("ttl"), d.total, 900);
        count($("s0"), d.conf.high || 0, 900);
        count($("s1"), d.conf.derived || 0, 900);
        count($("s2"), d.conf.medium || 0, 900);
        $("s3").textContent = fmt.format(d.conf.contradicted || d.conf.low || 0);
      },
      R ? 0 : t + 820,
    ),
  );
}

// ---------------------------------------------------------------- tables

const pill = (c) => `<span class="pill ${c}">${c}</span>`;
const td = (v, cls) => `<td${cls ? ` class="${cls}"` : ""}>${v}</td>`;

function rows(tbodyId, data, render) {
  const body = document.querySelector(`#${tbodyId} tbody`);
  body.innerHTML = data.length
    ? data.map(render).join("")
    : `<tr><td colspan="9" class="muted">Nothing matched.</td></tr>`;
}

async function fillPickers() {
  const concepts = await query(
    `select distinct concept from 'mart_financials.parquet'
     where concept is not null order by concept`,
  );
  $("c1").innerHTML = concepts
    .map((r) => `<option${r.concept === "revenue" ? " selected" : ""}>${r.concept}</option>`)
    .join("");

  // The newest year exists for only the one or two filers whose fiscal year has
  // already closed, so defaulting to it shows an almost empty table. Default to the
  // most recent year that most filers actually reach.
  const years = await query(
    `select calendar_year_equivalent as y, count(distinct ticker) as filers
     from 'mart_financials.parquet'
     where period_kind = 'annual' and calendar_year_equivalent is not null
     group by 1 order by y desc limit 14`,
  );
  const best = Math.max(...years.map((r) => Number(r.filers)));
  const fullest = years.find((r) => Number(r.filers) >= best * 0.6) || years[0];
  $("c2").innerHTML = years
    .map((r) => `<option${r.y === fullest.y ? " selected" : ""}>${r.y}</option>`)
    .join("");

  const tickers = await query(
    `select distinct ticker from 'mart_financials.parquet' order by ticker`,
  );
  $("c3").innerHTML = tickers.map((r) => `<option>${r.ticker}</option>`).join("");

  $("c1").onchange = showCompare;
  $("c2").onchange = showCompare;
  $("c3").onchange = showCompany;
}

async function showCompare() {
  const concept = $("c1").value;
  const year = Number($("c2").value);
  const data = await query(
    `select ticker, fiscal_year, value / 1e6 as m, source_tag, confidence
     from 'mart_financials.parquet'
     where period_kind = 'annual' and concept = ? and calendar_year_equivalent = ?
     order by value desc nulls last`,
    [concept, year],
  );
  $("th1").textContent = concept.replace(/_/g, " ") + ", $m";
  rows("t1", data, (r) =>
    "<tr>" +
    td(r.ticker, "tk") +
    td(r.fiscal_year, "yr") +
    td(money(r.m), "num") +
    td(r.source_tag || "", "tg") +
    td(pill(r.confidence)) +
    "</tr>");
  sparklines(concept);
}

async function sparklines(concept) {
  const data = await query(
    `select ticker, calendar_year_equivalent as y, value
     from 'mart_financials.parquet'
     where period_kind = 'annual' and concept = ? and value is not null
     order by ticker, y`,
    [concept],
  );
  const byTicker = new Map();
  for (const r of data) {
    if (!byTicker.has(r.ticker)) byTicker.set(r.ticker, []);
    byTicker.get(r.ticker).push(Number(r.value));
  }
  const spk = $("spk");
  spk.innerHTML = "";
  for (const [ticker, series] of byTicker) {
    if (series.length < 2) continue;
    const lo = Math.min(...series);
    const hi = Math.max(...series);
    const span = hi - lo || 1;
    const pts = series.map((v, i) => [
      (i / (series.length - 1)) * 100,
      28 - ((v - lo) / span) * 24,
    ]);
    const d = document.createElement("div");
    d.className = "c";
    d.innerHTML =
      `<div class="r"><span class="t">${ticker}</span>` +
      `<span class="v">${money(series[series.length - 1] / 1e6)}M</span></div>` +
      `<svg viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true"><path d="M` +
      pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" L") +
      `"/></svg>`;
    spk.appendChild(d);
  }
  requestAnimationFrame(() =>
    spk.querySelectorAll("path").forEach((p) => p.style.setProperty("--L", p.getTotalLength())),
  );
  spk.classList.add("go");
}

async function showCompany() {
  const ticker = $("c3").value;
  const data = await query(
    `select fiscal_year, concept, value / 1e6 as m, source_tag, confidence
     from 'mart_financials.parquet'
     where ticker = ? and period_kind = 'annual'
     order by fiscal_year desc, statement, concept`,
    [ticker],
  );
  rows("t2", data, (r) =>
    "<tr>" +
    td(r.fiscal_year, "yr") +
    td(r.concept.replace(/_/g, " ")) +
    td(money(r.m), "num") +
    td(r.source_tag || "", "tg") +
    td(pill(r.confidence)) +
    "</tr>");
  timeline(ticker);
}

// A filer changing which tag it uses mid history is the problem this project exists
// for, so it gets drawn rather than described: one band per concept, split wherever
// the tag changed.
async function timeline(ticker) {
  const data = await query(
    `select concept, calendar_year_equivalent as y, any_value(source_tag) as tag,
            any_value(confidence) as confidence
     from 'mart_financials.parquet'
     where ticker = ? and period_kind = 'annual' and source_tag is not null
     group by 1, 2 order by 1, 2`,
    [ticker],
  );
  const tl = $("tl");
  if (!data.length) {
    tl.innerHTML = `<div class="empty">No annual values carry a source tag for ${ticker}.</div>`;
    return;
  }
  const years = [...new Set(data.map((r) => Number(r.y)))].sort((a, b) => a - b);
  const y0 = years[0];
  const y1 = years[years.length - 1];
  const span = y1 - y0 + 1;

  const byConcept = new Map();
  for (const r of data) {
    if (!byConcept.has(r.concept)) byConcept.set(r.concept, []);
    byConcept.get(r.concept).push(r);
  }

  const colour = { high: "var(--high)", medium: "var(--med)", derived: "var(--drv)" };
  let html = "";
  for (const [concept, series] of byConcept) {
    const runs = [];
    for (const r of series) {
      const last = runs[runs.length - 1];
      if (last && last.tag === r.tag) last.to = Number(r.y);
      else runs.push({ tag: r.tag, from: Number(r.y), to: Number(r.y), confidence: r.confidence });
    }
    const segs = runs
      .map((run) => {
        const w = ((run.to - run.from + 1) / span) * 100;
        const short = run.tag.replace(/^[a-z-]+:/, "");
        return `<i style="flex:0 0 ${w}%;background:${colour[run.confidence] || "var(--med)"}"
                   title="${run.tag}, ${run.from} to ${run.to}"><span>${short}</span></i>`;
      })
      .join("");
    html += `<div class="r"><div class="n">${concept.replace(/_/g, " ")}</div>
             <div class="segs">${segs}</div></div>`;
  }
  html += `<div class="axis"><div></div><div class="y"><span>${y0}</span>
           <span>${Math.round((y0 + y1) / 2)}</span><span>${y1}</span></div></div>`;
  tl.innerHTML = html;
  tl.querySelectorAll(".segs i").forEach((el, i) => {
    el.style.transitionDelay = (R ? 0 : i * 110) + "ms";
  });
  requestAnimationFrame(() => tl.classList.add("go"));
}

// The confidence bar says how much needed judgement. It cannot say which. This does,
// and it has a real empty state, because nothing flagged is the best outcome rather
// than a missing section.
async function showDistrust() {
  const [{ n: annual }] = await query(
    `select count(*) as n from 'mart_confidence_report.parquet'
     where trust = 'check' and period_kind = 'annual'`,
  );
  const [{ n: all }] = await query(
    `select count(*) as n from 'mart_confidence_report.parquet' where trust = 'check'`,
  );
  const flagged = Number(annual);

  if (flagged === 0) {
    $("dh").textContent = "Nothing is currently flagged for review";
    $("dwrap").innerHTML =
      `<div class="empty">Every annual statement passed its identity checks on this
       publish. That is the best outcome, not a missing section.</div>`;
    $("dm").textContent = "";
    return;
  }

  $("dh").textContent =
    `The ${flagged} annual statement${flagged === 1 ? "" : "s"} worth your own look`;

  const data = await query(
    `select ticker, fiscal_year, statement,
            medium_lines, derived_lines, incoherent_lines, contradicted_lines,
            identity_gap, identity_holds
     from 'mart_confidence_report.parquet'
     where trust = 'check' and period_kind = 'annual'
     order by abs(coalesce(identity_gap, 0)) desc
     limit 12`,
  );

  rows("t3", data, (r) => {
    let why;
    let signal;
    if (Number(r.contradicted_lines) > 0) {
      why = "The filing's own calculation arcs disagree with a value on this statement.";
      signal = "contradicted";
    } else if (!r.identity_holds && r.identity_gap !== null) {
      why = `The accounting identity is off by ${money(Number(r.identity_gap) / 1e6)}M on this statement.`;
      signal = "medium";
    } else if (Number(r.incoherent_lines) > 0) {
      why = "Carries a line newer than the filing it was read from, so it cannot claim to be as reported.";
      signal = "medium";
    } else if (Number(r.derived_lines) > 0) {
      why = `${r.derived_lines} line(s) were computed because the company never tagged them.`;
      signal = "derived";
    } else {
      why = `${r.medium_lines} line(s) needed a judgement call on which tag to read.`;
      signal = "medium";
    }
    return (
      "<tr>" +
      td(r.ticker, "tk") +
      td(r.fiscal_year, "yr") +
      td(String(r.statement).replace(/_/g, " ")) +
      td(why, "wrap-cell") +
      td(pill(signal)) +
      "</tr>"
    );
  });
  document.querySelectorAll("#t3 tbody tr").forEach((tr, i) => {
    tr.style.transitionDelay = (R ? 0 : i * 70) + "ms";
  });
  $("t3").classList.add("go");
  $("dm").textContent =
    `${Math.max(flagged - data.length, 0)} more, and ${fmt.format(Number(all))} ` +
    `across every period kind, not just annual.`;
}

async function showBuild() {
  const [m] = await query(
    `select count(*) as values_published,
            count(distinct ticker) as filers,
            count(distinct concept) as concepts,
            count(distinct source_tag) as tags
     from 'mart_financials.parquet'`,
  );
  rows("t5", [m], (r) =>
    `<tr>${td("Companies")}${td(fmt.format(Number(r.filers)), "num")}${td("Software and SaaS filers, defined in config rather than in code", "wrap-cell")}</tr>` +
    `<tr>${td("Canonical concepts")}${td(fmt.format(Number(r.concepts)), "num")}${td("What every filer's own tags are reconciled onto", "wrap-cell")}</tr>` +
    `<tr>${td("Distinct source tags")}${td(fmt.format(Number(r.tags)), "num")}${td("The raw XBRL tags behind those concepts", "wrap-cell")}</tr>` +
    `<tr>${td("Values published")}${td(fmt.format(Number(r.values_published)), "num")}${td("Every one carries the tag it came from and how much to trust it", "wrap-cell")}</tr>` +
    `<tr>${td("Running cost")}${td("$0", "num")}${td("Free tiers throughout, scaled to zero, no card on file", "wrap-cell")}</tr>`);
}

// ---------------------------------------------------------------- sql

const SAMPLE = $("sql").value;
$("btn-run").onclick = runSql;
$("btn-reset").onclick = () => {
  $("sql").value = SAMPLE;
};

async function runSql() {
  const sql = $("sql").value.trim().replace(/;\s*$/, "");
  const started = performance.now();
  try {
    const data = await query(sql);
    const ms = Math.round(performance.now() - started);
    if (!data.length) {
      $("so").innerHTML = `<table><tbody><tr><td class="muted">No rows.</td></tr></tbody></table>`;
      $("sm").textContent = `0 rows in ${ms} ms`;
      return;
    }
    const keys = Object.keys(data[0]);
    $("so").innerHTML =
      "<table><thead><tr>" +
      keys.map((k) => `<th>${k}</th>`).join("") +
      "</tr></thead><tbody>" +
      data
        .slice(0, 200)
        .map(
          (row) =>
            "<tr>" +
            keys
              .map((k) => {
                const v = row[k];
                if (v === null || v === undefined) return td('<span class="muted">null</span>');
                // A year is a label, not a quantity, so it must not pick up a
                // thousands separator and become 2,026.
                if (/year|cik|quarter/i.test(k)) return td(String(v), "yr");
                if (typeof v === "bigint" || typeof v === "number")
                  return td(fmt.format(Number(v)), "num");
                return td(String(v));
              })
              .join("") +
            "</tr>",
        )
        .join("") +
      "</tbody></table>";
    $("sm").textContent = `${fmt.format(data.length)} row${data.length === 1 ? "" : "s"} in ${ms} ms`;
  } catch (err) {
    $("so").innerHTML = `<table><tbody><tr><td class="err">${String(err.message || err)}</td></tr></tbody></table>`;
    $("sm").textContent = "";
  }
}

// ---------------------------------------------------------------- chrome

document.querySelectorAll("#tabs button").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll("#tabs button").forEach((x) => {
      x.setAttribute("aria-selected", String(x === b));
    });
    document.querySelectorAll(".panel").forEach((p) => {
      p.classList.toggle("on", p.id === b.dataset.p);
    });
    if (b.dataset.p === "p1") $("spk").classList.add("go");
    if (b.dataset.p === "p2") $("tl").classList.add("go");
    if (b.dataset.p === "p3") $("t3").classList.add("go");
    relayout();
  });
});

function relayout() {
  wires();
}
addEventListener("resize", relayout);
addEventListener("load", relayout);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(relayout);
if (window.ResizeObserver) new ResizeObserver(relayout).observe($("bench"));
setTimeout(relayout, 900);
setTimeout(relayout, 4200);

boot().catch((err) => {
  $("stat").textContent = "could not load the data";
  $("so").innerHTML = `<table><tbody><tr><td class="err">${String(err.message || err)}</td></tr></tbody></table>`;
  console.error(err);
});
