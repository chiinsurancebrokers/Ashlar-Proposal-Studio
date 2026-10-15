"""The client report as one self-contained HTML page.

WHY THIS EXISTS ALONGSIDE THE PDF
---------------------------------
The PDF is the document a client keeps. This page is the document a client
reads: it opens on a phone, the comparison table scrolls without a pinch, the
broker can send it as a link or as one file, and it prints to a clean PDF from
any browser. It is built from exactly the same inputs as `build_pdf_bytes`, so
the two cannot say different things about the same case.

Everything is inline -- styles, marks, layout -- so the file survives being
emailed, saved to a desktop, or opened with no network. The only external
request is the Google Fonts stylesheet, and the font stack falls back to the
system serif and sans when it cannot be reached.

THE TWO RULES IT ENFORCES VISUALLY
---------------------------------
1. Scope before price. When the plans are not written for the same territory,
   the page says so in a strip above the first premium the reader meets. A
   Europe-only premium beside two worldwide premiums reads as a bargain when it
   is a different product.

2. A benefit that is not covered reads "Not covered" and carries no
   specification beside the cross. The reduction happens in
   `build_comparison_matrix`, and this renderer prints what it is given.

State is carried by both a symbol and a colour, never colour alone, so the
marks still read for a colour-blind client and in a black-and-white printout.
"""
from __future__ import annotations

from datetime import date
from html import escape

from .benefit_state import ACTION, COVERED, NOT_COVERED, SUB_LIMIT, UNKNOWN
from .benefit_state import mark as benefit_mark
from .client_analysis import (
    client_facing_deductible,
    coverage_scope_note,
    find_plan_narrative,
    plan_display_name,
    premium_display,
)
from .report_labels import all_labels, category_label, is_greek, topic_label

FONTS_HREF = (
    "https://fonts.googleapis.com/css2"
    "?family=Fraunces:ital,opsz,wght,SOFT@0,9..144,300..700,0..100;1,9..144,300..700,0..100"
    "&family=Instrument+Sans:ital,wght@0,400..700;1,400..700"
    "&family=JetBrains+Mono:wght@400;500&display=swap"
)

# The four states, each with a symbol as well as a hue. "unknown" is not a
# fifth state: a benefit the documents never specified gets plain words, not a
# mark, because inventing a mark for it would imply the documents said
# something they did not.
MARK_SYMBOL = {COVERED: "●", ACTION: "○", SUB_LIMIT: "▲", NOT_COVERED: "✕"}
MARK_LABEL_KEY = {
    COVERED: "mark_covered",
    ACTION: "mark_action",
    SUB_LIMIT: "mark_sub_limit",
    NOT_COVERED: "mark_not_covered",
}

CSS = """
:root{
  --paper:#F6F8FB; --paper-fine:#FFFFFF; --mortar:#E1E7EF; --mortar-dark:#12243A;
  --ink:#0C1A2A; --oxblood:#6C4CF5; --verdigris:#15966A; --amber:#E7AD43;
  --muted:#6C768A;
  --display:"Fraunces",Georgia,"Times New Roman",serif;
  --sans:"Instrument Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
/* Dark mode. A client opens this on a phone, often in the evening, and a
   limestone page at full brightness is what they put down again.

   The ground inverts, the roles do not: verdigris still means covered,
   oxblood still means absent. Both are lifted, because the screen versions of
   #4A6E6B and #70181C on a dark ground fall below a readable contrast.

   The print block at the end of this file re-declares every one of these
   tokens with !important. That is not belt and braces -- it is the specific
   failure this page is avoiding. A rule written as
   :root:not([data-theme="light"]) outranks a plain :root on specificity, so a
   print stylesheet that redefines the tokens without !important loses to the
   dark rule, and a client printing from a dark-mode machine gets near-white
   ink on white paper. That is exactly how the first version of the Polat
   comparison printed: the title and the marks simply were not there. */
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#151C27; --paper-fine:#1B2432; --mortar:#2E3A4D;
    --ink:#ECE6DB; --mortar-dark:#2E3A4D; --muted:#9A9387;
    --oxblood:#9A85FF; --verdigris:#3FC78E; --amber:#F0C168;
    color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --paper:#151C27; --paper-fine:#1B2432; --mortar:#2E3A4D;
  --ink:#ECE6DB; --mortar-dark:#2E3A4D; --muted:#9A9387;
  --oxblood:#9A85FF; --verdigris:#3FC78E; --amber:#F0C168;
  color-scheme:dark;
}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.55;
  font-variant-numeric:tabular-nums;
}
.wrap{max-width:1240px; margin:0 auto; padding:0 clamp(16px,3vw,32px)}
section{padding:clamp(28px,4vw,52px) 0; border-top:1px solid var(--mortar)}
section:first-of-type{border-top:0}

/* --- type ------------------------------------------------------------- */
h1,h2,h3{font-family:var(--display); font-weight:400; text-wrap:balance; margin:0}
h1{font-size:clamp(30px,5vw,56px); line-height:1.04; letter-spacing:-.025em}
h2{font-size:clamp(22px,3vw,34px); line-height:1.12; letter-spacing:-.02em; margin-bottom:14px}
h3{font-size:clamp(17px,2vw,21px); line-height:1.25; margin-bottom:8px}
h1 em,h2 em{font-style:italic; font-variation-settings:"SOFT" 60; color:var(--oxblood)}
p{margin:0 0 12px}
.lede{font-family:var(--display); font-size:clamp(17px,2vw,21px); line-height:1.5; max-width:62ch}
.eyebrow{
  font-family:var(--mono); font-size:10px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--muted); margin:0 0 10px
}
.prose{max-width:74ch}
.muted{color:var(--muted)}
ul{margin:0 0 12px; padding-left:18px}
li{margin:0 0 6px}

/* --- masthead --------------------------------------------------------- */
.masthead{background:var(--ink); color:var(--paper-fine); border-bottom:1px solid var(--mortar)}
.masthead .wrap{padding-top:clamp(34px,6vw,76px); padding-bottom:clamp(30px,5vw,60px)}
.masthead .eyebrow{color:var(--amber)}
.masthead h1{color:var(--paper-fine)}
.masthead .client{
  font-family:var(--display); font-size:clamp(19px,2.4vw,27px); margin:18px 0 0;
  color:var(--paper-fine)
}
.masthead .sub{color:#C9C0B2; max-width:58ch; margin-top:12px}
.meta{
  display:flex; flex-wrap:wrap; gap:0; margin-top:clamp(22px,3vw,34px);
  border:1px solid var(--mortar-dark); border-collapse:collapse
}
.meta div{
  flex:1 1 180px; padding:12px 16px; border-right:1px solid var(--mortar-dark);
  font-family:var(--mono); font-size:11px; letter-spacing:.06em
}
.meta div:last-child{border-right:0}
.meta span{display:block; color:#8E9AAC; font-size:9.5px; letter-spacing:.14em;
  text-transform:uppercase; margin-bottom:4px}

/* --- scope strip ------------------------------------------------------ */
.strip{border:1px solid var(--mortar); border-left:4px solid var(--amber);
  background:var(--paper-fine); padding:18px 22px}
.strip .eyebrow{color:var(--amber); margin-bottom:6px}
.strip p{margin:0; max-width:80ch}

/* --- the wall (plan blocks, difference cards) ------------------------- */
.wall{display:grid; gap:0; border:1px solid var(--mortar); background:var(--paper-fine)}
.wall.one{grid-template-columns:1fr}
.wall.two{grid-template-columns:1fr 1fr}
.wall.three{grid-template-columns:repeat(3,1fr)}
.block{padding:20px 22px; border-right:1px solid var(--mortar); border-bottom:1px solid var(--mortar)}
.block:last-child{border-right:0}
.facts{width:100%; border-collapse:collapse; border:1px solid var(--mortar);
  background:var(--paper-fine); margin:0 0 20px}
.facts th,.facts td{border:1px solid var(--mortar); padding:10px 12px; text-align:left;
  vertical-align:top; font-size:14px}
.facts th{font-family:var(--mono); font-size:10px; letter-spacing:.12em; text-transform:uppercase;
  color:var(--muted); font-weight:400; width:1%; white-space:nowrap}
.plan{border-top:1px solid var(--mortar); padding-top:26px; margin-top:26px}
.plan:first-of-type{border-top:0; padding-top:0; margin-top:0}
.col-head{font-family:var(--mono); font-size:10px; letter-spacing:.14em; text-transform:uppercase;
  margin:0 0 10px}
.col-head.good{color:var(--verdigris)}
.col-head.watch{color:var(--amber)}

/* --- comparison table ------------------------------------------------- */
.scroller{overflow-x:auto; border:1px solid var(--mortar); background:var(--paper-fine)}
table.compare{width:100%; border-collapse:collapse; font-size:14px; min-width:640px}
table.compare th,table.compare td{border:1px solid var(--mortar); padding:10px 12px;
  text-align:left; vertical-align:top}
table.compare thead th{background:var(--ink); color:var(--paper-fine);
  font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase;
  font-weight:400; position:sticky; top:0}
table.compare tbody th{font-family:var(--sans); font-size:13.5px; font-weight:600;
  background:var(--paper); width:22%}
table.compare tr.band th{background:var(--paper); color:var(--muted);
  font-family:var(--mono); font-size:10px; letter-spacing:.14em; text-transform:uppercase;
  font-weight:400}
.mark{display:inline-flex; align-items:baseline; gap:7px}
.mark-sym{font-size:11px; line-height:1.4; flex:0 0 auto}
.m-covered .mark-sym{color:var(--verdigris)}
.m-action .mark-sym{color:var(--ink)}
.m-sub_limit .mark-sym{color:var(--amber)}
.m-not_covered .mark-sym{color:var(--oxblood)}
.m-not_covered .mark-text{color:var(--oxblood)}
.key{display:flex; flex-wrap:wrap; gap:0; margin-top:18px; border:1px solid var(--mortar);
  border-collapse:collapse}
.key div{flex:1 1 170px; padding:10px 14px; border-right:1px solid var(--mortar);
  font-family:var(--mono); font-size:10px; letter-spacing:.08em; text-transform:uppercase}
.key div:last-child{border-right:0}

/* --- recommendation --------------------------------------------------- */
.rec{border:1px solid var(--mortar); background:var(--paper-fine); padding:24px 26px}
.rec h2{color:var(--oxblood)}
.named{font-family:var(--mono); font-size:11px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--verdigris); margin:0 0 10px}
.sources dt{font-family:var(--mono); font-size:10px; letter-spacing:.12em; text-transform:uppercase;
  color:var(--muted); margin-top:14px}
.sources dd{margin:4px 0 0}
a{color:var(--oxblood); text-decoration-thickness:1px; text-underline-offset:2px}

/* --- footer ----------------------------------------------------------- */
footer{background:var(--ink); color:#C9C0B2; border-top:1px solid var(--mortar)}
footer .wrap{padding:30px clamp(16px,3vw,32px)}
footer p{max-width:86ch; font-size:13px}
footer .line{font-family:var(--mono); font-size:10px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--amber)}

@media (max-width:980px){
  .wall.two,.wall.three{grid-template-columns:1fr}
  .block{border-right:0}
  table.compare tbody th{width:34%}
}

@media (prefers-color-scheme:dark){
  /* The masthead is light-on-dark by construction: background var(--ink),
     text var(--paper-fine). Invert the tokens and those two swap, so the
     title is painted dark on a dark ground and disappears -- the same way it
     disappeared from the printed Polat comparison, for the same reason. The
     ground and the ink are therefore named explicitly here rather than left
     to the tokens. */
  :root:not([data-theme="light"]) .masthead,
  :root:not([data-theme="light"]) footer{background:var(--paper-fine);
    color:var(--ink)}
  :root:not([data-theme="light"]) .masthead h1,
  :root:not([data-theme="light"]) .masthead .client{color:var(--ink)}
  :root:not([data-theme="light"]) .masthead .sub,
  :root:not([data-theme="light"]) footer p{color:#A8A194}
  :root:not([data-theme="light"]) .meta span{color:#8E887C}
  :root:not([data-theme="light"]) table.compare thead th{background:#0F141D}
  :root:not([data-theme="light"]) table.compare tbody th{background:var(--paper)}
  :root:not([data-theme="light"]) table.compare tr.band th{background:var(--paper)}
}

@media print{
  /* Every token again, each one !important. The dark rule above is written as
     :root:not([data-theme="light"]), which beats a plain :root on
     specificity -- so without !important here, printing from a machine set to
     dark mode puts near-white ink on white paper. */
  :root, :root[data-theme="dark"], :root:not([data-theme="light"]){
    --paper:#fff!important; --paper-fine:#fff!important;
    --mortar:#B9AE9B!important; --mortar-dark:#B9AE9B!important;
    --ink:#0C1A2A!important; --muted:#5C6474!important;
    --oxblood:#6C4CF5!important; --verdigris:#0E6F4F!important;
    --amber:#9A7420!important;
    color-scheme:light;
  }
  body{background:#fff!important; color:var(--ink)!important; font-size:10.5pt}
  .masthead,footer{background:#fff!important; color:var(--ink)!important}
  table.compare thead th{background:#fff!important; color:var(--ink)!important}
  table.compare tbody th,table.compare tr.band th{background:#fff!important}
  section{padding:14pt 0; break-inside:avoid}
  .masthead,footer{border-color:var(--mortar)}
  .masthead h1,.masthead .client{color:var(--ink)!important}
  .masthead .sub,footer p{color:var(--muted)}
  .masthead .eyebrow,footer .line{color:var(--oxblood)}
  .meta div{border-color:var(--mortar)}
  .meta span{color:var(--muted)}
  table.compare thead th{position:static; border-bottom:1.5px solid var(--ink)}
  .scroller{overflow:visible}
  table.compare{min-width:0}
  thead{display:table-header-group}
  tr,.plan,.rec,.strip{break-inside:avoid}
  a{color:var(--ink)}
  a[href^="http"]::after{content:" (" attr(href) ")"; font-size:8pt; color:var(--muted)}
}
"""


def _e(value) -> str:
    """Escape for HTML, treating every empty-ish value as an empty string."""
    text = str(value or "").strip()
    return escape(text, quote=True)


def _p(value, cls: str = "") -> str:
    text = _e(value)
    if not text:
        return ""
    attr = f' class="{cls}"' if cls else ""
    return f"<p{attr}>{text}</p>"


def _ul(items, limit: int | None = None) -> str:
    kept = [_e(x) for x in (items or []) if str(x or "").strip()]
    if limit:
        kept = kept[:limit]
    if not kept:
        return ""
    return "<ul>" + "".join(f"<li>{x}</li>" for x in kept) + "</ul>"


def _mark_html(cell: dict, lab: dict) -> str:
    """One comparison cell: symbol plus text, or plain words when unknown."""
    state = cell.get("state") or UNKNOWN
    text = _e(cell.get("text")) or _e(lab["mark_unknown"])
    if state not in MARK_SYMBOL:
        return f'<span class="muted">{text}</span>'
    return (
        f'<span class="mark m-{state}">'
        f'<span class="mark-sym" aria-hidden="true">{MARK_SYMBOL[state]}</span>'
        f'<span class="mark-text">{text}</span></span>'
    )


def _row_cells(row: dict, names: list[str], lab: dict) -> str:
    """The cells of one comparison row.

    `marks` is read when the matrix supplied it and recomputed from the text
    when it did not, so a case stored before marks existed still renders with
    them rather than silently losing the states.
    """
    values = row.get("values") or {}
    marks = row.get("marks") or {}
    is_benefit = str(row.get("category") or "") == "Benefits"
    out = []
    for name in names:
        raw = values.get(name)
        if not is_benefit:
            out.append(f"<td>{_e(raw) or _e(lab['mark_unknown'])}</td>")
            continue
        cell = marks.get(name) or benefit_mark(raw)
        out.append(f"<td>{_mark_html(cell, lab)}</td>")
    return "".join(out)


def _comparison(client_analysis: dict, results: list[dict], lab: dict, language: str) -> str:
    matrix = client_analysis.get("comparison_matrix") or []
    if not matrix:
        return ""
    names = [plan_display_name(r) for r in results]
    head = "".join(f"<th scope='col'>{_e(n)}</th>" for n in names)
    body, seen_category = [], None
    for row in matrix:
        category = str(row.get("category") or "").strip()
        if category and category != seen_category:
            seen_category = category
            body.append(
                f'<tr class="band"><th scope="rowgroup" colspan="{len(names) + 1}">'
                f"{_e(category_label(category, language))}</th></tr>"
            )
        body.append(
            f'<tr><th scope="row">{_e(topic_label(row.get("topic"), language))}</th>'
            f"{_row_cells(row, names, lab)}</tr>"
        )
    key = "".join(
        f'<div><span class="mark m-{state}">'
        f'<span class="mark-sym" aria-hidden="true">{MARK_SYMBOL[state]}</span>'
        f"<span>{_e(lab[MARK_LABEL_KEY[state]])}</span></span></div>"
        for state in (COVERED, ACTION, SUB_LIMIT, NOT_COVERED)
    )
    return (
        "<section id='comparison'><div class='wrap'>"
        f"<h2>{_e(lab['compare'])}</h2>"
        f"{_p(lab['compare_note'], 'prose muted')}"
        f"<p class='eyebrow'>{_e(lab['marks_key'])}</p>"
        f"<div class='key' style='margin:0 0 18px'>{key}</div>"
        "<div class='scroller'><table class='compare'>"
        f"<thead><tr><th scope='col'>{_e(lab['benefit'])}</th>{head}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
        "</div></section>"
    )


def _scope_strip(client_analysis: dict, results: list[dict], lab: dict, language: str) -> str:
    """The warning that has to appear above the first premium on the page.

    The note is normally composed by `apply_client_report_rules`. It is
    recomputed here when a stored report predates that, because the one thing
    this strip must never do is go missing when the scopes differ.
    """
    note = str(client_analysis.get("coverage_scope_note") or "").strip()
    if not note:
        note = coverage_scope_note(results, language=language)
    if not note:
        return ""
    return (
        "<section id='scope'><div class='wrap'><div class='strip'>"
        f"<p class='eyebrow'>{_e(lab['scope_warning'])}</p>"
        f"<p>{_e(note)}</p>"
        "</div></div></section>"
    )


def _masthead(client_analysis: dict, results: list[dict], lab: dict, language: str) -> str:
    title = _e(client_analysis.get("report_title")) or _e(lab["subtitle"])
    today = date.today().strftime("%d/%m/%Y" if is_greek(language) else "%d %b %Y")
    cells = [
        (lab["prepared_for"], client_analysis.get("client_name") or "Client"),
        (lab["prepared_on"], today),
    ]
    reference = str(client_analysis.get("case_reference") or "").strip()
    if reference:
        cells.append(("Ref", reference))
    if results:
        cells.append((lab["plans_compared"], str(len(results))))
    meta = "".join(
        f"<div><span>{_e(k)}</span>{_e(v)}</div>" for k, v in cells
    )
    return (
        "<header class='masthead'><div class='wrap'>"
        "<p class='eyebrow'>Ashlar Assurance</p>"
        f"<h1>{title}</h1>"
        f"<p class='client'>{_e(client_analysis.get('client_name') or 'Client')}</p>"
        f"<p class='sub'>{_e(lab['subtitle'])}</p>"
        f"<div class='meta'>{meta}</div>"
        "</div></header>"
    )


def _context(client_analysis: dict, lab: dict) -> str:
    needs = client_analysis.get("client_needs_summary") or client_analysis.get("client_priorities")
    profile = client_analysis.get("client_profile")
    parts = []
    if needs:
        parts.append(f"<h2>{_e(lab['context'])}</h2>")
        parts.append(_p(needs, "lede"))
    if profile and str(profile).strip() != "Not supplied":
        parts.append(f"<h3>{_e(lab['profile'])}</h3>")
        parts.append(_p(profile, "prose"))
    summary = client_analysis.get("executive_summary")
    if summary:
        parts.append(f"<h3>{_e(lab['exec'])}</h3>")
        parts.append(_p(summary, "prose"))
    if not parts:
        return ""
    return "<section id='context'><div class='wrap'>" + "".join(parts) + "</div></section>"


def _plans(client_analysis: dict, results: list[dict], lab: dict) -> str:
    if not results:
        return ""
    narratives = client_analysis.get("plans") or []
    blocks = []
    for result in results:
        a = result.get("analysis") or {}
        n = find_plan_narrative(narratives, result)
        facts = [
            (lab["f_premium"], premium_display(a)),
            (lab["f_limit"], a.get("annual_limit") or lab["mark_unknown"]),
            (lab["f_deductible"],
             client_facing_deductible(a.get("deductible_or_excess") or lab["mark_unknown"])),
            (lab["f_area"], a.get("area_of_cover") or lab["mark_unknown"]),
        ]
        rows = "".join(
            f"<tr><th scope='row'>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in facts
        )
        columns = ""
        strengths, considerations = n.get("strengths") or [], n.get("considerations") or []
        if strengths or considerations:
            columns = (
                "<div class='wall two'>"
                f"<div class='block'><p class='col-head good'>{_e(lab['strengths'])}</p>"
                f"{_ul(strengths, 5)}</div>"
                f"<div class='block'><p class='col-head watch'>{_e(lab['consider'])}</p>"
                f"{_ul(considerations, 5)}</div></div>"
            )
        positioning = _p(n.get("positioning"), "eyebrow")
        blocks.append(
            "<article class='plan'>"
            f"{positioning}"
            f"<h2>{_e(plan_display_name(result))}</h2>"
            f"<table class='facts'><tbody>{rows}</tbody></table>"
            f"{_p(n.get('summary'), 'prose')}"
            f"{columns}"
            f"{_p(n.get('best_suited_when'), 'prose muted')}"
            "</article>"
        )
    return "<section id='plans'><div class='wrap'>" + "".join(blocks) + "</div></section>"


def _differences(client_analysis: dict, lab: dict) -> str:
    items = (client_analysis.get("key_differences") or [])[:6]
    if not items:
        return ""
    cards = "".join(
        "<div class='block'>"
        f"<h3>{_e(d.get('title') or lab['diff'])}</h3>"
        f"{_p(d.get('analysis'))}"
        f"{_p(d.get('client_impact'), 'muted')}"
        "</div>"
        for d in items
    )
    return (
        "<section id='differences'><div class='wrap'>"
        f"<h2>{_e(lab['diff'])}</h2>"
        f"<div class='wall two'>{cards}</div>"
        "</div></section>"
    )


def _named_option(label: str, provider, plan, *paragraphs) -> str:
    provider, plan = str(provider or "").strip(), str(plan or "").strip()
    if not provider and not plan:
        return ""
    body = "".join(_p(x) for x in paragraphs if str(x or "").strip())
    return (
        "<div class='block'>"
        f"<p class='named'>{_e(label)}</p>"
        f"<h3>{_e((provider + ' ' + plan).strip())}</h3>{body}</div>"
    )


def _recommendation(client_analysis: dict, lab: dict) -> str:
    ass = client_analysis.get("ashlar_assessment") or {}
    if not ass:
        return ""
    options = "".join([
        _named_option(lab["preferred"], ass.get("recommended_provider"),
                      ass.get("recommended_plan"), *(ass.get("reasoning") or [])),
        _named_option(lab["alternative"], ass.get("alternative_provider"),
                      ass.get("alternative_plan"), ass.get("alternative_reason"),
                      ass.get("when_the_alternative_may_be_better")),
        _named_option(lab["extras"], ass.get("extras_provider"),
                      ass.get("extras_plan"), ass.get("extras_reason")),
        _named_option(lab["budget"], ass.get("budget_provider"),
                      ass.get("budget_plan"), ass.get("budget_reason")),
    ])
    wall = f"<div class='wall two'>{options}</div>" if options else ""
    return (
        "<section id='recommendation'><div class='wrap'><div class='rec'>"
        f"<p class='eyebrow'>{_e(lab['assessment'])}</p>"
        f"<h2>{_e(ass.get('headline') or lab['our_view'])}</h2>"
        f"{wall}</div></div></section>"
    )


def _next_steps(client_analysis: dict, lab: dict) -> str:
    """Considerations and next steps, skipping whichever of the two is empty.

    A heading standing over an empty list reads as a document that failed to
    load rather than as a report with nothing to add there.
    """
    blocks = [
        (lab["important"], client_analysis.get("important_considerations") or []),
        (lab["next"], client_analysis.get("next_steps") or []),
    ]
    present = [(title, items) for title, items in blocks if any(str(x or "").strip() for x in items)]
    if not present:
        return ""
    if len(present) == 1:
        # One block left: title the section after it rather than announcing
        # "considerations & next steps" above a page that has only one of them.
        title, items = present[0]
        return (
            "<section id='next'><div class='wrap'>"
            f"<h2>{_e(title)}</h2>"
            f"<div class='wall one'><div class='block'>{_ul(items)}</div></div>"
            "</div></section>"
        )
    cards = "".join(
        f"<div class='block'><h3>{_e(title)}</h3>{_ul(items)}</div>" for title, items in present
    )
    return (
        "<section id='next'><div class='wrap'>"
        f"<h2>{_e(lab['important_next'])}</h2>"
        f"<div class='wall two'>{cards}</div>"
        "</div></section>"
    )


def _sources(source_documents, lab: dict) -> str:
    docs = list(source_documents or [])
    if not docs:
        return ""
    grouped: dict[str, list[dict]] = {}
    for src in docs:
        grouped.setdefault(str(src.get("provider") or "Provider"), []).append(src)
    parts = []
    for provider, items in grouped.items():
        parts.append(f"<dt>{_e(provider)}</dt>")
        for src in items:
            doc_type = str(src.get("doc_type") or "document").replace("_", " ").title()
            plan_name = str(src.get("plan_name") or "").strip()
            prefix = f"{doc_type} - {plan_name}" if plan_name else doc_type
            filename = src.get("filename") or "Provider document"
            url = str(src.get("url") or "").strip()
            if url.startswith(("http://", "https://")):
                link = f' &middot; <a href="{_e(url)}" rel="noopener">{_e(lab["open_doc"])}</a>'
            else:
                link = ""
            parts.append(f"<dd>{_e(prefix)}: {_e(filename)}{link}</dd>")
    return (
        "<section id='sources'><div class='wrap'>"
        f"<h2>{_e(lab['sources'])}</h2>"
        f"{_p(lab['sources_note'], 'prose muted')}"
        f"<dl class='sources'>{''.join(parts)}</dl>"
        "</div></section>"
    )


def _footer(client_analysis: dict, lab: dict) -> str:
    return (
        "<footer><div class='wrap'>"
        f"<p class='line'>{_e(lab['notice'])}</p>"
        f"{_p(lab['broker_review'])}"
        f"{_p(client_analysis.get('disclaimer'))}"
        "</div></footer>"
    )


def build_html(
    *,
    client_analysis: dict,
    results: list[dict],
    language: str = "English",
    source_documents: list[dict] | None = None,
) -> str:
    """The whole report as one HTML document. Same arguments as the PDF."""
    client_analysis = client_analysis or {}
    results = list(results or [])
    lab = all_labels(language)
    title = _e(client_analysis.get("report_title")) or "Ashlar Insurance Comparative Analysis"
    body = "".join([
        _masthead(client_analysis, results, lab, language),
        # Scope before price: this strip sits above the first premium on the page.
        _scope_strip(client_analysis, results, lab, language),
        _context(client_analysis, lab),
        _plans(client_analysis, results, lab),
        _comparison(client_analysis, results, lab, language),
        _differences(client_analysis, lab),
        _recommendation(client_analysis, lab),
        _next_steps(client_analysis, lab),
        _sources(source_documents, lab),
        _footer(client_analysis, lab),
    ])
    return (
        "<!doctype html>\n"
        f'<html lang="{"el" if is_greek(language) else "en"}">\n'
        "<head>\n<meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        '<meta name="author" content="Ashlar Assurance">\n'
        f'<meta name="description" content="{_e(lab["subtitle"])}">\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        f'<link rel="stylesheet" href="{FONTS_HREF}">\n'
        f"<style>{CSS}</style>\n</head>\n"
        f"<body>{body}</body>\n</html>\n"
    )


def build_html_bytes(**kwargs) -> bytes:
    """UTF-8 bytes, for a download button or a file write."""
    return build_html(**kwargs).encode("utf-8")
