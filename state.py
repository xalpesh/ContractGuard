from typing import Annotated, Dict, List, Optional, Union
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

from models import (
   AuditReport,
   GoodsReceiptRecord,
   Invoice,
   MaterialContractTerms,
   ServiceContractTerms,
   ServiceEntrySheet,
)


def _merge_traces(left: Optional[Dict[str, list]], right: Optional[Dict[str, list]]) -> Dict[str, list]:
   return {**(left or {}), **(right or {})}


class InvoiceComplianceState(TypedDict):
   invoice_raw_path: str
   contract_raw_path: str
   po_or_sow_id: str
   track: Optional[str]

   extracted_invoice: Optional[Invoice]
   contract_terms: Optional[Union[MaterialContractTerms, ServiceContractTerms]]
   
   goods_receipts: Optional[List[GoodsReceiptRecord]]
   service_entry_sheets: Optional[List[ServiceEntrySheet]]

   external_indices: Dict[str, float]
   audit_report: Optional[AuditReport]

   requires_human_approval: bool
   human_reviewer_decision: Optional[str]
   human_notes: Optional[str]

   generated_erp_payload: Optional[Dict]
   generated_vendor_email: Optional[str]

   compliance_verdict: Optional[Dict]
   posting_result: Optional[str]
   agent_trace: Annotated[Dict[str, list], _merge_traces]

   messages: Annotated[list, add_messages]
   processing_errors: List[str]
