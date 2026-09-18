from typing import Any, Dict

from agents.base import llm_available, run_tool_loop
from models import ComplianceStatus, InvoiceTrack
from reasoner import compliance_reasoner_node as material_audit
from service_reasoner import service_compliance_reasoner_node as service_audit
from state import InvoiceComplianceState

SYSTEM_PROMPT = """You are the Compliance Agent in an accounts-payable agent swarm for a manufacturer.
Your only job is to decide whether a vendor invoice complies with its contract.

Process:
1. Call get_case_summary to see what you are auditing.
2. Call run_audit. It is the deterministic, cent-accurate audit engine. Never do the arithmetic yourself
   and never contradict its numbers.
3. Call submit_verdict with a short plain-English rationale that cites the contract clause and evidence
   (goods receipt, service entry sheet, gate log, index) behind each finding.
The final PASS/FAIL decision is enforced from the audit engine's result; your rationale explains it."""

TOOLS = [
   {
       "name": "get_case_summary",
       "description": "Get invoice header, track, contract id and which evidence documents are available.",
       "input_schema": {"type": "object", "properties": {}},
   },
   {
       "name": "run_audit",
       "description": "Run the deterministic compliance audit for this invoice's track and return the findings.",
       "input_schema": {"type": "object", "properties": {}},
   },
   {
       "name": "submit_verdict",
       "description": "Submit your final compliance verdict with rationale.",
       "input_schema": {
           "type": "object",
           "properties": {
               "decision": {"type": "string", "enum": ["PASS", "FAIL"]},
               "rationale": {"type": "string"},
           },
           "required": ["decision", "rationale"],
       },
   },
]


def _run_audit(state: InvoiceComplianceState) -> Dict[str, Any]:
   if state.get("track") == InvoiceTrack.SERVICE.value:
       return service_audit(state)
   return material_audit(state)


def _verdict_from_report(report, rationale: str, agent_mode: str) -> Dict[str, Any]:
   passed = report.status == ComplianceStatus.APPROVED and not report.discrepancies
   return {
       "decision": "PASS" if passed else "FAIL",
       "rationale": rationale,
       "discrepancy_count": len(report.discrepancies),
       "total_disputed": report.total_disputed,
       "agent_mode": agent_mode,
   }


def _default_rationale(report) -> str:
   if not report.discrepancies:
       return "All lines reconcile with the contract and operational evidence."
   return "; ".join(
       f"{d.discrepancy_type.value}: {d.audit_explanation}" for d in report.discrepancies
   )


def compliance_agent_node(state: InvoiceComplianceState) -> Dict[str, Any]:
   audit_result: Dict[str, Any] = {}
   invoice = state["extracted_invoice"]

   def get_case_summary(_: Dict[str, Any]) -> Dict[str, Any]:
       return {
           "invoice_number": invoice.invoice_number,
           "vendor_id": invoice.vendor_id,
           "track": state.get("track"),
           "contract_id": state["contract_terms"].contract_id,
           "reference": state.get("po_or_sow_id"),
           "line_items": len(invoice.line_items),
           "additional_charges": [c.charge_type for c in invoice.additional_charges],
           "total_invoiced": invoice.total_invoiced_amount,
           "has_goods_receipts": bool(state.get("goods_receipts")),
           "has_service_entry_sheets": bool(state.get("service_entry_sheets")),
       }

   def run_audit(_: Dict[str, Any]) -> Dict[str, Any]:
       audit_result.update(_run_audit(state))
       report = audit_result["audit_report"]
       return {
           "status": report.status.value,
           "total_invoiced": report.total_invoiced,
           "total_approved": report.total_approved,
           "total_disputed": report.total_disputed,
           "discrepancies": [d.model_dump(mode="json") for d in report.discrepancies],
       }

   trace = []
   rationale = None
   agent_mode = "deterministic"

   if llm_available():
       try:
           trace, verdict_input = run_tool_loop(
               SYSTEM_PROMPT,
               f"Audit invoice {invoice.invoice_number} from vendor {invoice.vendor_id}.",
               TOOLS,
               {
                   "get_case_summary": get_case_summary,
                   "run_audit": run_audit,
                   "submit_verdict": lambda i: {"accepted": True},
               },
               terminal_tool="submit_verdict",
           )
           if verdict_input:
               rationale = verdict_input.get("rationale")
               agent_mode = "claude"
       except Exception as exc:
           trace.append({"type": "thought", "text": f"LLM unavailable ({exc}); using deterministic audit."})

   if not audit_result:
       audit_result.update(_run_audit(state))
       trace.append({"type": "tool_call", "tool": "run_audit", "input": {}, "result": "deterministic fallback"})

   report = audit_result["audit_report"]
   verdict = _verdict_from_report(report, rationale or _default_rationale(report), agent_mode)

   return {
       "audit_report": report,
       "requires_human_approval": False,
       "compliance_verdict": verdict,
       "agent_trace": {"compliance": trace},
   }
