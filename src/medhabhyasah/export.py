"""Printable HTML worksheet export — parent zone only.

Turns a reviewed batch's approved questions into a single, self-contained
HTML file: a worksheet (no answers shown) followed by an answer-key page.
Every AI- or parent-authored string is HTML-escaped before interpolation,
since this file is opened directly in a real browser with none of the app's
own DOM-level protections (textContent rendering, CSP on index.html).
"""
import html
import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return (slug or "worksheet")[:max_len]


def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def render_worksheet_html(request: dict, questions: list[dict]) -> str:
    """request: a generation_requests row (topic/subject/grade/exam).
    questions: approved question rows, each with options/answer/explanation.
    Returns a complete, self-contained HTML document as a string.
    """
    letters = ["A", "B", "C", "D"]
    title = f"{request['topic']} ({request['subject']})"

    worksheet_items = []
    answer_items = []
    for i, q in enumerate(questions, start=1):
        options = q.get("options") or []
        options_html = "".join(
            f"<li><span class='opt-letter'>{letters[j]}</span> {_esc(opt)}</li>"
            for j, opt in enumerate(options)
        )
        worksheet_items.append(f"""
<li class="q-item">
  <p class="q-text">{_esc(q['question'])}</p>
  <ul class="opt-list">{options_html}</ul>
</li>""")

        answer_idx = q.get("answer")
        answer_idx = answer_idx if isinstance(answer_idx, int) else None
        correct_letter = letters[answer_idx] if answer_idx is not None and 0 <= answer_idx < len(letters) else "?"
        explanation = _esc(q.get("explanation") or "")
        answer_items.append(f"""
<li class="a-item">
  <strong>{i}. {correct_letter}</strong>
  <p class="a-explain">{explanation}</p>
</li>""")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none';">
<title>{_esc(title)}</title>
<style>
:root{{--paper:#f3f5fa;--ink:#16233f;--muted:#55617a;--line:#d6dce9;--pen:#2346c7}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font:400 16px/1.6 "Segoe UI",Arial,sans-serif}}
main{{max-width:800px;margin:24px auto;padding:32px 40px;background:#fff;border:1px solid var(--line);border-radius:10px}}
h1{{font-size:26px;margin:0 0 4px}}
.meta{{color:var(--muted);font-size:14px;margin:0 0 24px}}
.toolbar{{margin-bottom:20px}}
.toolbar button{{padding:8px 18px;font-size:14px;background:var(--pen);color:#fff;border:none;border-radius:6px;cursor:pointer}}
ol.q-list{{list-style:none;margin:0;padding:0}}
li.q-item{{margin:0 0 22px;padding-bottom:18px;border-bottom:1px solid var(--line)}}
.q-text{{font-weight:600;margin:0 0 10px}}
ul.opt-list{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}}
ul.opt-list li{{padding:6px 10px;border:1px solid var(--line);border-radius:6px}}
.opt-letter{{display:inline-block;width:20px;font-weight:700;color:var(--muted)}}
.answer-key{{margin-top:12px}}
ol.a-list{{list-style:none;margin:0;padding:0}}
li.a-item{{margin:0 0 14px}}
.a-explain{{color:var(--muted);margin:4px 0 0;white-space:pre-wrap}}
@media print {{
  body{{background:#fff}}
  main{{border:0;margin:0;max-width:none}}
  .toolbar{{display:none}}
  .answer-key{{break-before:page}}
}}
</style>
</head>
<body>
<main>
<div class="toolbar"><button onclick="window.print()">Print</button></div>
<h1>{_esc(title)}</h1>
<p class="meta">Class {_esc(request['grade'])} &middot; {_esc(request['exam'])} &middot; {len(questions)} question(s)</p>
<ol class="q-list">{"".join(worksheet_items)}</ol>
<section class="answer-key">
<h1>Answer Key</h1>
<p class="meta">{_esc(title)}</p>
<ol class="a-list">{"".join(answer_items)}</ol>
</section>
</main>
</body>
</html>
"""
