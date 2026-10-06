import pymupdf  # PyMuPDF
import pdfplumber
from typing import List, Dict, Any, Optional, TypedDict
import pytesseract
from pdf2image import convert_from_path
import docx
from docx.document import Document as _Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
import openpyxl
import xlrd

class ParsedTable(TypedDict):
    rows: List[List[str]]

class ParsedPage(TypedDict):
    page_number: int
    text: str
    tables: List[ParsedTable]
    ocr_confidence: Optional[float]  # None for non-OCR pages

class ParsedDocument(TypedDict):
    document_id: str
    filename: str
    pages: List[ParsedPage]
    metadata: Dict[str, str]

def extract_text_pymupdf(pdf_path: str, document_id: str, filename: str) -> ParsedDocument:
    """
    Opens a PDF and returns a ParsedDocument with tables extracted via pdfplumber
    and plain paragraph text extracted via PyMuPDF, with table regions deduplicated
    from the plain text so no content appears twice.
    """
    pages: List[ParsedPage] = []

    # Use pdfplumber to extract table bounding boxes and cell data
    with pdfplumber.open(pdf_path) as plumber_doc:
        plumber_pages = plumber_doc.pages

        with pymupdf.open(pdf_path) as fitz_doc:
            for i, (fitz_page, plumber_page) in enumerate(
                zip(fitz_doc, plumber_pages), start=1
            ):
                # --- Extract tables ---
                raw_tables = plumber_page.extract_tables() or []
                parsed_tables: List[ParsedTable] = []
                for raw_table in raw_tables:
                    row_data = []
                    for row in raw_table:
                        # pdfplumber may return None for empty cells
                        cell_data = [
                            (cell or "").replace("\n", " ").strip()
                            for cell in row
                        ]
                        if any(c for c in cell_data):
                            row_data.append(cell_data)
                    if row_data:
                        parsed_tables.append({"rows": row_data})

                # --- Extract plain text, excluding table bounding boxes ---
                # Get bounding boxes of detected tables to avoid duplication
                table_bboxes = [
                    t.bbox for t in (plumber_page.find_tables() or [])
                ]

                if table_bboxes:
                    # Collect words that don't fall inside any table bbox
                    words = fitz_page.get_text("words")  # (x0,y0,x1,y1,word,...)
                    # pdfplumber uses (x0, top, x1, bottom) coords relative to page
                    # fitz uses (x0, y0, x1, y1) from top-left — same convention
                    kept_words = []
                    for w in words:
                        wx0, wy0, wx1, wy1 = w[0], w[1], w[2], w[3]
                        in_table = False
                        for bx0, by0, bx1, by1 in table_bboxes:
                            if wx0 >= bx0 and wy0 >= by0 and wx1 <= bx1 and wy1 <= by1:
                                in_table = True
                                break
                        if not in_table:
                            kept_words.append(w[4])
                    text = " ".join(kept_words)
                else:
                    text = fitz_page.get_text()

                pages.append(
                    {"page_number": i, "text": text, "tables": parsed_tables, "ocr_confidence": None}
                )

    return {
        "document_id": document_id,
        "filename": filename,
        "pages": pages,
        "metadata": {}
    }


def is_scanned(pdf_path: str) -> bool:
    """
    Heuristic: if the total extracted text across all pages is under 50 chars,
    the PDF is likely scanned (image-only) with no real text layer.
    """
    total_text = ""
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            total_text += page.get_text()
    return len(total_text.strip()) < 50


from PIL import Image
import cv2
import numpy as np

def preprocess_image_for_ocr(pil_image: Image.Image) -> Image.Image:
    """
    Prepares an image for Tesseract OCR without destroying content.

    Pipeline:
      1. Gentle non-local-means denoising to reduce sensor noise while
         keeping edge sharpness.
      2. Grayscale conversion.
      3. CLAHE (Contrast Limited Adaptive Histogram Equalization) to lift
         local contrast in shadows and highlights — safe for handwriting
         on varied backgrounds.
      4. Otsu binarisation on the CLAHE result. If the binary image would
         be >95% white (i.e. threshold destroyed content), fall back to
         the CLAHE image directly so Tesseract still has something to read.
      5. Mild skew correction (only applied for angles > 0.5° and < 10°
         to avoid over-rotation artefacts on non-document photos).
    """
    img = np.array(pil_image)

    # --- Step 1: gentle denoising (luminance only when colour) ---
    if len(img.shape) == 3:
        h_param = 6  # low strength — preserve pen strokes
        if img.shape[2] == 4:
            img_bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        else:
            img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        img_bgr = cv2.fastNlMeansDenoisingColored(img_bgr, None, h_param, h_param, 7, 21)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = cv2.fastNlMeansDenoising(img, None, 6, 7, 21)

    # --- Step 2: CLAHE for local contrast enhancement ---
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # --- Step 3: Otsu binarisation with content-preservation guard ---
    _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    white_ratio = np.sum(binary == 255) / binary.size
    if white_ratio > 0.95:
        # Threshold turned the image almost entirely white — use the
        # CLAHE-enhanced grayscale instead so Tesseract still sees ink.
        print("[OCR DEBUG] Binarisation produced >95% white image; "
              "falling back to CLAHE-enhanced grayscale.")
        result = enhanced
    else:
        result = binary

    # --- Step 4: conservative skew correction ---
    coords = np.column_stack(np.where(result < 200))
    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        # Only correct small, clear skews — large angles on photos are
        # usually perspective distortion, not document tilt.
        if 0.5 < abs(angle) < 10:
            (h, w) = result.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            result = cv2.warpAffine(
                result, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderValue=255,
            )

    return Image.fromarray(result)

def _compute_confidence(data: dict, text: str) -> float:
    """
    Computes average Tesseract word confidence from image_to_data output.

    Returns 0.0 if the extracted text is empty/whitespace-only — a confidence
    score is meaningless without any content to be confident about.
    """
    if not text or not text.strip():
        return 0.0

    page_conf_sum = 0.0
    page_words = 0
    for conf in data.get('conf', []):
        try:
            conf_val = float(conf)
            if conf_val >= 0:
                page_conf_sum += conf_val
                page_words += 1
        except ValueError:
            pass

    return round(page_conf_sum / page_words, 2) if page_words > 0 else 0.0


def _run_tesseract(image: Image.Image) -> tuple[str, float]:
    """Low-level helper: run Tesseract on *image* and return (text, confidence)."""
    text = pytesseract.image_to_string(image)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    conf = _compute_confidence(data, text)
    return text, conf


def _ocr_image(image: Image.Image, debug_filename: Optional[str] = None) -> tuple[str, float]:
    """
    Preprocesses the image, runs Tesseract OCR, and returns (text, avg_confidence).

    Fallback behaviour: if preprocessing yields 0 extracted characters, OCR is
    retried once on the original unprocessed image — some photos OCR better
    without preprocessing depending on their original quality.

    If *debug_filename* is provided the preprocessed image is saved to
    /app/uploads/debug_preprocessed_<debug_filename> for visual inspection.
    """
    import os
    processed_image = preprocess_image_for_ocr(image)

    # --- DEBUG: persist the preprocessed image so we can inspect it ---
    if debug_filename:
        debug_dir = "/app/uploads"
        os.makedirs(debug_dir, exist_ok=True)
        safe_name = os.path.basename(debug_filename)
        debug_path = os.path.join(debug_dir, f"debug_preprocessed_{safe_name}")
        try:
            processed_image.save(debug_path)
            print(f"[OCR DEBUG] Preprocessed image saved to {debug_path}")
        except Exception as _save_err:
            print(f"[OCR DEBUG] Could not save preprocessed image: {_save_err}")

    text, avg_conf = _run_tesseract(processed_image)

    # --- DEBUG: log raw OCR output length before any filtering ---
    print(f"[OCR DEBUG] Raw OCR text length after Tesseract (preprocessed): {len(text)} chars")

    # --- Fallback: retry on original image if preprocessing wiped the text ---
    if not text.strip():
        print("[OCR DEBUG] Preprocessed path returned 0 chars — retrying on "
              "original unprocessed image.")
        text, avg_conf = _run_tesseract(image)
        print(f"[OCR DEBUG] Raw OCR text length after Tesseract (original): {len(text)} chars")
        if not text.strip():
            print("[OCR DEBUG] WARNING: Both preprocessed and original image returned "
                  "empty text. Confidence forced to 0.")
            avg_conf = 0.0

    return text, avg_conf

async def _apply_vision(image: Image.Image, ocr_text: str, is_diagram: bool, ocr_confidence: float = 100.0) -> tuple[str, str]:
    """
    Always runs the vision model on the image.
    Uses DIAGRAM_PROMPT when is_diagram is True, otherwise GENERAL_IMAGE_PROMPT.
    Returns (ocr_chunk_text, vision_description_text).
    If the vision call fails, vision_description_text is empty.
    """
    import io
    import base64
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    image_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    prompt = DIAGRAM_PROMPT if is_diagram else GENERAL_IMAGE_PROMPT
    vision_text = await _call_vision_safe(image_b64, prompt)

    # Build OCR chunk text
    if is_diagram:
        parts = []
        if ocr_text.strip():
            parts.append(f"OCR-detected labels:\n{ocr_text.strip()}")
        else:
            parts.append("OCR-detected labels: (none — image may be low contrast)")
        if vision_text.strip():
            parts.append(f"Vision description:\n{vision_text.strip()}")
        else:
            parts.append("Vision description: (not available)")
        ocr_chunk_text = "\n\n".join(parts)
    else:
        ocr_chunk_text = ocr_text

    # Build vision description chunk text
    vision_chunk_text = ""
    if vision_text.strip():
        if ocr_confidence < 60.0:
            vision_chunk_text = (
                f"OCR confidence low ({ocr_confidence:.0f}%); text below comes from the vision model.\n\n"
                f"{vision_text.strip()}"
            )
        else:
            vision_chunk_text = vision_text.strip()

    return ocr_chunk_text, vision_chunk_text

async def ocr_scanned_pdf(pdf_path: str, document_id: str, filename: str, is_diagram: bool = False) -> ParsedDocument:
    """
    Renders each PDF page as an image and extracts text using OCR.
    Logs average OCR confidence per page. Always invokes the vision model.
    """
    pages: List[ParsedPage] = []
    images = convert_from_path(pdf_path)
    
    total_confidence = 0.0
    total_vision_length = 0
    pages_count = 0
    vision_texts: List[Dict[str, Any]] = []  # [{"page": int, "text": str}]
    
    for i, image in enumerate(images, start=1):
        debug_name = f"{filename}_page{i}.png"
        text, page_avg_conf = _ocr_image(image, debug_filename=debug_name)
        print(f"[OCR] {pdf_path} Page {i} average confidence: {page_avg_conf:.2f}")
        
        ocr_chunk_text, vision_chunk_text = await _apply_vision(image, text, is_diagram, ocr_confidence=page_avg_conf)
        if vision_chunk_text:
            total_vision_length += len(vision_chunk_text)
            vision_texts.append({"page": i, "text": vision_chunk_text, "ocr_confidence": page_avg_conf})
        
        pages.append({"page_number": i, "text": ocr_chunk_text, "tables": [], "ocr_confidence": page_avg_conf})
        total_confidence += page_avg_conf
        pages_count += 1
        
    avg_confidence = total_confidence / pages_count if pages_count > 0 else 0.0
    
    metadata: Dict[str, Any] = {"avg_ocr_confidence": str(round(avg_confidence, 2))}
    if is_diagram:
        metadata["diagram_mode"] = "true"
    metadata["vision_description_length"] = str(total_vision_length)
    metadata["vision_texts"] = vision_texts
    
    return {
        "document_id": document_id,
        "filename": filename,
        "pages": pages,
        "metadata": metadata
    }

async def extract_text_image(image_path: str, document_id: str, filename: str, is_diagram: bool = False) -> ParsedDocument:
    """
    Reads a standalone image and extracts text using OCR.
    Always invokes the vision model for richer text extraction.
    """
    image = Image.open(image_path)
    text, conf = _ocr_image(image, debug_filename=filename)
    print(f"[OCR] Image {filename} average confidence: {conf:.2f}")

    ocr_chunk_text, vision_chunk_text = await _apply_vision(image, text, is_diagram, ocr_confidence=conf)
    
    page: ParsedPage = {
        "page_number": 1,
        "text": ocr_chunk_text,
        "tables": [],
        "ocr_confidence": conf
    }
    
    metadata: Dict[str, Any] = {"avg_ocr_confidence": str(round(conf, 2))}
    if is_diagram:
        metadata["diagram_mode"] = "true"
    vision_texts: List[Dict[str, Any]] = []
    if vision_chunk_text:
        vision_texts.append({"page": 1, "text": vision_chunk_text, "ocr_confidence": conf})
    metadata["vision_description_length"] = str(len(vision_chunk_text))
    metadata["vision_texts"] = vision_texts

    return {
        "document_id": document_id,
        "filename": filename,
        "pages": [page],
        "metadata": metadata
    }


# ---------------------------------------------------------------------------
# Vision prompts
# ---------------------------------------------------------------------------

GENERAL_IMAGE_PROMPT = (
    "Transcribe all text visible in this image exactly as written, "
    "preserving lists and headings. Then describe what the image "
    "contains in one or two factual sentences. Do not guess unreadable "
    "text; write [unreadable]. Please answer in under 150 words."
)

DIAGRAM_PROMPT = (
    "Describe this diagram or technical drawing factually. "
    "List each labeled component or node you can actually read in the "
    "image, using its exact visible label text. Describe how each "
    "component connects to or relates to other components, using the "
    "format: '<label A> connects to <label B>'. "
    "Only describe labels and connections you can clearly see in the "
    "image -- do not invent, guess, or use example labels from these "
    "instructions. If a label or connection is unclear or illegible, "
    "say so explicitly rather than guessing a plausible-sounding value. "
    "This may be any kind of diagram (flowchart, org chart, network "
    "diagram, tree structure, schematic, etc.) -- describe what is "
    "actually present rather than assuming a specific diagram type. "
    "Do not describe visual styling -- focus only on labels and "
    "relationships. Please answer in under 150 words."
)


def _clean_vision_text(text: str) -> str:
    if not text:
        return text
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        if not cleaned_lines or line.strip() != cleaned_lines[-1].strip():
            cleaned_lines.append(line)
    cleaned_text = "\n".join(cleaned_lines)
    return cleaned_text[:3000]

async def _call_vision_safe(image_b64: str, prompt: str) -> str:
    """
    Sends base64 encoded image to the vision model with the given prompt.
    Returns the vision model's textual description, or an empty string if the call fails.
    """
    from app.ai_gateway.gateway import gateway
    from app.ai_gateway.registry import get_model_name

    try:
        vision_model = get_model_name("vision")
        print(f"[VISION] Calling {vision_model} for image description")
        description = await gateway.vision(vision_model, image_b64, prompt, options={"num_predict": 400})
        cleaned = _clean_vision_text(description)
        print(f"[VISION] Description length: {len(cleaned)} chars")
        return cleaned

    except Exception as exc:
        print(f"[VISION] WARNING: vision call failed ({exc}). "
              "Falling back to OCR-only for this image.")
        return ""


async def describe_diagram_with_vision(image_path: str) -> str:
    """
    Encodes *image_path* as base64 and sends it to the vision model
    with a diagram-specific prompt.
    """
    import base64
    try:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        return await _call_vision_safe(image_b64, DIAGRAM_PROMPT)
    except Exception as exc:
        print(f"[VISION] WARNING: file read failed ({exc}). "
              "Falling back to OCR-only for this image.")
        return ""





def iter_block_items(parent):
    """
    Generate a reference to each paragraph and table child within *parent*,
    in document order.
    """
    if isinstance(parent, _Document):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError("something's not right")

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def extract_text_docx(docx_path: str, document_id: str, filename: str) -> ParsedDocument:
    doc = docx.Document(docx_path)
    
    text_blocks = []
    tables: List[ParsedTable] = []
    
    # Metadata
    core_props = doc.core_properties
    metadata = {}
    if core_props.title:
        metadata["title"] = core_props.title
    if core_props.author:
        metadata["author"] = core_props.author
        
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            if block.text.strip():
                text_blocks.append(block.text.strip())
        elif isinstance(block, Table):
            row_data = []
            for row in block.rows:
                cell_data = []
                for cell in row.cells:
                    cell_text = cell.text.replace('\n', ' ').strip()
                    cell_data.append(cell_text)
                row_data.append(cell_data)
            tables.append({"rows": row_data})
            text_blocks.append(f"__TABLE_{len(tables)-1}__")
                
    full_text = "\n\n".join(text_blocks)
    
    return {
        "document_id": document_id,
        "filename": filename,
        "pages": [{"page_number": 1, "text": full_text, "tables": tables}],
        "metadata": metadata
    }


def extract_text_xlsx(xlsx_path: str, document_id: str, filename: str) -> ParsedDocument:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    pages: List[ParsedPage] = []
    
    for i, sheet_name in enumerate(wb.sheetnames, start=1):
        sheet = wb[sheet_name]
        
        row_data = []
        for row in sheet.iter_rows(values_only=True):
            cell_data = [str(cell) if cell is not None else "" for cell in row]
            if any(cell.strip() for cell in cell_data):
                row_data.append(cell_data)
                
        if not row_data:
            continue
            
        tables = [{"rows": row_data}]
        text = f"Sheet: {sheet_name}\n__TABLE_0__"
        pages.append({"page_number": i, "text": text, "tables": tables, "ocr_confidence": None})
        
    return {
        "document_id": document_id,
        "filename": filename,
        "pages": pages,
        "metadata": {}
    }

def extract_text_xls(xls_path: str, document_id: str, filename: str) -> ParsedDocument:
    wb = xlrd.open_workbook(xls_path)
    pages: List[ParsedPage] = []
    
    for i, sheet in enumerate(wb.sheets(), start=1):
        row_data = []
        for row_idx in range(sheet.nrows):
            # xlrd gives types like float, string, etc. so we convert to str
            cell_data = [str(cell) if cell is not None else "" for cell in sheet.row_values(row_idx)]
            if any(cell.strip() for cell in cell_data):
                row_data.append(cell_data)
                
        if not row_data:
            continue
            
        tables = [{"rows": row_data}]
        text = f"Sheet: {sheet.name}\n__TABLE_0__"
        pages.append({"page_number": i, "text": text, "tables": tables, "ocr_confidence": None})
        
    return {
        "document_id": document_id,
        "filename": filename,
        "pages": pages,
        "metadata": {}
    }

def serialize_document(doc: ParsedDocument) -> List[Dict]:
    """
    Takes a ParsedDocument and flattens it into chunkable text pages.
    Each returned dict has {"page": page_number, "text": serialized_text}.
    """
    serialized_pages = []
    
    metadata_lines = []
    if doc["metadata"]:
        for k, v in doc["metadata"].items():
            if k not in ["avg_ocr_confidence", "vision_texts"]:
                metadata_lines.append(f"{k.capitalize()}: {v}")
            
    meta_text = "Document Metadata:\n" + "\n".join(metadata_lines) + "\n\n" if metadata_lines else ""
    
    for idx, page in enumerate(doc["pages"]):
        text = page["text"]
        for t_idx, table in enumerate(page["tables"]):
            table_text = []
            for r_idx, row in enumerate(table["rows"]):
                table_text.append(" | ".join(row))
            if table_text:
                table_text[0] = f"Table: {table_text[0]}"
            
            serialized_table = "\n".join(table_text)
            
            marker = f"__TABLE_{t_idx}__"
            if marker in text:
                text = text.replace(marker, serialized_table)
            else:
                text += "\n\n" + serialized_table
                
        if idx == 0 and meta_text:
            text = meta_text + text
            
        serialized_pages.append({
            "page": page["page_number"],
            "text": text,
            "ocr_confidence": page.get("ocr_confidence"),  # None for non-OCR pages
        })
        
    return serialized_pages


def chunk_text(
    pages: List[Dict],
    chunk_size: int = 800,
    overlap: int = 150,
) -> List[Dict]:
    """
    Splits each page's text into overlapping chunks of roughly chunk_size chars.
    Returns [{"page": n, "text": chunk_text}, ...].
    Empty or whitespace-only chunks are skipped.
    """
    chunks = []
    for page_info in pages:
        page_num = page_info["page"]
        text = page_info["text"]

        if not text or not text.strip():
            # Log explicitly so this silent skip is visible in the output
            print(f"[CHUNK] Page {page_num}: skipping — text is empty or whitespace-only "
                  f"(raw length={len(text) if text else 0}). "
                  "This page will contribute 0 chunks.")
            continue

        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append({
                    "page": page_num,
                    "text": chunk,
                    "ocr_confidence": page_info.get("ocr_confidence")
                })
            start += chunk_size - overlap

    return chunks
