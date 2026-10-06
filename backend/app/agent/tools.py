import ast
import operator
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import DocumentChunk, User, Deliverable
from app.services.retrieve import retrieve_context
from app.agent.sandbox import run_in_sandbox
from app.services.documents_out import generate_docx as _generate_docx_service
from app.services.documents_out import generate_xlsx as _generate_xlsx_service
from app.services.documents_out import generate_pdf as _generate_pdf_service
from app.services.documents_out import generate_pptx as _generate_pptx_service
from app.services.audit import log_action

# Safe arithmetic operators mapping for AST evaluation
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.Eq: operator.eq,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.NotEq: operator.ne,
}


def _eval_ast_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        return SAFE_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _eval_ast_node(node.operand)
        return SAFE_OPERATORS[op_type](operand)
    elif isinstance(node, ast.Compare):
        left = _eval_ast_node(node.left)
        for op, comp in zip(node.ops, node.comparators):
            op_type = type(op)
            if op_type not in SAFE_OPERATORS:
                raise ValueError(f"Unsupported comparison operator: {op_type.__name__}")
            right = _eval_ast_node(comp)
            if not SAFE_OPERATORS[op_type](left, right):
                return False
            left = right
        return True
    else:
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")


async def calculate(expression: str) -> str:
    """
    Safely evaluates a basic math expression using AST parsing without raw eval().
    Returns the calculation result as a string or an error message.
    """
    try:
        parsed = ast.parse(expression.strip(), mode="eval")
        result = _eval_ast_node(parsed.body)
        return str(result)
    except Exception as e:
        return f"Error evaluating expression '{expression}': {str(e)}"


from app.api.documents import _apply_acl_filter

async def read_file(document_id: str, db: Session, user: User) -> str:
    """
    Fetches all DocumentChunk rows for that document_id, concatenates their text in
    page/chunk order, and returns the full reconstructed text.
    """
    if not document_id:
        return "Error: document_id must be provided."

    query = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id)
    if user.role != "admin":
        from sqlalchemy import or_, and_, select
        from app.db.models import DocumentAcl, DocumentStatus
        # Same logic as retrieve.py
        acl_exists = select(DocumentAcl.id).where(DocumentAcl.document_id == DocumentChunk.document_id).exists()
        acl_matches = select(DocumentAcl.id).where(
            and_(
                DocumentAcl.document_id == DocumentChunk.document_id,
                or_(DocumentAcl.user_id == user.id, DocumentAcl.role == user.role)
            )
        ).exists()
        query = query.join(DocumentStatus, DocumentChunk.document_id == DocumentStatus.document_id, isouter=True)
        query = query.filter(
            or_(
                ~acl_exists,
                acl_matches,
                DocumentStatus.uploader_id == user.id
            )
        )

    chunks = (
        query
        .order_by(DocumentChunk.page.asc(), DocumentChunk.id.asc())
        .all()
    )

    if not chunks:
        return f"Error: Document with ID '{document_id}' not found, has no text content, or access denied."

    full_text = "\n\n".join([c.text for c in chunks if c.text])
    return full_text


async def search_knowledge(query: str, user: User, db: Session) -> List[Dict[str, Any]]:
    """
    Performs pgvector cosine similarity search on DocumentChunks within the user's workspace.
    """
    if not query:
        return []
    return await retrieve_context(db=db, query=query, user=user)


async def run_code(code: str) -> str:
    """
    Runs python code in a sandboxed docker environment.
    """
    result = run_in_sandbox(code)
    
    output = []
    if result["stdout"]:
        output.append(f"STDOUT:\n{result['stdout']}")
    if result["stderr"]:
        output.append(f"STDERR:\n{result['stderr']}")
    if result["timed_out"]:
        output.append("EXECUTION TIMED OUT.")
        
    output.append(f"Exit Code: {result['exit_code']}")
    
    return "\n\n".join(output)


async def generate_docx(title: str, content: str, db: Session = None, user: User = None) -> str:
    """
    Generates a Word (.docx) document with the given title as a heading and
    content as body paragraphs. Returns the filename that can be used to
    build a download URL: GET /api/documents/download/<filename>
    """
    try:
        filename = _generate_docx_service(title=title, content=content)
        download_path = f"/api/documents/download/{filename}"
        if db and user:
            log_action(db=db, user=user, action="document_generated", resource=filename, details={"format": "docx", "title": title})
            
            # Record deliverable
            deliverable = Deliverable(
                filename=filename,
                file_type="docx",
                generated_by=user.id,
                download_path=download_path
            )
            db.add(deliverable)
            db.commit()

        return f"Document generated successfully. Download at: {download_path}"
    except Exception as e:
        return f"Error generating document: {str(e)}"


async def generate_xlsx(
    filename: str,
    headers: list,
    rows: list,
    sheet_name: str = "Sheet1",
    db: Session = None,
    user: User = None,
) -> str:
    """
    Generates an Excel (.xlsx) spreadsheet with a bold header row and data rows.
    Returns the filename that can be used to build a download URL:
    GET /api/documents/download/<filename>
    """
    try:
        out_filename = _generate_xlsx_service(
            filename=filename,
            headers=headers,
            rows=rows,
            sheet_name=sheet_name,
        )
        download_path = f"/api/documents/download/{out_filename}"
        if db and user:
            log_action(
                db=db, user=user, action="document_generated", resource=out_filename,
                details={"format": "xlsx", "filename": filename, "sheet_name": sheet_name, "num_rows": len(rows)},
            )
            deliverable = Deliverable(
                filename=out_filename,
                file_type="xlsx",
                generated_by=user.id,
                download_path=download_path
            )
            db.add(deliverable)
            db.commit()
            
        return f"Document generated successfully. Download at: {download_path}"
    except Exception as e:
        return f"Error generating spreadsheet: {str(e)}"


async def generate_pdf(
    filename: str,
    title: str,
    sections: list,
    table: dict = None,
    db: Session = None,
    user: User = None,
) -> str:
    """
    Generates a PDF document with the given title, sections, and an optional table.
    Returns the filename that can be used to build a download URL:
    GET /api/documents/download/<filename>
    """
    try:
        out_filename = _generate_pdf_service(
            filename=filename,
            title=title,
            sections=sections,
            table=table,
        )
        download_path = f"/api/documents/download/{out_filename}"
        if db and user:
            log_action(
                db=db, user=user, action="document_generated", resource=out_filename,
                details={"format": "pdf", "filename": filename, "title": title},
            )
            deliverable = Deliverable(
                filename=out_filename,
                file_type="pdf",
                generated_by=user.id,
                download_path=download_path
            )
            db.add(deliverable)
            db.commit()
            
        return f"Document generated successfully. Download at: {download_path}"
    except Exception as e:
        return f"Error generating PDF: {str(e)}"


async def generate_pptx(
    filename: str,
    title_slide: dict,
    slides: list,
    db: Session = None,
    user: User = None,
) -> str:
    """
    Generates a PowerPoint (.pptx) presentation with the given title slide and content slides.
    Returns the filename that can be used to build a download URL:
    GET /api/documents/download/<filename>
    """
    try:
        out_filename = _generate_pptx_service(
            filename=filename,
            title_slide=title_slide,
            slides=slides,
        )
        download_path = f"/api/documents/download/{out_filename}"
        if db and user:
            log_action(
                db=db, user=user, action="document_generated", resource=out_filename,
                details={"format": "pptx", "filename": filename},
            )
            deliverable = Deliverable(
                filename=out_filename,
                file_type="pptx",
                generated_by=user.id,
                download_path=download_path
            )
            db.add(deliverable)
            db.commit()
            
        return f"Document generated successfully. Download at: {download_path}"
    except Exception as e:
        return f"Error generating PowerPoint: {str(e)}"


# TOOLS Registry mapping tool names to functions
TOOLS = {
    "read_file": read_file,
    "search_knowledge": search_knowledge,
    "calculate": calculate,
    "run_code": run_code,
    "generate_docx": generate_docx,
    "generate_xlsx": generate_xlsx,
    "generate_pdf": generate_pdf,
    "generate_pptx": generate_pptx,
}
