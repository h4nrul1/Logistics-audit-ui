import os
import sys
import argparse
import datetime
from typing import Dict, Any, List

# Add backend directory to path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import vertexai
from vertexai.preview import reasoning_engines
from agent.root_agent import get_master_agent_config, MASTER_COORDINATOR_SYSTEM_INSTRUCTION
from agent.subagents import ALL_AGENT_TOOLS
from agent.config import DEFAULT_MODEL

PROJECT_ID = os.getenv("PROJECT_ID", "it-ai-briggs-agentspace")
LOCATION = os.getenv("LOCATION", "us-central1")
STAGING_BUCKET = os.getenv("STAGING_BUCKET", "gs://logistics-agent-staging")

class LogisticsAuditAgentEngine:
    """
    Vertex AI Reasoning Engine Wrapper for the Logistics Audit ADK Master Coordinator Agent.
    """
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self.system_instruction = MASTER_COORDINATOR_SYSTEM_INSTRUCTION

    def query(self, prompt: str, shipment_id: str = None) -> Dict[str, Any]:
        """
        Executes a reasoning query turn against the ADK Logistics Audit Master Coordinator.
        """
        # Lazy import inside query method for Vertex AI cloud worker environment
        from google import genai
        from agent.subagents import ALL_AGENT_TOOLS

        client = genai.Client()
        full_prompt = prompt
        if shipment_id:
            full_prompt = f"[Active Context: Shipment #{shipment_id}]\n{prompt}"

        response = client.models.generate_content(
            model=self.model_name,
            contents=full_prompt,
            config={
                "system_instruction": self.system_instruction,
                "tools": ALL_AGENT_TOOLS,
                "temperature": 0.2
            }
        )

        return {
            "response": response.text,
            "shipment_id": shipment_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

def deploy_agent():
    """
    Deploys the Logistics Audit Agent to GCP Vertex AI Reasoning Engine.
    """
    print(f"[INFO] Initializing Vertex AI Deployment for Project: '{PROJECT_ID}' in Region: '{LOCATION}'...")
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)

    agent_instance = LogisticsAuditAgentEngine(model_name=DEFAULT_MODEL)

    requirements = [
        "google-genai",
        "google-cloud-bigquery",
        "google-cloud-storage",
        "pandas",
        "pydantic",
        "reportlab",
        "pypdf"
    ]

    print("[INFO] Uploading ADK Agent package to Vertex AI Reasoning Engine...")
    remote_agent = reasoning_engines.ReasoningEngine.create(
        agent_instance,
        requirements=requirements,
        display_name="Logistics Audit ADK Agent",
        description="Cross-document auditing agent for CIV, PKL, SLI, and VGM documents powered by Gemini 2.5 Pro.",
    )

    print("\n[SUCCESS] Agent Successfully Deployed to Google Cloud Agent Platform!")
    print(f"[RESOURCE NAME] {remote_agent.resource_name}")

def list_agents():
    """
    Lists all active Reasoning Engine deployments in Vertex AI.
    """
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    print(f"[INFO] Fetching active Reasoning Engine instances in '{PROJECT_ID}'...")
    engines = reasoning_engines.ReasoningEngine.list()
    if not engines:
        print("[INFO] No active Reasoning Engine instances found.")
        return
    for eng in engines:
        print(f"• Name: {eng.display_name} | Resource ID: {eng.resource_name}")

def test_query(resource_name: str, prompt: str):
    """
    Sends a test query to a deployed Vertex AI Reasoning Engine agent.
    """
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    print(f"[INFO] Querying remote agent '{resource_name}' with prompt: '{prompt}'...")
    remote_agent = reasoning_engines.ReasoningEngine(resource_name)
    response = remote_agent.query(prompt=prompt)
    print(f"\n[AGENT RESPONSE]\n{response}")

def main():
    parser = argparse.ArgumentParser(description="Deploy & Manage ADK Master Coordinator Agent on GCP Vertex AI Agent Engine")
    subparsers = parser.add_subparsers(dest="command")

    # Deploy
    subparsers.add_parser("deploy", help="Deploy the ADK Agent to Vertex AI Reasoning Engine")
    
    # List
    subparsers.add_parser("list", help="List active deployed Agent Engine instances")

    # Test
    test_parser = subparsers.add_parser("test", help="Test a deployed Agent Engine instance")
    test_parser.add_argument("--resource-name", required=True, help="Full resource name of the deployed agent")
    test_parser.add_argument("--prompt", default="Show all shipments with weight discrepancies", help="Test prompt")

    args = parser.parse_args()

    if args.command == "deploy":
        deploy_agent()
    elif args.command == "list":
        list_agents()
    elif args.command == "test":
        test_query(args.resource_name, args.prompt)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
