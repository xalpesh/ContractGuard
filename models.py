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
   RETURNED_TO_VENDOR = "RETURNED_TO_VENDOR"


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
