import csv
import io
from datetime import date
from flask import (Blueprint, render_template, request,
                   Response, stream_with_context)
from flask_login import current_user
from app import db
from app.models.supply_chain import (PurchaseOrder, SKU, Container,
                                      Vessel, Allocation)
from app.auth.routes import supply_chain_required

reports_bp = Blueprint("reports", __name__)

@reports_bp.route("/")
@supply_chain_required
def index():
    return render_template("reports/index.html")

# ── Helper: CSV response ──────────────────────────────────────────────────────
def _csv_response(filename, headers, rows):
    def generate():
        buf = io.StringIO()
        w   = csv.writer(buf)
        w.writerow(headers)
        yield buf.getvalue()
        buf.seek(0); buf.truncate()
        for row in rows:
            w.writerow(row)
            yield buf.getvalue()
            buf.seek(0); buf.truncate()
    return Response(
        stream_with_context(generate()),
        mimetype="text/csv",
        headers={"Content-Disposition":
                 f"attachment;filename={filename}"}
    )

# ── Report 1 — PO Allocation Status ──────────────────────────────────────────
@reports_bp.route("/po-allocation")
@supply_chain_required
def po_allocation():
    status_filter   = request.args.get("status","")
    supplier_filter = request.args.get("supplier","").strip()
    export          = request.args.get("export","")

    query = SKU.query.join(PurchaseOrder)
    if status_filter:
        query = query.filter(PurchaseOrder.po_status == status_filter)
    if supplier_filter:
        query = query.filter(
            PurchaseOrder.supplier_name.ilike(f"%{supplier_filter}%"))
    skus = query.order_by(
        PurchaseOrder.supplier_name,
        PurchaseOrder.po_number,
        SKU.jj_sku
    ).all()

    if export == "csv":
        headers = [
            "PO Number","PI Number","CI Number","Supplier",
            "Currency","PO Status",
            "JJ SKU","Supplier SKU","Product Name","HS Code",
            "Shipment Type","Buying Price","Buying QTY",
            "No of Ctns","Total Units","Amount",
            "CI Price","CI QTY","CI Amount",
            "Price Variance","QTY Variance","CI Acknowledged",
            "Alloc QTY","Pending QTY","Total CBM",
            "Cargo Ready Date","SKU Status",
            "Container(s)"
        ]
        rows = []
        for sku in skus:
            po = sku.purchase_order
            active_allocs = [a for a in sku.allocations if a.is_active]
            containers = ", ".join(
                set(a.container_id for a in active_allocs)
            ) or ""
            rows.append([
                po.po_number, po.pi_number or "", po.ci_number or "",
                po.supplier_name, po.currency or "", po.po_status,
                sku.jj_sku or "", sku.supplier_sku or "",
                sku.product_name, sku.hs_code or "",
                sku.shipment_type or "",
                sku.buying_price or "", sku.buying_qty or 0,
                sku.no_of_ctns or "", sku.total_units or "",
                sku.amount or "",
                sku.ci_price or "", sku.ci_qty or "",
                sku.ci_total_amount or "",
                sku.price_variance or "", sku.qty_variance or "",
                "Yes" if sku.ci_variance_acknowledged else "No",
                sku.allocated_qty or 0, sku.pending_qty,
                sku.total_cbm or "",
                sku.cargo_ready_date or "", sku.sku_status,
                containers
            ])
        return _csv_response(
            f"po_allocation_status_{date.today()}.csv",
            headers, rows)

    # Group by PO for display
    po_map = {}
    for sku in skus:
        pn = sku.po_number
        if pn not in po_map:
            po_map[pn] = {"po": sku.purchase_order, "skus": []}
        po_map[pn]["skus"].append(sku)

    suppliers = [s[0] for s in
                 db.session.query(PurchaseOrder.supplier_name)
                 .distinct().all()]
    return render_template("reports/po_allocation.html",
                           po_map=po_map,
                           suppliers=suppliers,
                           status_filter=status_filter,
                           supplier_filter=supplier_filter,
                           today=date.today())

# ── Report 2 — Container CBM Utilisation ─────────────────────────────────────
@reports_bp.route("/cbm-utilisation")
@supply_chain_required
def cbm_utilisation():
    export     = request.args.get("export","")
    containers = Container.query.order_by(
        Container.status, Container.container_id).all()

    if export == "csv":
        headers = [
            "Container ID","Shipment Type","Status",
            "CBM Capacity","CBM Used","CBM Remaining",
            "Utilisation %","Planned Departure",
            "Vessel Name","Voyage No","ETA","Container Number",
            "SKUs Allocated","Total Alloc Units"
        ]
        rows = []
        for c in containers:
            v = c.vessels[0] if c.vessels else None
            rows.append([
                c.container_id, c.shipment_type or "",
                c.status,
                c.cbm_capacity or "", c.total_cbm_used,
                c.cbm_remaining or "",
                c.cbm_utilisation_pct or "",
                c.planned_departure or "",
                v.vessel_name if v else "",
                v.voyage_number if v else "",
                v.eta if v else "",
                v.container_number if v else "",
                len(c.active_allocations),
                sum(a.allocated_units or 0 for a in c.active_allocations)
            ])
        return _csv_response(
            f"cbm_utilisation_{date.today()}.csv",
            headers, rows)

    return render_template("reports/cbm_utilisation.html",
                           containers=containers)

# ── Report 3 — SKU Readiness ──────────────────────────────────────────────────
@reports_bp.route("/sku-readiness")
@supply_chain_required
def sku_readiness():
    export          = request.args.get("export","")
    status_filter   = request.args.get("status","")
    supplier_filter = request.args.get("supplier","").strip()

    query = SKU.query.join(PurchaseOrder).filter(
        PurchaseOrder.po_status == "Active"
    )
    if status_filter:
        query = query.filter(SKU.sku_status == status_filter)
    if supplier_filter:
        query = query.filter(
            PurchaseOrder.supplier_name.ilike(f"%{supplier_filter}%"))
    skus = query.order_by(SKU.cargo_ready_date.asc().nullslast(),
                          SKU.sku_status).all()

    if export == "csv":
        headers = [
            "PO Number","Supplier","JJ SKU","Product Name",
            "HS Code","Buying QTY","Pending QTY",
            "No of Ctns","Total CBM","Cargo Ready Date",
            "SKU Status","CI Acknowledged"
        ]
        rows = [[
            s.po_number,
            s.purchase_order.supplier_name,
            s.jj_sku or "", s.product_name,
            s.hs_code or "",
            s.buying_qty or 0, s.pending_qty,
            s.no_of_ctns or "", s.total_cbm or "",
            s.cargo_ready_date or "", s.sku_status,
            "Yes" if s.ci_variance_acknowledged else "No"
        ] for s in skus]
        return _csv_response(
            f"sku_readiness_{date.today()}.csv",
            headers, rows)

    suppliers = [s[0] for s in
                 db.session.query(PurchaseOrder.supplier_name)
                 .distinct().all()]
    statuses = [
        "Pending Date","Awaiting Production",
        "Ready for Allocation","Partially Allocated","Fully Allocated"
    ]
    return render_template("reports/sku_readiness.html",
                           skus=skus,
                           suppliers=suppliers,
                           statuses=statuses,
                           status_filter=status_filter,
                           supplier_filter=supplier_filter,
                           today=date.today())

# ── Report 4 — Unallocated SKUs ───────────────────────────────────────────────
@reports_bp.route("/unallocated")
@supply_chain_required
def unallocated():
    export          = request.args.get("export","")
    supplier_filter = request.args.get("supplier","").strip()

    query = SKU.query.join(PurchaseOrder).filter(
        SKU.sku_status.in_(["Ready for Allocation",
                             "Partially Allocated",
                             "Awaiting Production",
                             "Pending Date"]),
        PurchaseOrder.po_status == "Active"
    )
    if supplier_filter:
        query = query.filter(
            PurchaseOrder.supplier_name.ilike(f"%{supplier_filter}%"))
    skus = query.order_by(
        SKU.sku_status, SKU.cargo_ready_date.asc().nullslast()
    ).all()

    if export == "csv":
        headers = [
            "PO Number","Supplier","JJ SKU","Product Name",
            "HS Code","Currency","Buying Price","Buying QTY",
            "Pending QTY","No of Ctns","Total CBM",
            "Cargo Ready Date","SKU Status","CI Acknowledged"
        ]
        rows = [[
            s.po_number,
            s.purchase_order.supplier_name,
            s.jj_sku or "", s.product_name,
            s.hs_code or "",
            s.purchase_order.currency or "",
            s.buying_price or "", s.buying_qty or 0,
            s.pending_qty,
            s.no_of_ctns or "", s.total_cbm or "",
            s.cargo_ready_date or "", s.sku_status,
            "Yes" if s.ci_variance_acknowledged else "No"
        ] for s in skus]
        return _csv_response(
            f"unallocated_skus_{date.today()}.csv",
            headers, rows)

    suppliers = [s[0] for s in
                 db.session.query(PurchaseOrder.supplier_name)
                 .distinct().all()]
    return render_template("reports/unallocated.html",
                           skus=skus,
                           suppliers=suppliers,
                           supplier_filter=supplier_filter)

# ── Report 5 — Vessel Schedule ────────────────────────────────────────────────
@reports_bp.route("/vessel-schedule")
@supply_chain_required
def vessel_schedule():
    export  = request.args.get("export","")
    vessels = Vessel.query.order_by(
        Vessel.etd.asc().nullslast()).all()

    if export == "csv":
        headers = [
            "Vessel Name","Voyage No","Carrier",
            "Port of Loading","Port of Discharge",
            "ETD","ETA","B/L Number",
            "Container ID","Container Number","Container Status",
            "CBM Used","CBM Capacity","Utilisation %"
        ]
        rows = []
        for v in vessels:
            c = v.container
            rows.append([
                v.vessel_name, v.voyage_number or "",
                v.carrier or "",
                v.port_of_loading or "",
                v.port_of_discharge or "",
                v.etd or "", v.eta or "",
                v.bill_of_lading_no or "",
                v.container_id or "",
                v.container_number or "",
                c.status if c else "",
                c.total_cbm_used if c else "",
                c.cbm_capacity if c else "",
                c.cbm_utilisation_pct if c else ""
            ])
        return _csv_response(
            f"vessel_schedule_{date.today()}.csv",
            headers, rows)

    return render_template("reports/vessel_schedule.html",
                           vessels=vessels,
                           today=date.today())
