from typing import Any, Dict, Literal
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from models import InvoiceTrack
from state import InvoiceComplianceState
from reasoner import compliance_reasoner_node as material_reasoner_node
from service_reasoner import service_compliance_reasoner_node as service_reasoner_node
from hitl_workflow import human_review_node, dispatcher_node, route_after_reasoning


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
   try:
       determined_track = _infer_invoice_track(state)
       return {"track": determined_track.value, "processing_errors": []}
   except Exception as exc:
       return {"track": None, "processing_errors": state.get("processing_errors", []) + [str(exc)]}


def routing_error_fallback_node(state: InvoiceComplianceState) -> Dict[str, Any]:
   errors = state.get("processing_errors") or ["Unknown classification error."]
   memo = "## Automated Routing Failure\n- " + "\n- ".join(errors)
   return {
       "requires_human_approval": True,
       "human_notes": "Routing failure: manual classification required.",
       "generated_vendor_email": memo,
   }


def route_by_track(state: InvoiceComplianceState) -> Literal["material_reasoner", "service_reasoner", "routing_error_fallback"]:
   track = state.get("track")
   if track == InvoiceTrack.MATERIAL.value:
       return "material_reasoner"
   elif track == InvoiceTrack.SERVICE.value:
       return "service_reasoner"
   return "routing_error_fallback"


def build_unified_compliance_graph():
   builder = StateGraph(InvoiceComplianceState)

   builder.add_node("invoice_router", invoice_router_node)
   builder.add_node("material_reasoner", material_reasoner_node)
   builder.add_node("service_reasoner", service_reasoner_node)
   builder.add_node("routing_error_fallback", routing_error_fallback_node)
   builder.add_node("human_review_node", human_review_node)
   builder.add_node("dispatcher_node", dispatcher_node)

   builder.add_edge(START, "invoice_router")
   builder.add_conditional_edges(
       "invoice_router",
       route_by_track,
       {
           "material_reasoner": "material_reasoner",
           "service_reasoner": "service_reasoner",
           "routing_error_fallback": "routing_error_fallback",
       },
   )

   for reasoner_node in ("material_reasoner", "service_reasoner"):
       builder.add_conditional_edges(
           reasoner_node,
           route_after_reasoning,
           {
               "human_review_node": "human_review_node",
               "dispatcher_node": "dispatcher_node",
           },
       )

   builder.add_edge("routing_error_fallback", "human_review_node")
   builder.add_edge("human_review_node", "dispatcher_node")
   builder.add_edge("dispatcher_node", END)

   return builder.compile(checkpointer=MemorySaver())
