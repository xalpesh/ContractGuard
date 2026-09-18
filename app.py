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
