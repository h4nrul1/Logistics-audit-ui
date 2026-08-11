from agent.tools.bq_tools import (
    fetch_master_queue,
    fetch_shipment_anomalies,
    save_field_override,
    reset_field_overrides,
    auto_resolve_shipment_discrepancies
)
from agent.tools.pipeline_tools import (
    trigger_drive_ingestion_sync,
    trigger_reprocess_all_shipments
)
from agent.tools.pdf_tools import list_shipment_pdfs

# Tool Collections for Sub-Agent Delegation
INGESTION_SUBAGENT_TOOLS = [
    trigger_drive_ingestion_sync,
    trigger_reprocess_all_shipments
]

AUDIT_SUBAGENT_TOOLS = [
    fetch_master_queue,
    fetch_shipment_anomalies
]

RESOLUTION_SUBAGENT_TOOLS = [
    save_field_override,
    reset_field_overrides,
    auto_resolve_shipment_discrepancies
]

REPORTING_SUBAGENT_TOOLS = [
    list_shipment_pdfs
]

ALL_AGENT_TOOLS = (
    INGESTION_SUBAGENT_TOOLS +
    AUDIT_SUBAGENT_TOOLS +
    RESOLUTION_SUBAGENT_TOOLS +
    REPORTING_SUBAGENT_TOOLS
)
