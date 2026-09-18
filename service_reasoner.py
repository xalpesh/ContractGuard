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
       match = re.search(r"(\d+)\s*days?", charge_justification, re.IGNORECASE)
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
       f"**Vendor ID:** {invoice.vendor_id} | **Total Disputed Amount:** ${total_disputed:,.2f}\n",
       "Discrepancies identified against contracted rate cards, skill matrices, and SES badge logs:\n",
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
   return "\n".join(memo)


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
