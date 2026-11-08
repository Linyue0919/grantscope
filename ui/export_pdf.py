"""PDF exports (spec section 9): single grant (detail panel) and saved summary.

Built locally from OpportunityView fields only; no network or LLM calls. Uses the
bundled DejaVu Sans font so marks (●◐○), curly quotes and dashes never render as
missing-glyph boxes; evidence marks are also spelled out in words.
"""
from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from ui.view_model import NOT_STATED, RECOMMENDATION_LABELS, agency_display_name, fmt_date, mark, to_eastern

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
NAVY, TEXT, MUTED, BORDER = (31, 78, 156), (27, 34, 48), (75, 85, 101), (217, 222, 229)
FOOTER = "GrantScope never guarantees eligibility. Confirm with the official announcement."


class BriefPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(16, 16, 16)

    def footer(self):
        self.set_y(-13)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, FOOTER, align="L")
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")

    # --- small writing helpers
    def text_block(self, text, size=10, bold=False, color=TEXT, h=5.2):
        self.set_font("DejaVu", "B" if bold else "", size)
        self.set_text_color(*color)
        self.multi_cell(0, h, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def heading(self, text, size=12):
        self.ln(2)
        self.text_block(text, size=size, bold=True)
        self.ln(0.5)

    def bullets(self, items, numbered=False, size=10):
        for i, item in enumerate(items, 1):
            self.set_font("DejaVu", "", size)
            self.set_text_color(*TEXT)
            prefix = f"{i}." if numbered else "•"
            self.cell(6, 5.2, prefix)
            self.multi_cell(0, 5.2, item, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def link_line(self, label, url):
        if not url:
            return
        self.set_font("DejaVu", "", 10)
        self.set_text_color(*NAVY)
        self.cell(0, 5.5, f"{label} ↗", link=url, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def rule(self):
        self.set_draw_color(*BORDER)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)


def _evidence(status):
    return f"{mark(status)} {status}"


def _deadline_text(view):
    if view.status == "forecasted":
        return "Not open yet (forecast)"
    if view.deadline_date:
        days = f" ({view.days_left} days left)" if view.days_left is not None else ""
        return f"{fmt_date(view.deadline_date)}{days}"
    return "Not stated"


def _fit_text(view):
    return f"{view.fit_score}/100 · {view.fit_tier} fit" if view.fit_score is not None else "Not scored"


def _plan_url(view):
    if view.plan_url and view.plan_page:
        return f"{view.plan_url}#page={view.plan_page}"
    return view.plan_url


def _grant_section(pdf, view):
    pdf.text_block(view.title, size=14, bold=True, h=6.5)
    pdf.text_block(view.agency_full_name, size=10, color=MUTED)
    pdf.ln(2)
    pdf.text_block(f"Recommendation · {RECOMMENDATION_LABELS.get(view.section, '')}  ·  Fit {_fit_text(view)}",
                   size=10, bold=True, color=NAVY)
    pdf.text_block(view.recommendation_sentence, size=10)

    pdf.heading("Application readiness", size=11)
    award = view.award_text if view.award_status != NOT_STATED else "Not stated"
    facts = [
        ("Deadline", _deadline_text(view)),
        ("Eligibility", f"{view.eligibility_short} ({_evidence(view.eligibility_status)})"),
        ("Effort", f"{view.effort_level} ({_evidence(view.effort_status)})"),
        ("Award", f"{award} ({_evidence(view.award_status)}; {view.expected_awards_text})"),
        ("Cost share", f"{view.cost_share_text} ({_evidence(view.cost_share_status)})"),
    ]
    for label, value in facts:
        pdf.set_font("DejaVu", "B", 10)
        pdf.set_text_color(*TEXT)
        pdf.cell(28, 5.4, label)
        pdf.set_font("DejaVu", "", 10)
        pdf.multi_cell(0, 5.4, value, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.heading(f"Why it matches your strategic plan · {view.fit_level} fit", size=11)
    pdf.bullets(view.fit_reasons or ["No plan goal was matched in the listing text."])
    if view.plan_quote:
        pdf.text_block(f"Your plan ({view.plan_quote_goal}): “{view.plan_quote}”", size=9, color=MUTED)

    if view.unclear_reason:
        pdf.heading("What's unclear", size=11)
        pdf.text_block(f"Not stated: {view.unclear_reason}", size=10)

    if view.eligibility_quote:
        pdf.heading("Eligibility evidence", size=11)
        pdf.text_block(f"“{view.eligibility_quote}”", size=9, color=MUTED)
        pdf.text_block(f"Source: {view.eligibility_source or 'Grants.gov'}", size=8, color=MUTED)

    if view.next_steps:
        pdf.heading("Next steps", size=11)
        pdf.bullets(view.next_steps, numbered=True)
    if view.officer_questions:
        pdf.heading("Questions for the program officer", size=11)
        pdf.bullets(view.officer_questions)

    pdf.heading("Links", size=11)
    pdf.link_line("Grants.gov listing", view.grants_gov_url)
    pdf.link_line("Funding notice (NOFO)", view.nofo_url)
    pdf.link_line(f"{view.plan_name or 'Agency'} strategic plan" + (f", p. {view.plan_page}" if view.plan_page else ""),
                  _plan_url(view))
    if view.opportunity_number:
        pdf.text_block(f"Opportunity number: {view.opportunity_number}", size=8, color=MUTED)


def _cover(pdf, title, agency, retrieved_at, count):
    pdf.text_block("GrantScope · " + title, size=18, bold=True, color=NAVY, h=8)
    pdf.text_block(agency_display_name(agency), size=12, bold=True)
    generated = datetime.now()
    retrieved = to_eastern(retrieved_at) if retrieved_at else None
    pdf.text_block(f"Generated {generated:%b %-d, %Y, %-I:%M %p}", size=9, color=MUTED)
    pdf.text_block("Data: Grants.gov" + (f", retrieved {retrieved:%b %-d, %Y, %-I:%M %p} ET" if retrieved else ""),
                   size=9, color=MUTED)
    pdf.text_block(f"{count} opportunit{'ies' if count != 1 else 'y'}", size=9, color=MUTED)
    pdf.ln(3)
    pdf.rule()


def build_grant_pdf(view, agency):
    pdf = BriefPDF()
    pdf.add_page()
    _cover(pdf, "Opportunity summary", agency, view.retrieved_at, 1)
    _grant_section(pdf, view)
    return bytes(pdf.output())


def build_summary_pdf(views, agency):
    pdf = BriefPDF()
    pdf.add_page()
    retrieved = next((v.retrieved_at for v in views if v.retrieved_at), None)
    _cover(pdf, "Funding summary", agency, retrieved, len(views))
    pdf.heading("Overview", size=12)
    widths = (68, 25, 27, 30, 34)
    pdf.set_font("DejaVu", "B", 8.5)
    pdf.set_fill_color(238, 241, 245)
    for w, h in zip(widths, ("Opportunity", "Deadline", "Award", "Fit", "Section")):
        pdf.cell(w, 6.5, h, border=0, fill=True)
    pdf.ln(6.5)
    pdf.set_font("DejaVu", "", 8.5)
    for v in views:
        title = v.short_name if len(v.short_name) < 44 else v.short_name[:42] + "…"
        award = v.award_chip if v.award_status != NOT_STATED else "Not stated"
        deadline = fmt_date(v.deadline_date) if v.deadline_date else ("Forecast" if v.status == "forecasted" else "Not stated")
        row = (title, deadline, award, f"{v.fit_score}/100 {v.fit_tier}" if v.fit_score is not None else "-",
               RECOMMENDATION_LABELS.get(v.section, ""))
        for w, cell in zip(widths, row):
            pdf.cell(w, 6, cell)
        pdf.ln(6)
        pdf.set_draw_color(*BORDER)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    for v in views:
        pdf.add_page()
        _grant_section(pdf, v)
    return bytes(pdf.output())


def pdf_filename(agency_short, kind="saved"):
    safe = "".join(c for c in (agency_short or "Agency") if c.isalnum()) or "Agency"
    return f"GrantScope_{safe}_{kind}_{datetime.now():%Y-%m-%d}.pdf"
