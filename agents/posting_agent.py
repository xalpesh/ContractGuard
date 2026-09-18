from typing import Any, Dict

from agents.base import llm_available, run_tool_loop
from state import InvoiceComplianceState

SYSTEM_PROMPT = """You are the Posting Agent in an accounts-payable agent swarm for a manufacturer.
You receive a compliance verdict from the Compliance Agent and act on it:
- PASS: call post_invoice_to_erp.
- FAIL: do NOT post. Call return_to_vendor with a polite, specific, professional notice that lists each
  discrepancy (what was billed, what the contract allows, the clause) and asks the vendor either to
  clarify/justify the charge or to issue a corrected invoice. Choose requested_action accordingly.
Call exactly one of the two tools, then stop. Posting a FAILED invoice is blocked by the system."""

TOOLS = [
   {
       "name": "post_invoice_to_erp",
       "description": "Post a fully compliant invoice to the ERP for payment. Only allowed when verdict is PASS.",
       "input_schema": {"type": "object", "properties": {"note": {"type": "string"}}},
   },
   {
       "name": "return_to_vendor",
       "description": "Return a non-compliant invoice to the vendor asking for clarification or a corrected invoice.",
       "input_schema": {
           "type": "object",
           "properties": {
               "subject": {"type": "string"},
               "body_markdown": {"type": "string"},
               "requested_action": {"type": "string", "enum": ["CLARIFICATION", "CORRECTED_INVOICE", "BOTH"]},
           },
           "required": ["subject", "body_markdown", "requested_action"],
       },
   },
]


def _erp_payload(state: InvoiceComplianceState, note: str) -> Dict[str, Any]:
   invoice = state["extracted_invoice"]
   return {
       "vendor_id": invoice.vendor_id,
       "invoice_number": invoice.invoice_number,
       "status": "CLEARED_FOR_PAYMENT",
       "amount": invoice.total_invoiced_amount,
       "notes": note or "Automated compliance check passed",
   }


def _default_vendor_notice(state: InvoiceComplianceState) -> Dict[str, Any]:
   invoice = state["extracted_invoice"]
   report = state["audit_report"]
   return {
       "subject": f"Invoice {invoice.invoice_number} returned - clarification or corrected invoice required",
       "body_markdown": report.dispute_memo_markdown
       or "Your invoice did not comply with contract terms. Please clarify or resubmit.",
       "requested_action": "BOTH",
   }


def posting_agent_node(state: InvoiceComplianceState) -> Dict[str, Any]:
   verdict = state["compliance_verdict"]
   invoice = state["extracted_invoice"]
   report = state["audit_report"]
   outcome: Dict[str, Any] = {}

   def post_invoice_to_erp(args: Dict[str, Any]) -> Dict[str, Any]:
       # Guardrail enforced in code, not only in the prompt.
       if verdict["decision"] != "PASS":
           return {"error": "BLOCKED: cannot post an invoice that failed compliance. Use return_to_vendor."}
       outcome["result"] = "POSTED"
       outcome["erp"] = _erp_payload(state, args.get("note", ""))
       return {"posted": True, "erp_payload": outcome["erp"]}

   def return_to_vendor(args: Dict[str, Any]) -> Dict[str, Any]:
       if verdict["decision"] == "PASS":
           return {"error": "Invoice passed compliance; post it instead."}
       outcome["result"] = "RETURNED_TO_VENDOR"
       outcome["notice"] = {
           "to_vendor": invoice.vendor_id,
           "invoice_number": invoice.invoice_number,
           "subject": args["subject"],
           "body_markdown": args["body_markdown"],
           "requested_action": args["requested_action"],
       }
       return {"sent": True}

   trace = []
   if llm_available():
       try:
           context = (
               f"Invoice {invoice.invoice_number} ({invoice.vendor_id}), total ${invoice.total_invoiced_amount:,.2f}.\n"
               f"Compliance verdict: {verdict['decision']}.\nRationale: {verdict['rationale']}\n"
           )
           if report.discrepancies:
               context += "Findings:\n" + "\n".join(
                   f"- {d.discrepancy_type.value}: billed ${d.billed_amount:,.2f}, allowed "
                   f"${d.contractually_allowed_amount:,.2f}, overcharge ${d.overcharge_amount:,.2f}. "
                   f"Clause: {d.referenced_contract_clause}. Evidence: {d.ground_truth_doc_reference}. "
                   f"{d.audit_explanation}"
                   for d in report.discrepancies
               )
           trace, _ = run_tool_loop(
               SYSTEM_PROMPT,
               context,
               TOOLS,
               {"post_invoice_to_erp": post_invoice_to_erp, "return_to_vendor": return_to_vendor},
               terminal_tool="post_invoice_to_erp" if verdict["decision"] == "PASS" else "return_to_vendor",
           )
       except Exception as exc:
           trace.append({"type": "thought", "text": f"LLM unavailable ({exc}); using deterministic posting."})

   if not outcome:
       if verdict["decision"] == "PASS":
           post_invoice_to_erp({})
       else:
           return_to_vendor(_default_vendor_notice(state))
       trace.append({"type": "tool_call", "tool": "deterministic_fallback", "input": {}, "result": outcome["result"]})

   if outcome["result"] == "POSTED":
       return {
           "posting_result": "POSTED",
           "generated_erp_payload": outcome["erp"],
           "generated_vendor_email": None,
           "agent_trace": {"posting": trace},
       }
   notice = outcome["notice"]
   return {
       "posting_result": "RETURNED_TO_VENDOR",
       "generated_erp_payload": {
           "vendor_id": invoice.vendor_id,
           "invoice_number": invoice.invoice_number,
           "status": "RETURNED_TO_VENDOR",
           "requested_action": notice["requested_action"],
           "blocked_amount": report.total_disputed,
       },
       "generated_vendor_email": f"**{notice['subject']}**\n\n{notice['body_markdown']}",
       "agent_trace": {"posting": trace},
   }
