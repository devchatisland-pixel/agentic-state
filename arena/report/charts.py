"""Inline-SVG charts for the results pages: no JavaScript, no library, readable offline, light and dark themes.

Colours are CSS variables defined by the page (--blue, --orange, --violet, --ok, --warn, --bad, --ink, --ink2,
--border); every mark carries a <title>, so hovering shows the exact value, k/n and the 95% interval.
"""
from __future__ import annotations

import html
import math

SERIES = ["var(--blue)", "var(--orange)", "var(--violet)", "var(--ok)", "var(--warn)", "var(--bad)", "var(--ink2)"]
DASH = ["", "6 4", "2 3", "8 3 2 3", "1 3", "10 4", "4 4"]


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def pct(v, d: int = 0) -> str:
    return f"{v:.{d}%}" if _ok(v) else "–"


def legend(items: list[tuple[str, str]], dashed: bool = False) -> str:
    out = []
    for i, (name, color) in enumerate(items):
        if dashed:
            sw = (f'<svg width="22" height="10" aria-hidden="true"><line x1="1" x2="21" y1="5" y2="5" stroke="{color}" '
                  f'stroke-width="2.5" stroke-dasharray="{DASH[i % len(DASH)]}"/></svg>')
        else:
            sw = f'<i style="background:{color}"></i>'
        out.append(f"<span>{sw}{esc(name)}</span>")
    return '<div class="legend">' + "".join(out) + "</div>"


def bars(rows: list[dict], title: str = "", chance: float | None = None, max_v: float = 1.0) -> str:
    """Horizontal bars with 95% whiskers. rows: {label, rate, lo, hi, k, n, color?, note?}."""
    if not rows:
        return '<p class="small">No data.</p>'
    w, left, right, rh = 640, 210, 70, 30
    h = rh * len(rows) + 34
    x = lambda v: left + (w - left - right) * max(0.0, min(v, max_v)) / max_v  # noqa: E731
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    for t in (0, .25, .5, .75, 1):
        if t <= max_v:
            out.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="4" y2="{h - 26}"/>'
                       f'<text class="axis" x="{x(t):.1f}" y="{h - 10}" text-anchor="middle">{t:.0%}</text>')
    if chance is not None:
        out.append(f'<line class="chance" x1="{x(chance):.1f}" x2="{x(chance):.1f}" y1="0" y2="{h - 26}"/>')
    for i, r in enumerate(rows):
        y = 6 + i * rh
        color = r.get("color", SERIES[0])
        lab = esc(r["label"])
        out.append(f'<text class="lab" x="{left - 8}" y="{y + 15}" text-anchor="end">{lab}</text>')
        if _ok(r.get("rate")):
            tip = f'{r["label"]}: {pct(r["rate"], 1)}'
            if r.get("n") is not None:
                tip += f' ({r.get("k", "?")}/{r["n"]})'
            if _ok(r.get("lo")):
                tip += f'; 95% CI {pct(r["lo"])}–{pct(r["hi"])}'
            out.append(f'<rect x="{left}" y="{y + 3}" width="{max(x(r["rate"]) - left, 1.5):.1f}" height="{rh - 10}" '
                       f'rx="3" fill="{color}" opacity=".85"><title>{esc(tip)}</title></rect>')
            if _ok(r.get("lo")):
                out.append(f'<line class="ci" x1="{x(r["lo"]):.1f}" x2="{x(r["hi"]):.1f}" y1="{y + rh / 2 - 2:.1f}" '
                           f'y2="{y + rh / 2 - 2:.1f}"/>')
            n = f' <tspan class="labn">n={r["n"]}</tspan>' if r.get("n") is not None else ""
            out.append(f'<text class="val" x="{w - right + 6}" y="{y + 15}">{pct(r["rate"])}{n}</text>')
        else:
            out.append(f'<text class="labn" x="{left + 4}" y="{y + 15}">no data</text>')
    out.append("</svg>")
    return "".join(out)


def grouped_bars(groups: list[str], series: list[tuple[str, list[dict | None]]], title: str = "",
                 y_label: str = "") -> str:
    """Vertical grouped bars with whiskers. series: [(name, [cell per group: {rate, lo, hi, k, n}])]."""
    if not groups or not series:
        return '<p class="small">No data.</p>'
    w, h, l, r, t, b = 640, 270, 46, 10, 14, 46
    gw = (w - l - r) / len(groups)
    bw = min(46, gw * 0.8 / len(series))
    y = lambda v: t + (h - t - b) * (1 - max(0.0, min(v, 1.0)))  # noqa: E731
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    for v in (0, .25, .5, .75, 1):
        out.append(f'<line class="grid" x1="{l}" x2="{w - r}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text class="axis" x="{l - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{v:.0%}</text>')
    if y_label:
        out.append(f'<text class="axis" x="12" y="{(h - b + t) / 2:.0f}" transform="rotate(-90 12 {(h - b + t) / 2:.0f})" '
                   f'text-anchor="middle">{esc(y_label)}</text>')
    for gi, g in enumerate(groups):
        cx = l + gw * gi + gw / 2
        out.append(f'<text class="axis" x="{cx:.1f}" y="{h - b + 18}" text-anchor="middle">{esc(g)}</text>')
        x0 = cx - bw * len(series) / 2
        for si, (name, cells) in enumerate(series):
            c = cells[gi] if gi < len(cells) else None
            if not c or not _ok(c.get("rate")):
                continue
            xx = x0 + si * bw
            tip = f'{name}, {g}: {pct(c["rate"], 1)} ({c.get("k", "?")}/{c.get("n", "?")})'
            if _ok(c.get("lo")):
                tip += f'; 95% CI {pct(c["lo"])}–{pct(c["hi"])}'
            out.append(f'<rect x="{xx + 2:.1f}" y="{y(c["rate"]):.1f}" width="{bw - 4:.1f}" '
                       f'height="{max(y(0) - y(c["rate"]), 1.5):.1f}" rx="3" fill="{SERIES[si % len(SERIES)]}" '
                       f'opacity=".85"><title>{esc(tip)}</title></rect>')
            if _ok(c.get("lo")):
                out.append(f'<line class="ci" x1="{xx + bw / 2:.1f}" x2="{xx + bw / 2:.1f}" y1="{y(c["lo"]):.1f}" '
                           f'y2="{y(c["hi"]):.1f}"/>')
    out.append("</svg>")
    return "".join(out) + legend([(n, SERIES[i % len(SERIES)]) for i, (n, _) in enumerate(series)])


def lines(series: list[tuple[str, list[dict]]], x_label: str = "", y_label: str = "", step: bool = False,
          x_ticks: list | None = None, title: str = "", marker: float | None = None, marker_text: str = "",
          band: bool = True) -> str:
    """Line chart, y in [0, 1]. series: [(name, [{x, y, lo?, hi?, n?}])]. `step` draws a step function (survival)."""
    pts_all = [p for _, pts in series for p in pts if _ok(p.get("y"))]
    if not pts_all:
        return '<p class="small">No data.</p>'
    xs = sorted({p["x"] for p in pts_all} | set(x_ticks or []))
    x_min, x_max = min(xs), max(xs)
    w, h, l, r, t, b = 640, 260, 46, 14, 14, 42
    X = lambda v: l + (w - l - r) * ((v - x_min) / (x_max - x_min) if x_max > x_min else 0.5)  # noqa: E731
    Y = lambda v: t + (h - t - b) * (1 - max(0.0, min(v, 1.0)))  # noqa: E731
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    for v in (0, .25, .5, .75, 1):
        out.append(f'<line class="grid" x1="{l}" x2="{w - r}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                   f'<text class="axis" x="{l - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{v:.0%}</text>')
    ticks = x_ticks or xs
    if len(ticks) > 14:
        ticks = ticks[::math.ceil(len(ticks) / 14)]
    for xv in ticks:
        out.append(f'<text class="axis" x="{X(xv):.1f}" y="{h - b + 16}" text-anchor="middle">{esc(xv)}</text>')
    if x_label:
        out.append(f'<text class="axis" x="{(l + w - r) / 2:.0f}" y="{h - 6}" text-anchor="middle">{esc(x_label)}</text>')
    if y_label:
        out.append(f'<text class="axis" x="12" y="{(h - b + t) / 2:.0f}" transform="rotate(-90 12 {(h - b + t) / 2:.0f})" '
                   f'text-anchor="middle">{esc(y_label)}</text>')
    if marker is not None:
        out.append(f'<line class="chance" x1="{X(marker):.1f}" x2="{X(marker):.1f}" y1="{t}" y2="{h - b}"/>'
                   f'<text class="chancet" x="{X(marker) + 4:.1f}" y="{t + 10}">{esc(marker_text)}</text>')
    for si, (name, pts) in enumerate(series):
        pts = sorted((p for p in pts if _ok(p.get("y"))), key=lambda p: p["x"])
        if not pts:
            continue
        color = SERIES[si % len(SERIES)]
        if band and all(_ok(p.get("lo")) for p in pts) and len(pts) > 1 and not step:
            up = " ".join(f"{X(p['x']):.1f},{Y(p['hi']):.1f}" for p in pts)
            dn = " ".join(f"{X(p['x']):.1f},{Y(p['lo']):.1f}" for p in reversed(pts))
            out.append(f'<polygon points="{up} {dn}" fill="{color}" opacity=".12"/>')
        if step:
            coords = []
            for i, p in enumerate(pts):
                if i:
                    coords.append(f"{X(p['x']):.1f},{Y(pts[i - 1]['y']):.1f}")
                coords.append(f"{X(p['x']):.1f},{Y(p['y']):.1f}")
            if pts[-1]["x"] < x_max:
                coords.append(f"{X(x_max):.1f},{Y(pts[-1]['y']):.1f}")
            d = " ".join(coords)
        else:
            d = " ".join(f"{X(p['x']):.1f},{Y(p['y']):.1f}" for p in pts)
        out.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2.4" '
                   f'stroke-dasharray="{DASH[si % len(DASH)]}"/>')
        for p in pts:
            tip = f"{name}, {x_label or 'x'} {p['x']}: {pct(p['y'], 1)}"
            if p.get("n") is not None:
                tip += f" (n={p['n']})"
            if _ok(p.get("lo")):
                tip += f"; 95% CI {pct(p['lo'])}–{pct(p['hi'])}"
            out.append(f'<circle cx="{X(p["x"]):.1f}" cy="{Y(p["y"]):.1f}" r="3.6" fill="{color}">'
                       f'<title>{esc(tip)}</title></circle>')
    out.append("</svg>")
    return "".join(out) + legend([(n, SERIES[i % len(SERIES)]) for i, (n, _) in enumerate(series)], dashed=True)


def heatmap(row_labels: list[str], col_labels: list[str], cells: list[list[dict | None]], title: str = "",
            note: str = "", color: str = "var(--bad)") -> str:
    """A table-like heatmap: cell = {rate, k, n} shaded by rate (0 = card colour, 1 = full `color`)."""
    if not row_labels or not col_labels:
        return '<p class="small">No data.</p>'
    head = "".join(f"<th>{esc(c)}</th>" for c in col_labels)
    body = []
    for rl, row in zip(row_labels, cells):
        tds = []
        for c in row:
            if not c or not _ok(c.get("rate")):
                tds.append('<td class="hm na">–</td>')
                continue
            a = 0.08 + 0.72 * c["rate"]
            tip = pct(c["rate"], 1) + (f' ({c["k"]}/{c["n"]})' if c.get("n") is not None else "")
            if _ok(c.get("lo")):
                tip += f'; 95% CI {pct(c["lo"])}–{pct(c["hi"])}'
            tds.append(f'<td class="hm" style="background:color-mix(in srgb, {color} {a * 100:.0f}%, var(--card))" '
                       f'title="{esc(tip)}"><b>{pct(c["rate"])}</b>'
                       + (f'<span>{c["k"]}/{c["n"]}</span>' if c.get("n") is not None else "") + '</td>')
        body.append(f"<tr><th class='rowh'>{esc(rl)}</th>{''.join(tds)}</tr>")
    return (f'<div class="tablewrap"><table class="heat" aria-label="{esc(title)}"><thead><tr><th></th>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>' + (f'<p class="small">{esc(note)}</p>' if note else ""))


def forest(rows: list[dict], title: str = "", lo_v: float = -1.0, hi_v: float = 1.0, unit_pct: bool = True) -> str:
    """Differences with 95% intervals around 0. rows: {label, diff, lo, hi, verdict?, n?}."""
    rows = [r for r in rows if r]
    if not rows:
        return '<p class="small">No data.</p>'
    w, left, right, rh = 640, 250, 60, 30
    h = rh * len(rows) + 34
    X = lambda v: left + (w - left - right) * (max(lo_v, min(v, hi_v)) - lo_v) / (hi_v - lo_v)  # noqa: E731
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    for t in (lo_v, lo_v / 2, 0, hi_v / 2, hi_v):
        cls = "zero" if t == 0 else "grid"
        out.append(f'<line class="{cls}" x1="{X(t):.1f}" x2="{X(t):.1f}" y1="2" y2="{h - 26}"/>'
                   f'<text class="axis" x="{X(t):.1f}" y="{h - 10}" text-anchor="middle">'
                   f'{f"{t:+.0%}" if unit_pct else f"{t:+.2f}"}</text>')
    vcol = {"Supported": "var(--ok)", "Not supported": "var(--bad)", "Inconclusive": "var(--warn)"}
    for i, r in enumerate(rows):
        y = 6 + i * rh + rh / 2
        out.append(f'<text class="lab" x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">{esc(r["label"][:40])}</text>')
        if not _ok(r.get("diff")):
            out.append(f'<text class="labn" x="{X(0) + 6:.1f}" y="{y + 4:.1f}">not testable</text>')
            continue
        color = vcol.get(r.get("verdict"), "var(--blue)")
        if _ok(r.get("lo")):
            out.append(f'<line x1="{X(r["lo"]):.1f}" x2="{X(r["hi"]):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="{color}" '
                       'stroke-width="3" stroke-linecap="round"/>')
        tip = f'{r["label"]}: {r["diff"]:+.1%}' + (f' (95% CI {r["lo"]:+.0%} to {r["hi"]:+.0%})' if _ok(r.get("lo")) else "")
        if r.get("verdict"):
            tip += f'; {r["verdict"]}'
        out.append(f'<circle cx="{X(r["diff"]):.1f}" cy="{y:.1f}" r="6.5" fill="{color}"><title>{esc(tip)}</title></circle>'
                   f'<text class="val" x="{w - right + 6}" y="{y + 4:.1f}">{r["diff"]:+.0%}</text>')
    out.append("</svg>")
    return "".join(out)


def stacked(rows: list[tuple[str, list[tuple[str, int]]]], colors: dict[str, str], title: str = "") -> str:
    """100% stacked horizontal bars. rows: [(label, [(category, count)])]."""
    rows = [(lab, parts) for lab, parts in rows if sum(c for _, c in parts)]
    if not rows:
        return '<p class="small">No data.</p>'
    w, left, right, rh = 640, 160, 10, 30
    h = rh * len(rows) + 8
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    for i, (lab, parts) in enumerate(rows):
        y = 4 + i * rh
        tot = sum(c for _, c in parts)
        x = left
        out.append(f'<text class="lab" x="{left - 8}" y="{y + 16}" text-anchor="end">{esc(lab)}</text>')
        for cat, c in parts:
            ww = (w - left - right) * c / tot
            if ww <= 0:
                continue
            out.append(f'<rect x="{x:.1f}" y="{y + 2}" width="{ww:.1f}" height="{rh - 8}" fill="{colors.get(cat, "var(--ink2)")}">'
                       f'<title>{esc(lab)}: {esc(cat)} {c}/{tot} ({c / tot:.0%})</title></rect>')
            if ww > 34:
                out.append(f'<text class="inbar" x="{x + ww / 2:.1f}" y="{y + 16}" text-anchor="middle">{c / tot:.0%}</text>')
            x += ww
    out.append("</svg>")
    return "".join(out) + legend(list(colors.items()))
