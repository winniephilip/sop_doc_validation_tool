"""Generate a self-contained HTML comparison report from a report dict."""
from __future__ import annotations

import difflib
import html
import re
from datetime import datetime
from typing import Any


# ── word-level diff ───────────────────────────────────────────────────────────

def _word_diff(a: str, b: str) -> tuple[str, str]:
    """Return (orig_html, new_html) with changed words wrapped in highlight spans."""
    tok_a = re.split(r"(\s+)", a)
    tok_b = re.split(r"(\s+)", b)
    matcher = difflib.SequenceMatcher(None, tok_a, tok_b, autojunk=False)
    orig_parts: list[str] = []
    new_parts:  list[str] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        seg_a = "".join(tok_a[i1:i2])
        seg_b = "".join(tok_b[j1:j2])
        if op == "equal":
            orig_parts.append(html.escape(seg_a))
            new_parts.append(html.escape(seg_b))
        elif op == "replace":
            orig_parts.append(f'<span class="hl-del">{html.escape(seg_a)}</span>')
            new_parts.append(f'<span class="hl-add">{html.escape(seg_b)}</span>')
        elif op == "delete":
            orig_parts.append(f'<span class="hl-del">{html.escape(seg_a)}</span>')
        elif op == "insert":
            new_parts.append(f'<span class="hl-add">{html.escape(seg_b)}</span>')
    return "".join(orig_parts), "".join(new_parts)


# ── helpers ───────────────────────────────────────────────────────────────────

def _esc(v: Any) -> str:
    if v is None:
        return "<em style='color:#aaa'>—</em>"
    if isinstance(v, list):
        return html.escape(", ".join(str(x) for x in v))
    return html.escape(str(v))


def _status_badge(status: str) -> str:
    colours = {
        "MATCH":    ("c6f6d5", "22543d"),
        "MISMATCH": ("fed7d7", "742a2a"),
        "MISSING":  ("fefcbf", "744210"),
        "ADDED":    ("bee3f8", "2a4365"),
        "ERROR":    ("fed7d7", "742a2a"),
    }
    bg, fg = colours.get(status, ("e2e8f0", "4a5568"))
    return (f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
            f'font-weight:700;font-size:.75rem;text-transform:uppercase;'
            f'background:#{bg};color:#{fg}">{html.escape(status)}</span>')


def _sim_bar(ratio: float | None) -> str:
    if ratio is None:
        return ""
    pct = round(ratio * 100)
    colour = "48bb78" if ratio >= 0.8 else "ed8936" if ratio >= 0.5 else "e53e3e"
    return (f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="flex:1;height:6px;border-radius:3px;background:#e2e8f0">'
            f'<div style="width:{pct}%;height:100%;border-radius:3px;background:#{colour}"></div>'
            f'</div><span style="font-size:.75rem;color:#718096">{pct}%</span></div>')


# ── section rendering ─────────────────────────────────────────────────────────

def _render_sections(sections: list[dict]) -> str:
    if not sections:
        return "<p style='color:#718096'>No sections found.</p>"
    parts: list[str] = []
    for i, s in enumerate(sections):
        status  = s.get("status", "")
        title   = html.escape(s.get("title") or "")
        o_text  = s.get("original_content") or ""
        n_text  = s.get("new_content")      or ""
        sim     = s.get("similarity")

        use_diff = (
            status in ("MATCH", "MISMATCH")
            and o_text and n_text
            and (status == "MISMATCH" or (sim is not None and sim < 1.0))
            and len(o_text.split()) <= 1000
            and len(n_text.split()) <= 1000
        )
        if use_diff:
            orig_html, new_html = _word_diff(o_text, n_text)
        else:
            orig_html = html.escape(o_text) if o_text else "<em style='color:#aaa'>(not present)</em>"
            new_html  = html.escape(n_text) if n_text else "<em style='color:#aaa'>(not present)</em>"

        uid = f"sec-{i}"
        parts.append(f"""
<div style="border:1px solid #e2e8f0;border-radius:8px;margin-bottom:12px;overflow:hidden">
  <div onclick="var b=document.getElementById('{uid}');b.style.display=b.style.display==='none'?'block':'none'"
       style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#f7fafc;cursor:pointer;user-select:none">
    {_status_badge(status)}
    <span style="font-weight:700;flex:1;color:#2d3748">{title}</span>
    {_sim_bar(sim)}
    <span>&#9660;</span>
  </div>
  <div id="{uid}" style="display:none">
    <div style="display:grid;grid-template-columns:1fr 1fr">
      <div style="padding:12px 14px;border-right:1px solid #e2e8f0">
        <h4 style="font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:#718096;margin-bottom:6px">Document</h4>
        <p style="font-size:.84rem;color:#4a5568;white-space:pre-wrap;line-height:1.6">{orig_html}</p>
      </div>
      <div style="padding:12px 14px">
        <h4 style="font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:#718096;margin-bottom:6px">HTML File</h4>
        <p style="font-size:.84rem;color:#4a5568;white-space:pre-wrap;line-height:1.6">{new_html}</p>
      </div>
    </div>
  </div>
</div>""")
    return "\n".join(parts)


# ── main entry point ──────────────────────────────────────────────────────────

def render_html_report(report: dict[str, Any], docx_name: str) -> str:
    """Return a self-contained HTML string for the given comparison report dict."""
    score   = report.get("score", 0)
    pct     = round(score * 100)
    overall = report.get("overall_status", "MISMATCH")
    summary = report.get("summary", {})
    fields  = report.get("field_results", [])
    sections = report.get("section_results", [])
    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    score_colour = "22543d" if pct >= 90 else "744210" if pct >= 70 else "742a2a"

    # ── field rows ──
    field_rows = ""
    for f in fields:
        sim_html = _sim_bar(f.get("similarity"))
        orig_val = _esc(f.get("original_value"))
        new_val  = _esc(f.get("new_value"))
        field_rows += (
            f"<tr>"
            f"<td><strong>{html.escape(f.get('field',''))}</strong></td>"
            f"<td>{_status_badge(f.get('status',''))}</td>"
            f"<td style='max-width:260px;word-break:break-word'>{orig_val}</td>"
            f"<td style='max-width:260px;word-break:break-word'>{new_val}</td>"
            f"<td>{sim_html}</td>"
            f"</tr>\n"
        )

    # ── summary chips ──
    chip_colours = {
        "MATCH":    ("c6f6d5","22543d"),
        "MISMATCH": ("fed7d7","742a2a"),
        "MISSING":  ("fefcbf","744210"),
        "ADDED":    ("bee3f8","2a4365"),
    }
    chips = ""
    for k, v in summary.items():
        bg, fg = chip_colours.get(k, ("e2e8f0","4a5568"))
        chips += (f'<span style="padding:5px 14px;border-radius:20px;font-size:.8rem;font-weight:700;'
                  f'background:#{bg};color:#{fg}">{v} {html.escape(k)}</span> ')

    sections_html = _render_sections(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Comparison Report — {html.escape(docx_name)}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f0f2f5;color:#1a1a2e;min-height:100vh}}
.app-header{{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:18px 32px;border-bottom:3px solid #005fab}}
.app-header h1{{font-size:1.3rem;font-weight:700}}
.app-header p{{font-size:.82rem;color:#a0aec0;margin-top:3px}}
.container{{max-width:1200px;margin:0 auto;padding:24px 16px}}
.card{{background:#fff;border-radius:10px;padding:22px;margin-bottom:18px;box-shadow:0 2px 12px rgba(0,0,0,.07)}}
.card h2{{font-size:1rem;font-weight:700;color:#2d3748;margin-bottom:14px;border-bottom:1px solid #e2e8f0;padding-bottom:8px}}
table{{width:100%;border-collapse:collapse;font-size:.84rem}}
th{{background:#f7fafc;padding:9px 11px;text-align:left;font-weight:700;color:#4a5568;border-bottom:2px solid #e2e8f0}}
td{{padding:8px 11px;border-bottom:1px solid #f0f2f5;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.hl-del{{background:#fed7d7;color:#742a2a;text-decoration:line-through;padding:0 2px;border-radius:2px}}
.hl-add{{background:#c6f6d5;color:#22543d;padding:0 2px;border-radius:2px}}
.summary-row{{display:flex;align-items:center;gap:20px;flex-wrap:wrap}}
.score-box{{display:flex;flex-direction:column;align-items:center;background:#f7f8fa;border-radius:8px;padding:12px 20px}}
.score-num{{font-size:2rem;font-weight:800;color:#{score_colour}}}
.score-lbl{{font-size:.72rem;color:#718096;text-transform:uppercase;letter-spacing:.05em}}
footer{{text-align:center;font-size:.75rem;color:#a0aec0;padding:20px 0}}
</style>
</head>
<body>
<div class="app-header">
  <h1>SOP Comparison Report</h1>
  <p>{html.escape(docx_name)} &nbsp;|&nbsp; Generated {generated}</p>
</div>
<div class="container">

  <div class="card">
    <h2>Summary</h2>
    <div class="summary-row">
      <div class="score-box">
        <span class="score-num">{pct}%</span>
        <span class="score-lbl">Match Score</span>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">{chips}</div>
      {_status_badge(overall)}
    </div>
  </div>

  <div class="card">
    <h2>Field Comparison</h2>
    <table>
      <thead><tr><th>Field</th><th>Status</th><th>Document</th><th>HTML File</th><th>Similarity</th></tr></thead>
      <tbody>{field_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>Section Comparison</h2>
    {sections_html}
  </div>

</div>
<footer>SOP Ingestion Validation Tool &nbsp;|&nbsp; Batch Report</footer>
</body>
</html>"""
