import os
import uuid
import re
from docx import Document


GENERATED_DIR = "/app/uploads/generated"


def _safe_filename(title: str) -> str:
    """Converts a title string into a safe filename component."""
    safe = re.sub(r"[^\w\s-]", "", title).strip()
    safe = re.sub(r"[\s-]+", "_", safe)
    return safe[:60] or "document"


def generate_docx(title: str, content: str) -> str:
    """
    Creates a Word .docx document with the given title (as a heading)
    and content (split on newlines into paragraphs).

    Saves to /app/uploads/generated/{uuid}_{safe_title}.docx and
    returns the filename (not the full path) so the caller can build a
    download URL.
    """
    os.makedirs(GENERATED_DIR, exist_ok=True)

    doc = Document()
    doc.add_heading(title, level=1)

    for line in content.split("\n"):
        stripped = line.strip()
        if stripped:
            doc.add_paragraph(stripped)
        else:
            # Preserve blank lines as empty paragraphs for spacing
            doc.add_paragraph("")

    safe_title = _safe_filename(title)
    file_uuid = str(uuid.uuid4())
    filename = f"{file_uuid}_{safe_title}.docx"
    dest_path = os.path.join(GENERATED_DIR, filename)

    doc.save(dest_path)
    return filename


def generate_xlsx(
    filename: str,
    headers: list,
    rows: list,
    sheet_name: str = "Sheet1",
) -> str:
    """
    Creates an Excel .xlsx workbook with a single sheet containing a bold
    header row and data rows.

    Saves to /app/uploads/generated/{uuid}_{safe_filename}.xlsx and
    returns the filename (not the full path) so the caller can build a
    download URL.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font

    os.makedirs(GENERATED_DIR, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    # Bold header row
    bold_font = Font(bold=True)
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = bold_font

    # Data rows
    for row_idx, row_data in enumerate(rows, start=2):
        for col_idx, value in enumerate(row_data, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    safe_name = _safe_filename(filename)
    file_uuid = str(uuid.uuid4())
    out_filename = f"{file_uuid}_{safe_name}.xlsx"
    dest_path = os.path.join(GENERATED_DIR, out_filename)

    wb.save(dest_path)
    return out_filename


def generate_pdf(
    filename: str,
    title: str,
    sections: list,
    table: dict = None,
) -> str:
    """
    Creates a PDF document with the given title, sections (headings and content),
    and an optional table.

    Saves to /app/uploads/generated/{uuid}_{safe_filename}.pdf and
    returns the filename (not the full path).
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors

    os.makedirs(GENERATED_DIR, exist_ok=True)
    
    safe_name = _safe_filename(filename)
    file_uuid = str(uuid.uuid4())
    out_filename = f"{file_uuid}_{safe_name}.pdf"
    dest_path = os.path.join(GENERATED_DIR, out_filename)

    doc = SimpleDocTemplate(dest_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph(title, styles['Title']))
    story.append(Spacer(1, 12))

    # Sections
    for section in sections:
        heading = section.get("heading")
        content = section.get("content", "")
        
        if heading:
            story.append(Paragraph(heading, styles['Heading2']))
            story.append(Spacer(1, 6))
            
        for paragraph in content.split("\n"):
            stripped = paragraph.strip()
            if stripped:
                story.append(Paragraph(stripped, styles['Normal']))
            story.append(Spacer(1, 6))
            
    # Table
    if table and "rows" in table:
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        
        table_data = []
        if headers:
            table_data.append(headers)
        table_data.extend(rows)
        
        if table_data:
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(Spacer(1, 12))
            story.append(t)

    doc.build(story)
    return out_filename


def generate_pptx(
    filename: str,
    title_slide: dict,
    slides: list,
) -> str:
    """
    Creates a PowerPoint .pptx presentation with the given title slide and
    content slides (which can contain bullets and/or tables).

    Saves to /app/uploads/generated/{uuid}_{safe_filename}.pptx and
    returns the filename (not the full path).
    """
    from pptx import Presentation
    from pptx.util import Inches

    os.makedirs(GENERATED_DIR, exist_ok=True)
    
    safe_name = _safe_filename(filename)
    file_uuid = str(uuid.uuid4())
    out_filename = f"{file_uuid}_{safe_name}.pptx"
    dest_path = os.path.join(GENERATED_DIR, out_filename)

    prs = Presentation()

    # Title slide
    if title_slide:
        title_slide_layout = prs.slide_layouts[0] # Title slide
        slide = prs.slides.add_slide(title_slide_layout)
        title_shape = slide.shapes.title
        subtitle_shape = slide.placeholders[1]

        title_shape.text = title_slide.get("title", "")
        if "subtitle" in title_slide:
            subtitle_shape.text = title_slide.get("subtitle")

    # Content slides
    for slide_data in slides:
        heading = slide_data.get("heading", "")
        bullets = slide_data.get("bullets", [])
        table = slide_data.get("table")

        if table:
            # Slide with title and table
            slide_layout = prs.slide_layouts[5] # Title Only
            slide = prs.slides.add_slide(slide_layout)
            if slide.shapes.title:
                slide.shapes.title.text = heading

            headers = table.get("headers", [])
            rows = table.get("rows", [])
            num_rows = len(rows) + (1 if headers else 0)
            num_cols = len(headers) if headers else (len(rows[0]) if rows else 1)
            
            if num_rows > 0 and num_cols > 0:
                x, y, cx, cy = Inches(1), Inches(2), Inches(8), Inches(4)
                shape = slide.shapes.add_table(num_rows, num_cols, x, y, cx, cy)
                table_shape = shape.table

                current_row = 0
                if headers:
                    for i, header in enumerate(headers):
                        table_shape.cell(current_row, i).text = str(header)
                    current_row += 1

                for row_data in rows:
                    for i, cell_val in enumerate(row_data):
                        if i < num_cols:
                            table_shape.cell(current_row, i).text = str(cell_val)
                    current_row += 1
        else:
            # Normal bullet slide
            slide_layout = prs.slide_layouts[1] # Title and Content
            slide = prs.slides.add_slide(slide_layout)
            if slide.shapes.title:
                slide.shapes.title.text = heading
                
            if bullets and len(slide.placeholders) > 1:
                tf = slide.placeholders[1].text_frame
                tf.text = bullets[0] if len(bullets) > 0 else ""
                for bullet in bullets[1:]:
                    p = tf.add_paragraph()
                    p.text = bullet
                    p.level = 0

    prs.save(dest_path)
    return out_filename
