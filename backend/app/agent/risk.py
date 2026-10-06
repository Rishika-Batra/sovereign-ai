from typing import Dict, Any, Optional

# Simple configurable rule set for defining risky actions
RISK_RULES = {
    "risky_tools": [
        "generate_docx",
        "generate_xlsx",
        "generate_pdf",
        "generate_pptx"
    ],
    "risky_answer_patterns": [
        "contradicts retrieved SOP",
        "override SOP",
        "ignore SOP",
        "not follow SOP"
    ]
}

def is_action_risky(tool_name: Optional[str], final_answer: Optional[str] = None) -> bool:
    """
    Evaluates if a given tool call or final answer is considered high-risk 
    based on the configured RISK_RULES.
    """
    if tool_name and tool_name in RISK_RULES["risky_tools"]:
        return True
        
    if final_answer:
        final_answer_lower = final_answer.lower()
        for pattern in RISK_RULES["risky_answer_patterns"]:
            if pattern.lower() in final_answer_lower:
                return True
                
    return False
