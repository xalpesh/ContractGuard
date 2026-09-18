# ContractGuard: Specialist Agent Swarm

Two Claude agents on a LangGraph pipeline:

    invoice_router -> Compliance Agent -> Posting Agent
                          |                   |-- PASS: post to ERP
                          |                   `-- FAIL: return to vendor (clarification / corrected invoice)
                          `-- tools: get_case_summary, run_audit (deterministic Decimal audit engine), submit_verdict

- The audit math stays deterministic (`reasoner.py`, `service_reasoner.py`). Claude reasons and explains; it never does the arithmetic.
- Guardrail in code: the PASS/FAIL decision comes from the audit engine, and `post_invoice_to_erp` rejects any FAILED invoice.
- Without `ANTHROPIC_API_KEY` (or if the API call fails) both agents fall back to a deterministic path, so the demo still runs.

## Run
    pip install -r requirements.txt
    set ANTHROPIC_API_KEY=...        (optional: ANTHROPIC_MODEL, default claude-sonnet-5)
    streamlit run app.py
    pytest -q

## Demo script
1. **Material Track**: overbilled invoice -> Compliance FAIL -> returned to vendor with itemized notice.
2. **Service Track**: inflated rates/hours/per diem -> FAIL -> returned.
3. **Material - Vendor Corrected Resubmission**: the vendor's fixed invoice -> PASS -> posted to ERP.

## Bring your own contract and invoice
Sidebar modes:
- **Upload contract**: choose MATERIAL or SERVICE and upload a PDF, image, text or JSON. Claude extracts the terms (`extraction.py`); JSON needs no API key. Saved to `contracts_library/` (`contract_store.py`). Check the extracted terms before use.
- **Submit invoice**: pick a contract, upload the invoice (PDF/image/text/JSON), optionally upload evidence JSON, and the swarm runs. Evidence JSON is `{"goods_receipts": [...]}` or `{"service_entry_sheets": [...]}`, plus `"external_indices": {...}`; see the fixtures for the shapes. With no evidence the audit uses sample evidence and the UI says so.
