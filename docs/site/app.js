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
// That is correct whatever the CDN decides to do, which means we do not have to know.

import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm";

const status = document.getElementById("status");
let connection = null;

const fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const fmt2 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

function say(message) {
  status.textContent = message;
}

async function boot() {
  // The index is the version marker, so it must never come from a cache.
  const index = await (await fetch("_index.json", { cache: "no-store" })).json();
  const version = (index.published_at || "0").replace(/[^0-9A-Za-z]/g, "");
  document.getElementById("as-of").textContent = index.published_at;

  say("Downloading the query engine. This happens once, then it is cached.");
  const started = performance.now();

  const bundles = duckdb.getJsDelivrBundles();
  const bundle = await duckdb.selectBundle(bundles);
  const workerUrl = URL.createObjectURL(
    new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }),
  );
  const worker = new Worker(workerUrl);
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(workerUrl);

  // Registered under the plain name, fetched with the version. Queries stay readable
  // and the stable URL keeps working for anyone pointing their own DuckDB at it.
  //
  // The fetch URL must be absolute. DuckDB runs in a worker created from a blob, so
  // a relative path has no page to resolve against and the request fails with
  // "Invalid URL" rather than a 404, which reads like a bug in the query.
  for (const mart of index.marts) {
    await db.registerFileURL(
      `${mart.name}.parquet`,
      new URL(`${mart.name}.parquet?v=${version}`, location.href).href,
      duckdb.DuckDBDataProtocol.HTTP,
      false,
    );
  }

  connection = await db.connect();
  const engineMs = Math.round(performance.now() - started);

  await Promise.all([fillYears(), fillTickers()]);
  await Promise.all([showCompare(), showCompany(), showQuality()]);

  const rows = index.marts.reduce((total, mart) => total + mart.rows, 0);
  const bytes = index.marts.reduce((total, mart) => total + mart.bytes, 0);
  say(
    `Ready in ${engineMs} ms. ${fmt.format(rows)} rows across ${index.marts.length} ` +
      `tables, ${Math.round(bytes / 1024)} KB of Parquet, all queried in this tab.`,
  );
}

async function query(sql, params = []) {
  const prepared = await connection.prepare(sql);
  const result = await prepared.query(...params);
  await prepared.close();
  return result.toArray().map((row) => row.toJSON());
}

// Rendering.

function table(rows, columns) {
  if (!rows.length) return `<p class="empty">Nothing matched.</p>`;
  const keys = columns || Object.keys(rows[0]);
  const head = keys.map((key) => `<th>${key}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${keys.map((key) => `<td>${cell(row[key], key)}</td>`).join("")}</tr>`)
    .join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

const CONFIDENCE = new Set(["high", "medium", "low", "derived"]);

function cell(value, key) {
  if (value === null || value === undefined) return `<span class="null">no value</span>`;
  // A year is a label, not a quantity, so it must not pick up a thousands separator.
  if (key.includes("year") || key.includes("label")) return String(value);
  if (typeof value === "bigint") return fmt.format(value);
  if (typeof value === "number") {
    // Per share figures and margins are small and need their decimals; millions do
    // not. Deciding by magnitude keeps one column readable for both.
    if (key === "margin" || Math.abs(value) < 1000) return fmt2.format(value);
    return fmt.format(value);
  }
  if (CONFIDENCE.has(value)) return `<span class="tag ${value}">${value}</span>`;
  if (value === "contradicted" || value === "check" || value === "missing") {
    return `<span class="tag warn">${value}</span>`;
  }
  // The filer called it a part and its own figures made it the total anyway, so this
  // reads as settled rather than as a caution.
  if (value === "equivalent" || value === "confirmed") {
    return `<span class="tag high">${value}</span>`;
  }
  return String(value);
}

function paint(id, rows, columns) {
  document.getElementById(id).innerHTML = table(rows, columns);
}

// The views.

async function fillYears() {
  const rows = await query(
    `select distinct calendar_year_equivalent as year from 'mart_income_statement.parquet'
     where period_kind = 'annual' and calendar_year_equivalent is not null
     order by year desc`,
  );
  const select = document.getElementById("compare-year");
  select.innerHTML = rows.map((r) => `<option>${r.year}</option>`).join("");
  // Default to the most recent year that most companies have actually filed.
  select.value = rows.length > 1 ? rows[1].year : rows[0].year;
  select.onchange = showCompare;
}

async function fillTickers() {
  const rows = await query(
    `select distinct ticker from 'mart_financials.parquet' order by ticker`,
  );
  const select = document.getElementById("company-ticker");
  select.innerHTML = rows.map((r) => `<option>${r.ticker}</option>`).join("");
  select.value = "CRM";
  select.onchange = showCompany;
}

async function showCompare() {
  const year = Number(document.getElementById("compare-year").value);
  const rows = await query(
    `select ticker,
            fiscal_year as "fiscal label",
            revenue / 1e6 as "revenue ($m)",
            revenue_confidence as "revenue from",
            gross_profit / 1e6 as "gross profit ($m)",
            gross_profit_confidence as "gross profit from",
            round(100.0 * gross_profit / nullif(revenue, 0), 1) as margin
     from 'mart_income_statement.parquet'
     where period_kind = 'annual' and calendar_year_equivalent = ?
     order by revenue desc nulls last`,
    [year],
  );
  paint("compare-table", rows);
}

async function showCompany() {
  const ticker = document.getElementById("company-ticker").value;
  const rows = await query(
    `select fiscal_year as "fiscal year",
            concept,
            case when unit = 'USD' then value / 1e6 else value end as value,
            case when unit = 'USD' then '$m' else unit end as unit,
            confidence,
            source_tag as "tag it came from",
            evidence
     from 'mart_financials.parquet'
     where ticker = ? and period_kind = 'annual'
     order by fiscal_year desc, statement, concept`,
    [ticker],
  );
  paint("company-table", rows);
}

async function showQuality() {
  const trust = await query(
    `select trust, count(*) as statements from 'mart_confidence_report.parquet'
     group by trust order by statements desc`,
  );
  document.getElementById("quality-summary").innerHTML = trust
    .map(
      (row) =>
        `<div class="card"><span class="count">${fmt.format(row.statements)}</span>` +
        `<span class="label">${row.trust}</span></div>`,
    )
    .join("");

  paint(
    "quality-check",
    await query(
      `select ticker, statement, fiscal_year as "fiscal year",
              lines_present as "lines present", lines_expected as "expected",
              ambiguous_lines as ambiguous, identity_holds as "identity holds"
       from 'mart_confidence_report.parquet'
       where trust = 'check'
       order by ticker, fiscal_year limit 25`,
    ),
  );

  paint(
    "quality-gaps",
    await query(
      `select ticker, fiscal_year as "fiscal year", concept, status
       from 'mart_mapping_coverage.parquet'
       where status = 'missing' order by ticker, fiscal_year`,
    ),
  );

  paint(
    "quality-contradicted",
    await query(
      `select ticker, fiscal_year as "fiscal year", period_kind as period, concept,
              value / 1e6 as "value ($m)", evidence,
              source_tag as "tag it came from"
       from 'mart_financials.parquet'
       where evidence in ('contradicted', 'equivalent')
       order by evidence, ticker, fiscal_year limit 25`,
    ),
  );
}

// The query box.

const EXAMPLE = `select ticker, fiscal_year, revenue / 1e6 as revenue_m,
       gross_profit / 1e6 as gross_profit_m, gross_profit_confidence
from 'mart_income_statement.parquet'
where period_kind = 'annual' and calendar_year_equivalent = 2025
order by revenue desc;`;

async function runSql() {
  const sql = document.getElementById("sql-input").value;
  const target = document.getElementById("sql-result");
  try {
    const result = await connection.query(sql);
    const rows = result.toArray().map((row) => row.toJSON());
    target.innerHTML = table(rows.slice(0, 200));
    if (rows.length > 200) {
      target.insertAdjacentHTML("beforeend", `<p class="aside">First 200 of ${rows.length}.</p>`);
    }
  } catch (error) {
    target.innerHTML = `<p class="error">${error}</p>`;
  }
}

// Tabs.

for (const button of document.querySelectorAll("#tabs button")) {
  button.onclick = () => {
    for (const other of document.querySelectorAll("#tabs button")) {
      other.classList.toggle("active", other === button);
    }
    for (const view of document.querySelectorAll(".view")) {
      view.classList.toggle("active", view.id === button.dataset.view);
    }
  };
}

document.getElementById("sql-input").value = EXAMPLE;
document.getElementById("sql-run").onclick = runSql;

boot().catch((error) => {
  say(`Could not start: ${error}`);
  console.error(error);
});
