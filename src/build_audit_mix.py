#!/usr/bin/env python3
"""The audit mix, 2020->present: performance audits fell four-fold while financial held flat.

  python3 src/build_audit_mix.py            # write viz/audit-mix.html
  python3 src/build_audit_mix.py --check    # CI: fail if the committed page is stale

Closes oregon-audits#4, and per that issue this lives in the corpus's OWN site build —
"not an artifact; this belongs next to the documents it summarises." Every number is a
count of committed, served reports; every year expands to the exact reports behind it.

CHART DISCIPLINE (corpus_toolkit.viz's rules, which are safety mechanisms):
  * Four charted series in fixed slot order; performance takes slot 1 because it IS the
    story. The three attestation-adjacent types (hotline, ACFR, statewide single audit)
    and the 4 reports with no recorded type are NOT charted — seven lines is noise —
    but they appear in the table view, so nothing is hidden, only de-emphasized.
  * The two sub-3:1 light slots (aqua, yellow) get their relief via the table view and
    the tooltip, per the relief rule.
  * 2026 is PARTIAL (ingested through July) and is drawn hollow with a dashed lead-in
    and an explicit annotation — without that the decline reads steeper than it is.
  * No causal language anywhere: the chart says what the mix did, not why.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import yaml

from corpus_toolkit import viz

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "viz" / "audit-mix.html"
REPO_URL = "https://github.com/OregonAI/oregon-audits"

# Charted series, slot order = story order. Everything else is table-only.
CHARTED = ("performance", "financial", "informational", "information technology")
PARTIAL_YEAR = "2026"

W, H, PAD_L, PAD_R, PAD_T, PAD_B = 880, 360, 44, 150, 18, 34


def collect():
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in sorted((ROOT / "reports").glob("*.md")):
        fm = yaml.safe_load(p.read_text(encoding="utf-8").split("---", 2)[1])
        year = (fm.get("report_date") or "")[:4]
        if not year:
            continue
        per[year][fm.get("audit_type") or "none recorded"].append(fm["id"])
    return {y: {t: sorted(ids) for t, ids in ts.items()} for y, ts in sorted(per.items())}


def render(data: dict) -> str:
    years = sorted(data)
    all_types = sorted({t for ts in data.values() for t in ts},
                      key=lambda t: (t not in CHARTED, CHARTED.index(t) if t in CHARTED else 0, t))
    ymax = max(len(ids) for ts in data.values() for ids in ts.values())
    ytop = ((ymax // 5) + 1) * 5
    xw = (W - PAD_L - PAD_R) / (len(years) - 1)

    def x(i): return PAD_L + i * xw
    def y(v): return PAD_T + (H - PAD_T - PAD_B) * (1 - v / ytop)

    svg = [f'<svg viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="Audit reports per year by type, {years[0]} to {years[-1]}">']
    for tick in range(0, ytop + 1, 5):
        svg.append(f'<line x1="{PAD_L}" y1="{y(tick):.1f}" x2="{W-PAD_R}" y2="{y(tick):.1f}" '
                   f'stroke="var(--grid)" stroke-width="1"/>')
        svg.append(f'<text x="{PAD_L-8}" y="{y(tick)+4:.1f}" text-anchor="end">{tick}</text>')
    for i, yr in enumerate(years):
        label = f"{yr}*" if yr == PARTIAL_YEAR else yr
        svg.append(f'<text x="{x(i):.1f}" y="{H-10}" text-anchor="middle">{label}</text>')
    svg.append(f'<line x1="{PAD_L}" y1="{y(0):.1f}" x2="{W-PAD_R}" y2="{y(0):.1f}" '
               f'stroke="var(--axis)" stroke-width="1"/>')

    for si, t in enumerate(CHARTED, 1):
        pts = [(x(i), y(len(data[yr].get(t, [])))) for i, yr in enumerate(years)]
        solid = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts[:-1])
        svg.append(f'<polyline points="{solid}" fill="none" stroke="var(--s{si})" '
                   f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        # the lead-in to the partial year is dashed: a different epistemic status,
        # drawn differently
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        svg.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                   f'stroke="var(--s{si})" stroke-width="2" stroke-dasharray="4 4"/>')
        for i, (px, py) in enumerate(pts):
            partial = years[i] == PARTIAL_YEAR
            fill = "var(--surface)" if partial else f"var(--s{si})"
            svg.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{fill}" '
                       f'stroke="{"var(--s%d)" % si if partial else "var(--surface)"}" '
                       f'stroke-width="2"/>')
        # selective end labels: the two story series only
        if t in ("performance", "financial"):
            n0, n1 = len(data[years[0]].get(t, [])), len(data[years[-2]].get(t, []))
            svg.append(f'<text class="val" x="{W-PAD_R+10}" y="{pts[-2][1]+4:.1f}">'
                       f'{t} {n0}→{n1}</text>')
    svg.append(f'<text x="{x(len(years)-1):.1f}" y="{PAD_T+2}" text-anchor="middle" '
               f'font-size="11">* through July</text>')
    svg.append("</svg>")

    legend = "".join(
        f'<span><span class="chip" style="background:var(--s{i})"></span>{t}</span>'
        for i, t in enumerate(CHARTED, 1))

    head = "<tr><th>type</th>" + "".join(
        f'<th class="num">{yr}{"*" if yr == PARTIAL_YEAR else ""}</th>' for yr in years) + \
        '<th class="num">total</th></tr>'
    rows = []
    for t in all_types:
        cells = "".join(f'<td class="num">{len(data[yr].get(t, [])) or "—"}</td>'
                        for yr in years)
        tot = sum(len(data[yr].get(t, [])) for yr in years)
        mark = "" if t in CHARTED else " <small>(table only)</small>"
        rows.append(f"<tr><td>{t}{mark}</td>{cells}<td class='num'>{tot}</td></tr>")
    table = f'<table><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table>'

    details = []
    for yr in years:
        links = []
        for t in all_types:
            for rid in data[yr].get(t, []):
                links.append(f'<a href="{REPO_URL}/blob/main/reports/{rid}.md">{rid}</a>')
        details.append(f"<details><summary>{yr}: {len(links)} report(s)</summary>"
                       f"<p>{' · '.join(links)}</p></details>")

    payload = {"years": years,
               "series": {t: [len(data[yr].get(t, [])) for yr in years] for t in CHARTED},
               "x0": PAD_L, "xw": xw, "partial": PARTIAL_YEAR}

    script = """
var D = __DATA__;
var svgEl = document.querySelector('svg'), tip = document.getElementById('tip');
var cross = document.createElementNS('http://www.w3.org/2000/svg','line');
cross.setAttribute('stroke','var(--axis)'); cross.setAttribute('stroke-width','1');
cross.setAttribute('y1','%(pt)d'); cross.setAttribute('y2','%(yb)d');
cross.style.display='none'; svgEl.appendChild(cross);
svgEl.addEventListener('pointermove', function(ev){
  var r = svgEl.getBoundingClientRect(), sx = %(w)d / r.width;
  var vx = (ev.clientX - r.left) * sx;
  var i = Math.round((vx - D.x0) / D.xw);
  if (i < 0 || i >= D.years.length) { cross.style.display='none'; tip.style.display='none'; return; }
  var cx = D.x0 + i * D.xw;
  cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.style.display='';
  tip.textContent = '';
  var h = document.createElement('div'); h.style.fontWeight = '600';
  h.textContent = D.years[i] + (D.years[i] === D.partial ? ' (partial, through July)' : '');
  tip.appendChild(h);
  Object.keys(D.series).forEach(function(name, si){
    var row = document.createElement('div');
    var key = document.createElement('span');
    key.style.cssText = 'display:inline-block;width:14px;height:2px;margin:0 6px 3px 0;'
      + 'background:var(--s' + (si + 1) + ')';
    var val = document.createElement('strong');
    val.textContent = D.series[name][i] + ' ';
    row.appendChild(key); row.appendChild(val);
    row.appendChild(document.createTextNode(name));
    tip.appendChild(row);
  });
  tip.style.display = 'block';
  tip.style.left = Math.min(ev.clientX + 14, innerWidth - 340) + 'px';
  tip.style.top = (ev.clientY + 14) + 'px';
});
svgEl.addEventListener('pointerleave', function(){
  cross.style.display='none'; tip.style.display='none'; });
""" % {"pt": PAD_T, "yb": H - PAD_B, "w": W}
    script = script.replace("__DATA__", json.dumps(payload))

    n_total = sum(len(ids) for ts in data.values() for ids in ts.values())
    perf0 = len(data[years[0]].get("performance", []))
    perf1 = len(data["2025"].get("performance", []))
    body = (f'<div class="panel">{svg_join(svg)}'
            f'<div class="legend">{legend}</div></div>'
            f'<div class="panel"><h2 style="font-size:14px;margin:0 0 8px">All {n_total} '
            f'reports by type and year</h2>{table}</div>'
            f'<div class="panel"><h2 style="font-size:14px;margin:0 0 8px">The reports '
            f'behind each point</h2>{"".join(details)}</div>')

    caveats = (
        f"<p><b>{PARTIAL_YEAR} is partial</b> — reports ingested through July; its points "
        f"are drawn hollow with a dashed lead-in and belong in no trend claim. "
        f"<b>audit_type is the Audits Division's own taxonomy</b>, taken from each "
        f"report's cover; 4 of {n_total} reports record no type and are counted in the "
        f"table as “none recorded”, never charted. Three further types (hotline, annual "
        f"comprehensive financial report, statewide single audit) are table-only to keep "
        f"the chart readable — nothing is omitted from the table. <b>This chart states "
        f"what the mix did, not why</b>: a change in audit mix has many possible causes "
        f"and this corpus records none of them.</p>")

    lede = (f"Across the five complete years {years[0]}–2025, financial audits held "
            f"roughly flat while performance audits — the type that asks whether a "
            f"program achieved its purpose, and the type that produces findings and "
            f"recommendations — fell from {perf0} to {perf1} per year. A financial "
            f"audit attests that the books balance; the mix shifted toward attestation.")

    return viz.chart_page(
        title="Oregon's audit mix: performance audits fell four-fold; financial held flat",
        eyebrow="oregon-audits · Secretary of State Audits Division reports, mirrored",
        lede_html=lede, body_html=body, caveats_html=caveats,
        sources=[{"label": f"the {n_total} mirrored reports (frontmatter: audit_type, "
                           f"report_date)", "url": f"{REPO_URL}/tree/main/reports"},
                 {"label": "SoS Audits Division", "url": "https://sos.oregon.gov/audits/"}],
        generated="from the committed corpus at build time", script=script)


def svg_join(parts):  # keeps render() readable
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    html = render(collect())
    if args.check:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != html:
            print(f"{OUT.relative_to(ROOT)} is stale — run: python3 src/build_audit_mix.py",
                  file=sys.stderr)
            return 1
        print(f"{OUT.relative_to(ROOT)} is current.")
        return 0
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
