from typing import Any, Dict, Literal
from langgraph.types import interrupt
from models import ComplianceStatus
from state import InvoiceComplianceState


def human_review_node(state: InvoiceComplianceState) -> Dict[str, Any]:
   report = state["audit_report"]
   invoice = state["extracted_invoice"]

   review_prompt = {
       "invoice_number": invoice.invoice_number,
       "vendor_id": invoice.vendor_id,
       "total_invoiced": report.total_invoiced,
       "total_disputed": report.total_disputed,
       "total_approved": report.total_approved,
       "discrepancies": [d.model_dump() for d in report.discrepancies],
       "dispute_memo": report.dispute_memo_markdown,
       "allowed_actions": ["DISPUTE_VENDOR", "OVERRIDE_AND_APPROVE", "REJECT_INVOICE"],
   }

   human_submission = interrupt(review_prompt)

   decision = human_submission.get("decision")
   notes = human_submission.get("notes", "")

   return {
       "human_reviewer_decision": decision,
       "human_notes": notes,
   }


def dispatcher_node(state: InvoiceComplianceState) -> Dict[str, Any]:
   decision = state.get("human_reviewer_decision")
   report = state["audit_report"]
   invoice = state["extracted_invoice"]

   if decision == "OVERRIDE_AND_APPROVE" or report.status == ComplianceStatus.APPROVED:
       erp_payload = {
           "vendor_id": invoice.vendor_id,
           "invoice_number": invoice.invoice_number,
           "status": "CLEARED_FOR_PAYMENT",
           "amount": invoice.total_invoiced_amount,
           "notes": state.get("human_notes") or "Automated 3-Way Match Passed",
       }
       return {
           "generated_erp_payload": erp_payload,
           "generated_vendor_email": None,
       }

   elif decision == "DISPUTE_VENDOR":
       erp_payload = {
           "vendor_id": invoice.vendor_id,
           "invoice_number": invoice.invoice_number,
           "status": "SHORT_PAY_HOLD",
           "payable_amount": report.total_approved,
           "blocked_amount": report.total_disputed,
       }
       return {
           "generated_erp_payload": erp_payload,
           "generated_vendor_email": report.dispute_memo_markdown,
       }

   else:
       return {
           "generated_erp_payload": {"status": "VOID_REJECTED"},
           "generated_vendor_email": f"Invoice {invoice.invoice_number} rejected. Reason: {state.get('human_notes')}",
       }


def route_after_reasoning(state: InvoiceComplianceState) -> Literal["human_review_node", "dispatcher_node"]:
   if state.get("requires_human_approval"):
       return "human_review_node"
   return "dispatcher_node"
