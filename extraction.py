import base64
import json
import os
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from agents.base import DEFAULT_MODEL, llm_available
from models import (
   GoodsReceiptRecord,
   Invoice,
   InvoiceTrack,
   MaterialContractTerms,
   ServiceContractTerms,
   ServiceEntrySheet,
)

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

CONTRACT_MODELS: Dict[str, Type[BaseModel]] = {
   InvoiceTrack.MATERIAL.value: MaterialContractTerms,
   InvoiceTrack.SERVICE.value: ServiceContractTerms,
}


def _unwrap_json(raw: bytes, key: str) -> Dict[str, Any]:
   """Accept either the bare object or a full fixture that nests it under `key`."""
   data = json.loads(raw.decode("utf-8"))
   return data.get(key, data) if isinstance(data, dict) else data


def _extract_with_claude(raw: bytes, filename: str, model_cls: Type[BaseModel], instructions: str) -> BaseModel:
   if not llm_available():
       raise RuntimeError("Reading PDF/text/image documents needs ANTHROPIC_API_KEY. Upload JSON instead, or set the key.")

   import anthropic

   ext = os.path.splitext(filename)[1].lower()
   if ext == ".pdf":
       doc = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                             "data": base64.b64encode(raw).decode()}}
   elif ext in IMAGE_TYPES:
       doc = {"type": "image", "source": {"type": "base64", "media_type": IMAGE_TYPES[ext],
                                          "data": base64.b64encode(raw).decode()}}
   else:
       doc = {"type": "text", "text": raw.decode("utf-8", errors="replace")}

   client = anthropic.Anthropic()
   response = client.messages.create(
       model=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
       max_tokens=4096,
       system=instructions,
       tools=[{"name": "record", "description": "Record the extracted structured data.",
               "input_schema": model_cls.model_json_schema()}],
       tool_choice={"type": "tool", "name": "record"},
       messages=[{"role": "user", "content": [doc, {"type": "text", "text": "Extract the data from this document."}]}],
   )
   for block in response.content:
       if block.type == "tool_use":
           return model_cls.model_validate(block.input)
   raise RuntimeError("Claude did not return structured data.")


def extract_contract(raw: bytes, filename: str, track: str) -> BaseModel:
   model_cls = CONTRACT_MODELS[track]
   if filename.lower().endswith(".json"):
       return model_cls.model_validate(_unwrap_json(raw, "contract_terms"))
   return _extract_with_claude(
       raw, filename, model_cls,
       f"You extract commercial terms from a {track.lower()} supply/services contract into the given schema. "
       "Use only what the document states; use schema defaults for anything absent. "
       "Dates are ISO (YYYY-MM-DD). Keys of rate_cards / base_material_unit_price are the SKU or role codes "
       "exactly as invoices will reference them.",
   )


def extract_invoice(raw: bytes, filename: str, track: str) -> Invoice:
   if filename.lower().endswith(".json"):
       invoice = Invoice.model_validate(_unwrap_json(raw, "invoice"))
   else:
       invoice = _extract_with_claude(
           raw, filename, Invoice,
           "You extract a vendor invoice into the given schema. Copy amounts exactly as printed; never "
           "recompute or correct them. Each line item's po_or_sow_reference is the PO / SOW number it bills against. "
           f"Set track to {track} and each line's item_type to {track}.",
       )
   invoice.track = InvoiceTrack(track)
   return invoice


def parse_evidence(raw: Optional[bytes], track: str) -> Dict[str, Any]:
   """Evidence JSON: {goods_receipts|service_entry_sheets: [...], external_indices: {...}} (or a full fixture)."""
   if not raw:
       return {}
   data = json.loads(raw.decode("utf-8"))
   out: Dict[str, Any] = {"external_indices": data.get("external_indices", {})}
   if track == InvoiceTrack.MATERIAL.value:
       out["goods_receipts"] = [GoodsReceiptRecord.model_validate(x) for x in data.get("goods_receipts", [])]
   else:
       out["service_entry_sheets"] = [ServiceEntrySheet.model_validate(x) for x in data.get("service_entry_sheets", [])]
   return out
