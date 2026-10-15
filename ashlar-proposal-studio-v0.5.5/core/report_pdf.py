"""Ashlar client-facing PDF report generator using ReportLab."""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape, quoteattr

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
)

from .client_analysis import plan_display_name, premium_display, client_facing_deductible, find_plan_narrative, coverage_scope_note
from .report_labels import all_labels as _labels, category_label, topic_label
from .benefit_state import ACTION, COVERED, NOT_COVERED, SUB_LIMIT
from .benefit_state import mark as benefit_mark

# The Ashlar palette. The names on the left are the roles the rest of this
# module already uses; the values are the house tokens, so the PDF, the HTML
# page and the website are the same document in three media. The old values
# (a navy masthead, a violet accent, a web-default green and gold) belonged to
# no Ashlar surface and made the client's PDF look like a different firm's.
INK = colors.HexColor("#1B2432")          # type and dark surfaces: not black, blue in it
NAVY = INK                                # masthead / table header
NAVY2 = colors.HexColor("#2A3444")        # mortar on dark surfaces
MUTED = colors.HexColor("#6B6256")        # warm grey, reads against limestone
PURPLE = colors.HexColor("#70181C")       # the one accent: oxblood
OXBLOOD = PURPLE
GOLD = colors.HexColor("#B88A2B")         # amber, caution only
AMBER = GOLD
GREEN = colors.HexColor("#4A6E6B")        # verdigris: covered / available
VERDIGRIS = GREEN
BORDER = colors.HexColor("#D7CDBC")       # mortar: 1px joints between blocks
LIGHT = colors.HexColor("#F9F6EE")        # the quietest surface inside a block
PAPER = colors.HexColor("#F2EDE4")        # limestone ground
WHITE = colors.HexColor("#F9F6EE")        # never pure white on an Ashlar surface



def _register_fonts():
    regular_candidates = [
        "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    bold_candidates = [
        "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    reg = next((p for p in regular_candidates if Path(p).exists()), None)
    bold = next((p for p in bold_candidates if Path(p).exists()), None)
    if reg and bold:
        pdfmetrics.registerFont(TTFont("AshlarSans", reg))
        pdfmetrics.registerFont(TTFont("AshlarSansBold", bold))
        return "AshlarSans", "AshlarSansBold"
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = _register_fonts()


def _p(text, style):
    return Paragraph(str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)


# Symbol as well as hue, so the state still reads in a black-and-white printout
# and for a colour-blind reader. "unknown" gets no mark: a benefit the
# documents never specified is not a fifth state, it is plain words.
MARK_SYMBOL = {COVERED: "\u25cf", ACTION: "\u25cb", SUB_LIMIT: "\u25b2", NOT_COVERED: "\u2715"}
MARK_COLOUR = {COVERED: "#4A6E6B", ACTION: "#1B2432", SUB_LIMIT: "#B88A2B", NOT_COVERED: "#70181C"}


def _marked(cell: dict, style):
    """One comparison cell: the state's symbol, then the text it applies to."""
    state = cell.get("state")
    text = str(cell.get("text") or "Not specified")
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if state not in MARK_SYMBOL:
        return Paragraph(f"<font color='#6B6256'>{safe}</font>", style)
    colour = MARK_COLOUR[state]
    if state == NOT_COVERED:
        safe = f"<font color='{colour}'>{safe}</font>"
    return Paragraph(f"<font color='{colour}'>{MARK_SYMBOL[state]}</font> {safe}", style)


def build_pdf_bytes(*, client_analysis: dict, results: list[dict], language: str = "English", source_documents: list[dict] | None = None) -> bytes:
    lab = _labels(language)
    buf = io.BytesIO()
    page = landscape(A4)
    doc = BaseDocTemplate(
        buf, pagesize=page, leftMargin=16*mm, rightMargin=16*mm,
        topMargin=17*mm, bottomMargin=14*mm,
        title=client_analysis.get("report_title") or "Ashlar Insurance Comparative Analysis",
        author="Ashlar Assurance",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")

    def on_page(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(NAVY); canvas.rect(0, page[1]-8*mm, page[0], 8*mm, stroke=0, fill=1)
        canvas.setFillColor(GOLD); canvas.rect(0, page[1]-8*mm, 4*mm, 8*mm, stroke=0, fill=1)
        canvas.setFont(FONT_BOLD, 8); canvas.setFillColor(WHITE)
        canvas.drawString(15*mm, page[1]-5.3*mm, "ASHLAR ASSURANCE")
        canvas.setFont(FONT, 7); canvas.setFillColor(MUTED)
        canvas.drawString(15*mm, 6*mm, lab["footer"])
        canvas.drawRightString(page[0]-15*mm, 6*mm, f"{date.today().strftime('%d %b %Y')}  |  {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.addPageTemplates(PageTemplate(id="main", frames=[frame], onPage=on_page))
    styles = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName=FONT_BOLD, fontSize=22, leading=27, textColor=INK, spaceAfter=8)
    H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName=FONT_BOLD, fontSize=14, leading=18, textColor=INK, spaceBefore=5, spaceAfter=6)
    Body = ParagraphStyle("Body", parent=styles["BodyText"], fontName=FONT, fontSize=9.2, leading=13.2, textColor=INK, spaceAfter=5)
    Small = ParagraphStyle("Small", parent=Body, fontSize=7.3, leading=9.6, textColor=MUTED)
    WhiteH = ParagraphStyle("WhiteH", parent=H1, textColor=WHITE, fontSize=25, leading=29)
    WhiteBody = ParagraphStyle("WhiteBody", parent=Body, textColor=colors.HexColor("#C9C0B2"), fontSize=10.5, leading=14.5)
    Bullet = ParagraphStyle("Bullet", parent=Body, leftIndent=10, firstLineIndent=-7, bulletIndent=0)

    story = []
    # Cover card: one-column layout with enough vertical room for 2–3 title lines.
    cover = Table([
        [_p("ASHLAR ASSURANCE", ParagraphStyle("Eyebrow", parent=Body, fontName=FONT_BOLD, fontSize=8.5, textColor=GOLD))],
        [_p(client_analysis.get("report_title") or "Insurance Comparative Analysis", WhiteH)],
        [_p(client_analysis.get("client_name") or "Client", ParagraphStyle("Client", parent=WhiteH, fontSize=16.5, leading=20))],
        [_p(lab["subtitle"], WhiteBody)],
    ], colWidths=[doc.width], rowHeights=[10*mm, 42*mm, 12*mm, 17*mm])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), NAVY), ("BOX", (0,0), (-1,-1), 0, NAVY),
        ("LEFTPADDING", (0,0), (-1,-1), 10*mm), ("RIGHTPADDING", (0,0), (-1,-1), 10*mm),
        ("TOPPADDING", (0,0), (-1,-1), 3*mm), ("BOTTOMPADDING", (0,0), (-1,-1), 2*mm),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story += [Spacer(1, 10*mm), cover, PageBreak()]

    scope_note = str(client_analysis.get("coverage_scope_note") or "").strip() or coverage_scope_note(results, language=language)
    if scope_note:
        strip = Table([[_p(lab["scope_warning"], ParagraphStyle("ScopeH", parent=H2, textColor=GOLD, spaceBefore=0)),
                        _p(scope_note, Body)]], colWidths=[62*mm, doc.width-62*mm])
        strip.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), LIGHT), ("BOX", (0,0), (-1,-1), .4, BORDER),
            ("LINEBEFORE", (0,0), (0,-1), 1.4, GOLD), ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
            ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        story += [strip, Spacer(1, 5*mm)]

    story += [_p(lab["context"], H1), _p(client_analysis.get("client_needs_summary") or client_analysis.get("client_priorities") or "No specific priorities supplied.", Body), Spacer(1, 3*mm)]
    profile = client_analysis.get("client_profile")
    if profile and profile != "Not supplied":
        story += [_p(lab["profile"], H2), _p(profile, Body)]
    story += [_p(lab["exec"], H2), _p(client_analysis.get("executive_summary") or "", Body), PageBreak()]

    # Plans
    narrative_plans = client_analysis.get("plans", [])
    for result in results:
        a = result.get("analysis") or {}
        key = (a.get("provider") or result.get("provider"), a.get("plan_name") or result.get("target_plan"))
        n = find_plan_narrative(narrative_plans, result)
        story += [_p(f"{key[0]} - {key[1]}", H1)]
        facts = [
            [lab["f_premium"], premium_display(a), lab["f_limit"], a.get("annual_limit") or "Not specified"],
            [lab["f_deductible"], client_facing_deductible(a.get("deductible_or_excess") or "Not specified"), lab["f_area"], a.get("area_of_cover") or "Not specified"],
        ]
        fact_tbl = Table([[ _p(c, Small if i%2==0 else Body) for i,c in enumerate(row)] for row in facts], colWidths=[30*mm, 85*mm, 30*mm, 105*mm])
        fact_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), WHITE), ("GRID", (0,0), (-1,-1), .35, BORDER),
            ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
            ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        story += [fact_tbl, Spacer(1, 4*mm), _p(n.get("summary") or "", Body)]
        cols = []
        for title, items, accent in [(lab["strengths"], n.get("strengths") or [], GREEN), (lab["consider"], n.get("considerations") or [], GOLD)]:
            parts = [_p(title, ParagraphStyle(title, parent=H2, textColor=accent))]
            parts += [_p("• " + str(x), Bullet) for x in items[:5]]
            cols.append(parts)
        two = Table([cols], colWidths=[125*mm, 125*mm])
        two.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 4*mm)]))
        story += [two, PageBreak()]

    # comparison
    story += [_p(lab["compare"], H1), _p(lab["compare_note"], Small)]
    matrix = client_analysis.get("comparison_matrix") or []
    names = [plan_display_name(r) for r in results]
    header = [_p(lab["benefit"], ParagraphStyle("TH", parent=Small, fontName=FONT_BOLD, textColor=WHITE))] + [_p(n, ParagraphStyle("TH2", parent=Small, fontName=FONT_BOLD, textColor=WHITE, alignment=TA_CENTER)) for n in names]
    data = [header]
    band_rows: list[int] = []
    seen_category = None
    for row in matrix:
        category = str(row.get("category") or "").strip()
        if category and category != seen_category:
            seen_category = category
            band_rows.append(len(data))
            data.append([_p(category_label(category, language), ParagraphStyle("Band", parent=Small, fontName=FONT_BOLD, textColor=MUTED))]
                        + [_p("", Small)] * len(names))
        topic = _p(topic_label(row.get("topic"), language), ParagraphStyle("Topic", parent=Small, fontName=FONT_BOLD, textColor=INK))
        values, marks = row.get("values") or {}, row.get("marks") or {}
        is_benefit = str(row.get("category") or "") == "Benefits"
        cells = []
        for n in names:
            raw = values.get(n)
            if not is_benefit:
                cells.append(_p(raw or "Not specified", Small))
                continue
            # Recomputed when the stored matrix predates the marks, so an older
            # case renders with its states rather than losing them.
            cells.append(_marked(marks.get(n) or benefit_mark(raw), Small))
        data.append([topic] + cells)
    first = 38*mm; other = (doc.width-first)/max(len(names),1)
    comp = Table(data, colWidths=[first]+[other]*len(names), repeatRows=1)
    comp.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("GRID", (0,0), (-1,-1), .3, BORDER), ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    for i in range(1, len(data)):
        if i in band_rows:
            comp.setStyle(TableStyle([
                ("SPAN", (0,i), (-1,i)), ("BACKGROUND", (0,i), (-1,i), PAPER),
            ]))
        elif i % 2 == 0:
            comp.setStyle(TableStyle([("BACKGROUND", (0,i), (-1,i), LIGHT)]))
    # The symbols are no use to a client who was never told what they mean.
    # One line, above the table: the reader meets the marks already knowing
    # what they are, and the key cannot be orphaned onto a page of its own or
    # push the table off this one.
    key_parts = []
    for state, key in ((COVERED, "mark_covered"), (ACTION, "mark_action"),
                       (SUB_LIMIT, "mark_sub_limit"), (NOT_COVERED, "mark_not_covered")):
        safe = str(lab[key]).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        key_parts.append(f"<font color='{MARK_COLOUR[state]}'>{MARK_SYMBOL[state]}</font> {safe}")
    legend = Paragraph("&nbsp;&nbsp;&nbsp;".join(key_parts), Small)
    story += [legend, Spacer(1, 2*mm), comp, PageBreak()]

    # Differences and assessment
    story += [_p(lab["diff"], H1)]
    for d in (client_analysis.get("key_differences") or [])[:6]:
        card = Table([[
            _p(d.get("title") or "Difference", ParagraphStyle("DT", parent=H2, textColor=PURPLE)),
            _p(d.get("analysis") or "", Body),
            _p(d.get("client_impact") or "", Small),
        ]], colWidths=[55*mm, 125*mm, 70*mm])
        card.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), WHITE), ("BOX", (0,0), (-1,-1), .4, BORDER), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
        story += [card, Spacer(1, 2.5*mm)]
    story += [PageBreak(), _p(lab["assessment"], H1)]
    ass = client_analysis.get("ashlar_assessment") or {}
    story += [_p(ass.get("headline") or lab["our_view"], ParagraphStyle("AHead", parent=H2, fontSize=16.5, leading=21, textColor=PURPLE))]
    if ass.get("recommended_provider") or ass.get("recommended_plan"):
        story += [_p(f"{lab["preferred"]}: {ass.get('recommended_provider','')} {ass.get('recommended_plan','')}", ParagraphStyle("Rec", parent=H2, textColor=GREEN))]
    for reason in ass.get("reasoning") or []:
        story += [_p("• " + str(reason), Bullet)]
    if ass.get("alternative_provider") or ass.get("alternative_plan"):
        story += [Spacer(1, 3*mm), _p(lab["alternative"], H2), _p(f"{ass.get('alternative_provider','')} {ass.get('alternative_plan','')}", Body), _p(ass.get("alternative_reason") or "", Body), _p(ass.get("when_the_alternative_may_be_better") or "", Small)]
    if ass.get("extras_provider") or ass.get("extras_plan"):
        story += [Spacer(1, 2*mm), _p(lab["extras"], H2), _p(f"{ass.get('extras_provider','')} {ass.get('extras_plan','')}", Body), _p(ass.get("extras_reason") or "", Small)]
    if ass.get("budget_provider") or ass.get("budget_plan"):
        story += [Spacer(1, 2*mm), _p(lab["budget"], H2), _p(f"{ass.get('budget_provider','')} {ass.get('budget_plan','')}", Body), _p(ass.get("budget_reason") or "", Small)]

    story += [PageBreak(), _p(lab["important_next"], H1), _p(lab["important"], H2)]
    for item in client_analysis.get("important_considerations") or []:
        story += [_p("• " + str(item), Bullet)]
    story += [_p(lab["next"], H2)]
    for item in client_analysis.get("next_steps") or []:
        story += [_p("• " + str(item), Bullet)]
    story += [Spacer(1, 5*mm), _p(lab["notice"], H2), _p(client_analysis.get("disclaimer") or "", Small)]

    source_documents = source_documents or []
    if source_documents:
        story += [PageBreak(), _p(lab["sources"], H1), _p(lab["sources_note"], Small), Spacer(1, 3*mm)]
        grouped: dict[str, list[dict]] = {}
        for src in source_documents:
            provider = str(src.get("provider") or "Provider")
            grouped.setdefault(provider, []).append(src)
        for provider, docs_for_provider in grouped.items():
            story += [_p(provider, H2)]
            for src in docs_for_provider:
                filename = str(src.get("filename") or "Provider document")
                doc_type = str(src.get("doc_type") or "document").replace("_", " ").title()
                plan_name = str(src.get("plan_name") or "").strip()
                prefix = f"{doc_type} - {plan_name}" if plan_name else doc_type
                url = str(src.get("url") or "").strip()
                if url:
                    link_markup = (
                        f"<b>{xml_escape(prefix)}</b>: {xml_escape(filename)} "
                        f"- <link href={quoteattr(url)} color='#70181C'>{xml_escape(lab['open_doc'])}</link>"
                    )
                    story += [Paragraph(link_markup, Body)]
                else:
                    story += [_p(f"{prefix}: {filename} (supplied separately in the client pack)", Body)]
            story += [Spacer(1, 2*mm)]

    doc.build(story)
    return buf.getvalue()
