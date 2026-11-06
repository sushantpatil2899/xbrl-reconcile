# The query page, redesigned

Status: proposed, not built. Written 2026-11-06.

## Why

The page works and looks like nothing. It opens on the word "loading" and a grey
box announcing that DuckDB is starting, which is the least interesting true fact
about it. Everything below that is a table.

That costs more than looks. The people who will open this link are recruiters,
hiring managers and people from a finance background. None of them will write
SQL, none will read a paragraph to find out why the problem is hard, and all
three decide whether to keep reading in about eight seconds. The current page
spends those eight seconds on infrastructure status.

## Goals

- A visitor understands the problem the project solves before reading a sentence.
- Every number on screen says how much to trust it, which is the project's actual
  claim.
- It still works as a tool: the SQL tab and the twelve marts stay exactly as they
  are.

## Non-goals

- Not a marketing site. No stock photography, no testimonials, no feature grid.
- Not a rewrite of the data layer. `app.js` keeps its DuckDB WASM boot, its
  `_index.json` cache keying and its range-request behaviour untouched.
- No framework. It stays three static files that GitHub Pages serves.

## Anti-goals

Things that would make this a failure even if it technically worked.

- **Looking generated.** This is the one the client raised by name. See the tells
  section; it is a checklist, not a sentiment.
- **Motion as decoration.** Anything that moves must carry information. If a
  reader learns nothing from a movement, it is removed.
- **Overstating the data.** The page's credibility rests on publishing its own
  weak spots. No visual may make a medium-confidence number look high.

## Constraints

- Zero cost, no server, no build step. Fonts self-hosted or from Google Fonts;
  everything else inline.
- Must stay fast on the first load, which already carries a WASM engine.
- Light and dark, keyboard focus, reduced motion, readable at 390px.

## Colour

Grounded in greenbar ledger paper: the banded continuous-feed stock that
financial printouts have been produced on for decades. A finance reader
recognises it immediately, and no language model reaches for it by default.

| Token | Light | Role |
|---|---|---|
| `--paper` | `#FCFCFB` | the sheet |
| `--band` | `#E8EEE5` | the ledger band, carries data rows |
| `--rule` | `#C9D3C6` | ruled line |
| `--ink` | `#1B2621` | text |
| `--ink-2` | `#4A574F` | secondary text |

Status colours, which are the only colours allowed to carry meaning:

| State | Light | Dark |
|---|---|---|
| high | `#13794F` | `#2E9A6A` |
| medium | `#B07A06` | `#B9871A` |
| derived | `#2F5FB0` | `#5C87D2` |
| contradicted | `#AE2F27` | `#CF6058` |

**These were computed, not chosen.** Both sets pass the dataviz validator on all
five checks: lightness band, chroma floor, colour-blindness separation between
adjacent pairs, normal-vision separation and 3:1 contrast against their surface.
Two earlier attempts failed, the first on chroma (the green read as grey) and the
second on protanopia separation against the amber, which is why the shipped green
is more saturated than it appears to need. Dark mode gets its own four steps
re-validated against the dark surface; it is never an inverted copy.

Confidence is a status encoding, not categorical identity, so colour never
travels alone: every use is accompanied by its word.

## Type

- **Public Sans** for all prose. It is the US Web Design System typeface that
  federal agencies publish in, and the subject is filings made to a federal
  agency.
- **IBM Plex Mono** for XBRL tags and every figure, because those genuinely are
  machine identifiers and numerals and want tabular alignment.

Emphasis comes from scale and the monospace shift, never from colouring a word.

## The tells being avoided, explicitly

The client rejected the first attempt as looking AI-generated, correctly. It had
five of the known tells at once. None of these may reappear:

1. A near-black background with one bright accent.
2. A single word or number in a headline coloured or gradiented for emphasis.
3. Tracked-out all-caps eyebrow labels above headings.
4. Meta strings joined with middle dots.
5. Monospace applied to every small label regardless of meaning.

Two more to stay clear of, given the subject's gravitational pull: cream
`#F4F1EA` with a high-contrast serif and a terracotta accent, and identical
rounded cards with the same radius and the same soft grey shadow.

## Motion

**The load sequence is the animation, and it runs on the real query.**

The hero does not illustrate the reconciliation, it performs it. The concepts
render first with zero counts. As DuckDB returns rows from
`mart_mapping_evidence`, each source tag appears on its ledger row, a pulse
travels the wire to its canonical concept, the wire lights, and the concept's
count increments. Arrivals are staggered and overlapping, because real results
are. When the last row lands the proportion bar grows and the status line
switches from the query it is running to the publish timestamp.

This replaces the grey "Starting DuckDB in your browser" box entirely. The wait
was always there; it is now the most informative thing on the page instead of an
apology for itself.

After the sequence the page is still. Hovering a row re-fires its pulse, and
motion that answers a click or hover is unrestricted because it shows what
changed.

One ambient exception, on probation: the ledger bands breathe on a nine second
cycle, like paper under a moving light. It is the only motion on the page that
carries no information, which is exactly why it is the one to be suspicious of.
It ships only if the client confirms it after seeing it toggled both ways.

Under `prefers-reduced-motion` every end state renders immediately, with no
pulses and no shimmer, and the page reads identically. This is a hard
requirement, not a courtesy: the hero carries the thesis, so it cannot depend on
animation to make its point.

The shimmer is confirmed: it ships.

### Reveal on scroll

**Each element's one reveal waits until the element is actually on screen.**
Fires once, at 25 percent visible, never again, including on scroll back.

This is a correctness rule before it is an effect. The proportion bar currently
animates whether or not anyone is looking at it, and at phone width it sits below
the fold, so the single moment it has is spent in an empty room. The same applies
to the sparklines and the evidence wall, which are further down still.

What gets a deferred reveal, and what the reveal is:

| Element | Reveal |
|---|---|
| Hero resolve | runs on load, it is above the fold by definition |
| Proportion bar | segments grow, counters run |
| Sparkline strip | each line draws left to right, the direction it is read |
| Flagged rows | rows appear in sequence, 70ms apart |

Explicitly refused, because each is a known tell or an annoyance: fade-and-slide
on every section, parallax, pinned scrollytelling, a scroll progress bar, and
anything that re-animates when scrolled past a second time. A generic fade-up
makes every section feel equally important, which is the opposite of what this
page needs to do.

Under reduced motion all of it is simply already there.

## Layout

Left-aligned throughout, one column of varying measure, prose capped near 58
characters. The ledger banding is the structural device and should align to real
data rows wherever rows exist, rather than running behind prose.

```
+--------------------------------------------------+
| xbrl-reconcile          28 filers, queried here   |
|                                                   |
| 976 invented tags, and 82% belong to              |
| one company alone.                                |
|                                                   |
| [lede, 58ch]                                      |
|                                                   |
| WDAY:OperatingExpenses ----\                      |
| CRM:Revenues -------------->  operating expenses  |
| SPLK:RevenueNet ----------->  revenue             |
| CRWD:ProfitLoss ----------->  net income          |
|                                                   |
| 21,121 high | 3,799 derived | 1,805 med | 0 contra|
+--------------------------------------------------+
| Compare 28 | One company | What to distrust | SQL |
+--------------------------------------------------+
```

## The four tabs

They keep their jobs and their queries. What changes is that each gains one
visual that answers its question faster than its table does.

**Compare 28.** Keeps the table. Adds a small multiple above it: one sparkline
per company for the selected concept, so the shape of 28 companies is visible
before any row is read. Confidence shown per cell as today.

**One company.** Keeps the value-and-tag table. Adds a tag timeline: a horizontal
band per concept across fiscal years, segmented where the company changed which
tag it used. This makes the project's premise legible for one company at a glance,
since a company switching tags mid-history is exactly the problem.

**What to distrust.** Named rows, not a picture. The client killed the evidence
wall here and was right to: it coloured 26,725 cells by confidence, which is the
exact encoding the proportion bar directly above it already carried. Two pictures
of one fact, and the bar wins on every count.

What replaces it is the thing the bar structurally cannot say. The bar reports
that 6.8 percent needed judgement; it cannot report *which*. This section names
the company, the fiscal year, the concept and the reason each statement is
flagged, sorted by how much the number moves if the call is wrong, so a reader can
open the filing and check us. That is a different and harder claim, which is why
it earns a section rather than repeating one.

**Ask it yourself.** Unchanged apart from type and palette. It is already the
right thing.

## Charts

Per the dataviz procedure: form first, colour last, validator run before
shipping. Sparklines are 2px lines with no axis and one direct label; the
evidence wall is a cell grid with a 2px surface gap; the tally is a stat row, not
a chart. Every chart gets a hover layer, because an HTML chart that cannot be
interrogated is a picture of a chart. No dual axes anywhere.

## Quality floor

- Visible keyboard focus on every control, including the tab strip.
- The hero's meaning survives with motion disabled and with CSS backgrounds off.
- 390px width with no horizontal scroll.
- Colour never the sole carrier of meaning; every status has its word beside it.
- The page must not regress first-paint: fonts load with `display=swap` and the
  hero renders before DuckDB finishes booting.

## Left to the builder

- Exact band pitch and where banding stops behind prose.
- Sparkline dimensions and whether Compare shows all 16 concepts or the selected
  one.
- Whether the tag timeline reads better as segments or as a step line.
- Dark-mode paper and band values, which need the same validator treatment the
  status colours got.

## Density

The first pass put the confidence tally in four equal bordered boxes. That is the
SaaS-card tell: identical containers, one radius on everything, mostly air. It is
replaced by a single proportional bar with an inline key, which occupies less than
half the height and shows something four separate numbers could not, namely that
high confidence dominates at 79 percent.

The general rule for this page: a box has to earn itself. Prefer a rule, a band or
alignment over a border, and never give two things the same container just because
they are the same kind of thing.

## Colour, second pass

Confidence no longer lives only in a legend square. Every tag row carries a two
pixel rule down its left edge in its confidence colour, so the judgement is
present on every line being judged. The concept rows take the same rule in green
once they have been reconciled against. Red still appears exactly once, against
the contradicted zero.

Rows sit on the ledger bands rather than floating above them, which is what the
first pass promised and did not do.


## Redundancy, as a standing rule

The evidence wall was cut because it re-encoded the proportion bar. That failure
is easy to repeat, so the rule is written down: **before adding a visual, say what
question it answers that nothing already on the page answers.** If the answer is
"the same question, more beautifully", it does not ship. The page's credibility
comes from density of distinct information, not from quantity of pictures.
