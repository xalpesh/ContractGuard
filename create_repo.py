import os
import zipfile
from pathlib import Path

FILES = {}

# --- requirements.txt ---
FILES["requirements.txt"] = """\
langgraph>=0.2.20
langchain-core>=0.3.0
pydantic>=2.7.0
streamlit>=1.38.0
pandas>=2.2.0
"""

# --- .gitignore ---
FILES[".gitignore"] = """\
__pycache__/
*.py[cod]
*$py.class
.venv/
env/
venv/
.DS_Store
*.sqlite
.streamlit/
"""

# --- models.py ---
FILES["models.py"] = '''\
from datetime import date
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class InvoiceTrack(str, Enum):
   MATERIAL = "MATERIAL"
   SERVICE = "SERVICE"


class DiscrepancyType(str, Enum):
   # Material Discrepancies
   PRICE_INDEX_MISMATCH = "PRICE_INDEX_MISMATCH"
   QUANTITY_OVER_TOLERANCE = "QUANTITY_OVER_TOLERANCE"
   PROHIBITED_SURCHARGE = "PROHIBITED_SURCHARGE"
   INCOTERM_VIOLATION = "INCOTERM_VIOLATION"
   DAMAGED_GOODS_BILLED = "DAMAGED_GOODS_BILLED"
   
   # Service Discrepancies
   SKILL_CERTIFICATION_UNVERIFIED = "SKILL_CERTIFICATION_UNVERIFIED"
   RATE_CARD_MISMATCH = "RATE_CARD_MISMATCH"
   OVERTIME_RATE_UNAUTHORIZED = "OVERTIME_RATE_UNAUTHORIZED"
   GATE_LOG_HOURS_MISMATCH = "GATE_LOG_HOURS_MISMATCH"
   SOW_HOURS_CAP_EXCEEDED = "SOW_HOURS_CAP_EXCEEDED"
   SOW_AMOUNT_CAP_EXCEEDED = "SOW_AMOUNT_CAP_EXCEEDED"
   PER_DIEM_EXCEEDED = "PER_DIEM_EXCEEDED"
   UNAPPROVED_EXPENSE = "UNAPPROVED_EXPENSE"
   
   # General
   ARITHMETIC_ERROR = "ARITHMETIC_ERROR"


class ComplianceStatus(str, Enum):
   APPROVED = "APPROVED"
   AUTO_REJECTED = "AUTO_REJECTED"
   FLAGGED_FOR_REVIEW = "FLAGGED_FOR_REVIEW"


class MaterialContractTerms(BaseModel):
   contract_id: str
   vendor_id: str
   effective_date: date
   incoterm: str = Field(description="Agreed Incoterm, e.g., 'DDP', 'FOB Destination'")
   quantity_tolerance_pct: float = Field(default=0.0)
   freight_allowed: bool = Field(default=False)
   packaging_fees_allowed: bool = Field(default=False)
   index_name: Optional[str] = None
   index_baseline_value: Optional[float] = None
   index_pass_through_coefficient: Optional[float] = Field(default=1.0)
   base_material_unit_price: Dict[str, float] = Field(default_factory=dict)


class ServiceRateCard(BaseModel):
   role_name: str
   required_certification: Optional[str] = Field(default=None)
   standard_hourly_rate: float
   overtime_hourly_rate: Optional[float] = None
   overtime_multiplier: float = Field(default=1.5)
   overtime_requires_preapproval: bool = True
   max_authorized_hours: Optional[float] = Field(default=None)
   downgrade_role_fallback: Optional[str] = Field(default=None)


class ServiceContractTerms(BaseModel):
   contract_id: str
   vendor_id: str
   effective_date: date
   rate_cards: Dict[str, ServiceRateCard]
   sow_total_budget_cap: Optional[float] = Field(default=None)
   per_diem_daily_cap: float = Field(default=0.0)
   mileage_rate_allowed: float = Field(default=0.0)
   tool_allowance_cap: float = Field(default=0.0)


class GoodsReceiptRecord(BaseModel):
   gr_number: str
   po_number: str
   line_item: int
   material_sku: str
   received_quantity: float
   accepted_quantity: float
   rejected_quantity: float = 0.0
   uom: str
   dock_receipt_date: date
   scale_ticket_id: Optional[str] = None


class ServiceEntrySheet(BaseModel):
   ses_number: str
   sow_number: str
   line_item: int
   technician_name: str
   role_classified: str
   technician_certifications: List[str] = Field(default_factory=list)
   badge_in_time: str
   badge_out_time: str
   regular_hours: float
   overtime_hours: float = 0.0
   verified_hours: float
   overtime_preapproved: bool = False
   work_order_id: str


class InvoiceLineItem(BaseModel):
   line_number: int
   item_type: InvoiceTrack
   sku_or_role: str
   description: str
   regular_hours_billed: Optional[float] = None
   overtime_hours_billed: Optional[float] = None
   billed_quantity: float
   billed_unit_price: float
   total_line_amount: float
   po_or_sow_reference: str


class AdditionalCharge(BaseModel):
   charge_type: str
   amount: float
   clause_justification: Optional[str] = None


class Invoice(BaseModel):
   invoice_number: str
   vendor_id: str
   invoice_date: date
   track: InvoiceTrack
   line_items: List[InvoiceLineItem]
   additional_charges: List[AdditionalCharge] = Field(default_factory=list)
   total_invoiced_amount: float


class AuditDiscrepancy(BaseModel):
   line_number: Optional[int]
   discrepancy_type: DiscrepancyType
   billed_amount: float
   contractually_allowed_amount: float
   overcharge_amount: float
   referenced_contract_clause: str
   ground_truth_doc_reference: str
   audit_explanation: str


class AuditReport(BaseModel):
   status: ComplianceStatus
   total_invoiced: float
   total_approved: float
   total_disputed: float
   discrepancies: List[AuditDiscrepancy]
   dispute_memo_markdown: Optional[str] = None
   erp_clearing_payload: Optional[Dict] = None
'''

# --- state.py ---
FILES["state.py"] = '''\
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

   messages: Annotated[list, add_messages]
   processing_errors: List[str]
'''

# --- reasoner.py (Material Track) ---
FILES["reasoner.py"] = '''\
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Tuple
from models import (
   AuditDiscrepancy,
   AuditReport,
   ComplianceStatus,
   DiscrepancyType,
   GoodsReceiptRecord,
   Invoice,
   InvoiceLineItem,
   MaterialContractTerms,
)
from state import InvoiceComplianceState


def _to_cents(value: float) -> Decimal:
   return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calculate_contract_unit_price(
   sku: str,
   contract: MaterialContractTerms,
   external_indices: Dict[str, float],
) -> Decimal:
   base_price = contract.base_material_unit_price.get(sku)
   if base_price is None:
       raise ValueError(f"SKU {sku} not found in contract rate schedule.")

   base_dec = _to_cents(base_price)
   if not contract.index_name or contract.index_baseline_value is None:
       return base_dec

   current_index = external_indices.get(contract.index_name)
   if current_index is None:
       return base_dec

   index_delta = current_index - contract.index_baseline_value
   coeff = contract.index_pass_through_coefficient or 1.0
   adjustment = Decimal(str(index_delta * coeff))
   return (base_dec + adjustment).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _audit_material_line(
   line: InvoiceLineItem,
   contract: MaterialContractTerms,
   gr_records: List[GoodsReceiptRecord],
   external_indices: Dict[str, float],
) -> Tuple[List[AuditDiscrepancy], Decimal]:
   discrepancies: List[AuditDiscrepancy] = []
   computed_line_total = _to_cents(line.billed_quantity * line.billed_unit_price)
   stated_line_total = _to_cents(line.total_line_amount)

   if computed_line_total != stated_line_total:
       diff = stated_line_total - computed_line_total
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.ARITHMETIC_ERROR,
               billed_amount=float(stated_line_total),
               contractually_allowed_amount=float(computed_line_total),
               overcharge_amount=float(diff),
               referenced_contract_clause="Standard Commercial Practice - Math Integrity",
               ground_truth_doc_reference=f"Invoice Line {line.line_number}",
               audit_explanation=f"Line calculation mismatch: {line.billed_quantity} * {line.billed_unit_price} = {computed_line_total}, billed {stated_line_total}.",
           )
       )

   try:
       allowed_unit_price = _calculate_contract_unit_price(line.sku_or_role, contract, external_indices)
   except ValueError as e:
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.RATE_CARD_MISMATCH,
               billed_amount=line.total_line_amount,
               contractually_allowed_amount=0.0,
               overcharge_amount=line.total_line_amount,
               referenced_contract_clause="Clause 3.1 - Approved Product Catalog",
               ground_truth_doc_reference=contract.contract_id,
               audit_explanation=str(e),
           )
       )
       return discrepancies, Decimal("0.00")

   billed_unit_price_dec = _to_cents(line.billed_unit_price)
   if billed_unit_price_dec > allowed_unit_price:
       unit_delta = billed_unit_price_dec - allowed_unit_price
       total_price_overcharge = _to_cents(float(unit_delta) * line.billed_quantity)
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.PRICE_INDEX_MISMATCH,
               billed_amount=float(billed_unit_price_dec),
               contractually_allowed_amount=float(allowed_unit_price),
               overcharge_amount=float(total_price_overcharge),
               referenced_contract_clause="Clause 5.2 - Dynamic Raw Material Indexation",
               ground_truth_doc_reference=f"Index: {contract.index_name or 'Base Rate Schedule'}",
               audit_explanation=(
                   f"Billed unit price ${billed_unit_price_dec} exceeds formula-adjusted price "
                   f"${allowed_unit_price} (Index: {contract.index_name})."
               ),
           )
       )

   matching_grs = [
       gr for gr in gr_records 
       if gr.material_sku == line.sku_or_role and gr.po_number == line.po_or_sow_reference
   ]

   if not matching_grs:
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.QUANTITY_OVER_TOLERANCE,
               billed_amount=line.total_line_amount,
               contractually_allowed_amount=0.0,
               overcharge_amount=line.total_line_amount,
               referenced_contract_clause="Clause 7.1 - Proof of Delivery & Acceptance",
               ground_truth_doc_reference=line.po_or_sow_reference,
               audit_explanation=f"No matching Goods Receipt dock record found for SKU {line.sku_or_role}.",
           )
       )
       return discrepancies, Decimal("0.00")

   total_accepted_qty = sum(gr.accepted_quantity for gr in matching_grs)
   total_rejected_qty = sum(gr.rejected_quantity for gr in matching_grs)
   gr_references = ", ".join(gr.gr_number for gr in matching_grs)

   if line.billed_quantity > total_accepted_qty and total_rejected_qty > 0:
       rejected_billed = min(line.billed_quantity - total_accepted_qty, total_rejected_qty)
       overcharge = _to_cents(rejected_billed * float(allowed_unit_price))
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.DAMAGED_GOODS_BILLED,
               billed_amount=float(_to_cents(rejected_billed * float(billed_unit_price_dec))),
               contractually_allowed_amount=0.0,
               overcharge_amount=float(overcharge),
               referenced_contract_clause="Clause 8.4 - Damaged and Rejected Freight Remedies",
               ground_truth_doc_reference=f"GR: {gr_references}",
               audit_explanation=f"Vendor billed for {rejected_billed} rejected/damaged units logged at receiving dock.",
           )
       )

   allowed_tolerance_qty = total_accepted_qty * (1.0 + (contract.quantity_tolerance_pct / 100.0))
   if line.billed_quantity > allowed_tolerance_qty:
       excess_qty = line.billed_quantity - allowed_tolerance_qty
       overcharge = _to_cents(excess_qty * float(allowed_unit_price))
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.QUANTITY_OVER_TOLERANCE,
               billed_amount=float(_to_cents(excess_qty * float(billed_unit_price_dec))),
               contractually_allowed_amount=0.0,
               overcharge_amount=float(overcharge),
               referenced_contract_clause=f"Clause 4.1 - Quantity Tolerance Cap (+/- {contract.quantity_tolerance_pct}%)",
               ground_truth_doc_reference=f"GR: {gr_references}",
               audit_explanation=f"Billed qty ({line.billed_quantity}) exceeds tolerance ceiling ({allowed_tolerance_qty}).",
           )
       )

   approved_payable_qty = min(line.billed_quantity, total_accepted_qty)
   line_approved = _to_cents(approved_payable_qty * float(allowed_unit_price))
   return discrepancies, line_approved


def _audit_additional_charges(
   invoice: Invoice,
   contract: MaterialContractTerms,
) -> Tuple[List[AuditDiscrepancy], Decimal]:
   discrepancies: List[AuditDiscrepancy] = []
   total_approved_charges = Decimal("0.00")

   for charge in invoice.additional_charges:
       charge_amt = _to_cents(charge.amount)
       charge_lower = charge.charge_type.lower()

       if ("freight" in charge_lower or "fuel" in charge_lower) and not contract.freight_allowed:
           discrepancies.append(
               AuditDiscrepancy(
                   line_number=None,
                   discrepancy_type=DiscrepancyType.INCOTERM_VIOLATION,
                   billed_amount=float(charge_amt),
                   contractually_allowed_amount=0.0,
                   overcharge_amount=float(charge_amt),
                   referenced_contract_clause=f"Clause 2.1 - Incoterms ({contract.incoterm}) Freight Obligation",
                   ground_truth_doc_reference=contract.contract_id,
                   audit_explanation=f"Freight/fuel charge prohibited under Incoterm {contract.incoterm}.",
               )
           )
       elif ("pallet" in charge_lower or "packaging" in charge_lower) and not contract.packaging_fees_allowed:
           discrepancies.append(
               AuditDiscrepancy(
                   line_number=None,
                   discrepancy_type=DiscrepancyType.PROHIBITED_SURCHARGE,
                   billed_amount=float(charge_amt),
                   contractually_allowed_amount=0.0,
                   overcharge_amount=float(charge_amt),
                   referenced_contract_clause="Clause 6.3 - Non-Reimbursable Packaging Materials",
                   ground_truth_doc_reference=contract.contract_id,
                   audit_explanation=f"Packaging charge '{charge.charge_type}' prohibited by contract.",
               )
           )
       else:
           total_approved_charges += charge_amt

   return discrepancies, total_approved_charges


def _generate_material_dispute_memo(invoice: Invoice, discrepancies: List[AuditDiscrepancy], total_disputed: Decimal) -> str:
   memo = [
       f"## Vendor Dispute Notice: Invoice #{invoice.invoice_number}",
       f"**Vendor ID:** {invoice.vendor_id} | **Total Disputed Amount:** ${total_disputed:,.2f}\\n",
       "The following discrepancies were identified against contract terms and dock receipt records:\\n",
       "| Line / Item | Issue Type | Billed | Allowed | Overcharge | Referenced Clause | Ground Truth Ref |",
       "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
   ]
   for d in discrepancies:
       line_ref = f"Line {d.line_number}" if d.line_number else "Charge"
       memo.append(
           f"| {line_ref} | {d.discrepancy_type.value} | ${d.billed_amount:,.2f} | "
           f"${d.contractually_allowed_amount:,.2f} | ${d.overcharge_amount:,.2f} | "
           f"{d.referenced_contract_clause} | {d.ground_truth_doc_reference} |"
       )
   return "\\n".join(memo)


def compliance_reasoner_node(state: InvoiceComplianceState) -> Dict[str, Any]:
   invoice: Invoice = state["extracted_invoice"]
   contract = state["contract_terms"]
   gr_records = state.get("goods_receipts") or []
   indices = state.get("external_indices") or {}

   if not isinstance(contract, MaterialContractTerms):
       raise TypeError("Expected MaterialContractTerms.")

   discrepancies: List[AuditDiscrepancy] = []
   total_approved = Decimal("0.00")

   for line in invoice.line_items:
       line_disc, line_approved = _audit_material_line(line, contract, gr_records, indices)
       discrepancies.extend(line_disc)
       total_approved += line_approved

   charge_disc, approved_charges = _audit_additional_charges(invoice, contract)
   discrepancies.extend(charge_disc)
   total_approved += approved_charges

   total_invoiced = _to_cents(invoice.total_invoiced_amount)
   total_disputed = sum((_to_cents(d.overcharge_amount) for d in discrepancies), Decimal("0.00"))

   if not discrepancies:
       status = ComplianceStatus.APPROVED
       memo = None
       erp_payload = {
           "vendor_id": invoice.vendor_id,
           "invoice_number": invoice.invoice_number,
           "clearing_status": "READY_FOR_PAYMENT",
           "payable_amount": float(total_approved),
       }
   else:
       status = ComplianceStatus.FLAGGED_FOR_REVIEW
       memo = _generate_material_dispute_memo(invoice, discrepancies, total_disputed)
       erp_payload = {
           "vendor_id": invoice.vendor_id,
           "invoice_number": invoice.invoice_number,
           "clearing_status": "BLOCKED_PAYMENT_DISPUTE",
           "held_amount": float(total_disputed),
           "approved_amount": float(total_approved),
       }

   audit_report = AuditReport(
       status=status,
       total_invoiced=float(total_invoiced),
       total_approved=float(total_approved),
       total_disputed=float(total_disputed),
       discrepancies=discrepancies,
       dispute_memo_markdown=memo,
       erp_clearing_payload=erp_payload,
   )

   return {
       "audit_report": audit_report,
       "requires_human_approval": status == ComplianceStatus.FLAGGED_FOR_REVIEW,
       "generated_vendor_email": memo if status == ComplianceStatus.FLAGGED_FOR_REVIEW else None,
       "generated_erp_payload": erp_payload,
   }
'''

# --- service_reasoner.py (Updated with Skills, Rates, Hours, & NTE Caps) ---
FILES["service_reasoner.py"] = '''\
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from models import (
   AuditDiscrepancy,
   AuditReport,
   ComplianceStatus,
   DiscrepancyType,
   Invoice,
   InvoiceLineItem,
   ServiceContractTerms,
   ServiceEntrySheet,
   ServiceRateCard,
)
from state import InvoiceComplianceState


def _to_cents(value: float) -> Decimal:
   return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _extract_per_diem_days(charge_justification: Optional[str], ses_records: List[ServiceEntrySheet]) -> int:
   if charge_justification:
       match = re.search(r"(\\d+)\\s*days?", charge_justification, re.IGNORECASE)
       if match:
           return int(match.group(1))

   logged_dates = set()
   for ses in ses_records:
       if ses.badge_in_time:
           logged_dates.add(ses.badge_in_time[:10])
   return len(logged_dates) if logged_dates else 1


def _validate_skill_and_credentials(
   line: InvoiceLineItem,
   rate_card: ServiceRateCard,
   matching_ses: List[ServiceEntrySheet],
   contract: ServiceContractTerms,
) -> Tuple[List[AuditDiscrepancy], Decimal, str]:
   discrepancies: List[AuditDiscrepancy] = []
   applicable_role = rate_card.role_name
   allowed_rate = _to_cents(rate_card.standard_hourly_rate)

   if not rate_card.required_certification:
       return discrepancies, allowed_rate, applicable_role

   required_cert = rate_card.required_certification
   unqualified_technicians = []

   for ses in matching_ses:
       if required_cert not in ses.technician_certifications:
           unqualified_technicians.append(f"{ses.technician_name} (Missing: {required_cert})")

   if unqualified_technicians:
       tech_list = ", ".join(unqualified_technicians)
       fallback_role = rate_card.downgrade_role_fallback
       fallback_card = contract.rate_cards.get(fallback_role) if fallback_role else None

       if fallback_card:
           allowed_rate = _to_cents(fallback_card.standard_hourly_rate)
           applicable_role = fallback_card.role_name
           remediation_msg = f"Reclassified to '{fallback_role}' at ${allowed_rate}/hr."
       else:
           allowed_rate = Decimal("0.00")
           remediation_msg = "No fallback rate found. Payment withheld."

       billed_unit_price = _to_cents(line.billed_unit_price)
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.SKILL_CERTIFICATION_UNVERIFIED,
               billed_amount=float(billed_unit_price),
               contractually_allowed_amount=float(allowed_rate),
               overcharge_amount=float(billed_unit_price - allowed_rate),
               referenced_contract_clause=f"Clause 3.2 - Mandatory Skill Certification ({required_cert})",
               ground_truth_doc_reference=f"Contractor Registry / SES: {tech_list}",
               audit_explanation=(
                   f"Technician(s) billed as '{rate_card.role_name}' lacked certification '{required_cert}'. "
                   f"{remediation_msg}"
               ),
           )
       )

   return discrepancies, allowed_rate, applicable_role


def _audit_service_line(
   line: InvoiceLineItem,
   contract: ServiceContractTerms,
   ses_records: List[ServiceEntrySheet],
) -> Tuple[List[AuditDiscrepancy], Decimal]:
   discrepancies: List[AuditDiscrepancy] = []

   # 1. Math Integrity
   computed_line_total = _to_cents(line.billed_quantity * line.billed_unit_price)
   stated_line_total = _to_cents(line.total_line_amount)
   if computed_line_total != stated_line_total:
       diff = stated_line_total - computed_line_total
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.ARITHMETIC_ERROR,
               billed_amount=float(stated_line_total),
               contractually_allowed_amount=float(computed_line_total),
               overcharge_amount=float(diff),
               referenced_contract_clause="Standard Commercial Terms - Math Accuracy",
               ground_truth_doc_reference=f"Invoice Line {line.line_number}",
               audit_explanation=f"Math error: {line.billed_quantity} hrs * ${line.billed_unit_price} != ${stated_line_total}.",
           )
       )

   # 2. Rate Card Existence
   rate_card = contract.rate_cards.get(line.sku_or_role)
   if not rate_card:
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.RATE_CARD_MISMATCH,
               billed_amount=line.total_line_amount,
               contractually_allowed_amount=0.0,
               overcharge_amount=line.total_line_amount,
               referenced_contract_clause="Schedule B - Approved Labor Classifications",
               ground_truth_doc_reference=contract.contract_id,
               audit_explanation=f"Role '{line.sku_or_role}' is not in the approved contract rate card.",
           )
       )
       return discrepancies, Decimal("0.00")

   matching_ses = [
       ses for ses in ses_records
       if ses.role_classified == line.sku_or_role and ses.sow_number == line.po_or_sow_reference
   ]
   ses_ref_str = ", ".join(set(s.ses_number for s in matching_ses)) or "NO_RECORD"

   # 3. Skill & Certification Validation
   skill_discrepancies, base_allowed_rate, active_role = _validate_skill_and_credentials(
       line=line,
       rate_card=rate_card,
       matching_ses=matching_ses,
       contract=contract,
   )
   discrepancies.extend(skill_discrepancies)

   # 4. Hours Reconciliation
   total_ses_hours = sum(s.verified_hours for s in matching_ses)
   ot_approved = any(s.overtime_preapproved for s in matching_ses)

   if line.billed_quantity > total_ses_hours:
       unlogged_hours = line.billed_quantity - total_ses_hours
       overcharge = _to_cents(unlogged_hours * line.billed_unit_price)
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.GATE_LOG_HOURS_MISMATCH,
               billed_amount=float(_to_cents(line.billed_quantity * line.billed_unit_price)),
               contractually_allowed_amount=float(_to_cents(total_ses_hours * line.billed_unit_price)),
               overcharge_amount=float(overcharge),
               referenced_contract_clause="Clause 4.1 - Physical Turnstile / SES Verification",
               ground_truth_doc_reference=f"SES/Gate Logs: {ses_ref_str}",
               audit_explanation=(
                   f"Billed {line.billed_quantity} hrs for '{line.sku_or_role}', but plant entry logs "
                   f"confirm only {total_ses_hours} total hours on-site."
               ),
           )
       )

   hours_to_audit = min(line.billed_quantity, total_ses_hours)
   if rate_card.max_authorized_hours and hours_to_audit > rate_card.max_authorized_hours:
       excess_cap_hours = hours_to_audit - rate_card.max_authorized_hours
       cap_overcharge = _to_cents(excess_cap_hours * float(base_allowed_rate))
       discrepancies.append(
           AuditDiscrepancy(
               line_number=line.line_number,
               discrepancy_type=DiscrepancyType.SOW_HOURS_CAP_EXCEEDED,
               billed_amount=float(_to_cents(hours_to_audit * float(base_allowed_rate))),
               contractually_allowed_amount=float(_to_cents(rate_card.max_authorized_hours * float(base_allowed_rate))),
               overcharge_amount=float(cap_overcharge),
               referenced_contract_clause="Schedule A - Maximum Labor Allocation Ceiling",
               ground_truth_doc_reference=f"SOW: {line.po_or_sow_reference}",
               audit_explanation=(
                   f"Authorized limit ({rate_card.max_authorized_hours} hrs) exceeded by {excess_cap_hours} hrs."
               ),
           )
       )
       hours_to_audit = rate_card.max_authorized_hours

   # 5. Rate & Overtime Audit
   billed_unit_price = _to_cents(line.billed_unit_price)
   is_overtime_billing = "overtime" in line.description.lower() or "ot" in line.description.lower()

   if is_overtime_billing:
       multiplier = Decimal(str(rate_card.overtime_multiplier))
       contracted_ot_rate = (base_allowed_rate * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

       if rate_card.overtime_requires_preapproval and not ot_approved:
           overcharge = _to_cents(hours_to_audit * float(billed_unit_price - base_allowed_rate))
           discrepancies.append(
               AuditDiscrepancy(
                   line_number=line.line_number,
                   discrepancy_type=DiscrepancyType.OVERTIME_RATE_UNAUTHORIZED,
                   billed_amount=float(billed_unit_price),
                   contractually_allowed_amount=float(base_allowed_rate),
                   overcharge_amount=float(overcharge),
                   referenced_contract_clause="Clause 5.3 - Overtime Prior Authorization Mandate",
                   ground_truth_doc_reference=f"SES: {ses_ref_str} (Pre-Approval: False)",
                   audit_explanation=(
                       f"Overtime multiplier ({rate_card.overtime_multiplier}x) denied. No pre-approval logged. "
                       f"Reverted to standard rate ${base_allowed_rate}/hr."
                   ),
               )
           )
           line_approved_amount = _to_cents(hours_to_audit * float(base_allowed_rate))
       else:
           if billed_unit_price > contracted_ot_rate:
               rate_delta = billed_unit_price - contracted_ot_rate
               overcharge = _to_cents(hours_to_audit * float(rate_delta))
               discrepancies.append(
                   AuditDiscrepancy(
                       line_number=line.line_number,
                       discrepancy_type=DiscrepancyType.RATE_CARD_MISMATCH,
                       billed_amount=float(billed_unit_price),
                       contractually_allowed_amount=float(contracted_ot_rate),
                       overcharge_amount=float(overcharge),
                       referenced_contract_clause="Schedule B - Overtime Rate Schedule",
                       ground_truth_doc_reference=contract.contract_id,
                       audit_explanation=f"Billed OT rate ${billed_unit_price}/hr exceeds allowable ${contracted_ot_rate}/hr.",
                   )
               )
           line_approved_amount = _to_cents(hours_to_audit * float(contracted_ot_rate))
   else:
       if billed_unit_price > base_allowed_rate:
           rate_delta = billed_unit_price - base_allowed_rate
           overcharge = _to_cents(hours_to_audit * float(rate_delta))
           discrepancies.append(
               AuditDiscrepancy(
                   line_number=line.line_number,
                   discrepancy_type=DiscrepancyType.RATE_CARD_MISMATCH,
                   billed_amount=float(billed_unit_price),
                   contractually_allowed_amount=float(base_allowed_rate),
                   overcharge_amount=float(overcharge),
                   referenced_contract_clause="Schedule B - Standard Labor Rate Schedule",
                   ground_truth_doc_reference=contract.contract_id,
                   audit_explanation=f"Billed rate ${billed_unit_price}/hr exceeds agreed rate of ${base_allowed_rate}/hr for '{active_role}'.",
               )
           )
       line_approved_amount = _to_cents(hours_to_audit * float(base_allowed_rate))

   return discrepancies, line_approved_amount


def _audit_service_expenses(
   invoice: Invoice,
   contract: ServiceContractTerms,
   ses_records: List[ServiceEntrySheet],
) -> Tuple[List[AuditDiscrepancy], Decimal]:
   discrepancies: List[AuditDiscrepancy] = []
   total_approved_expenses = Decimal("0.00")

   for charge in invoice.additional_charges:
       charge_amt = _to_cents(charge.amount)
       charge_name = charge.charge_type.lower()

       if "per diem" in charge_name or "meal" in charge_name or "lodging" in charge_name:
           num_days = _extract_per_diem_days(charge.clause_justification, ses_records)
           daily_cap = _to_cents(contract.per_diem_daily_cap)
           max_allowed = _to_cents(num_days * float(daily_cap))

           if charge_amt > max_allowed:
               overcharge = charge_amt - max_allowed
               discrepancies.append(
                   AuditDiscrepancy(
                       line_number=None,
                       discrepancy_type=DiscrepancyType.PER_DIEM_EXCEEDED,
                       billed_amount=float(charge_amt),
                       contractually_allowed_amount=float(max_allowed),
                       overcharge_amount=float(overcharge),
                       referenced_contract_clause=f"Clause 9.3 - Per Diem Daily Cap (${daily_cap}/day)",
                       ground_truth_doc_reference="Plant Gate Log Timesheets",
                       audit_explanation=f"Per diem of ${charge_amt} for {num_days} days exceeds cap of ${max_allowed}.",
                   )
               )
               total_approved_expenses += max_allowed
           else:
               total_approved_expenses += charge_amt

       elif "tool" in charge_name or "equipment" in charge_name:
           cap = _to_cents(contract.tool_allowance_cap)
           if charge_amt > cap:
               overcharge = charge_amt - cap
               discrepancies.append(
                   AuditDiscrepancy(
                       line_number=None,
                       discrepancy_type=DiscrepancyType.UNAPPROVED_EXPENSE,
                       billed_amount=float(charge_amt),
                       contractually_allowed_amount=float(cap),
                       overcharge_amount=float(overcharge),
                       referenced_contract_clause=f"Clause 11.2 - Tool Reimbursement Cap (${cap})",
                       ground_truth_doc_reference=contract.contract_id,
                       audit_explanation=f"Tool expense ${charge_amt} exceeds cap of ${cap}.",
                   )
               )
               total_approved_expenses += cap
           else:
               total_approved_expenses += charge_amt
       else:
           discrepancies.append(
               AuditDiscrepancy(
                   line_number=None,
                   discrepancy_type=DiscrepancyType.UNAPPROVED_EXPENSE,
                   billed_amount=float(charge_amt),
                   contractually_allowed_amount=0.0,
                   overcharge_amount=float(charge_amt),
                   referenced_contract_clause="Clause 9.1 - Non-Reimbursable Miscellaneous Charges",
                   ground_truth_doc_reference=contract.contract_id,
                   audit_explanation=f"Charge '{charge.charge_type}' is not reimbursable.",
               )
           )

   return discrepancies, total_approved_expenses


def _generate_service_dispute_memo(invoice: Invoice, discrepancies: List[AuditDiscrepancy], total_disputed: Decimal) -> str:
   memo = [
       f"## Vendor Dispute Notice: Service Invoice #{invoice.invoice_number}",
       f"**Vendor ID:** {invoice.vendor_id} | **Total Disputed Amount:** ${total_disputed:,.2f}\\n",
       "Discrepancies identified against contracted rate cards, skill matrices, and SES badge logs:\\n",
       "| Item | Issue Type | Billed | Allowed | Overcharge | Referenced Clause | Ground Truth Ref |",
       "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
   ]
   for d in discrepancies:
       item_ref = f"Line {d.line_number}" if d.line_number else "Expense"
       memo.append(
           f"| {item_ref} | {d.discrepancy_type.value} | ${d.billed_amount:,.2f} | "
           f"${d.contractually_allowed_amount:,.2f} | ${d.overcharge_amount:,.2f} | "
           f"{d.referenced_contract_clause} | {d.ground_truth_doc_reference} |"
       )
   return "\\n".join(memo)


def service_compliance_reasoner_node(state: InvoiceComplianceState) -> Dict[str, Any]:
   invoice: Invoice = state["extracted_invoice"]
   contract = state["contract_terms"]
   ses_records = state.get("service_entry_sheets") or []

   if not isinstance(contract, ServiceContractTerms):
       raise TypeError("Expected ServiceContractTerms.")

   discrepancies: List[AuditDiscrepancy] = []
   total_approved = Decimal("0.00")

   # 1. Audit Labor Lines
   for line in invoice.line_items:
       line_disc, line_approved = _audit_service_line(line, contract, ses_records)
       discrepancies.extend(line_disc)
       total_approved += line_approved

   # 2. Audit Expenses
   expense_disc, approved_expenses = _audit_service_expenses(invoice, contract, ses_records)
   discrepancies.extend(expense_disc)
   total_approved += approved_expenses

   # 3. Overall SOW Financial Cap
   if contract.sow_total_budget_cap:
       nte_cap = _to_cents(contract.sow_total_budget_cap)
       if total_approved > nte_cap:
           overage = total_approved - nte_cap
           discrepancies.append(
               AuditDiscrepancy(
                   line_number=None,
                   discrepancy_type=DiscrepancyType.SOW_AMOUNT_CAP_EXCEEDED,
                   billed_amount=float(total_approved),
                   contractually_allowed_amount=float(nte_cap),
                   overcharge_amount=float(overage),
                   referenced_contract_clause=f"Clause 2.4 - SOW Not-to-Exceed Cap (${nte_cap:,.2f})",
                   ground_truth_doc_reference=f"SOW: {contract.contract_id}",
                   audit_explanation=f"Total payable exceeds SOW budget ceiling of ${nte_cap:,.2f}.",
               )
           )
           total_approved = nte_cap

   # 4. Aggregations & Status
   total_invoiced = _to_cents(invoice.total_invoiced_amount)
   total_disputed = sum((_to_cents(d.overcharge_amount) for d in discrepancies), Decimal("0.00"))

   status = ComplianceStatus.APPROVED if not discrepancies else ComplianceStatus.FLAGGED_FOR_REVIEW
   memo = _generate_service_dispute_memo(invoice, discrepancies, total_disputed) if discrepancies else None

   erp_payload = {
       "vendor_id": invoice.vendor_id,
       "invoice_number": invoice.invoice_number,
       "clearing_status": "READY_FOR_PAYMENT" if status == ComplianceStatus.APPROVED else "BLOCKED_SERVICE_DISPUTE",
       "payable_amount": float(total_approved),
       "held_amount": float(total_disputed),
       "cost_center": "PLANT_OPERATIONS_MRO",
   }

   audit_report = AuditReport(
       status=status,
       total_invoiced=float(total_invoiced),
       total_approved=float(total_approved),
       total_disputed=float(total_disputed),
       discrepancies=discrepancies,
       dispute_memo_markdown=memo,
       erp_clearing_payload=erp_payload,
   )

   return {
       "audit_report": audit_report,
       "requires_human_approval": status == ComplianceStatus.FLAGGED_FOR_REVIEW,
       "generated_vendor_email": memo,
       "generated_erp_payload": erp_payload,
   }
'''

# --- hitl_workflow.py ---
FILES["hitl_workflow.py"] = '''\
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
'''

# --- router.py ---
FILES["router.py"] = '''\
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
   memo = "## Automated Routing Failure\\n- " + "\\n- ".join(errors)
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
'''

# --- app.py ---
FILES["app.py"] = '''\
import json
import streamlit as st
import pandas as pd
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from models import (
   GoodsReceiptRecord,
   Invoice,
   MaterialContractTerms,
   ServiceContractTerms,
   ServiceEntrySheet,
   ComplianceStatus,
)
from router import build_unified_compliance_graph

st.set_page_config(
   page_title="InvoiceGuard | Manufacturing Compliance Swarm",
   page_icon="🛡️",
   layout="wide",
   initial_sidebar_state="expanded",
)

if "graph_app" not in st.session_state:
   st.session_state.checkpointer = MemorySaver()
   st.session_state.graph_app = build_unified_compliance_graph()

if "thread_id" not in st.session_state:
   st.session_state.thread_id = "INV-SESSION-001"

if "pipeline_run" not in st.session_state:
   st.session_state.pipeline_run = False


@st.cache_data
def load_fixture(fixture_type: str) -> dict:
   filename = "material_fixture.json" if fixture_type == "Material Track" else "service_fixture.json"
   with open(filename, "r") as f:
       return json.load(f)


def prepare_state_payload(fixture_data: dict, fixture_type: str) -> dict:
   is_material = fixture_type == "Material Track"
   return {
       "invoice_raw_path": f"invoices/{fixture_data['invoice']['invoice_number']}.pdf",
       "contract_raw_path": f"contracts/{fixture_data['contract_terms']['contract_id']}.pdf",
       "po_or_sow_id": fixture_data["invoice"]["line_items"][0]["po_or_sow_reference"],
       "track": None,
       "extracted_invoice": Invoice.model_validate(fixture_data["invoice"]),
       "contract_terms": (
           MaterialContractTerms.model_validate(fixture_data["contract_terms"])
           if is_material
           else ServiceContractTerms.model_validate(fixture_data["contract_terms"])
       ),
       "goods_receipts": (
           [GoodsReceiptRecord.model_validate(gr) for gr in fixture_data["goods_receipts"]]
           if is_material
           else None
       ),
       "service_entry_sheets": (
           [ServiceEntrySheet.model_validate(ses) for ses in fixture_data["service_entry_sheets"]]
           if not is_material
           else None
       ),
       "external_indices": fixture_data.get("external_indices", {}),
       "processing_errors": [],
       "messages": [],
   }


with st.sidebar:
   st.header("⚙️ Audit Control Plane")
   fixture_choice = st.selectbox("Select Test Scenario", ["Material Track", "Service Track"])
   st.text_input("Thread ID (LangGraph State Key)", key="thread_id")

   if st.button("🚀 Run Compliance Pipeline", type="primary", use_container_width=True):
       raw_fixture = load_fixture(fixture_choice)
       payload = prepare_state_payload(raw_fixture, fixture_choice)
       config = {"configurable": {"thread_id": st.session_state.thread_id}}

       with st.spinner("Reconciling 3-way match & index clauses..."):
           for _ in st.session_state.graph_app.stream(payload, config=config):
               pass
       st.session_state.pipeline_run = True
       st.rerun()

   if st.button("Reset Session", use_container_width=True):
       st.session_state.pipeline_run = False
       st.session_state.thread_id = f"INV-SESSION-{pd.Timestamp.now().strftime('%M%S')}"
       st.rerun()


st.title("🛡️ InvoiceGuard: Autonomous Compliance Swarm")
st.caption("Deterministic 3-Way Reconciliation & Dynamic Index Verification for Manufacturing Operations")

config = {"configurable": {"thread_id": st.session_state.thread_id}}
current_state = st.session_state.graph_app.get_state(config)

if not current_state.values or not st.session_state.pipeline_run:
   st.info("Select a test scenario in the sidebar and click **Run Compliance Pipeline** to begin.")
   st.stop()

state_values = current_state.values
report = state_values.get("audit_report")
invoice = state_values.get("extracted_invoice")
is_paused = bool(current_state.next)

col1, col2, col3, col4 = st.columns(4)
with col1:
   st.metric("Invoiced Amount", f"${report.total_invoiced:,.2f}" if report else "$0.00")
with col2:
   st.metric("Approved Payable", f"${report.total_approved:,.2f}" if report else "$0.00")
with col3:
   disputed = report.total_disputed if report else 0.0
   st.metric("Disputed Overcharge", f"${disputed:,.2f}", delta=f"-${disputed:,.2f}" if disputed > 0 else "0.00", delta_color="inverse")
with col4:
   if is_paused:
       st.metric("Pipeline State", "PAUSED", delta="HITL Gate Active", delta_color="off")
   elif report and report.status == ComplianceStatus.APPROVED:
       st.metric("Pipeline State", "CLEARED", delta="Auto-Approved", delta_color="normal")
   else:
       st.metric("Pipeline State", "COMPLETED", delta="Dispatched", delta_color="normal")

st.divider()
st.markdown(
   f"**Reconciliation Track:** `{state_values.get('track')}` | "
   f"**Invoice #:** `{invoice.invoice_number}` | "
   f"**Vendor ID:** `{invoice.vendor_id}` | "
   f"**Reference:** `{state_values.get('po_or_sow_id')}`"
)

st.subheader("🔍 Side-by-Side Audit Findings")
if report and report.discrepancies:
   table_data = []
   for d in report.discrepancies:
       table_data.append({
           "Target": f"Line {d.line_number}" if d.line_number else "Expense",
           "Violation Type": d.discrepancy_type.value,
           "Billed": f"${d.billed_amount:,.2f}",
           "Allowed": f"${d.contractually_allowed_amount:,.2f}",
           "Overcharge": f"${d.overcharge_amount:,.2f}",
           "Contract Clause": d.referenced_contract_clause,
           "Operational Proof": d.ground_truth_doc_reference,
           "Audit Explanation": d.audit_explanation,
       })
   st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
else:
   st.success("✅ Clean Match: All line items reconcile with dock receipts, rate cards, and skill matrices.")

if is_paused:
   st.warning("⚠️ **Human Approval Required:** System detected variance exceeding contractual tolerance.")
   with st.container(border=True):
       st.subheader("✍️ Reviewer Action Desk")
       with st.expander("📄 View Auto-Generated Legal Dispute Memo", expanded=True):
           st.markdown(report.dispute_memo_markdown)

       reviewer_notes = st.text_area("Reviewer Justification / Notes", placeholder="State rationale for short-pay or approval...")
       btn_col1, btn_col2, btn_col3 = st.columns(3)

       with btn_col1:
           if st.button("🟡 Submit Short-Pay & Dispute", type="primary", use_container_width=True):
               submission = {"decision": "DISPUTE_VENDOR", "notes": reviewer_notes}
               for _ in st.session_state.graph_app.stream(Command(resume=submission), config=config):
                   pass
               st.rerun()

       with btn_col2:
           if st.button("🟢 Override & Approve Full Amount", use_container_width=True):
               submission = {"decision": "OVERRIDE_AND_APPROVE", "notes": reviewer_notes}
               for _ in st.session_state.graph_app.stream(Command(resume=submission), config=config):
                   pass
               st.rerun()

       with btn_col3:
           if st.button("🔴 Void & Reject Entire Invoice", use_container_width=True):
               submission = {"decision": "REJECT_INVOICE", "notes": reviewer_notes}
               for _ in st.session_state.graph_app.stream(Command(resume=submission), config=config):
                   pass
               st.rerun()

if not is_paused and state_values.get("generated_erp_payload"):
   st.subheader("📦 Final Dispatch Artifacts")
   out_col1, out_col2 = st.columns(2)
   with out_col1:
       st.markdown("**ERP Accounts Payable Integration Payload**")
       st.json(state_values["generated_erp_payload"])
   with out_col2:
       st.markdown("**Outbound Vendor Notice**")
       if state_values.get("generated_vendor_email"):
           st.info(state_values["generated_vendor_email"])
       else:
           st.success("Invoice cleared cleanly. Scheduled for automated ERP clearing run.")
'''

# --- material_fixture.json ---
FILES["material_fixture.json"] = '''\
{
 "contract_terms": {
   "contract_id": "CTR-MAT-2026-081",
   "vendor_id": "VEND-SOLVENTS-INC",
   "effective_date": "2026-01-15",
   "incoterm": "DDP",
   "quantity_tolerance_pct": 5.0,
   "freight_allowed": false,
   "packaging_fees_allowed": false,
   "index_name": "ICIS_RESIN",
   "index_baseline_value": 800.0,
   "index_pass_through_coefficient": 0.5,
   "base_material_unit_price": {
     "SOLVENT-X": 1200.0,
     "POLY-RESIN-A": 450.0
   }
 },
 "goods_receipts": [
   {
     "gr_number": "GR-901124",
     "po_number": "PO-88231",
     "line_item": 1,
     "material_sku": "SOLVENT-X",
     "received_quantity": 100.0,
     "accepted_quantity": 95.0,
     "rejected_quantity": 5.0,
     "uom": "MT",
     "dock_receipt_date": "2026-09-12",
     "scale_ticket_id": "SCALE-TX-4402"
   }
 ],
 "external_indices": {
   "ICIS_RESIN": 840.0
 },
 "invoice": {
   "invoice_number": "INV-2026-9981",
   "vendor_id": "VEND-SOLVENTS-INC",
   "invoice_date": "2026-09-15",
   "track": "MATERIAL",
   "line_items": [
     {
       "line_number": 1,
       "item_type": "MATERIAL",
       "sku_or_role": "SOLVENT-X",
       "description": "Industrial Grade Solvent X - Bulk Delivery",
       "billed_quantity": 100.0,
       "billed_unit_price": 1250.0,
       "total_line_amount": 125000.0,
       "po_or_sow_reference": "PO-88231"
     }
   ],
   "additional_charges": [
     {
       "charge_type": "Emergency Fuel Surcharge",
       "amount": 1200.0,
       "clause_justification": "Carrier linehaul diesel adjustment"
     },
     {
       "charge_type": "Pallet & Restaging Fee",
       "amount": 350.0,
       "clause_justification": "Handling fee for specialized drum return"
     }
   ],
   "total_invoiced_amount": 126550.0
 }
}
'''

# --- service_fixture.json (Updated with Skill Certifications & SOW Budget Cap) ---
FILES["service_fixture.json"] = '''\
{
 "contract_terms": {
   "contract_id": "MSA-SRV-2026-004",
   "vendor_id": "VEND-PLANT-MAINT-CORP",
   "effective_date": "2026-02-01",
   "sow_total_budget_cap": 15000.0,
   "rate_cards": {
     "Master Millwright": {
       "role_name": "Master Millwright",
       "required_certification": "NCCER_ADVANCED",
       "standard_hourly_rate": 140.0,
       "overtime_multiplier": 1.5,
       "overtime_requires_preapproval": true,
       "max_authorized_hours": 80.0,
       "downgrade_role_fallback": "General Mechanic"
     },
     "General Mechanic": {
       "role_name": "General Mechanic",
       "required_certification": null,
       "standard_hourly_rate": 85.0,
       "overtime_multiplier": 1.5,
       "overtime_requires_preapproval": true,
       "max_authorized_hours": 120.0
     },
     "L3 Vibration Specialist": {
       "role_name": "L3 Vibration Specialist",
       "required_certification": "ISO_18436_CAT_III",
       "standard_hourly_rate": 175.0,
       "overtime_multiplier": 2.0,
       "overtime_requires_preapproval": true,
       "max_authorized_hours": 40.0,
       "downgrade_role_fallback": "General Mechanic"
     }
   },
   "per_diem_daily_cap": 65.0,
   "mileage_rate_allowed": 0.67,
   "tool_allowance_cap": 500.0
 },
 "service_entry_sheets": [
   {
     "ses_number": "SES-2026-00412",
     "sow_number": "SOW-TURBINE-OVERHAUL",
     "line_item": 1,
     "technician_name": "Marcus Vance",
     "role_classified": "L3 Vibration Specialist",
     "technician_certifications": ["OSHA_10"],
     "badge_in_time": "2026-09-08T07:00:00Z",
     "badge_out_time": "2026-09-11T16:00:00Z",
     "regular_hours": 32.0,
     "overtime_hours": 8.0,
     "verified_hours": 40.0,
     "overtime_preapproved": false,
     "work_order_id": "WO-PLANT-0941"
   },
   {
     "ses_number": "SES-2026-00413",
     "sow_number": "SOW-TURBINE-OVERHAUL",
     "line_item": 2,
     "technician_name": "Dave Briggs",
     "role_classified": "Master Millwright",
     "technician_certifications": ["NCCER_ADVANCED"],
     "badge_in_time": "2026-09-08T07:00:00Z",
     "badge_out_time": "2026-09-12T16:30:00Z",
     "regular_hours": 40.0,
     "overtime_hours": 0.0,
     "verified_hours": 40.0,
     "overtime_preapproved": false,
     "work_order_id": "WO-PLANT-0941"
   }
 ],
 "invoice": {
   "invoice_number": "INV-TURB-7740",
   "vendor_id": "VEND-PLANT-MAINT-CORP",
   "invoice_date": "2026-09-14",
   "track": "SERVICE",
   "line_items": [
     {
       "line_number": 1,
       "item_type": "SERVICE",
       "sku_or_role": "L3 Vibration Specialist",
       "description": "Onsite dynamic balancing and diagnostic logging",
       "billed_quantity": 50.0,
       "billed_unit_price": 195.0,
       "total_line_amount": 9750.0,
       "po_or_sow_reference": "SOW-TURBINE-OVERHAUL"
     },
     {
       "line_number": 2,
       "item_type": "SERVICE",
       "sku_or_role": "Master Millwright",
       "description": "Turbine casing alignment and torque verification",
       "billed_quantity": 40.0,
       "billed_unit_price": 155.0,
       "total_line_amount": 6200.0,
       "po_or_sow_reference": "SOW-TURBINE-OVERHAUL"
     }
   ],
   "additional_charges": [
     {
       "charge_type": "Per Diem - Meals & Lodging",
       "amount": 380.0,
       "clause_justification": "4 days travel per diem at $95.00/day"
     }
   ],
   "total_invoiced_amount": 16330.0
 }
}
'''


def write_repo_files(base_dir: str | os.PathLike[str] | None = None) -> str:
    """Write each generated file into the target repository directory."""
    root = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
    root.mkdir(parents=True, exist_ok=True)

    for relative_path, content in FILES.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    return str(root)


def create_repo_archive(base_dir: str | os.PathLike[str], archive_path: str | os.PathLike[str] | None = None) -> str:
    """Create a zip archive of the generated repo in the parent folder."""
    root = Path(base_dir)
    archive = Path(archive_path) if archive_path is not None else root.parent / f"{root.name}.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(root.rglob("*")):
            if file_path.is_dir():
                continue
            zf.write(file_path, arcname=file_path.relative_to(root.parent))

    return str(archive)


if __name__ == "__main__":
    repo_root = write_repo_files()
    archive_path = create_repo_archive(repo_root)
    print(f"Generated repository at: {repo_root}")
    print(f"Created archive: {archive_path}")
