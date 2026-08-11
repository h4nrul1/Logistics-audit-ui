import os
import sys
import json
import traceback
from typing import Dict, Any, List

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from agent.config import PROJECT_ID, LOCATION, DEFAULT_MODEL
from agent.root_agent import MASTER_COORDINATOR_SYSTEM_INSTRUCTION
from agent.subagents import (
    fetch_master_queue,
    fetch_shipment_anomalies,
    save_field_override,
    reset_field_overrides,
    auto_resolve_shipment_discrepancies,
    trigger_drive_ingestion_sync,
    trigger_reprocess_all_shipments,
    list_shipment_pdfs
)

# Tool Map for dynamic invocation
TOOL_MAP = {
    "fetch_master_queue": fetch_master_queue,
    "fetch_shipment_anomalies": fetch_shipment_anomalies,
    "save_field_override": save_field_override,
    "reset_field_overrides": reset_field_overrides,
    "auto_resolve_shipment_discrepancies": auto_resolve_shipment_discrepancies,
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

def run_agent_turn(user_prompt: str, session_id: str = "default_session") -> Dict[str, Any]:
    """Execute a single multi-step reasoning turn for the ADK Agent, calling tools dynamically
    and capturing step-by-step thoughts and tool executions.
    """
    trajectory = []
    
    # Try importing google.genai
    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
        
        tools_list = list(TOOL_MAP.values())
        
        # Prepare content history
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
            
            # Check for text output
            if response.text:
                final_text += response.text
            
            # Check for function calls
            function_calls = response.function_calls
            if not function_calls:
                # No more tools to call
                break
                
            # Process function calls
            for call in function_calls:
                func_name = call.name
                func_args = dict(call.args) if call.args else {}
                
                trajectory.append({
                    "step": f"Calling Tool: {func_name}",
                    "tool": func_name,
                    "arguments": func_args
                })
                
                # Execute tool
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
                
                # Append tool call & response to turn contents for follow-up model reasoning
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
        # Fallback keyword execution for robustness
        return fallback_agent_turn(user_prompt, session_id)

def fallback_agent_turn(user_prompt: str, session_id: str) -> Dict[str, Any]:
    """Fallback runner if genai SDK is unavailable or encounters API issues."""
    trajectory = []
    prompt_lower = user_prompt.lower()
    
    if "queue" in prompt_lower or "list" in prompt_lower or "status" in prompt_lower:
        trajectory.append({"step": "Executing Tool: fetch_master_queue", "tool": "fetch_master_queue"})
        res = fetch_master_queue()
        return {
            "status": "success",
            "session_id": session_id,
            "response": f"Here is the master audit queue summary:\n```json\n{res}\n```",
            "trajectory": trajectory
        }
    elif "sync" in prompt_lower or "drive" in prompt_lower or "ingest" in prompt_lower:
        trajectory.append({"step": "Executing Tool: trigger_drive_ingestion_sync", "tool": "trigger_drive_ingestion_sync"})
        res = trigger_drive_ingestion_sync()
        return {
            "status": "success",
            "session_id": session_id,
            "response": f"Triggered Google Drive ingestion job:\n`{res}`",
            "trajectory": trajectory
        }
    else:
        return {
            "status": "success",
            "session_id": session_id,
            "response": f"I received your request: '{user_prompt}'. I am configured as the Master Logistics Audit Coordinator Agent.",
            "trajectory": trajectory
        }
