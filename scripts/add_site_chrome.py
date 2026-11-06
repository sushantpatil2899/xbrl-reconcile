"""Give the generated diagram pages the site's header.

Archify emits each diagram as a standalone HTML file that knows nothing about the
site around it: no navigation, its own dark theme, its own title treatment. This
injects the same header the hand written index carries, so the three pages read as
one site and the bar does not move when a reader crosses between them.

Matching matters more than it sounds. The index centres its content in a 1680px
measure, so its brand sits 153px from the left at 1920 wide. A full bleed bar would
put the brand at 30px, and crossing pages would shift it sideways by more than a
hundred pixels, which reads as the page jumping. The injected header therefore uses
the same inner wrapper, the same gutter and the same height.

Runs at publish time against docs/site, never against the generator's output, so
re-running Archify does not have to remember this step. Injection is keyed on a
marker comment, so running it twice is a no-op rather than two headers.
"""

import pathlib
import re
import sys

MARK = "<!--site-chrome-->"

INJECT_SKIP = {"index.html"}  # hand written, carries the header in its own markup

PAGES = [
    ("index.html", "Explore the data", "."),
    ("architecture.html", "Architecture", "architecture.html"),
    ("reconciliation.html", "How a tag is judged", "reconciliation.html"),
]

TITLES = {
    "architecture.html": (
        "The pipeline, end to end",
        "Every component from the SEC's three sources through to the API and this "
        "page. Each box cites the file and the line it was read from.",
    ),
    "reconciliation.html": (
        "How a tag earns its labels",
        "The decision path one raw XBRL tag takes to reach a confidence level and "
        "an evidence verdict, including every branch that sends it to review.",
    ),
}

API = (
    "https://ca-xbrl-reconcile-api.wonderfulwater-66905cf2."
    "northcentralus.azurecontainerapps.io/docs"
)

CSS = """
<style id="site-chrome-css">
  :root{
    --sc-deep:#15201B;
    --sc-on-2:#A6B8AD;
    --sc-high:#3EB183;
    --sc-med:#D9A436;
    --sc-gut:clamp(18px,2.2vw,40px);
  }
  /* the viewer pads its body 32px; the header must still reach both edges */
  body{ padding-top:0 !important; background:#FBFBF9; }
  #site-nav, #site-head{ margin-left:calc(50% - 50vw); margin-right:calc(50% - 50vw); }
  .sc-in{ width:100%; max-width:1680px; margin:0 auto; padding:0 var(--sc-gut); }

  #site-nav{
    position:relative; z-index:2147483000; background:var(--sc-deep);
    border-bottom:1px solid rgba(255,255,255,.09);
    font-family:"Public Sans",ui-sans-serif,system-ui,sans-serif;
  }
  #site-nav .sc-in{ display:flex; align-items:center; gap:4px; height:52px;
    overflow-x:auto; scrollbar-width:none; }
  #site-nav .sc-in::-webkit-scrollbar{ display:none; }
  #site-nav .brand{ font-weight:800; font-size:15px; letter-spacing:-0.015em; color:#fff;
    text-decoration:none; margin-right:20px; white-space:nowrap; }
  #site-nav a.l{ color:var(--sc-on-2); text-decoration:none; font-size:13.5px; font-weight:500;
    padding:6px 13px; border-radius:5px; white-space:nowrap; }
  #site-nav a.l:hover{ color:#fff; background:rgba(255,255,255,.07); }
  #site-nav a.l[aria-current="page"]{ color:#fff; background:rgba(62,177,131,.17);
    font-weight:600; }
  #site-nav .sp{ flex:1 1 auto; }
  #site-nav .api{ color:var(--sc-on-2); text-decoration:none; font-size:12.5px;
    white-space:nowrap; }
  #site-nav .api:hover{ color:#fff; }
  #site-nav .api small{ color:var(--sc-med); }
  #site-nav a:focus-visible{ outline:2px solid var(--sc-high); outline-offset:3px; }

  #site-head{ background:var(--sc-deep); color:#EDF2EE; position:relative; overflow:hidden;
    font-family:"Public Sans",ui-sans-serif,system-ui,sans-serif; }
  #site-head::before{ content:""; position:absolute; inset:0; pointer-events:none; opacity:.5;
    background:
      radial-gradient(60% 90% at 78% 10%, rgba(62,177,131,.14), transparent 62%),
      repeating-linear-gradient(to bottom, rgba(255,255,255,.028) 0 1px, transparent 1px 34px); }
  #site-head .sc-in{ position:relative; z-index:2;
    padding-top:clamp(30px,3.4vw,54px); padding-bottom:clamp(26px,3vw,44px); }
  #site-head h1{ margin:0 0 10px; color:#fff; font-weight:800; letter-spacing:-0.03em;
    line-height:1.07; font-size:clamp(26px,3.2vw,46px); max-width:20ch; }
  #site-head p{ margin:0; color:var(--sc-on-2); font-size:clamp(14.5px,1.05vw,18px);
    line-height:1.6; max-width:62ch; }

  /* The viewer's toolbar is absolute to body at top:32px, which is behind the
     header we just added. --sc-chrome-h is measured at runtime below. */
  body > .toolbar{ top: calc(var(--sc-chrome-h, 150px) + 16px) !important; }

  @media (max-width:560px){ #site-nav .api{ display:none; } }
</style>
<script id="site-chrome-js">
(function () {
  function fit() {
    var nav = document.getElementById('site-nav');
    var head = document.getElementById('site-head');
    if (!nav) return;
    var h = nav.offsetHeight + (head ? head.offsetHeight : 0);
    document.documentElement.style.setProperty('--sc-chrome-h', h + 'px');
  }
  fit();
  addEventListener('resize', fit);
  addEventListener('load', fit);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  setTimeout(fit, 300); setTimeout(fit, 1200);
})();
</script>"""


def chrome(current):
    links = []
    for filename, label, href in PAGES:
        here = ' aria-current="page"' if filename == current else ""
        links.append(f'<a class="l" href="{href}"{here}>{label}</a>')
    title, blurb = TITLES.get(current, ("", ""))
    head = ""
    if title:
        head = (
            '<header id="site-head"><div class="sc-in">'
            f"<h1>{title}</h1><p>{blurb}</p></div></header>"
        )
    return (
        MARK
        + CSS
        + '<nav id="site-nav" aria-label="Site"><div class="sc-in">'
        + '<a class="brand" href=".">xbrl-reconcile</a>'
        + "".join(links)
        + '<span class="sp"></span>'
        + f'<a class="api" href="{API}" target="_blank" rel="noopener">'
        + "API <small>wakes in ~10s</small></a>"
        + "</div></nav>"
        + head
    )


def main(site):
    touched = 0
    for filename, _, _ in PAGES:
        if filename in INJECT_SKIP:
            print(f"  skip   {filename}: hand written, carries the header already")
            continue
        path = site / filename
        if not path.exists():
            print(f"  skip   {filename}: not published")
            continue
        html = path.read_text(encoding="utf-8")
        if MARK in html:
            print(f"  ok     {filename}: already carries the header")
            continue
        if "<body" not in html:
            print(f"  FAIL   {filename}: no body tag to inject after")
            return 1

        # the viewer ships dark; the site's content surface is paper
        html = re.sub(r'(<html[^>]*?)\s+data-theme="[^"]*"', r"\1", html, count=1)
        html = html.replace("<html", '<html data-theme="light"', 1)

        at = html.index(">", html.index("<body")) + 1
        path.write_text(html[:at] + chrome(filename) + html[at:], encoding="utf-8")
        print(f"  added  {filename}")
        touched += 1
    print(f"{touched} page(s) given the site header")
    return 0


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "docs/site")
    raise SystemExit(main(root))
