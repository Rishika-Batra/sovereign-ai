import json
import re
import inspect
from typing import TypedDict, List, Dict, Any, Optional
# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, END

from app.ai_gateway.gateway import gateway
from app.ai_gateway.router import route_task
from app.ai_gateway.registry import get_model_name
from app.agent.tools import TOOLS

MAX_STEPS = 15


class AgentState(TypedDict):
    task: str
    user: Any
    db: Any
    history: List[Dict[str, Any]]
    pending_tool: Optional[Dict[str, Any]]
    final_answer: Optional[str]
    step_count: int
    session_id: Optional[int]
    awaiting_approval: Optional[bool]
    pending_action_id: Optional[int]


SYSTEM_PROMPT = """You are an autonomous AI agent with access to tools.
Your goal is to solve the user's task step-by-step.

AVAILABLE TOOLS:
1. search_knowledge(query: str) - Searches the knowledge base. Returns text chunks with document_id, filename, and text.
2. read_file(document_id: str) - Reads the FULL text of a document by its document_id.
3. calculate(expression: str) - Evaluates a math expression (e.g. "110 / 100"). ALWAYS use this for arithmetic.
4. run_code(code: str) - Runs python code in a secure sandbox.
5. generate_docx(title: str, content: str) - Generates a Word document. Returns a download URL.
6. generate_xlsx(filename: str, headers: list[str], rows: list[list], sheet_name: str = "Sheet1") - Generates an Excel spreadsheet.
7. generate_pdf(filename: str, title: str, sections: list, table: dict = None) - Generates a PDF document.
8. generate_pptx(filename: str, title_slide: dict, slides: list) - Generates a PowerPoint presentation.

WORKFLOW - Follow this exact sequence:
Phase 1 - SEARCH: Call search_knowledge ONCE with a targeted query about the subject.
Phase 2 - READ: Use the document_id from search results to call read_file and get the full document text.
Phase 3 - ANSWER: Once you have the document text, produce a final_answer that directly cites the specific data found.

CRITICAL RULES:
- Respond with ONLY valid JSON matching ONE of these shapes:
  Shape 1 (Call a tool): {"tool": "<name>", "args": {"<param>": "<val>"}}
  Shape 2 (Final answer): {"final_answer": "<your complete answer here>"}
- NEVER call search_knowledge more than twice total. After searching, use read_file to get full document content.
- NEVER repeat a search with the same or similar query. Check EXECUTION HISTORY first.
- Your final_answer MUST cite specific values, readings, and statuses from the documents — not generic descriptions.
- Quote exact figures from the context.
- Say "not found in the provided documents" when a value is absent.
- Never describe code that would compute a value instead of stating it.
- A value is a number or text that appears as a result (for example a printed output, a table cell, or a sentence stating it). Source code that would print or compute a value is NOT the value.
- Example: if the context only contains code like print('Test MAE:', mae) but no actual number, the correct answer is: not found in the provided documents.
- If the task asks for a risk level, you MUST state one: Low, Medium, High, or Critical with justification citing specific data.
- NEVER use key names like "next_action", "action", "risk_level" etc. Only use "tool"/"args" or "final_answer".
- NEVER call generate_docx/xlsx/pdf/pptx with placeholder content. Only use real data from EXECUTION HISTORY.
- After a generate_* tool succeeds with a download URL, your NEXT response MUST be a final_answer with that URL.

FEW-SHOT EXAMPLES:

Example 1 - Search:
{"tool": "search_knowledge", "args": {"query": "M-104 inspection"}}

Example 2 - Read file after search found document_id "abc-123":
{"tool": "read_file", "args": {"document_id": "abc-123"}}

Example 3 - Final answer citing specific data:
{"final_answer": "## Inspection Analysis for M-104\\n\\n**Component Summary:**\\n- Pump: OK (reading: 72 psi, within normal range)\\n- Motor: FAIL (reading: 110°C, exceeds 95°C threshold)\\n- Valve: WARN (reading: 88%, approaching limit)\\n\\n**Overall Risk Level: HIGH**\\nJustification: The motor has failed with a reading of 110°C, which is 15.8% above the critical threshold of 95°C. This represents an imminent failure risk.\\n\\n**Recommended Next Action:** Immediately shut down M-104 for motor replacement. Schedule preventive inspection of valve V-204 within 7 days."}

Example 4 - Calculate:
{"tool": "calculate", "args": {"expression": "110 - 95"}}

REMINDER: Output ONLY valid JSON. Cite SPECIFIC numbers and statuses from documents in your final_answer.
"""


def extract_json(text: str) -> dict:
    """
    Extracts and parses a JSON object from text, handling markdown code blocks or trailing text.
    """
    cleaned = text.strip()
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```$", "", cleaned, flags=re.IGNORECASE).strip()

    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Could not parse valid JSON from text: {text}")


def validate_parsed_json(parsed: Any) -> bool:
    """
    Validates if parsed JSON matches one of the two allowed shapes:
    1. {"tool": str (in TOOLS), "args": dict}
    2. {"final_answer": str}
    Also normalizes common LLM key variants to the canonical shapes.
    """
    if not isinstance(parsed, dict):
        return False

    # Alias 'action' to 'tool' for tolerance
    if "action" in parsed and "tool" not in parsed:
        parsed["tool"] = parsed.pop("action")

    # Alias various answer-like keys to 'final_answer'
    for alt_key in ("next_action", "response", "answer", "result", "summary"):
        if alt_key in parsed and "final_answer" not in parsed and "tool" not in parsed:
            parsed["final_answer"] = parsed.pop(alt_key)
            break

    # If the model returned a dict with no recognized keys but has prose values,
    # treat the whole thing as a final answer
    if "final_answer" not in parsed and "tool" not in parsed:
        # Check if it looks like a structured analysis (has string values)
        string_values = [v for v in parsed.values() if isinstance(v, str) and len(v) > 20]
        if string_values:
            # Combine all string values into a single final answer
            parsed["final_answer"] = "\n\n".join(str(v) for v in parsed.values() if isinstance(v, str))

    has_tool = "tool" in parsed and isinstance(parsed["tool"], str) and parsed["tool"] in TOOLS
    has_args = "args" in parsed and isinstance(parsed["args"], dict) if has_tool else False

    if has_tool and has_args:
        return True

    has_final_answer = "final_answer" in parsed and parsed["final_answer"] is not None
    if has_final_answer:
        return True

    return False


async def plan_node(state: AgentState) -> Dict[str, Any]:
    step_count = state.get("step_count", 0) + 1

    if step_count > MAX_STEPS:
        return {
            "step_count": step_count,
            "pending_tool": None,
            "final_answer": f"Agent reached maximum step limit ({MAX_STEPS}) before completing task.",
        }

    history = state.get("history", [])
    if history:
        history_lines = []
        for i, step in enumerate(history, 1):
            history_lines.append(
                f"Step {i}:\n"
                f"- Tool: {step.get('tool')}\n"
                f"- Args: {json.dumps(step.get('args'))}\n"
                f"- Result: {step.get('result')}\n"
            )
        history_str = "\n" + "\n".join(history_lines)
    else:
        history_str = " No tools executed yet."

    user_prompt = (
        f"TASK: {state['task']}\n\n"
        f"EXECUTION HISTORY:{history_str}\n\n"
        "Decide your next action. Respond in JSON format only."
    )

    task_key = await route_task(state["task"])
    model_name = get_model_name(task_key)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response_text = await gateway.chat(model_name, messages)
    parsed = None
    is_valid = False

    try:
        parsed = extract_json(response_text)
        is_valid = validate_parsed_json(parsed)
    except Exception as e:
        print(f"[Plan Node] Initial JSON parse error: {e}")

    # Retry once if initial response was invalid JSON or wrong schema
    if not is_valid:
        print(f"[Plan Node] Response invalid shape. Retrying once... Raw: {response_text}")
        retry_user_prompt = (
            f"{user_prompt}\n\n"
            "ERROR: Your previous response did not match the required JSON format.\n"
            "You MUST respond with ONLY valid JSON matching either {'tool': '<name>', 'args': {...}} "
            "or {'final_answer': '<answer>'}. Never use any other key names (like 'next_action'). Try again."
        )
        retry_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": retry_user_prompt},
        ]
        response_text = await gateway.chat(model_name, retry_messages)
        try:
            parsed = extract_json(response_text)
            is_valid = validate_parsed_json(parsed)
        except Exception as e:
            print(f"[Plan Node] Retry JSON parse error: {e}")

    if is_valid and parsed:
        if "final_answer" in parsed:
            # Check for risky final answer
            from app.agent.risk import is_action_risky
            from app.db.models import PendingAction
            from app.services.audit import log_action
            
            final_ans_str = str(parsed["final_answer"])
            if is_action_risky(tool_name=None, final_answer=final_ans_str):
                db = state.get("db")
                user = state.get("user")
                if db and user:
                    pa = PendingAction(
                        user_id=user.id,
                        session_id=state.get("session_id"),
                        tool="final_answer",
                        arguments={"final_answer": final_ans_str},
                        status="pending"
                    )
                    db.add(pa)
                    db.commit()
                    log_action(db, user, "action_pending", "agent", {"tool": "final_answer", "action_id": pa.id})
                    
                    return {
                        "step_count": step_count,
                        "pending_tool": None,
                        "final_answer": None,
                        "awaiting_approval": True,
                        "pending_action_id": pa.id,
                    }
                    
            return {
                "step_count": step_count,
                "pending_tool": None,
                "final_answer": final_ans_str,
            }
        elif "tool" in parsed:
            return {
                "step_count": step_count,
                "pending_tool": {
                    "tool": parsed["tool"],
                    "args": parsed.get("args", {}),
                },
                "final_answer": None,
            }

    # Fallback: model refused or produced non-JSON after retry.
    # Return a structured error rather than leaking the raw response text.
    print(f"[Plan Node] Model refused to produce valid JSON after retry. Raw: {response_text[:200]}")
    return {
        "step_count": step_count,
        "pending_tool": None,
        "final_answer": (
            "I was unable to complete this task. The AI model did not return a valid "
            "response. Please try rephrasing your request or contact an administrator."
        ),
    }


async def tool_node(state: AgentState) -> Dict[str, Any]:
    pending = state.get("pending_tool")
    if not pending or not pending.get("tool"):
        return {"pending_tool": None}

    tool_name = pending["tool"]
    args = pending.get("args", {})
    tool_func = TOOLS.get(tool_name)

    from app.agent.risk import is_action_risky
    from app.db.models import PendingAction
    from app.services.audit import log_action

    db = state.get("db")
    user = state.get("user")

    if is_action_risky(tool_name=tool_name):
        if db and user:
            pa = PendingAction(
                user_id=user.id,
                session_id=state.get("session_id"),
                tool=tool_name,
                arguments=args,
                status="pending"
            )
            db.add(pa)
            db.commit()
            log_action(db, user, "action_pending", "agent", {"tool": tool_name, "action_id": pa.id})
            
            return {
                "awaiting_approval": True,
                "pending_action_id": pa.id,
            }

    if not tool_func:
        result = f"Error: Tool '{tool_name}' not found."
    else:
        call_args = args.copy()
        sig = inspect.signature(tool_func)
        if "db" in sig.parameters and db:
            call_args["db"] = db
        if "user" in sig.parameters and user:
            call_args["user"] = user

        try:
            if inspect.iscoroutinefunction(tool_func):
                result = await tool_func(**call_args)
            else:
                result = tool_func(**call_args)
        except Exception as e:
            result = f"Error executing {tool_name}: {str(e)}"

    history = list(state.get("history", []))
    history.append(
        {
            "tool": tool_name,
            "args": args,
            "result": result,
        }
    )

    # Deliverable-producing tools terminate the loop deterministically —
    # do not rely on the model to notice and self-terminate.
    TERMINAL_TOOLS = {"generate_docx", "generate_xlsx", "generate_pdf", "generate_pptx"}
    if tool_name in TERMINAL_TOOLS and isinstance(result, str) and "Download at:" in result:
        url_match = re.search(r"(/api/documents/download/\S+)", result)
        download_url = url_match.group(1) if url_match else result
        return {
            "history": history,
            "pending_tool": None,
            "final_answer": f"I've generated the document. You can download it here: {download_url}",
        }

    return {
        "history": history,
        "pending_tool": None,
    }


def route_decision(state: AgentState) -> str:
    if state.get("awaiting_approval"):
        return "end"
    if state.get("final_answer") is not None:
        return "end"
    if state.get("step_count", 0) >= MAX_STEPS:
        return "end"
    if state.get("pending_tool") is not None:
        return "tool"
    return "end"


def route_after_tool(state: AgentState) -> str:
    # If tool_node already set a terminal final_answer (e.g. after
    # generate_docx succeeded), stop here instead of looping back to plan,
    # where it would get silently overwritten.
    if state.get("awaiting_approval"):
        return "end"
    if state.get("final_answer") is not None:
        return "end"
    return "plan"


def build_agent_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("plan", plan_node)
    workflow.add_node("tool", tool_node)

    workflow.set_entry_point("plan")
    workflow.add_conditional_edges(
        "plan",
        route_decision,
        {
            "tool": "tool",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "tool",
        route_after_tool,
        {
            "plan": "plan",
            "end": END,
        },
    )

    return workflow.compile()


agent_graph = build_agent_graph()
