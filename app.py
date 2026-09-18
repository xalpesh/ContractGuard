import json
import streamlit as st
import pandas as pd

from models import (
   GoodsReceiptRecord,
   Invoice,
   MaterialContractTerms,
   ServiceContractTerms,
   ServiceEntrySheet,
)
from router import build_unified_compliance_graph
from contract_store import list_contracts, load_contract, save_contract
from extraction import extract_contract, extract_invoice, parse_evidence

st.set_page_config(
   page_title="ContractGuard | Manufacturing Compliance Swarm",
   page_icon="🛡️",
   layout="wide",
   initial_sidebar_state="expanded",
)

if "graph_app" not in st.session_state:
   st.session_state.graph_app = build_unified_compliance_graph()

if "thread_id" not in st.session_state:
   st.session_state.thread_id = "INV-SESSION-001"

if "pipeline_run" not in st.session_state:
   st.session_state.pipeline_run = False


FIXTURE_FILES = {
   "Material Track": "material_fixture.json",
   "Service Track": "service_fixture.json",
   "Material - Clean Invoice": "material_clean_fixture.json",
   "Material - Vendor Corrected Resubmission": "material_clean_fixture.json",
}


@st.cache_data
def load_fixture(fixture_type: str) -> dict:
   filename = FIXTURE_FILES[fixture_type]
   with open(filename, "r", encoding="utf-8") as f:
       return json.load(f)


def prepare_state_payload(fixture_data: dict, fixture_type: str) -> dict:
   is_material = fixture_type != "Service Track"
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


def _reset_results():
   st.session_state.pipeline_run = False


with st.sidebar:
   st.header("⚙️ Audit Control Plane")
   mode = st.radio("Mode", ["Demo scenarios", "Upload contract", "Submit invoice"],
                   key="mode", on_change=_reset_results)

   if mode == "Demo scenarios":
       fixture_choice = st.selectbox("Select Test Scenario", list(FIXTURE_FILES))
       st.text_input("Thread ID (LangGraph State Key)", key="thread_id")

       if st.button("🚀 Run Compliance Pipeline", type="primary", use_container_width=True):
           raw_fixture = load_fixture(fixture_choice)
           payload = prepare_state_payload(raw_fixture, fixture_choice)
           config = {"configurable": {"thread_id": st.session_state.thread_id}}

           with st.spinner("Compliance Agent auditing, then Posting Agent acting..."):
               for _ in st.session_state.graph_app.stream(payload, config=config):
                   pass
           st.session_state.pipeline_run = True
           st.rerun()

   if st.button("Reset Session", use_container_width=True):
       st.session_state.pipeline_run = False
       st.session_state.thread_id = f"INV-SESSION-{pd.Timestamp.now().strftime('%M%S')}"
       st.rerun()


st.title("🛡️ ContractGuard: Specialist Agent Swarm")
st.caption("Compliance Agent audits the invoice → Posting Agent posts it, or returns it to the vendor")


def sample_evidence(track: str) -> dict:
   fx = load_fixture("Service Track" if track == "SERVICE" else "Material Track")
   return parse_evidence(json.dumps(fx).encode("utf-8"), track)


if mode == "Upload contract":
   st.subheader("📑 Upload a New Contract")
   st.caption("PDF, image, text or JSON. Claude reads documents; JSON uses the fixture schema (needs no API key).")
   track_choice = st.radio("Contract type", ["MATERIAL", "SERVICE"], horizontal=True)
   contract_file = st.file_uploader("Contract file", type=["pdf", "png", "jpg", "jpeg", "webp", "txt", "md", "json"])
   if contract_file and st.button("Extract & save contract", type="primary"):
       try:
           with st.spinner("Extracting contract terms..."):
               terms = extract_contract(contract_file.getvalue(), contract_file.name, track_choice)
           save_contract(track_choice, terms, contract_file.name)
           st.success(f"Saved contract **{terms.contract_id}** (vendor {terms.vendor_id}).")
           with st.expander("Extracted terms - verify before use", expanded=True):
               st.json(terms.model_dump(mode="json"))
       except Exception as exc:
           st.error(f"Could not extract contract: {exc}")

   library = list_contracts()
   st.subheader(f"📚 Contract Library ({len(library)})")
   for cid, entry in library.items():
       st.markdown(f"- `{cid}` | {entry['track']} | vendor `{entry['contract_terms']['vendor_id']}` | from `{entry['source_filename']}`")
   st.stop()

if mode == "Submit invoice":
   st.subheader("🧾 Submit an Invoice Against a Contract")
   library = list_contracts()
   if not library:
       st.info("No contracts yet. Switch to **Upload contract** in the sidebar first.")
       st.stop()

   contract_id = st.selectbox("Contract", list(library))
   invoice_file = st.file_uploader("Invoice file", type=["pdf", "png", "jpg", "jpeg", "webp", "txt", "md", "json"], key="inv_file")
   evidence_file = st.file_uploader(
       "Evidence JSON (optional): goods_receipts or service_entry_sheets, plus external_indices",
       type=["json"], key="ev_file")

   if invoice_file and st.button("🚀 Submit invoice to swarm", type="primary"):
       try:
           track, terms = load_contract(contract_id)
           with st.spinner("Reading invoice..."):
               invoice_in = extract_invoice(invoice_file.getvalue(), invoice_file.name, track)
           notes = []
           if invoice_in.vendor_id != terms.vendor_id:
               notes.append(f"Invoice vendor {invoice_in.vendor_id} differs from contract vendor {terms.vendor_id}.")
           evidence = parse_evidence(evidence_file.getvalue() if evidence_file else None, track)
           if not evidence:
               evidence = sample_evidence(track)
               notes.append("No evidence uploaded: audited against SAMPLE evidence, so results are illustrative only.")
           payload = {
               "invoice_raw_path": invoice_file.name,
               "contract_raw_path": contract_id,
               "po_or_sow_id": invoice_in.line_items[0].po_or_sow_reference if invoice_in.line_items else "",
               "track": None,
               "extracted_invoice": invoice_in,
               "contract_terms": terms,
               "goods_receipts": evidence.get("goods_receipts"),
               "service_entry_sheets": evidence.get("service_entry_sheets"),
               "external_indices": evidence.get("external_indices", {}),
               "processing_errors": notes,
               "messages": [],
           }
           st.session_state.thread_id = f"INV-{invoice_in.invoice_number}-{pd.Timestamp.now().strftime('%H%M%S')}"
           config = {"configurable": {"thread_id": st.session_state.thread_id}}
           with st.spinner("Compliance Agent auditing, then Posting Agent acting..."):
               for _ in st.session_state.graph_app.stream(payload, config=config):
                   pass
           st.session_state.pipeline_run = True
           st.session_state.submit_notes = notes
       except Exception as exc:
           st.session_state.pipeline_run = False
           st.error(f"Submission failed: {exc}")

   for note in st.session_state.get("submit_notes", []) if st.session_state.pipeline_run else []:
       st.warning(note)
   st.divider()

config = {"configurable": {"thread_id": st.session_state.thread_id}}
current_state = st.session_state.graph_app.get_state(config)

if not current_state.values or not st.session_state.pipeline_run:
   st.info("Pick a mode in the sidebar. Demo scenarios: click **Run Compliance Pipeline**. Submit invoice: upload and submit above.")
   st.stop()

state_values = current_state.values
report = state_values.get("audit_report")
invoice = state_values.get("extracted_invoice")
verdict = state_values.get("compliance_verdict") or {}
posting_result = state_values.get("posting_result")
traces = state_values.get("agent_trace") or {}

col1, col2, col3, col4 = st.columns(4)
with col1:
   st.metric("Invoiced Amount", f"${report.total_invoiced:,.2f}" if report else "$0.00")
with col2:
   st.metric("Approved Payable", f"${report.total_approved:,.2f}" if report else "$0.00")
with col3:
   disputed = report.total_disputed if report else 0.0
   st.metric("Disputed Overcharge", f"${disputed:,.2f}", delta=f"-${disputed:,.2f}" if disputed > 0 else "0.00", delta_color="inverse")
with col4:
   if posting_result == "POSTED":
       st.metric("Outcome", "POSTED", delta="Cleared for payment", delta_color="normal")
   else:
       st.metric("Outcome", "RETURNED", delta="Sent back to vendor", delta_color="inverse")

st.divider()
st.markdown(
   f"**Track:** `{state_values.get('track')}` | "
   f"**Invoice #:** `{invoice.invoice_number}` | "
   f"**Vendor ID:** `{invoice.vendor_id}` | "
   f"**Reference:** `{state_values.get('po_or_sow_id')}`"
)


def render_trace(steps: list):
   for step in steps:
       if step["type"] == "thought":
           st.markdown(f"💭 {step['text']}")
       else:
           st.markdown(f"🔧 `{step['tool']}`")
           if isinstance(step.get("result"), dict):
               with st.expander("result", expanded=False):
                   st.json(step["result"])


agent1, agent2 = st.columns(2)
with agent1:
   with st.container(border=True):
       st.subheader("1️⃣ Compliance Agent")
       st.caption(f"mode: {verdict.get('agent_mode', 'n/a')}")
       render_trace(traces.get("compliance", []))
       if verdict.get("decision") == "PASS":
           st.success(f"PASS. {verdict.get('rationale', '')}")
       else:
           st.error(f"FAIL. {verdict.get('rationale', '')}")
with agent2:
   with st.container(border=True):
       st.subheader("2️⃣ Posting Agent")
       render_trace(traces.get("posting", []))
       if posting_result == "POSTED":
           st.success("Invoice posted to ERP.")
           st.json(state_values["generated_erp_payload"])
       else:
           st.warning("Invoice returned to vendor.")
           st.markdown("**Outbound vendor notice**")
           st.info(state_values.get("generated_vendor_email") or "")
           st.json(state_values["generated_erp_payload"])

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
