from datetime import datetime
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)

# Rule: matches tokens.css exactly -- the PDF and web app share one brand.
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

# Workaround: ReportLab's fonts have no ৳ glyph; uses ASCII "Tk" instead.
CURRENCY_PREFIX = "Tk"


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


def _styles():
    # Workaround: fresh objects per call -- ReportLab styles carry mutable state.
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
        # Rule: matches _line_items_table()'s FONTSIZE so cells look uniform.
        "table_cell": ParagraphStyle("table_cell", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK),
        "table_cell_right": ParagraphStyle("table_cell_right", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK, alignment=TA_RIGHT),
        # Edge: header cells wrap too -- a long plain header would overflow.
        "table_header": ParagraphStyle("table_header", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white),
        "table_header_right": ParagraphStyle("table_header_right", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white, alignment=TA_RIGHT),
    }


# Workaround: buffers every page, then replays each with the now-known total.
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


def _draw_header(canvas, page_size, profile, watermark_text=None):
    canvas.saveState()
    page_w, page_h = page_size
    top = page_h - MARGIN

    logo_w = 0
    # Workaround: ReportLab can't rasterize SVG; an SVG logo renders as text.
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
            # Edge: a corrupt logo file falls back to no logo, not a crash.
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
    joined = "  |  ".join(parts)
    if len(joined) <= max_chars or len(parts) < 2:
        return [joined] if joined else []
    mid = len(parts) // 2 or 1
    return ["  |  ".join(parts[:mid]), "  |  ".join(parts[mid:])]


def _draw_footer(canvas, page_size, profile, generated_at, generated_by=None):
    canvas.saveState()
    page_w, _ = page_size
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, FOOTER_H, page_w - MARGIN, FOOTER_H)

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SLATE)
    generated_line = f"Generated {format_datetime(generated_at)}"
    if generated_by:
        generated_line += f" by {generated_by}"
    canvas.drawString(MARGIN, FOOTER_H - 6 * mm, generated_line)
    canvas.drawString(MARGIN, FOOTER_H - 10 * mm, "This is a computer-generated document.")
    canvas.drawRightString(page_w - MARGIN, FOOTER_H - 10 * mm, (profile["name"] or "")[:60])
    # Rule: page N of M is filled in later by _NumberedCanvas.
    canvas.restoreState()


def _page_decorator(page_size, profile, watermark_text, generated_at, generated_by=None):
    def _decorate(canvas, doc):
        _draw_header(canvas, page_size, profile, watermark_text)
        _draw_footer(canvas, page_size, profile, generated_at, generated_by)
    return _decorate


def _frame(page_size):
    page_w, page_h = page_size
    return Frame(
        MARGIN, FOOTER_H, page_w - 2 * MARGIN, page_h - HEADER_H - FOOTER_H,
        id="body", leftPadding=0, rightPadding=0, topPadding=6 * mm, bottomPadding=0,
    )


def _make_doc(buffer, title, page_size, profile, watermark_text=None, generated_at=None, generated_by=None):
    generated_at = generated_at or timezone.now()
    doc = BaseDocTemplate(
        buffer, pagesize=page_size, title=title,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    )
    decorate = _page_decorator(page_size, profile, watermark_text, generated_at, generated_by)
    doc.addPageTemplates([PageTemplate(id="main", frames=[_frame(page_size)], onPage=decorate)])
    return doc


def _response(buffer, filename):
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _line_items_table(headers, rows, col_widths, aligns):
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


def render_document(
    *, filename, doc_type_label, doc_number, issue_date, status_label, status_variant,
    table_headers, table_rows, col_widths, col_aligns,
    party=None, meta_extra=None, totals=None, signatures=None, watermark_text=None,
    generated_by=None,
):
    """Builds one transactional document PDF -- PO, Invoice, or Adjustment Note."""
    from frontend.models import SystemSettings
    profile = SystemSettings.get_company_profile()
    styles = _styles()
    buffer = BytesIO()
    doc = _make_doc(buffer, f"{doc_type_label} {doc_number}", PORTRAIT, profile, watermark_text, generated_by=generated_by)

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


def render_tabular_report(*, filename, title, headers, rows, filters_summary=None, watermark_text=None, generated_by=None):
    """Builds one report PDF: title, optional filters line, then a wide table."""
    from frontend.models import SystemSettings
    profile = SystemSettings.get_company_profile()
    styles = _styles()
    # Rule: more than 6 columns forces landscape -- keeps columns readable.
    page_size = LANDSCAPE if len(headers) > 6 else PORTRAIT
    buffer = BytesIO()
    doc = _make_doc(buffer, title, page_size, profile, watermark_text, generated_by=generated_by)

    elements = [Spacer(1, 2 * mm), Paragraph(title.upper(), styles["doc_title"]), Spacer(1, 2 * mm)]
    if filters_summary:
        elements.append(Paragraph("Filters: " + "; ".join(filters_summary), styles["small"]))
    elements.append(Spacer(1, 4 * mm))

    if not rows:
        rows = [["No data available for the selected filters."] + [""] * (len(headers) - 1)]

    # Workaround: colWidths=None auto-sizes to unwrapped width, clipping columns.
    aligns = _guess_aligns(headers)
    available_width = page_size[0] - 2 * MARGIN
    col_widths = _guess_col_widths(headers, aligns, available_width)
    cell_style = {"L": styles["table_cell"], "C": styles["table_cell"], "R": styles["table_cell_right"]}
    # Workaround: escape() first -- Paragraph parses its text as XML.
    display_rows = [
        [Paragraph(escape(str(cell)), cell_style[aligns[i]]) for i, cell in enumerate(row)]
        for row in rows
    ]
    header_style = {"L": styles["table_header"], "C": styles["table_header"], "R": styles["table_header_right"]}
    display_headers = [Paragraph(escape(str(h)), header_style[aligns[i]]) for i, h in enumerate(headers)]
    elements.append(_line_items_table(display_headers, display_rows, col_widths, aligns))

    doc.build(elements, canvasmaker=_NumberedCanvas)
    return _response(buffer, filename)


def _guess_aligns(headers):
    # Rule: guess numeric-looking headers right-aligned, others left.
    numeric_hints = ("qty", "quantity", "cost", "price", "total", "value", "amount", "stock", "level", "rate", "confidence", "days", "change", "%", "risk")
    return ["R" if any(hint in h.lower() for hint in numeric_hints) else "L" for h in headers]


def _guess_col_widths(headers, aligns, available_width):
    # Rule: 'R' columns get a narrow fixed width; 'L'/'C' split what's left.
    numeric_hint_width = 70
    # Assumption: widened per header -- a fixed 70pt wrapped long words mid-word.
    # Rule: matches _line_items_table's own LEFTPADDING(6) + RIGHTPADDING(6).
    cell_padding = 12
    for header, align in zip(headers, aligns):
        if align != "R":
            continue
        for word in str(header).split():
            numeric_hint_width = max(numeric_hint_width, stringWidth(word, "Helvetica-Bold", 8.5) + cell_padding + 2)

    text_cols = [i for i, a in enumerate(aligns) if a != "R"]
    numeric_cols = len(aligns) - len(text_cols)
    reserved = numeric_hint_width * numeric_cols
    text_width = max(60, (available_width - reserved) / max(len(text_cols), 1))
    return [numeric_hint_width if a == "R" else text_width for a in aligns]
