from typing import Any, Dict
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from models import InvoiceTrack
from state import InvoiceComplianceState
from agents import compliance_agent_node, posting_agent_node


def _infer_invoice_track(state: InvoiceComplianceState) -> InvoiceTrack:
   invoice = state.get("extracted_invoice")
   if not invoice:
       raise ValueError("Cannot route invoice: 'extracted_invoice' missing.")

   if invoice.track in (InvoiceTrack.MATERIAL, InvoiceTrack.SERVICE):
       return invoice.track

   material_lines = sum(1 for line in invoice.line_items if line.item_type == InvoiceTrack.MATERIAL)
   service_lines = sum(1 for line in invoice.line_items if line.item_type == InvoiceTrack.SERVICE)

   if material_lines > 0 and service_lines == 0:
       return InvoiceTrack.MATERIAL
   if service_lines > 0 and material_lines == 0:
       return InvoiceTrack.SERVICE

   ref_string = (state.get("po_or_sow_id") or "").upper()
   if any(prefix in ref_string for prefix in ("SOW", "SES", "MSA", "WO-")):
       return InvoiceTrack.SERVICE
   if any(prefix in ref_string for prefix in ("PO-", "GR-", "BOL")):
       return InvoiceTrack.MATERIAL

   raise ValueError(f"Ambiguous invoice structure under ref '{ref_string}'.")


def invoice_router_node(state: InvoiceComplianceState) -> Dict[str, Any]:
   determined_track = _infer_invoice_track(state)
   return {"track": determined_track.value, "processing_errors": []}


def build_unified_compliance_graph():
   """Specialist swarm: router -> Compliance Agent -> Posting Agent."""
   builder = StateGraph(InvoiceComplianceState)

   builder.add_node("invoice_router", invoice_router_node)
   builder.add_node("compliance_agent", compliance_agent_node)
   builder.add_node("posting_agent", posting_agent_node)

   builder.add_edge(START, "invoice_router")
   builder.add_edge("invoice_router", "compliance_agent")
   builder.add_edge("compliance_agent", "posting_agent")
   builder.add_edge("posting_agent", END)

   return builder.compile(checkpointer=MemorySaver())
