"""Render a DI packet (from ai.generate_di_packets) into a printable, student-
facing HTML page with real visual MODELS drawn as SVG (ten-frames, pairing
counters, base-ten blocks, arrays, number lines, equal teams). The model is
chosen per benchmark; each problem carries an integer value so it can be drawn.

Self-contained HTML (Google-Fonts link only) so it prints cleanly from the
browser and matches the approved packet design.
"""
from __future__ import annotations

import html
import math

GREEN = "#BFE3A0"
PINK = "#F4B6AC"
FRAME = "#B9C2AE"


def _i(v, default=0):
    try:
        return int(round(float(v)))
    except Exception:
        return default


def _ten_frame(n: int, filled=True) -> str:
    """One or two 2x5 ten-frames holding n dots (n clamped 0-20)."""
    n = max(0, min(20, n))
    frames = 1 if n <= 10 else 2
    W = 202
    parts = [f'<svg width="{W}" height="{86*frames-6}" viewBox="0 0 {W} {86*frames-6}" role="img" aria-label="ten frame showing {n}">']
    placed = 0
    for f in range(frames):
        oy = f * 86
        parts.append(f'<rect x="1" y="{oy+1}" width="200" height="80" rx="6" fill="#fff" stroke="{FRAME}" stroke-width="2"/>')
        for x in (41, 81, 121, 161):
            parts.append(f'<line x1="{x}" y1="{oy+1}" x2="{x}" y2="{oy+81}" stroke="{FRAME}"/>')
        parts.append(f'<line x1="1" y1="{oy+41}" x2="201" y2="{oy+41}" stroke="{FRAME}" stroke-width="2"/>')
        if filled:
            for cell in range(10):
                if placed >= n:
                    break
                col = cell % 5
                row = cell // 5
                cx = 21 + col * 40
                cy = oy + 21 + row * 40
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="12" fill="{GREEN}"/>')
                placed += 1
    parts.append("</svg>")
    return "".join(parts)


def _pairing(n: int, reveal: bool = True, per_row: int = 10) -> str:
    """Counters for even/odd, wrapped into rows so large numbers never overflow.
    reveal=True (worked example) colors even green / odd pink and draws the pairs +
    the leftover, modeling the answer. reveal=False (practice) shows plain neutral
    counters in rows — the STUDENT pairs them, so the picture doesn't give away the
    answer. Rows wrap at `per_row` (kept even so a pair never splits a row)."""
    n = max(0, min(30, n))
    even = n % 2 == 0
    per_row = max(2, per_row - (per_row % 2))
    r, sp, pad, rowh = 11, 26, 8, 30
    rows = max(1, (n + per_row - 1) // per_row)
    ncols = min(n, per_row) if n else per_row
    W = pad * 2 + ncols * sp
    H = pad * 2 + rows * rowh
    def cx(i):
        return pad + r + (i % per_row) * sp
    def cy(i):
        return pad + r + (i // per_row) * rowh
    color = (GREEN if even else PINK) if reveal else "#DDE6CE"
    parts = [f'<svg width="100%" height="{H}" viewBox="0 0 {W} {H}" '
             f'preserveAspectRatio="xMinYMin meet" style="max-width:{W}px" '
             f'role="img" aria-label="{n} counters">']
    if reveal:
        # Outline each pair; dash the leftover on an odd count.
        i = 0
        while i + 1 < n:
            if i % per_row == per_row - 1:      # pair would straddle a row — skip box
                i += 1
                continue
            x0, y0 = cx(i) - r - 3, cy(i) - r - 3
            parts.append(f'<rect x="{x0}" y="{y0}" width="{sp + 2 * r + 6}" '
                         f'height="{2 * r + 6}" rx="{r + 3}" fill="none" '
                         f'stroke="#8a9b7f" stroke-width="2"/>')
            i += 2
        if not even and n:
            x0, y0 = cx(n - 1) - r - 3, cy(n - 1) - r - 3
            parts.append(f'<rect x="{x0}" y="{y0}" width="{2 * r + 6}" '
                         f'height="{2 * r + 6}" rx="{r + 2}" fill="none" '
                         f'stroke="#c9807a" stroke-width="2" stroke-dasharray="4 4"/>')
    for i in range(n):
        parts.append(f'<circle cx="{cx(i)}" cy="{cy(i)}" r="{r}" fill="{color}" '
                     f'stroke="#9aa98c" stroke-width="1"/>')
    parts.append("</svg>")
    return "".join(parts)


def _base_ten(v: int) -> str:
    """Base-ten blocks: hundreds flats, tens rods, ones units for v (0-999)."""
    v = max(0, min(999, v))
    h, t, o = v // 100, (v % 100) // 10, v % 10
    parts = [f'<svg width="100%" height="90" viewBox="0 0 320 90" role="img" aria-label="base ten blocks for {v}">']
    x = 6
    for _ in range(h):  # flat 30x30 grid
        parts.append(f'<rect x="{x}" y="10" width="34" height="34" fill="#CFE3BE" stroke="#4E7C2F"/>')
        for gx in range(1, 3):
            parts.append(f'<line x1="{x+gx*11}" y1="10" x2="{x+gx*11}" y2="44" stroke="#4E7C2F" stroke-width=".6"/>')
            parts.append(f'<line x1="{x}" y1="{10+gx*11}" x2="{x+34}" y2="{10+gx*11}" stroke="#4E7C2F" stroke-width=".6"/>')
        x += 40
    for _ in range(t):  # rod 8x34
        parts.append(f'<rect x="{x}" y="10" width="10" height="34" fill="#BFE3A0" stroke="#4E7C2F"/>')
        x += 15
    for _ in range(o):  # unit 8x8
        parts.append(f'<rect x="{x}" y="34" width="10" height="10" fill="#EED9A8" stroke="#C9880E"/>')
        x += 14
    parts.append('</svg>')
    return "".join(parts)


def _array(r: int, c: int) -> str:
    r = max(1, min(10, r))
    c = max(1, min(10, c))
    step = 26
    W, H = c * step + 6, r * step + 6
    parts = [f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{r} by {c} array">']
    for i in range(r):
        for j in range(c):
            parts.append(f'<circle cx="{9+j*step}" cy="{9+i*step}" r="9" fill="{GREEN}" stroke="#4E7C2F"/>')
    parts.append("</svg>")
    return "".join(parts)


def _number_line(v: int, mx: int) -> str:
    mx = max(5, min(30, mx or 20))
    v = max(0, min(mx, v))
    W = 360
    x0, x1 = 20, W - 20
    def px(k):
        return x0 + (x1 - x0) * k / mx
    parts = [f'<svg width="100%" height="56" viewBox="0 0 {W} 56" role="img" aria-label="number line 0 to {mx}, mark at {v}">']
    parts.append(f'<line x1="{x0}" y1="34" x2="{x1}" y2="34" stroke="#4E7C2F" stroke-width="2.5"/>')
    for k in range(mx + 1):
        X = px(k)
        parts.append(f'<line x1="{X}" y1="28" x2="{X}" y2="40" stroke="#4E7C2F" stroke-width="1.5"/>')
        if k % 5 == 0 or k == v:
            parts.append(f'<text x="{X}" y="52" font-size="10" text-anchor="middle" fill="#26302A">{k}</text>')
    parts.append(f'<circle cx="{px(v)}" cy="34" r="7" fill="{PINK}" stroke="#C0392B" stroke-width="2"/>')
    parts.append("</svg>")
    return "".join(parts)


def _equal_teams(a: int, b: int) -> str:
    a, b = max(0, min(10, a)), max(0, min(10, b))
    def team(vals, ox, color):
        s = [f'<rect x="{ox-4}" y="10" width="{max(1,vals)*26+8}" height="40" rx="10" fill="none" stroke="#8a9b7f"/>']
        for i in range(vals):
            s.append(f'<circle cx="{ox+9+i*26}" cy="30" r="10" fill="{color}"/>')
        return "".join(s)
    w = (max(1, a) + max(1, b)) * 26 + 70
    return (f'<svg width="{w}" height="60" viewBox="0 0 {w} 60" role="img" aria-label="two equal teams">'
            + team(a, 8, GREEN)
            + f'<text x="{a*26+30}" y="36" font-size="20" fill="#26302A">+</text>'
            + team(b, a * 26 + 48, "#EED9A8") + "</svg>")


import re as _re


def _ctx_text(spec: dict) -> str:
    """All the words attached to one problem — used to recover model numbers the
    AI wrote in the text but didn't pass as structured fields."""
    return " ".join(str(spec.get(k, "")) for k in ("statement", "problem", "text"))


def _ints(text: str) -> list:
    return [int(n) for n in _re.findall(r"\d+", text or "")]


def _array_dims(spec: dict) -> tuple:
    """rows x cols for an array — structured fields first, else parsed from text
    (e.g. '3 equal rows with 3 counters in each row' -> 3 x 3)."""
    r, c = spec.get("rows"), spec.get("cols")
    if r is not None and c is not None:
        return _i(r, 1), _i(c, 1)
    t = _ctx_text(spec)
    rm = _re.search(r"(\d+)\s*(?:equal\s+)?rows", t, _re.I)
    cm = (_re.search(r"(?:each row (?:has|of|with)|in each row|in one row)\s*(\d+)", t, _re.I)
          or _re.search(r"(\d+)\s*counters?\s*(?:in each|per row|in one row|in each row)", t, _re.I))
    rows = _i(rm.group(1), 0) if rm else 0
    cols = _i(cm.group(1), 0) if cm else 0
    if not rows or not cols:
        nums = _ints(t)
        if len(nums) >= 2:
            rows = rows or nums[0]
            cols = cols or nums[1]
    return max(1, rows or 2), max(1, cols or 2)


def _val(spec: dict, default=0) -> int:
    """A single value for ten_frame/pairing/base_ten/number_line — structured
    'value' first, else the first number in the problem's text."""
    if spec.get("value") is not None:
        return _i(spec.get("value"), default)
    nums = _ints(_ctx_text(spec))
    return nums[0] if nums else default


def svg_model(model: str, spec: dict, reveal: bool = True) -> str:
    """Draw the chosen model for one problem's spec, recovering the numbers from
    the problem text when the structured fields are missing. reveal=False renders a
    practice picture that does not give away the answer (used for problems the
    student solves)."""
    if not isinstance(spec, dict):
        return ""
    try:
        if model == "ten_frame":
            return _ten_frame(_val(spec))
        if model == "pairing":
            # Vary the row width by the number so problems don't all look alike.
            v = _val(spec)
            per = 8 if (v % 3 == 0) else (12 if v > 14 else 10)
            return _pairing(v, reveal=reveal, per_row=per)
        if model == "base_ten":
            return _base_ten(_val(spec))
        if model == "array":
            r, c = _array_dims(spec)
            return _array(r, c)
        if model == "number_line":
            return _number_line(_val(spec), _i(spec.get("max"), 20))
        if model == "equal_teams":
            a, b = spec.get("a"), spec.get("b")
            if a is None or b is None:
                nums = _ints(_ctx_text(spec))
                a = a if a is not None else (nums[0] if nums else 0)
                b = b if b is not None else (nums[1] if len(nums) > 1 else 0)
            return _equal_teams(_i(a), _i(b))
    except Exception:
        return ""
    return ""


_TIER_META = {
    "Intensive": ("red", "#C0392B", "★"),
    "Cusp": ("amber", "#C9880E", "★★"),
    "Strategic": ("blue", "#2E86C1", "★★★"),
}

_CSS = """
:root{--paper:#FBF8F1;--ink:#26302A;--muted:#6B7A6E;--line:#DED7C6;--brand:#4E7C2F;--brand-deep:#38601F;--frame:#B9C2AE;}
*{box-sizing:border-box;}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Atkinson Hyperlegible",system-ui,sans-serif;font-size:16px;line-height:1.5;}
.wrap{max-width:820px;margin:0 auto;padding:26px 22px 60px;}h1,h2,h3{font-family:"Baloo 2","Atkinson Hyperlegible",cursive;}
.band{background:var(--brand-deep);color:#fff;border-radius:14px;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;}
.band .eyebrow{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#CFE3BE;font-weight:700;}
.band h1{margin:.1em 0 0;font-size:18px;font-weight:800;line-height:1.15;}.band .std{font-size:12px;color:#DDEBCE;margin-top:3px;}
.namebar{display:flex;gap:12px;font-size:13px;color:#E8F1DE;}.namebar span{border-bottom:2px solid #7BA35C;padding:0 24px 2px 6px;}
.copies{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin-top:12px;font-size:13px;}
.copies .lbl{font-weight:700;color:var(--ink);}
.copies .cc{font-weight:700;color:#fff;border-radius:999px;padding:2px 10px;}
.choices{display:flex;flex-direction:column;gap:9px;margin-top:10px;}
.choice{display:flex;align-items:center;gap:9px;border:1.5px solid var(--line);border-radius:10px;padding:7px 12px;font-size:15px;}
.choice .b{width:24px;height:24px;border-radius:50%;border:2px solid var(--frame);display:inline-grid;place-items:center;font-family:"Baloo 2";font-weight:700;font-size:13px;flex:none;}
.ican{font-family:"Baloo 2";font-size:19px;font-weight:700;color:var(--brand-deep);margin:16px 2px 4px;}
.missed{background:#fff;border:1px solid var(--line);border-left:5px solid var(--brand);border-radius:12px;padding:12px 16px;margin-top:12px;font-size:14px;}
.tier{background:#fff;border:1px solid var(--line);border-radius:20px;padding:20px;margin-top:22px;border-top-width:8px;}
.tier-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.pill{font-family:"Baloo 2";font-weight:800;font-size:15px;color:#fff;padding:4px 14px;border-radius:999px;}
.tier-head h2{margin:0;font-size:22px;}
.day{display:flex;align-items:center;gap:10px;margin:18px 0 6px;padding:7px 14px;border-radius:12px;font-family:"Baloo 2";font-weight:800;font-size:17px;color:#fff;}
.day .small{font-family:"Atkinson Hyperlegible";font-weight:400;font-size:13px;opacity:.9;margin-left:auto;}
.phase{display:flex;align-items:center;gap:10px;margin:14px 0 6px;}
.phase .pn{width:28px;height:28px;border-radius:8px;display:grid;place-items:center;font-family:"Baloo 2";font-weight:800;color:#fff;font-size:15px;background:var(--muted);}
.phase h3{margin:0;font-size:17px;}.phase .gr{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:700;margin-left:auto;}
.phase-body{border-left:3px solid var(--line);margin-left:13px;padding-left:18px;}
.example{background:#EEF4E6;color:var(--ink);border:1px solid #CFE0BC;border-left:5px solid var(--brand);border-radius:12px;padding:11px 14px;display:flex;gap:16px;flex-wrap:wrap;align-items:center;}
.example .tag{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--brand-deep);font-weight:700;width:100%;}
.example .st{font-family:"Baloo 2";font-weight:800;font-size:16px;color:var(--ink);}
.example .cap{color:var(--muted);}
.example .verdict .even{color:#2e7d32;}.example .verdict .odd{color:#C0392B;}
.steps{display:grid;gap:7px;margin:4px 0;}.step{display:grid;grid-template-columns:26px 1fr;gap:9px;align-items:start;}
.step .n{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-family:"Baloo 2";font-weight:800;color:#fff;font-size:13px;background:var(--muted);}
.prob{border:1.5px solid var(--line);border-radius:12px;padding:12px;background:#fff;}
.prob .q{font-family:"Baloo 2";font-weight:700;font-size:15px;margin:0 0 6px;}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;}@media(max-width:560px){.grid{grid-template-columns:1fr;}}
.practicelabel{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:700;margin:8px 0 4px;}
.opm{background:#FBEBE8;border:1px solid #EAD2CE;border-radius:20px;padding:18px 20px;margin-top:22px;border-top:8px solid #C0392B;}
.opm h2{margin:0;font-size:20px;color:#C0392B;}.foot{margin-top:24px;text-align:center;color:var(--muted);font-size:13px;}
@media print{body{background:#fff;font-size:12pt;}.wrap{max-width:none;padding:0;}
.tier,.phase-body{break-inside:auto;}.prob,.example,.opm{break-inside:avoid;}
.phase,.day{break-after:avoid;}.band{border-radius:0;}
.tier{margin-top:14px;padding:16px;}.day{margin:12px 0 6px;}.phase{margin:10px 0 6px;}
.wrap{padding-bottom:0;}@page{margin:1.1cm;}}
"""
# For PDF rendering (WeasyPrint) the same rules apply without @media print.
_CSS_PDF_EXTRA = """
.tier,.phase-body{break-inside:auto;}.prob,.example,.opm{break-inside:avoid;}
.phase,.day{break-after:avoid;}
@page{size:Letter;margin:1.1cm;}
body{background:#fff;}
"""


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _choices_html(choices) -> str:
    """Multiple-choice answers, stacked one per line with a lettered bubble and
    clear spacing so young students don't confuse them (A. / B. / C. / D.)."""
    if not isinstance(choices, list) or not choices:
        return ""
    letters = "ABCDEFGH"
    rows = []
    for i, ch in enumerate(choices[:8]):
        rows.append(f'<div class="choice"><span class="b">{letters[i]}</span>'
                    f'<span>{_esc(ch)}</span></div>')
    return f'<div class="choices">{"".join(rows)}</div>'


def _problem_html(model, p, show_default=True) -> str:
    q = _esc(p.get("text") or p.get("problem"))
    vis = ""
    if p.get("show_model", show_default) and (p.get("value") is not None or "rows" in p or "a" in p):
        # Practice picture — neutral, so it doesn't reveal the answer.
        vis = svg_model(model, p, reveal=False)
    choices = _choices_html(p.get("choices"))
    if choices:
        ans = choices  # multiple choice — no write-in box needed
    else:
        ans = ('<div style="margin-top:10px;color:var(--muted);font-size:13px;">'
               'Answer: <span style="border:2px dashed var(--frame);border-radius:8px;'
               'display:inline-block;width:110px;height:30px;vertical-align:middle;"></span></div>')
    return f'<div class="prob"><p class="q">{q}</p>{vis}{ans}</div>'


def _extra_review_html(packet: dict) -> str:
    """A few OTHER questions the class missed — on standards outside this packet's
    reteach — added to each tier's practice so the teacher can review them too.
    Drawn from the 'Target the Misses' clusters whose standard differs from the
    packet's. Text + choices (no forced model). Cached on the packet."""
    if "_extra_review" not in packet:
        std = str(packet.get("standard", ""))
        samples = []
        for cl in (packet.get("target_the_misses") or []):
            if str(cl.get("standard", "")) and str(cl.get("standard")) != std:
                for s in (cl.get("fix_samples") or []):
                    samples.append({**s, "_std": cl.get("standard")})
        packet["_extra_review"] = samples[:3]
    samples = packet.get("_extra_review") or []
    if not samples:
        return ""
    cards = "".join(_problem_html("none", s) for s in samples)
    return ('<p class="practicelabel" style="color:#8E44AD;margin-top:12px;">'
            '⭐ Extra review — other questions the class missed</p>'
            f'<div class="grid">{cards}</div>')


def render_di_packet_html(packet: dict, for_pdf: bool = False) -> str:
    model = packet.get("model", "none")
    std = _esc(packet.get("standard"))
    desc = _esc(packet.get("description"))
    grade = _esc(packet.get("grade_level"))
    missed = packet.get("test_items") or []

    css = _CSS + (_CSS_PDF_EXTRA if for_pdf else "")
    head = [f'<!doctype html><html><head><meta charset="utf-8">',
            f'<meta name="viewport" content="width=device-width, initial-scale=1">',
            f'<title>DI Packet — {std}</title>']
    if not for_pdf:
        # WeasyPrint renders with locally installed fonts, so the web font link is
        # only useful for the browser-print path.
        head += ['<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
                 '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@600;700;800&family=Atkinson+Hyperlegible:wght@400;700&display=swap">']
    head.append(f'<style>{css}</style></head><body><div class="wrap">')
    out = list(head)
    teacher = _esc(packet.get("teacher"))
    eyebrow = f"Grade {grade} · Math · DI Center Packet"
    if teacher:
        n_classes = teacher.count(",") + 1
        eyebrow += (f" · {n_classes} classes: {teacher}" if n_classes > 1
                    else f" · {teacher}'s class")
    out.append(f'<div class="band"><div><div class="eyebrow">{eyebrow}</div>'
               f'<h1>{desc or std}</h1><div class="std">B.E.S.T. — {std}</div></div>'
               f'<div class="namebar"><span>Name</span><span>Date</span></div></div>')
    if missed:
        items = " · ".join(f'Q{_esc(m.get("position"))}' for m in missed[:8])
        out.append(f'<div class="missed"><b>We are fixing the questions the class missed most:</b> {items}. '
                   f'These packets reteach those exact ideas.</div>')

    # Copies to make — how many of each tier to print (for the copier).
    tiers = packet.get("tiers", []) or []
    tcount = {t.get("tier"): t.get("student_count", 0) for t in tiers}
    total = sum(tcount.values())
    if total:
        chips = "".join(
            f'<span class="cc" style="background:{_TIER_META.get(name, ("", "#888", ""))[1]}">'
            f'{label} ×{tcount.get(name,0)}</span>'
            for name, label in (("Intensive", "Red"), ("Cusp", "Yellow"),
                                ("Strategic", "Green")))
        who = f"{_esc(teacher)}" if teacher else "grade-wide"
        out.append(f'<div class="copies"><span class="lbl">📋 Copies to make ({who}):</span>'
                   f'{chips}<span class="cc" style="background:#38601F">Total ×{total}</span></div>')

    for t in packet.get("tiers", []):
        css, hexc, stars = _TIER_META.get(t.get("tier"), ("blue", "#2E86C1", ""))
        out.append(f'<section class="tier" style="border-top-color:{hexc}">')
        out.append(f'<div class="tier-head"><span class="pill" style="background:{hexc}">{stars} {_esc(t.get("tier"))}</span>'
                   f'<h2>{_esc(t.get("band"))}</h2></div>')
        for day in t.get("days", []):
            out.append(f'<div class="day" style="background:{hexc}">Day {_esc(day.get("day"))} — {_esc(day.get("title"))}'
                       f'<span class="small">{_esc(day.get("pacing"))}</span></div>')
            # Watch it
            w = day.get("watch_it") or {}
            if w:
                out.append('<div class="phase"><span class="pn" style="background:%s">1</span><h3>Watch it</h3><span class="gr">I do</span></div>' % hexc)
                out.append('<div class="phase-body"><div class="example"><div class="tag">Study this one</div>'
                           + svg_model(model, w)
                           + f'<div class="st">{_esc(w.get("statement"))}</div></div></div>')
            # Try it
            tr = day.get("try_it") or {}
            if tr:
                out.append('<div class="phase"><span class="pn" style="background:%s">2</span><h3>Try it</h3><span class="gr">We do</span></div>' % hexc)
                steps = "".join(f'<div class="step"><span class="n">{i+1}</span><p>{_esc(s)}</p></div>'
                                for i, s in enumerate(tr.get("steps", [])))
                out.append(f'<div class="phase-body"><div class="prob"><p class="q">{_esc(tr.get("problem"))}</p>'
                           + svg_model(model, tr, reveal=False)
                           + (f'<div class="steps">{steps}</div>' if steps else "") + '</div></div>')
            # On your own
            oyo = day.get("on_your_own") or []
            if oyo:
                out.append('<div class="phase"><span class="pn" style="background:%s">3</span><h3>On your own</h3><span class="gr">You do</span></div>' % hexc)
                cards = "".join(_problem_html(model, p) for p in oyo)
                extra = _extra_review_html(packet)
                out.append(f'<div class="phase-body"><p class="practicelabel">Practice — keep going until time is up</p>'
                           f'<div class="grid">{cards}</div>{extra}</div>')
        # OPM
        opm = t.get("opm") or []
        if opm:
            cards = "".join(_problem_html(model, {**p, "show_model": False}) for p in opm)
            out.append(f'<div class="opm"><h2>Quick Check — Did I Grow? ✅</h2><div class="grid" style="margin-top:10px;">{cards}</div></div>')
        out.append('</section>')

    # Layer 2 — Target the Misses: matched fix-it samples per misconception cluster.
    misses = packet.get("target_the_misses") or []
    if misses:
        out.append('<section class="tier" style="border-top-color:#8E44AD">')
        out.append('<div class="tier-head"><span class="pill" style="background:#8E44AD">🎯 Fix the Questions We Missed</span></div>')
        out.append('<p class="tier-sub">Matched practice for the exact questions the class missed most — do these after the reteach to rectify the mistake.</p>')
        if not packet.get("stems_captured", True):
            out.append('<p class="helper">Note: the test PDF wasn\'t uploaded for this topic, so these mirror the skill and format. Upload the test to match the exact wording.</p>')
        for cl in misses:
            qs = ", ".join(_esc(q) for q in (cl.get("questions") or []))
            std = _esc(cl.get("standard"))
            head = qs or "Missed items"
            if std:
                head += f" · {std}"
            out.append(f'<div class="day" style="background:#8E44AD">{head}'
                       f'<span class="small">{_esc(cl.get("why_missed"))}</span></div>')
            # Mirror the real (often multiple-choice) test questions: text + choices,
            # no forced manipulative model since a cluster may be off the packet's
            # standard.
            cards = "".join(_problem_html("none", p) for p in (cl.get("fix_samples") or []))
            out.append(f'<div class="phase-body"><div class="grid">{cards}</div></div>')
        out.append('</section>')

    out.append(f'<div class="foot">Avocado · Grade {grade} · {std} — Reteach the skill, then Target the Misses · Red &amp; Yellow = 2 days · Green = 1 day</div>')
    out.append('</div></body></html>')
    return "".join(out)
