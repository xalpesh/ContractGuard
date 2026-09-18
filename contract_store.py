import json
import os
import re
from typing import Dict, List, Tuple

from pydantic import BaseModel

from extraction import CONTRACT_MODELS

LIBRARY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contracts_library")


def _path(contract_id: str) -> str:
   return os.path.join(LIBRARY_DIR, re.sub(r"[^A-Za-z0-9_.-]", "_", contract_id) + ".json")


def save_contract(track: str, terms: BaseModel, source_filename: str) -> str:
   os.makedirs(LIBRARY_DIR, exist_ok=True)
   with open(_path(terms.contract_id), "w", encoding="utf-8") as f:
       json.dump({"track": track, "source_filename": source_filename,
                  "contract_terms": terms.model_dump(mode="json")}, f, indent=2)
   return terms.contract_id


def list_contracts() -> Dict[str, Dict]:
   """contract_id -> {track, source_filename, contract_terms(dict)}"""
   if not os.path.isdir(LIBRARY_DIR):
       return {}
   out = {}
   for name in sorted(os.listdir(LIBRARY_DIR)):
       if name.endswith(".json"):
           with open(os.path.join(LIBRARY_DIR, name), encoding="utf-8") as f:
               entry = json.load(f)
           out[entry["contract_terms"]["contract_id"]] = entry
   return out


def load_contract(contract_id: str) -> Tuple[str, BaseModel]:
   entry = list_contracts()[contract_id]
   return entry["track"], CONTRACT_MODELS[entry["track"]].model_validate(entry["contract_terms"])
