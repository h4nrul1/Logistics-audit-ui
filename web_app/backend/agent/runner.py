import os
import sys
import json
import re
import traceback
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from agent.config import PROJECT_ID, LOCATION, DEFAULT_MODEL
from agent.root_agent import MASTER_COORDINATOR_SYSTEM_INSTRUCTION
from agent.subagents import (
    fetch_master_queue,
    fetch_shipment_anomalies,
    save_field_override,
    batch_update_document_overrides,
    reset_field_overrides,
    auto_resolve_shipment_discrepancies,
    query_foreign_currency_shipments,
    query_zero_dollar_item_shipments,
    query_shipments_by_custom_filter,
    trigger_drive_ingestion_sync,
    trigger_reprocess_all_shipments,
    list_shipment_pdfs,
)
from agent.tools.bq_tools import fetch_document_raw

# Tool Map for dynamic invocation
TOOL_MAP = {
    "fetch_master_queue": fetch_master_queue,
    "fetch_shipment_anomalies": fetch_shipment_anomalies,
    "save_field_override": save_field_override,
    "batch_update_document_overrides": batch_update_document_overrides,
    "reset_field_overrides": reset_field_overrides,
    "auto_resolve_shipment_discrepancies": auto_resolve_shipment_discrepancies,
    "query_foreign_currency_shipments": query_foreign_currency_shipments,
    "query_zero_dollar_item_shipments": query_zero_dollar_item_shipments,
    "query_shipments_by_custom_filter": query_shipments_by_custom_filter,
    "trigger_drive_ingestion_sync": trigger_drive_ingestion_sync,
    "trigger_reprocess_all_shipments": trigger_reprocess_all_shipments,
    "list_shipment_pdfs": list_shipment_pdfs
}

# In-Memory Session History Store
session_store: Dict[str, List[Any]] = {}

def get_session_history(session_id: str) -> List[Any]:
    if session_id not in session_store:
        session_store[session_id] = []
    return session_store[session_id]

def extract_target_shipment_id(user_prompt: str, session_id: str) -> str:
    """Extract 8-digit shipment ID.
    STRICT PRIORITY HIERARCHY:
    1. Explicit shipment ID typed in user message body (e.g. 'Correct shipment 10385992').
    2. Active Conversation Thread Topic (most recent shipment ID discussed in prior turns).
    3. Active Canvas Context header (e.g. '[Active Canvas Context: Currently inspecting Shipment #10385745]').
    4. Default fallback ('10385992').
    """
    parts = user_prompt.split("\n\n", 1)
    if len(parts) > 1 and "[Active Canvas Context" in parts[0]:
        canvas_context = parts[0]
        user_body = parts[1]
    else:
        canvas_context = ""
        user_body = user_prompt

    # Priority 1: Explicit shipment ID typed in user body!
    body_match = re.search(r'\b(10\d{6,7}|\d{8})\b', user_body)
    if body_match:
        return body_match.group(1)

    # Priority 2: Immediate preceding chat turn in session history (Active Thread Topic)!
    history = get_session_history(session_id)
    if history:
        for content in reversed(history):
            text_val = ""
            if hasattr(content, "parts"):
                for part in content.parts:
                    if hasattr(part, "text") and part.text:
                        text_val += " " + part.text
            elif isinstance(content, dict):
                text_val = content.get("content", "") or content.get("text", "")
                
            if text_val:
                h_match = re.search(r'\b(10\d{6,7}|\d{8})\b', text_val)
                if h_match:
                    return h_match.group(1)

    # Priority 3: Active Canvas Context header!
    if canvas_context:
        ctx_match = re.search(r'\b(10\d{6,7}|\d{8})\b', canvas_context)
        if ctx_match:
            return ctx_match.group(1)

    return "10385992"

def format_tool_response(tool_res_str: str, target_sid: str) -> str:
    """Formats raw JSON tool results into clean, dynamic professional markdown for the UI."""
    try:
        data = json.loads(tool_res_str) if isinstance(tool_res_str, str) else tool_res_str
        target_sid = str(target_sid).replace("#", "")
        
        if isinstance(data, dict):
            status = data.get("status")
            resolutions = data.get("resolutions", [])
            
            # Dynamic bullet points for resolutions
            bullets = []
            for r in resolutions:
                cat = r.get("category", "")
                field = r.get("field", "")
                val = r.get("value_applied", "")
                
                if "weight" in cat.lower() or "weight" in field.lower():
                    bullets.append(f"• **Weight Discrepancy Resolved**: Updated `{field}` on SLI to **{val} kg** to match the Packing List (PKL) source of truth.")
            
            if status == "requires_user_specification":
                prompt_user = data.get("prompt_user", "")
                prompt_user = prompt_user.replace("##", "#").replace(f"#{target_sid}", f"#{target_sid}")
                
                lines = [f"I have inspected **Shipment #{target_sid}**.", ""]
                if bullets:
                    lines.extend(bullets)
                    lines.append("")
                    
                lines.extend([
                    "• **Financial Discrepancy (Line Items Action Required)**:",
                    f"{prompt_user}",
                    "",
                    "Once you specify your desired line item changes, I will execute the batch update in BigQuery and re-generate the audited PDF certificate."
                ])
                return "\n".join(lines)
                
            elif status == "success":
                msg = data.get("message", "Successfully resolved discrepancies.")
                msg = msg.replace("##", "#")
                
                lines = [
                    f"All right, I have successfully audited and corrected the documents for **Shipment #{target_sid}**.",
                    "",
                    f"• {msg}"
                ]
                if bullets:
                    lines.extend(bullets)
                    
                lines.append("\nThe final, audited PDF certificate for this shipment has been re-generated and updated in the system.")
                return "\n".join(lines)
    except Exception:
        pass
        
    return f"I have executed the automated audit pipeline for shipment #{target_sid}:\n\n{tool_res_str}"

ORDINAL_MAP = {
    "first": 0, "1st": 0, "1": 0,
    "second": 1, "2nd": 1, "2": 1,
    "third": 2, "3rd": 2, "3": 2,
    "fourth": 3, "4th": 3, "4": 3,
    "fifth": 4, "5th": 4, "5": 4,
    "sixth": 5, "6th": 5, "6": 5,
    "seventh": 6, "7th": 6, "7": 6,
    "eighth": 7, "8th": 7, "8": 7,
    "ninth": 8, "9th": 8, "9": 8,
    "tenth": 9, "10th": 9, "10": 9
}

def parse_and_execute_item_instruction(user_prompt: str, target_sid: str) -> Optional[str]:
    """Uses Gemini 2.5 Flash to zero-shot classify intent and interpret ANY natural language line-item edit instruction
    (differences, splits, relative math, ordinals, conditionals, multi-sentence prompts) and executes
    batch_update_document_overrides. Returns None if the prompt is a general question or search query.
    """
    try:
        raw_doc = fetch_document_raw(target_sid, "SLI")
        items = json.loads(raw_doc.get("items", "[]")) if isinstance(raw_doc.get("items"), str) else (raw_doc.get("items") or [])
        if not items:
            return None

        anom_raw = fetch_shipment_anomalies(target_sid)
        anom_data = json.loads(anom_raw) if isinstance(anom_raw, str) else (anom_raw or {})
        anomalies = anom_data.get("anomalies", []) if isinstance(anom_data, dict) else []

        system_instruction = """You are an intelligent logistics document auditor and line-item adjustment translator.
Your job is to read the user's natural language prompt, classify its intent, and if it is an instruction to modify/edit line items on the active shipment SLI document, calculate the exact new numeric values.

CRITICAL INTENT CLASSIFICATION RULE:
- Set `is_item_update = true` if the user prompt is an explicit request to modify, edit, adjust, add to, subtract from, set, split, or "add the differences of all three fields / all fields" for line items on the current shipment document.
- Set `is_item_update = false` ONLY if the user prompt is a general question, search query, database query across all shipments (e.g. "Show all shipments with...", "List shipments...", "Which shipments..."), or unrelated inquiry.

Target Fields available per item index (0-indexed, where "first item" or "item #1" = index 0):
- `items_{idx}_value_usd`
- `items_{idx}_gross_weight_kg`
- `items_{idx}_net_weight_kg`

Rule & Math Directives:
1. If the user asks to "add the differences of all three fields", "apply all differences", or "add differences" to an item (e.g. "first item" / "item 1"):
   - For Financial discrepancy (e.g., SLI total $1774 vs CIV source $1800, difference +$26): Add $26 to item #1 current `value_usd`.
   - For Gross Weight discrepancy (e.g., SLI total 110.4 kg vs PKL source 168 kg, difference +57.6 kg): Add 57.6 kg to item #1 current `gross_weight_kg`.
   - For Net Weight discrepancy (e.g., SLI total 87.4 kg vs PKL source 114.1 kg, difference +26.7 kg): Add 26.7 kg to item #1 current `net_weight_kg`.
2. Compute new_value = current_item_value + calculated_difference for each specified field.
3. Keep current item values unchanged unless specified or affected by the prompt.
4. Return exact floating point numbers rounded to 3 decimal places as string values in `overrides`.

Output Schema (JSON):
{
  "is_item_update": boolean,
  "reasoning": "Step-by-step reasoning explaining intent classification and how target item new values were derived",
  "applied_descriptions": ["Added $26 to item #1 value_usd", "Added 57.6 kg to item #1 gross_weight_kg", "Added 26.7 kg to item #1 net_weight_kg"],
  "overrides": {
    "items_0_value_usd": "71.000",
    "items_0_gross_weight_kg": "60.360",
    "items_0_net_weight_kg": "28.870"
  }
}
"""

        context_prompt = f"""Target Shipment ID: {target_sid}
User Prompt: "{user_prompt}"

Current Items Array ({len(items)} items total):
{json.dumps(items, indent=2)}

Active Discrepancy Anomalies:
{json.dumps(anomalies, indent=2)}
"""

        client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=context_prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        
        parsed_res = json.loads(response.text)
        if parsed_res.get("is_item_update") and parsed_res.get("overrides"):
            overrides = parsed_res.get("overrides", {})
            payload = json.dumps(overrides)
            batch_update_document_overrides(target_sid, "SLI", payload)
            
            descriptions = parsed_res.get("applied_descriptions", [])
            desc_list = "\n".join(f"• {desc}" for desc in descriptions) if descriptions else "• Applied requested line-item adjustments."
            reasoning = parsed_res.get("reasoning", "")
            
            return (
                f"All right, I have processed your instruction using Gemini LLM reasoning for **Shipment #{target_sid}**:\n\n"
                f"**Reasoning**: {reasoning}\n\n"
                f"**Applied Adjustments**:\n{desc_list}\n\n"
                f"• **BigQuery Table**: Saved item overrides to `Audited_Overrides_Tbl`.\n"
                f"• **Audited PDF**: Re-generated and uploaded the certified audited PDF to Cloud Storage!"
            )

    except Exception as err:
        print(f"Error in Gemini LLM parse_and_execute_item_instruction: {err}")
        
    return None

def run_agent_turn(user_prompt: str, session_id: str = "default_session") -> Dict[str, Any]:
    """Execute a single multi-step reasoning turn for the ADK Agent, calling tools dynamically
    and capturing step-by-step thoughts and tool executions.
    """
    trajectory = []
    target_sid = extract_target_shipment_id(user_prompt, session_id)
    
    # 1. Check if prompt is a natural language item override instruction (e.g. "Add $2 to the last item on SLI")
    item_exec_res = parse_and_execute_item_instruction(user_prompt, target_sid)
    if item_exec_res:
        trajectory.append({
            "step": "Calling Tool: batch_update_document_overrides",
            "tool": "batch_update_document_overrides",
            "arguments": {"shipment_id": target_sid, "prompt": user_prompt}
        })
        
        # Save to session history
        history = get_session_history(session_id)
        history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]))
        history.append(types.Content(role="model", parts=[types.Part.from_text(text=item_exec_res)]))
        session_store[session_id] = history[-20:]
        
        return {
            "status": "success",
            "session_id": session_id,
            "response": item_exec_res,
            "trajectory": trajectory
        }

    # 2. Otherwise run Vertex AI Gemini tool invocation loop
    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
        tools_list = list(TOOL_MAP.values())
        
        history = get_session_history(session_id)
        contents = list(history)
        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_prompt)]
        ))
        
        config = types.GenerateContentConfig(
            system_instruction=MASTER_COORDINATOR_SYSTEM_INSTRUCTION,
            tools=tools_list,
            temperature=0.2
        )
        
        max_turns = 5
        turn_count = 0
        final_text = ""
        
        while turn_count < max_turns:
            turn_count += 1
            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=contents,
                config=config
            )
            
            if response.text:
                final_text += response.text
            
            function_calls = response.function_calls
            if not function_calls:
                break
                
            for call in function_calls:
                func_name = call.name
                func_args = dict(call.args) if call.args else {}
                
                trajectory.append({
                    "step": f"Calling Tool: {func_name}",
                    "tool": func_name,
                    "arguments": func_args
                })
                
                if func_name in TOOL_MAP:
                    try:
                        tool_output = TOOL_MAP[func_name](**func_args)
                    except Exception as exec_err:
                        tool_output = f"Tool execution error: {exec_err}"
                else:
                    tool_output = f"Unknown tool: {func_name}"
                
                trajectory.append({
                    "step": f"Tool Result: {func_name}",
                    "output": tool_output
                })
                
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part.from_function_call(name=func_name, args=func_args)]
                ))
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=func_name,
                        response={"result": tool_output}
                    )]
                ))
                
        if not final_text.strip() and trajectory:
            tool_summaries = []
            for step in trajectory:
                if step.get("step", "").startswith("Tool Result:"):
                    tool_summaries.append(f"• **{step.get('tool', 'Action')}**: {step.get('output', '')[:300]}")
            if tool_summaries:
                final_text = "Executed the following audit tool actions:\n" + "\n".join(tool_summaries)

        # HARD ANTI-HALLUCINATION GUARD:
        # If no tools were called during this turn (trajectory is empty), BUT the prompt requests action or claims execution
        prompt_lower = user_prompt.lower()
        is_general_query = any(kw in prompt_lower for kw in ["show", "list", "find", "search", "query", "display", "which", "how many", "all shipments"])
        is_action_prompt = any(kw in prompt_lower for kw in ["correct", "audit", "fix", "resolve", "update"])
        claims_execution = any(kw in final_text.lower() for kw in ["successfully audited", "updated the", "resolved", "re-generated", "corrected the"])
        
        if not trajectory and not is_general_query and (is_action_prompt or claims_execution):
            tool_res = auto_resolve_shipment_discrepancies(target_sid)
            trajectory.append({
                "step": "Calling Tool: auto_resolve_shipment_discrepancies",
                "tool": "auto_resolve_shipment_discrepancies",
                "arguments": {"shipment_id": target_sid}
            })
            trajectory.append({
                "step": "Tool Result: auto_resolve_shipment_discrepancies",
                "output": tool_res
            })
            
            final_text = format_tool_response(tool_res, target_sid)

        # Save user prompt & response to history
        history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]))
        history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
        session_store[session_id] = history[-20:] # Keep last 10 turns
        
        return {
            "status": "success",
            "session_id": session_id,
            "response": final_text or "Agent turn completed successfully.",
            "trajectory": trajectory
        }
        
    except Exception as e:
        traceback.print_exc()
        return fallback_agent_turn(user_prompt, session_id)

def fallback_agent_turn(user_prompt: str, session_id: str) -> Dict[str, Any]:
    """Fallback runner if genai SDK is unavailable or encounters API issues."""
    trajectory = []
    target_sid = extract_target_shipment_id(user_prompt, session_id)
    
    item_res = parse_and_execute_item_instruction(user_prompt, target_sid)
    if item_res:
        trajectory.append({"step": "Executing Tool: batch_update_document_overrides", "tool": "batch_update_document_overrides", "arguments": {"shipment_id": target_sid}})
        return {
            "status": "success",
            "session_id": session_id,
            "response": item_res,
            "trajectory": trajectory
        }
        
    prompt_lower = user_prompt.lower()
    if any(kw in prompt_lower for kw in ["correct", "audit", "fix", "resolve", "update"]):
        trajectory.append({"step": "Executing Tool: auto_resolve_shipment_discrepancies", "tool": "auto_resolve_shipment_discrepancies", "arguments": {"shipment_id": target_sid}})
        res = auto_resolve_shipment_discrepancies(target_sid)
        formatted_res = format_tool_response(res, target_sid)
        return {
            "status": "success",
            "session_id": session_id,
            "response": formatted_res,
            "trajectory": trajectory
        }
    elif "currency" in prompt_lower or "foreign" in prompt_lower:
        trajectory.append({"step": "Executing Tool: query_foreign_currency_shipments", "tool": "query_foreign_currency_shipments"})
        res = query_foreign_currency_shipments()
        return {
            "status": "success",
            "session_id": session_id,
            "response": f"Here are the foreign currency shipment query results:\n```json\n{res}\n```",
            "trajectory": trajectory
        }
    elif "$0" in prompt_lower or "zero" in prompt_lower or "0 item" in prompt_lower or "zero dollar" in prompt_lower:
        trajectory.append({"step": "Executing Tool: query_zero_dollar_item_shipments", "tool": "query_zero_dollar_item_shipments"})
        res = query_zero_dollar_item_shipments()
        return {
            "status": "success",
            "session_id": session_id,
            "response": f"Here are the zero-dollar ($0) item shipment query results:\n```json\n{res}\n```",
            "trajectory": trajectory
        }
    else:
        return {
            "status": "success",
            "session_id": session_id,
            "response": f"I received your request: '{user_prompt}'. I am configured as the Master Logistics Audit Coordinator Agent.",
            "trajectory": trajectory
        }
