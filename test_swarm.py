import json
import os

import pytest


from models import (
   GoodsReceiptRecord,
   Invoice,
   MaterialContractTerms,
   ServiceContractTerms,
   ServiceEntrySheet,
)
from router import build_unified_compliance_graph
from agents.posting_agent import posting_agent_node


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
   # .env may supply a real key at import time; tests must exercise the deterministic path.
   import agents.base
   monkeypatch.setattr(agents.base, "_load_env", lambda: None)
   monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def build_state(path: str, material: bool) -> dict:
   with open(path) as f:
       d = json.load(f)
   return {
       "invoice_raw_path": "",
       "contract_raw_path": "",
       "po_or_sow_id": d["invoice"]["line_items"][0]["po_or_sow_reference"],
       "track": None,
       "extracted_invoice": Invoice.model_validate(d["invoice"]),
       "contract_terms": (MaterialContractTerms if material else ServiceContractTerms).model_validate(d["contract_terms"]),
       "goods_receipts": [GoodsReceiptRecord.model_validate(x) for x in d["goods_receipts"]] if material else None,
       "service_entry_sheets": None if material else [ServiceEntrySheet.model_validate(x) for x in d["service_entry_sheets"]],
       "external_indices": d.get("external_indices", {}),
       "processing_errors": [],
       "messages": [],
   }


def run(path: str, material: bool, thread: str) -> dict:
   graph = build_unified_compliance_graph()
   return graph.invoke(build_state(path, material), {"configurable": {"thread_id": thread}})


def test_flawed_material_invoice_returned():
   out = run("material_fixture.json", True, "t1")
   assert out["compliance_verdict"]["decision"] == "FAIL"
   assert out["posting_result"] == "RETURNED_TO_VENDOR"
   assert out["generated_erp_payload"]["status"] == "RETURNED_TO_VENDOR"
   assert out["generated_vendor_email"]


def test_flawed_service_invoice_returned():
   out = run("service_fixture.json", False, "t2")
   assert out["compliance_verdict"]["decision"] == "FAIL"
   assert out["posting_result"] == "RETURNED_TO_VENDOR"


def test_clean_material_invoice_posted():
   out = run("material_clean_fixture.json", True, "t3")
   assert out["compliance_verdict"]["decision"] == "PASS"
   assert out["posting_result"] == "POSTED"
   assert out["generated_erp_payload"]["status"] == "CLEARED_FOR_PAYMENT"


def test_posting_guardrail_blocks_failed_invoice():
   out = run("material_fixture.json", True, "t4")
   from agents import posting_agent
   state = dict(out)
   state["compliance_verdict"] = {"decision": "FAIL", "rationale": "x"}
   # Deterministic path can only return to vendor; it must never post.
   assert posting_agent_node(state)["posting_result"] == "RETURNED_TO_VENDOR"


def test_contract_upload_then_invoice_submission(tmp_path, monkeypatch):
   import contract_store
   from extraction import extract_contract, extract_invoice, parse_evidence

   monkeypatch.setattr(contract_store, "LIBRARY_DIR", str(tmp_path))
   fixture = open("material_clean_fixture.json", "rb").read()

   terms = extract_contract(fixture, "contract.json", "MATERIAL")
   contract_store.save_contract("MATERIAL", terms, "contract.json")
   track, loaded = contract_store.load_contract(terms.contract_id)
   assert track == "MATERIAL" and loaded.contract_id == terms.contract_id

   invoice = extract_invoice(fixture, "invoice.json", track)
   evidence = parse_evidence(fixture, track)
   state = {
       "invoice_raw_path": "invoice.json", "contract_raw_path": terms.contract_id,
       "po_or_sow_id": invoice.line_items[0].po_or_sow_reference, "track": None,
       "extracted_invoice": invoice, "contract_terms": loaded,
       "goods_receipts": evidence["goods_receipts"], "service_entry_sheets": None,
       "external_indices": evidence["external_indices"], "processing_errors": [], "messages": [],
   }
   out = build_unified_compliance_graph().invoke(state, {"configurable": {"thread_id": "t5"}})
   assert out["posting_result"] == "POSTED"


def test_non_json_upload_without_key_gives_clear_error():
   from extraction import extract_contract
   with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
       extract_contract(b"%PDF-1.4", "c.pdf", "MATERIAL")
