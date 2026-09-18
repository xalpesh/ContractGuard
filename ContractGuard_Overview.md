# ContractGuard: Specialist Agent Swarm
### Page 1 of 3: What it is and how it works

**The problem.** Accounts-payable teams in manufacturing pay invoices that quietly disagree with the contract: an index-adjusted price billed at the wrong rate, goods billed that were rejected at the dock, overtime nobody approved, a per diem above the cap. Catching these means reading a contract, an invoice and the operational proof (receipts, gate logs) side by side. It is slow, and errors get paid.

**The idea.** Two specialist Claude agents, each with one job and its own tools, handing off to each other:

```
 Contract + Invoice (+ evidence)
            |
      [ Router ]  material or service track
            |
 [ 1. Compliance Agent ]  Does this invoice comply with the contract?
            |  verdict: PASS / FAIL + rationale
            |
 [ 2. Posting Agent ]
      |-- PASS -> post to ERP (cleared for payment)
      `-- FAIL -> return to vendor: itemized notice asking for
                  clarification or a corrected invoice
```

**How a run goes**
1. **Load a contract.** Upload a contract (PDF, image, text or JSON). It is extracted into structured terms and saved to the contract library. Or use the built-in demo scenarios.
2. **Submit an invoice** against a saved contract, with optional evidence: goods receipts or service entry sheets, plus market index values.
3. **Compliance Agent** reviews the case, runs the audit engine and writes a plain-English rationale that cites the contract clause and evidence behind each finding.
4. **Posting Agent** acts on the verdict. Clean invoices are posted to the ERP. Failed invoices are never posted. Instead the vendor gets a specific, polite notice listing what was billed, what the contract allows and which clause applies, asking them to explain or send a corrected invoice.
5. **The vendor resubmits.** A corrected invoice goes through the same path and posts if it passes. The demo includes this loop.

**What the audit checks (13 discrepancy types)**

| Track | Checks |
|---|---|
| Material | Line arithmetic, index-adjusted unit price, quantity against goods receipt and tolerance, damaged or rejected goods billed, prohibited freight and packaging surcharges, incoterm violations |
| Service | Technician skill certification, rate-card rates, unauthorized overtime, hours against gate-log badge times, SOW hour and budget caps, per diem cap, unapproved expenses |

**Two agents instead of one.** Checking and acting are different responsibilities. Keeping them apart gives each a small prompt, a small toolset and a clear audit trail, and it lets the action step be locked down independently of the reasoning step.

<div style="page-break-after: always;"></div>

# Page 2 of 3: Behind the scenes

The agent does not train or fine-tune anything. Everything it "learns" about a contract is captured as structured data it can reuse. The four stages are below.

## 1. Extract
- Claude reads the uploaded contract or invoice (PDF, image or text) and returns structured data by calling a `record` tool whose input schema is generated from our Pydantic models. This forces a machine-readable answer instead of free text.
- Extraction instructions say: use only what the document states, copy invoice amounts exactly as printed, never recompute or correct them.
- JSON uploads skip the model entirely and load directly, so the system also works offline.

## 2. Learn (contract memory)
- A contract is parsed once into typed terms: rate cards, price index baseline and pass-through coefficient, tolerances, freight and packaging rules, per diem and SOW caps.
- Terms are saved to a contract library on disk and reused for every later invoice against that contract. The agent does not re-read the PDF each time.
- The extracted terms are shown in the UI so a person can check them before any invoice is judged against them.

## 3. Infer (agentic reasoning)
- The **Compliance Agent** works through tool calls: `get_case_summary` to see what it is auditing, `run_audit` to run the audit engine, `submit_verdict` to record PASS or FAIL with its rationale.
- The **Posting Agent** receives the verdict and findings and chooses between `post_invoice_to_erp` and `return_to_vendor`. It writes the vendor notice itself, choosing between clarification, a corrected invoice, or both.
- Claude does the judgment and language work. It never does the arithmetic.

## 4. Validate (guardrails in code, not just prompts)
- **Deterministic audit engine.** Money is computed with `Decimal` to the cent. For example, the allowed price is `base + (current_index - baseline) x coefficient`. Every finding carries the billed amount, the allowed amount, the overcharge, the contract clause and the evidence reference.
- **The decision cannot be talked around.** PASS or FAIL is derived from the audit engine's result, not from what the model says.
- **The posting tool refuses failed invoices.** `post_invoice_to_erp` returns a block error on any FAIL verdict, and `return_to_vendor` refuses a PASS. A confused or manipulated model cannot pay a bad invoice.
- **Schema validation.** Every extracted contract, invoice and evidence file is validated against Pydantic models before use, so malformed extractions fail loudly instead of producing a wrong audit.
- **Graceful fallback.** With no API key or if the API call fails, both agents fall back to a non-LLM path so the pipeline still produces a result.
- **Tests.** Automated tests cover a flawed material invoice, a flawed service invoice, a clean invoice, the vendor-corrected resubmission, the posting guardrail and the contract upload flow.

<div style="page-break-after: always;"></div>

# Page 3 of 3: Why it is worth backing

**Built for trust, not a demo trick**
- **Explainable.** Every dispute names the clause, the evidence and the dollar amount. The UI shows each agent's tool calls as they happen, so a reviewer can see how a decision was reached.
- **Safe by construction.** The dangerous action, paying money, is gated in code. The model's job is to reason and communicate.
- **Accurate where it counts.** Cent-level `Decimal` math and rule-based checks, with the model kept away from calculation.
- **Closes the loop.** It does not stop at "flagged". It writes the vendor notice and processes the corrected invoice, which is the actual AP workflow.

**Practical to adopt**
- **Bring your own contract.** Upload a contract and start submitting invoices against it, with no per-contract coding.
- **Works with messy inputs.** PDFs, scans and text, with JSON as an offline path.
- **Runs anywhere.** Standard Python, LangGraph and Streamlit. The only external dependency is the Anthropic API, and the system still runs without it.
- **Model-flexible.** The model is a single setting (`ANTHROPIC_MODEL`, default `claude-sonnet-5`).

**Clean architecture for the swarm pattern**
- Specialist agents with narrow prompts and narrow toolsets.
- A LangGraph pipeline with typed shared state and a live agent trace.
- A new specialist, for example a duplicate-invoice detector or a tax checker, can be added as another node with its own tools.

**Demo story (about 3 minutes)**
1. An overbilled material invoice: the Compliance Agent flags a wrong index-adjusted price, rejected goods billed and prohibited surcharges. The Posting Agent returns it with an itemized notice.
2. An inflated service invoice: rates, overtime, hours and per diem are flagged and it is returned.
3. The vendor's corrected invoice goes through and is posted to the ERP.
4. Upload a brand-new contract live and submit an invoice against it.

**Honest limits and next steps**
- Uploaded contracts should be reviewed by a person once after extraction. The UI shows the terms for that purpose.
- Evidence (receipts, service entry sheets, indices) is supplied as JSON today. The next step is connecting to ERP and receiving systems directly.
- Posting to the ERP is simulated with a payload. A production version would call the real AP integration.
- Natural next specialists: duplicate-invoice detection, tax and currency validation, vendor-risk scoring.
