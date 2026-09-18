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
       f"**Vendor ID:** {invoice.vendor_id} | **Total Disputed Amount:** ${total_disputed:,.2f}\n",
       "The following discrepancies were identified against contract terms and dock receipt records:\n",
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
   return "\n".join(memo)


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
