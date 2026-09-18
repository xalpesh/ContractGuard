import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

styles = getSampleStyleSheet()

# Custom typography
title_style = ParagraphStyle(
   "DocTitle",
   parent=styles["Heading1"],
   fontSize=18,
   leading=22,
   textColor=colors.HexColor("#1e293b"),
   spaceAfter=6,
)
meta_style = ParagraphStyle(
   "DocMeta",
   parent=styles["Normal"],
   fontSize=9,
   leading=13,
   textColor=colors.HexColor("#475569"),
)
h2_style = ParagraphStyle(
   "DocH2",
   parent=styles["Heading2"],
   fontSize=12,
   leading=16,
   textColor=colors.HexColor("#0f172a"),
   spaceBefore=10,
   spaceAfter=4,
)
body_style = ParagraphStyle(
   "DocBody",
   parent=styles["Normal"],
   fontSize=9,
   leading=13,
   textColor=colors.HexColor("#334155"),
)
clause_style = ParagraphStyle(
   "DocClause",
   parent=styles["Normal"],
   fontSize=8.5,
   leading=12,
   textColor=colors.HexColor("#1e293b"),
)
badge_red = ParagraphStyle(
   "BadgeRed",
   parent=styles["Normal"],
   fontSize=8,
   leading=10,
   textColor=colors.HexColor("#b91c1c"),
)
badge_green = ParagraphStyle(
   "BadgeGreen",
   parent=styles["Normal"],
   fontSize=8,
   leading=10,
   textColor=colors.HexColor("#15803d"),
)


def create_header(canvas, doc):
   canvas.saveState()
   canvas.setFont("Helvetica-Bold", 8)
   canvas.setFillColor(colors.HexColor("#94a3b8"))
   canvas.drawString(54, 750, "INVOICEGUARD TEST FIXTURE ARTIFACT")
   canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
   canvas.setLineWidth(0.5)
   canvas.line(54, 742, 558, 742)
   canvas.restoreState()


# ==============================================================================
# 1. MATERIAL CONTRACT (CTR-MAT-2026-081)
# ==============================================================================
def build_material_contract(filename="material_contract.pdf"):
   doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
   story = []

   story.append(Paragraph("MASTER PURCHASE AGREEMENT", title_style))
   story.append(Paragraph("<b>Contract ID:</b> CTR-MAT-2026-081  |  <b>Vendor:</b> Solvents Industrial Corp (VEND-SOLVENTS-INC)  |  <b>Effective:</b> Jan 15, 2026", meta_style))
   story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=10))

   story.append(Paragraph("1. Commercial Scope & Delivery Terms", h2_style))
   story.append(Paragraph("<b>Clause 2.1 (Incoterms):</b> All deliveries are contracted under <b>Incoterms 2020: DDP (Delivered Duty Paid)</b>, Apex Baytown Terminal. Freight, shipping insurance, and fuel volatility are strictly the Seller's obligation. Separate freight or fuel surcharges are contractually barred.", clause_style))
   story.append(Spacer(1, 4))
   story.append(Paragraph("<b>Clause 4.1 (Quantity & Receiving Acceptance):</b> Invoices must strictly bill accepted dock volume per certified scale weight receipts. A quantity delivery variance tolerance of <b>±5.0%</b> is allowed against purchase order line targets. Damaged or rejected drums logged at the delivery dock are not payable.", clause_style))
   story.append(Spacer(1, 4))
   story.append(Paragraph("<b>Clause 5.2 (Dynamic Index Pricing Formula):</b> Base prices are indexed to the monthly ICIS Petrochemical Solvent Index (ICIS_RESIN baseline = 800.0). Formula: <code>Unit Price = Base Rate + 0.5 * (Current Index - 800.0)</code>.", clause_style))
   story.append(Spacer(1, 4))
   story.append(Paragraph("<b>Clause 6.3 (Packaging & Pallets):</b> Standard palletizing, banding, and shrink-wrap are incorporated into the product unit price. Separate staging or packaging fees are prohibited.", clause_style))

   story.append(Paragraph("2. Base Product Rate Schedule", h2_style))
   table_data = [
       ["Product SKU", "Commodity Class", "Base Unit Rate", "Index Key", "Pass-Through"],
       ["SOLVENT-X", "Industrial Grade Solvent", "$1,200.00 / MT", "ICIS_RESIN", "50% (0.50)"],
       ["POLY-RESIN-A", "Bulk Polymer Pellets", "$450.00 / MT", "ICIS_RESIN", "50% (0.50)"],
   ]
   t = Table(table_data, colWidths=[110, 150, 90, 80, 74])
   t.setStyle(TableStyle([
       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
       ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
       ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
       ("FONTSIZE", (0, 0), (-1, -1), 8.5),
       ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
       ("ALIGN", (2, 0), (-1, -1), "CENTER"),
   ]))
   story.append(t)

   doc.build(story)


# ==============================================================================
# 2. MATERIAL INVOICES (COMPLIANT & NON-COMPLIANT)
# ==============================================================================
def build_material_invoice_compliant(filename="invoice_mat_compliant.pdf"):
   doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
   story = []

   story.append(Paragraph("INVOICE #INV-MAT-1001", title_style))
   story.append(Paragraph("<b>Vendor:</b> Solvents Industrial Corp  |  <b>PO Ref:</b> PO-88231  |  <b>Contract:</b> CTR-MAT-2026-081  |  <b>Date:</b> Sep 15, 2026", meta_style))
   story.append(Paragraph("COMPLIANT TEST FIXTURE (FORMULA MATCHED & SCALE ALIGNED)", badge_green))
   story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=10))

   story.append(Paragraph("Bill To: Apex Manufacturing - Baytown Works  |  Payment Terms: Net 30", meta_style))
   story.append(Spacer(1, 8))

   table_data = [
       ["Line", "SKU / Description", "Billed Qty", "UOM", "Unit Price", "Total Amount"],
       ["1", "SOLVENT-X (Bulk Delivery)\nIndexed: $1200 + 0.5*(840-800)", "95.00", "MT", "$1,220.00", "$115,900.00"],
   ]
   t = Table(table_data, colWidths=[30, 244, 60, 40, 65, 65])
   t.setStyle(TableStyle([
       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
       ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
       ("FONTSIZE", (0, 0), (-1, -1), 8.5),
       ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
       ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
   ]))
   story.append(t)
   story.append(Spacer(1, 10))

   summary = [
       ["", "Subtotal:", "$115,900.00"],
       ["", "Freight / Surcharges (DDP Included):", "$0.00"],
       ["", "Total Invoiced Amount:", "$115,900.00"],
   ]
   st = Table(summary, colWidths=[314, 125, 65])
   st.setStyle(TableStyle([
       ("FONTNAME", (1, 2), (-1, 2), "Helvetica-Bold"),
       ("FONTSIZE", (0, 0), (-1, -1), 8.5),
       ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
       ("LINEABOVE", (1, 2), (-1, 2), 1, colors.HexColor("#0f172a")),
   ]))
   story.append(st)
   doc.build(story)


def build_material_invoice_noncompliant(filename="invoice_mat_noncompliant.pdf"):
   doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
   story = []

   story.append(Paragraph("INVOICE #INV-2026-9981", title_style))
   story.append(Paragraph("<b>Vendor:</b> Solvents Industrial Corp  |  <b>PO Ref:</b> PO-88231  |  <b>Contract:</b> CTR-MAT-2026-081  |  <b>Date:</b> Sep 15, 2026", meta_style))
   story.append(Paragraph("NON-COMPLIANT TEST FIXTURE (PRICE INDEX, DAMAGED GOODS, FREIGHT LEAKS)", badge_red))
   story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=10))

   story.append(Paragraph("Bill To: Apex Manufacturing - Baytown Works  |  Payment Terms: Net 30", meta_style))
   story.append(Spacer(1, 8))

   table_data = [
       ["Line", "SKU / Description", "Billed Qty", "UOM", "Unit Price", "Total Amount"],
       ["1", "SOLVENT-X Bulk Chemical\n(Billed at unadjusted baseline)", "100.00", "MT", "$1,250.00", "$125,000.00"],
       ["-", "Emergency Fuel Surcharge\n(Diesel carrier volatility)", "1.00", "LOT", "$1,200.00", "$1,200.00"],
       ["-", "Pallet & Restaging Surcharge\n(Drum return processing)", "1.00", "LOT", "$350.00", "$350.00"],
   ]
   t = Table(table_data, colWidths=[30, 244, 60, 40, 65, 65])
   t.setStyle(TableStyle([
       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fef2f2")),
       ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
       ("FONTSIZE", (0, 0), (-1, -1), 8.5),
       ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
       ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
   ]))
   story.append(t)
   story.append(Spacer(1, 10))

   summary = [
       ["", "Subtotal:", "$125,000.00"],
       ["", "Ancillary Surcharges:", "$1,550.00"],
       ["", "Total Invoiced Amount:", "$126,550.00"],
   ]
   st = Table(summary, colWidths=[314, 125, 65])
   st.setStyle(TableStyle([
       ("FONTNAME", (1, 2), (-1, 2), "Helvetica-Bold"),
       ("FONTSIZE", (0, 0), (-1, -1), 8.5),
       ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
       ("LINEABOVE", (1, 2), (-1, 2), 1, colors.HexColor("#0f172a")),
   ]))
   story.append(st)
   doc.build(story)


# ==============================================================================
# 3. SERVICE CONTRACT (MSA-SRV-2026-004)
# ==============================================================================
def build_service_contract(filename="service_contract.pdf"):
   doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
   story = []

   story.append(Paragraph("MASTER SERVICES AGREEMENT (MRO & TURNAROUND)", title_style))
   story.append(Paragraph("<b>Contract ID:</b> MSA-SRV-2026-004  |  <b>Vendor:</b> Plant Maintenance Corp  |  <b>Effective:</b> Feb 01, 2026", meta_style))
   story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=10))

   story.append(Paragraph("1. Labor Classifications & Compliance Standards", h2_style))
   story.append(Paragraph("<b>Clause 2.4 (SOW Cap):</b> SOW-TURBINE-OVERHAUL carries a Not-To-Exceed (NTE) budget cap of <b>$15,000.00</b>.", clause_style))
   story.append(Spacer(1, 4))
   story.append(Paragraph("<b>Clause 3.2 (Mandatory Skills & Certifications):</b> Specialized roles require verified certifications on file before badge access. 'L3 Vibration Specialist' requires certified <b>ISO_18436_CAT_III</b> credential. If uncertified, labor is downgraded to 'General Mechanic' at $85.00/hr.", clause_style))
   story.append(Spacer(1, 4))
   story.append(Paragraph("<b>Clause 4.1 (Physical Access & Verified Hours):</b> Billed hours are reconciled strictly against plant turnstile badge logs (SES). Portal-to-portal travel is non-billable.", clause_style))
   story.append(Spacer(1, 4))
   story.append(Paragraph("<b>Clause 5.3 (Overtime Authorization):</b> Overtime multipliers (1.5x) require prior written approval. Unauthorized overtime reverts to standard rates.", clause_style))
   story.append(Spacer(1, 4))
   story.append(Paragraph("<b>Clause 9.3 (Per Diem Caps):</b> Lodging and meals are reimbursed at actual receipt value capped at <b>$65.00/day</b>.", clause_style))

   story.append(Paragraph("2. Approved Labor Rate Schedule", h2_style))
   table_data = [
       ["Labor Classification", "Mandatory Certification", "Standard Rate", "OT Mult.", "Max SOW Hrs", "Fallback Role"],
       ["L3 Vibration Specialist", "ISO_18436_CAT_III", "$175.00 / hr", "2.0x", "40.0 hrs", "General Mechanic"],
       ["Master Millwright", "NCCER_ADVANCED", "$140.00 / hr", "1.5x", "80.0 hrs", "General Mechanic"],
       ["General Mechanic", "None", "$85.00 / hr", "1.5x", "120.0 hrs", "None"],
   ]
   t = Table(table_data, colWidths=[120, 110, 75, 50, 65, 84])
   t.setStyle(TableStyle([
       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
       ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
       ("FONTSIZE", (0, 0), (-1, -1), 8),
       ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
       ("ALIGN", (2, 0), (-1, -1), "CENTER"),
   ]))
   story.append(t)
   doc.build(story)


# ==============================================================================
# 4. SERVICE INVOICES (COMPLIANT & NON-COMPLIANT)
# ==============================================================================
def build_service_invoice_compliant(filename="invoice_srv_compliant.pdf"):
   doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
   story = []

   story.append(Paragraph("INVOICE #INV-SRV-2001", title_style))
   story.append(Paragraph("<b>Vendor:</b> Plant Maintenance Corp  |  <b>SOW Ref:</b> SOW-TURBINE-OVERHAUL  |  <b>Contract:</b> MSA-SRV-2026-004  |  <b>Date:</b> Sep 14, 2026", meta_style))
   story.append(Paragraph("COMPLIANT TEST FIXTURE (CERTIFIED TECHNICIAN & BADGE-VERIFIED)", badge_green))
   story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=10))

   story.append(Paragraph("Bill To: Apex Manufacturing - Baytown Works  |  Payment Terms: Net 30", meta_style))
   story.append(Spacer(1, 8))

   table_data = [
       ["Line", "Skill Role / Description", "Billed Hrs", "Rate", "Total Amount"],
       ["1", "Master Millwright - Dave Briggs\n(NCCER Verified, SES #SES-2026-00413)", "40.00", "$140.00", "$5,600.00"],
       ["-", "Per Diem Expense - Dave Briggs\n(4 Days @ $65.00 contract cap)", "4.00", "$65.00", "$260.00"],
   ]
   t = Table(table_data, colWidths=[30, 274, 65, 65, 70])
   t.setStyle(TableStyle([
       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
       ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
       ("FONTSIZE", (0, 0), (-1, -1), 8.5),
       ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
       ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
   ]))
   story.append(t)
   story.append(Spacer(1, 10))

   summary = [
       ["", "Labor Subtotal:", "$5,600.00"],
       ["", "Approved Per Diem:", "$260.00"],
       ["", "Total Invoiced Amount:", "$5,860.00"],
   ]
   st = Table(summary, colWidths=[304, 130, 70])
   st.setStyle(TableStyle([
       ("FONTNAME", (1, 2), (-1, 2), "Helvetica-Bold"),
       ("FONTSIZE", (0, 0), (-1, -1), 8.5),
       ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
       ("LINEABOVE", (1, 2), (-1, 2), 1, colors.HexColor("#0f172a")),
   ]))
   story.append(st)
   doc.build(story)


def build_service_invoice_noncompliant(filename="invoice_srv_noncompliant.pdf"):
   doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
   story = []

   story.append(Paragraph("INVOICE #INV-TURB-7740", title_style))
   story.append(Paragraph("<b>Vendor:</b> Plant Maintenance Corp  |  <b>SOW Ref:</b> SOW-TURBINE-OVERHAUL  |  <b>Contract:</b> MSA-SRV-2026-004  |  <b>Date:</b> Sep 14, 2026", meta_style))
   story.append(Paragraph("NON-COMPLIANT TEST FIXTURE (SKILL UNVERIFIED, INFLATED RATES, SOW BUDGET OVERRUN)", badge_red))
   story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=10))

   story.append(Paragraph("Bill To: Apex Manufacturing - Baytown Works  |  Payment Terms: Net 30", meta_style))
   story.append(Spacer(1, 8))

   table_data = [
       ["Line", "Skill Role / Description", "Billed Hrs", "Rate", "Total Amount"],
       ["1", "L3 Vibration Specialist - Marcus Vance\n(Billed 50 hrs vs 40 hrs SES; lacks ISO cert)", "50.00", "$195.00", "$9,750.00"],
       ["2", "Master Millwright - Dave Briggs\n(Billed $155/hr vs $140/hr contract rate)", "40.00", "$155.00", "$6,200.00"],
       ["-", "Per Diem Travel Expenses\n(4 days travel @ $95.00/day vs $65 cap)", "4.00", "$95.00", "$380.00"],
   ]
   t = Table(table_data, colWidths=[30, 274, 65, 65, 70])
   t.setStyle(TableStyle([
       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fef2f2")),
       ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
       ("FONTSIZE", (0, 0), (-1, -1), 8.5),
       ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
       ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
   ]))
   story.append(t)
   story.append(Spacer(1, 10))

   summary = [
       ["", "Labor Subtotal:", "$15,950.00"],
       ["", "Per Diem Subtotal:", "$380.00"],
       ["", "Total Invoiced Amount (Exceeds $15k SOW Cap):", "$16,330.00"],
   ]
   st = Table(summary, colWidths=[274, 160, 70])
   st.setStyle(TableStyle([
       ("FONTNAME", (1, 2), (-1, 2), "Helvetica-Bold"),
       ("FONTSIZE", (0, 0), (-1, -1), 8.5),
       ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
       ("LINEABOVE", (1, 2), (-1, 2), 1, colors.HexColor("#0f172a")),
   ]))
   story.append(st)
   doc.build(story)


if __name__ == "__main__":
   print("Generating contract and invoice PDF artifacts...")
   build_material_contract()
   build_material_invoice_compliant()
   build_material_invoice_noncompliant()
   build_service_contract()
   build_service_invoice_compliant()
   build_service_invoice_noncompliant()
   print("Complete. 6 PDF files generated successfully:")
   for f in [
       "material_contract.pdf",
       "invoice_mat_compliant.pdf",
       "invoice_mat_noncompliant.pdf",
       "service_contract.pdf",
       "invoice_srv_compliant.pdf",
       "invoice_srv_noncompliant.pdf",
   ]:
       print(f" - {f} ({os.path.getsize(f):,} bytes)")
