"""
Phase 13 — shared PDF document infrastructure. Every generated PDF in this
project (the 3 per-record documents below, plus the 9 REPORT_BUILDERS/
Movement History exports in frontend/reports.py) renders through
render_document()/render_tabular_report() here, so a header/footer/style/
currency/date change is made once and every document picks it up — see
docs/project_memory.md §13 for the full disclosure of what this replaced.

ReportLab only, per this phase's own standing rules — no WeasyPrint, no
svglib, no new PDF/rendering library. Two real constraints that follow
directly from that and are disclosed rather than silently worked around:

1. The Bangladeshi Taka sign (৳, U+09F3) has no glyph in any of
   ReportLab's built-in fonts (Helvetica/Times/Courier are the standard
   14 PDF fonts — WinAnsi/Latin-1 encoded, no Bengali script coverage at
   all), and this repo ships no TTF font to register instead. PDFs use
   the ASCII prefix "Tk" for currency; every web page keeps the real ৳
   glyph unchanged (a browser's own font stack has no such gap).
2. SystemSettings.company_logo accepts SVG (frontend/validators.py), but
   ReportLab's Image flowable needs a raster image PIL can open — SVG
   isn't one, and rasterizing it would mean adding svglib or similar,
   which the standing rules forbid. An SVG logo therefore renders in the
   PDF header the same way a *missing* logo does: company name in type,
   not a broken image box. It still displays correctly everywhere on the
   web (a plain <img src>, which every browser handles natively).
"""
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)

# ---------------------------------------------------------------- Palette
# tokens.css's own values (frontend/static/css/tokens.css) — not
# approximated, so a PDF and the web app are provably the same brand,
# not just similarly-colored.
BRAND_INDIGO = colors.HexColor("#3D4FE0")
BRAND_AMBER = colors.HexColor("#F2A93B")
INK = colors.HexColor("#10162B")
SLATE = colors.HexColor("#64708A")
SLATE_LIGHT = colors.HexColor("#EEF0FD")
BORDER = colors.HexColor("#D1D5DB")
ROW_TINT = colors.HexColor("#F3F4F6")
SUCCESS = colors.HexColor("#1FA97A")
DANGER = colors.HexColor("#E14B4B")
WARNING = colors.HexColor("#9C6B12")

STATUS_COLORS = {
    "success": SUCCESS, "danger": DANGER, "warning": WARNING,
    "indigo": BRAND_INDIGO, "slate": SLATE,
}

PORTRAIT = letter
LANDSCAPE = landscape(letter)
MARGIN = 20 * mm
HEADER_H = 30 * mm
FOOTER_H = 16 * mm

CURRENCY_PREFIX = "Tk"  # see module docstring, point 1


def format_currency(value):
    if value is None:
        value = Decimal("0")
    return f"{CURRENCY_PREFIX} {Decimal(value):,.2f}"


def format_date(value):
    if not value:
        return "—"
    if isinstance(value, datetime):
        value = timezone.localtime(value).date()
    return value.strftime("%d %b %Y")


def format_datetime(value):
    if not value:
        return "—"
    return timezone.localtime(value).strftime("%d %b %Y, %I:%M %p")


# ------------------------------------------------------------------ Styles

def _styles():
    """Fresh ParagraphStyle objects per call — ReportLab styles carry
    mutable state (a shared getSampleStyleSheet() instance is what every
    other generator in this project already mutates in place, Phase 8.98d's
    own risk this sidesteps entirely). Three sizes, per the visual-quality
    bar: 20pt document title, 10-11pt section/body, 7.5-8pt small print."""
    return {
        "doc_title": ParagraphStyle("doc_title", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK),
        "company_name": ParagraphStyle("company_name", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=INK),
        "meta_label": ParagraphStyle("meta_label", fontName="Helvetica", fontSize=8, leading=11, textColor=SLATE, alignment=TA_RIGHT),
        "meta_value": ParagraphStyle("meta_value", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=INK, alignment=TA_RIGHT),
        "section_heading": ParagraphStyle("section_heading", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=SLATE, spaceAfter=3),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, leading=11, textColor=SLATE),
        "totals_label": ParagraphStyle("totals_label", fontName="Helvetica", fontSize=9.5, leading=14, textColor=SLATE, alignment=TA_RIGHT),
        "totals_value": ParagraphStyle("totals_value", fontName="Helvetica", fontSize=9.5, leading=14, textColor=INK, alignment=TA_RIGHT),
        "grand_total_label": ParagraphStyle("grand_total_label", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=INK, alignment=TA_RIGHT),
        "grand_total_value": ParagraphStyle("grand_total_value", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=BRAND_INDIGO, alignment=TA_RIGHT),
        "sig_name": ParagraphStyle("sig_name", fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=INK),
    }


# --------------------------------------------------------- Numbered pages
# "Page N of M" needs the total page count, which isn't known until the
# whole document has already been built once — the standard ReportLab
# recipe (buffer every page's drawing, then replay each one adding the
# now-known total on save()) rather than a second full render pass.
class _NumberedCanvas(pdfcanvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_page_number(total)
            super().showPage()
        super().save()

    def _draw_page_number(self, total):
        page_w, _ = self._pagesize
        self.setFont("Helvetica", 7.5)
        self.setFillColor(SLATE)
        self.drawRightString(page_w - MARGIN, FOOTER_H - 6 * mm, f"Page {self.getPageNumber()} of {total}")


# --------------------------------------------------------- Page furniture

def _draw_header(canvas, page_size, profile, watermark_text=None):
    canvas.saveState()
    page_w, page_h = page_size
    top = page_h - MARGIN

    logo_w = 0
    if profile["logo_path"] and not profile["logo_is_svg"]:
        try:
            from reportlab.lib.utils import ImageReader
            img = ImageReader(profile["logo_path"])
            iw, ih = img.getSize()
            logo_h = 16 * mm
            logo_w = logo_h * (iw / float(ih))
            canvas.drawImage(
                img, MARGIN, top - logo_h, width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            # A corrupt/unreadable file on disk must never take the whole
            # PDF down — same fallback as "no logo at all", below.
            logo_w = 0

    text_x = MARGIN + (logo_w + 6 * mm if logo_w else 0)
    canvas.setFont("Helvetica-Bold", 17)
    canvas.setFillColor(INK)
    canvas.drawString(text_x, top - 6 * mm, profile["name"] or "Company name not set")

    detail_parts = [p for p in (
        (profile["address"] or "").replace("\n", ", "), profile["phone"], profile["email"],
        profile["tax_number"] and f"Tax/BIN: {profile['tax_number']}",
    ) if p]
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(SLATE)
    y = top - 11 * mm
    max_chars = 130 if page_w > page_h else 95
    for line in _wrap_detail_line(detail_parts, max_chars):
        canvas.drawString(text_x, y, line)
        y -= 3.6 * mm

    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.75)
    canvas.line(MARGIN, top - HEADER_H + 4 * mm, page_w - MARGIN, top - HEADER_H + 4 * mm)

    if watermark_text:
        canvas.saveState()
        canvas.translate(page_w / 2, page_h / 2)
        canvas.rotate(38)
        canvas.setFillColor(DANGER, alpha=0.14)
        canvas.setFont("Helvetica-Bold", 66)
        canvas.drawCentredString(0, 0, watermark_text)
        canvas.restoreState()

    canvas.restoreState()


def _wrap_detail_line(parts, max_chars):
    """Company address/phone/email/tax-number joined with ' | ', wrapped
    onto at most 2 lines rather than overflowing the header band — a
    plain char-budget wrap (this is one short line of plain text, not a
    place that needs Paragraph's full layout engine)."""
    joined = "  |  ".join(parts)
    if len(joined) <= max_chars or len(parts) < 2:
        return [joined] if joined else []
    mid = len(parts) // 2 or 1
    return ["  |  ".join(parts[:mid]), "  |  ".join(parts[mid:])]


def _draw_footer(canvas, page_size, profile, generated_at):
    canvas.saveState()
    page_w, _ = page_size
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, FOOTER_H, page_w - MARGIN, FOOTER_H)

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SLATE)
    canvas.drawString(MARGIN, FOOTER_H - 6 * mm, f"Generated {format_datetime(generated_at)}")
    canvas.drawString(MARGIN, FOOTER_H - 10 * mm, "This is a computer-generated document.")
    canvas.drawRightString(page_w - MARGIN, FOOTER_H - 10 * mm, (profile["name"] or "")[:60])
    # Page N of M is drawn by _NumberedCanvas itself, once the total page
    # count is known — see that class.
    canvas.restoreState()


def _page_decorator(page_size, profile, watermark_text, generated_at):
    def _decorate(canvas, doc):
        _draw_header(canvas, page_size, profile, watermark_text)
        _draw_footer(canvas, page_size, profile, generated_at)
    return _decorate


def _frame(page_size):
    page_w, page_h = page_size
    return Frame(
        MARGIN, FOOTER_H, page_w - 2 * MARGIN, page_h - HEADER_H - FOOTER_H,
        id="body", leftPadding=0, rightPadding=0, topPadding=6 * mm, bottomPadding=0,
    )


def _make_doc(buffer, title, page_size, profile, watermark_text=None, generated_at=None):
    generated_at = generated_at or timezone.now()
    doc = BaseDocTemplate(
        buffer, pagesize=page_size, title=title,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    )
    decorate = _page_decorator(page_size, profile, watermark_text, generated_at)
    doc.addPageTemplates([PageTemplate(id="main", frames=[_frame(page_size)], onPage=decorate)])
    return doc


def _response(buffer, filename):
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# -------------------------------------------------------------- Tables

def _line_items_table(headers, rows, col_widths, aligns):
    """Styled header row (solid fill, light type), subtle alternating row
    shading, per-column alignment (money right, qty centre, text left) —
    the exact look every document type shares. `aligns`: one of 'L'/'C'/'R'
    per column, same order as `headers`."""
    align_map = {"L": "LEFT", "C": "CENTER", "R": "RIGHT"}
    data = [headers] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_TINT]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for col, align in enumerate(aligns):
        style.append(("ALIGN", (col, 0), (col, -1), align_map.get(align, "LEFT")))
    table.setStyle(TableStyle(style))
    return table


def _totals_table(lines):
    """`lines`: [(label, value_str, emphasized_bool), ...]. Right-aligned,
    sitting directly under the table (a Table of its own, floated right
    via colWidths + hAlign, not a separate flow) — grand total gets a
    rule above and heavier type."""
    styles = _styles()
    data = []
    style = [
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]
    for i, (label, value, emphasized) in enumerate(lines):
        label_style = styles["grand_total_label"] if emphasized else styles["totals_label"]
        value_style = styles["grand_total_value"] if emphasized else styles["totals_value"]
        data.append([Paragraph(label, label_style), Paragraph(value, value_style)])
        if emphasized:
            style.append(("LINEABOVE", (0, i), (-1, i), 1, INK))
            style.append(("TOPPADDING", (0, i), (-1, i), 6))
    table = Table(data, colWidths=[35 * mm, 40 * mm], hAlign="RIGHT")
    table.setStyle(TableStyle(style))
    return table


def _party_block(heading, lines):
    styles = _styles()
    body = [Paragraph(heading.upper(), styles["section_heading"])]
    for line in lines:
        if line:
            body.append(Paragraph(line, styles["body"]))
    table = Table([[body]], colWidths=[85 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SLATE_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _meta_block(doc_number, issue_date, status_label, status_variant, extra_lines=None):
    styles = _styles()
    rows = [
        [Paragraph("Document #", styles["meta_label"]), Paragraph(doc_number, styles["meta_value"])],
        [Paragraph("Issue date", styles["meta_label"]), Paragraph(format_date(issue_date), styles["meta_value"])],
        [Paragraph("Status", styles["meta_label"]), Paragraph(status_label, styles["meta_value"])],
    ]
    for label, value in (extra_lines or []):
        rows.append([Paragraph(label, styles["meta_label"]), Paragraph(value, styles["meta_value"])])
    table = Table(rows, colWidths=[28 * mm, 45 * mm], hAlign="RIGHT")
    status_color = STATUS_COLORS.get(status_variant, INK)
    table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("TEXTCOLOR", (1, 2), (1, 2), status_color),
    ]))
    return table


def _signature_block(entries):
    """entries: [{'role', 'name', 'timestamp', 'level'}, ...]. A ruled
    line under each name — this is the paper trail Phase 12/12.1's
    approval-authority work exists to produce; an admin-only approval
    shows the admin, by name, here."""
    styles = _styles()
    if not entries:
        return None
    cells = []
    for entry in entries:
        block = [
            Paragraph(entry["role"].upper(), styles["section_heading"]),
            Spacer(1, 10 * mm),
            Table([[""]], colWidths=[55 * mm], rowHeights=[0.1], style=TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.75, INK)])),
            Spacer(1, 2),
            Paragraph(entry["name"], styles["sig_name"]),
        ]
        detail_bits = [b for b in (entry.get("level"), entry.get("timestamp")) if b]
        if detail_bits:
            block.append(Paragraph(" &middot; ".join(detail_bits), styles["small"]))
        cells.append(block)
    table = Table([cells], colWidths=[60 * mm] * len(cells))
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return table


# --------------------------------------------------------- Public builders

def render_document(
    *, filename, doc_type_label, doc_number, issue_date, status_label, status_variant,
    table_headers, table_rows, col_widths, col_aligns,
    party=None, meta_extra=None, totals=None, signatures=None, watermark_text=None,
):
    """The shared shape every transactional document (Purchase Order,
    Sales Invoice, Stock Adjustment Note) is built from — see the Party
    block/Totals block/Signature block helpers above for what each
    optional section renders. `party`: (heading, [line, ...]) or None.
    `totals`: [(label, value_str, emphasized_bool), ...] or None.
    `signatures`: [{'role','name','timestamp','level'}, ...] or None."""
    from frontend.models import SystemSettings
    profile = SystemSettings.get_company_profile()
    styles = _styles()
    buffer = BytesIO()
    doc = _make_doc(buffer, f"{doc_type_label} {doc_number}", PORTRAIT, profile, watermark_text)

    elements = [Spacer(1, 2 * mm)]

    title_row = Table(
        [[Paragraph(doc_type_label.upper(), styles["doc_title"]), _meta_block(doc_number, issue_date, status_label, status_variant, meta_extra)]],
        colWidths=[95 * mm, 73 * mm],
    )
    title_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    elements += [title_row, Spacer(1, 6 * mm)]

    if party:
        heading, lines = party
        elements += [_party_block(heading, lines), Spacer(1, 8 * mm)]

    elements.append(_line_items_table(table_headers, table_rows, col_widths, col_aligns))
    elements.append(Spacer(1, 4 * mm))

    tail = []
    if totals:
        tail.append(_totals_table(totals))
        tail.append(Spacer(1, 10 * mm))
    if signatures:
        sig = _signature_block(signatures)
        if sig:
            tail.append(sig)
    if tail:
        elements.append(KeepTogether(tail))

    doc.build(elements, canvasmaker=_NumberedCanvas)
    return _response(buffer, filename)


def render_tabular_report(*, filename, title, headers, rows, filters_summary=None, watermark_text=None):
    """The shared shape for the 9 REPORT_BUILDERS exports and Movement
    History's export — a title, an optional filters line, then one wide
    table. Same header/footer/palette as render_document(), no party/
    totals/signature blocks (a report is plural by nature; a single
    "totals" line across mixed rows wouldn't mean anything). Wide tables
    (>6 columns) render landscape; narrower ones stay portrait."""
    from frontend.models import SystemSettings
    profile = SystemSettings.get_company_profile()
    styles = _styles()
    page_size = LANDSCAPE if len(headers) > 6 else PORTRAIT
    buffer = BytesIO()
    doc = _make_doc(buffer, title, page_size, profile, watermark_text)

    elements = [Spacer(1, 2 * mm), Paragraph(title.upper(), styles["doc_title"]), Spacer(1, 2 * mm)]
    if filters_summary:
        elements.append(Paragraph("Filters: " + "; ".join(filters_summary), styles["small"]))
    elements.append(Spacer(1, 4 * mm))

    display_rows = [[str(cell) for cell in row] for row in rows]
    if not display_rows:
        display_rows = [["No data available for the selected filters."] + [""] * (len(headers) - 1)]
    elements.append(_line_items_table(headers, display_rows, None, _guess_aligns(headers)))

    doc.build(elements, canvasmaker=_NumberedCanvas)
    return _response(buffer, filename)


def _guess_aligns(headers):
    """Report tables (REPORT_BUILDERS) don't carry per-column alignment
    metadata the way render_document()'s callers do — headers are plain
    strings. A conservative name-based guess (numeric-looking headers
    right-aligned, everything else left) beats left-aligning money."""
    numeric_hints = ("qty", "quantity", "cost", "price", "total", "value", "amount", "stock", "level", "rate", "confidence", "days", "change", "%")
    return ["R" if any(hint in h.lower() for hint in numeric_hints) else "L" for h in headers]
