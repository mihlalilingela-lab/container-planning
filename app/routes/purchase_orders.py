from datetime import datetime, timezone
from flask import (Blueprint, render_template, redirect,
                   url_for, flash, request, Response)
from flask_login import current_user
from app import db
from app.models.supply_chain import PurchaseOrder, SKU, AuditLog
from app.auth.routes import supply_chain_required
from app.services.sku_status import (refresh_sku_statuses,
                                      check_sku_allocation_eligibility)
from app.services.csv_import import import_csv

po_bp = Blueprint("po", __name__)

def _log(action, table_name=None, record_id=None, detail=None):
    entry = AuditLog(
        username=current_user.username, action=action,
        table_name=table_name, record_id=record_id, detail=detail,
    )
    db.session.add(entry)
    db.session.commit()

@po_bp.route("/")
@supply_chain_required
def list_pos():
    status_filter   = request.args.get("status", "")
    supplier_filter = request.args.get("supplier", "").strip()
    query = PurchaseOrder.query
    if status_filter:
        query = query.filter(PurchaseOrder.po_status == status_filter)
    if supplier_filter:
        query = query.filter(
            PurchaseOrder.supplier_name.ilike(f"%{supplier_filter}%"))
    pos       = query.order_by(PurchaseOrder.created_at.desc()).all()
    suppliers = [s[0] for s in
                 db.session.query(PurchaseOrder.supplier_name).distinct().all()]
    return render_template("po/list.html", pos=pos, suppliers=suppliers,
                           status_filter=status_filter,
                           supplier_filter=supplier_filter)

@po_bp.route("/<po_number>")
@supply_chain_required
def detail(po_number):
    po = db.session.get(PurchaseOrder, po_number)
    if not po:
        flash(f"PO {po_number} not found.", "danger")
        return redirect(url_for("po.list_pos"))
    return render_template("po/detail.html", po=po)

@po_bp.route("/new", methods=["GET","POST"])
@supply_chain_required
def create_po():
    if request.method == "POST":
        po_number = request.form.get("po_number","").strip()
        if not po_number:
            flash("PO Number is required.", "danger")
            return render_template("po/form.html", po=None)
        if db.session.get(PurchaseOrder, po_number):
            flash(f"PO {po_number} already exists.", "danger")
            return render_template("po/form.html", po=None)
        po = PurchaseOrder(
            po_number     = po_number,
            pi_number     = request.form.get("pi_number","").strip() or None,
            ci_number     = request.form.get("ci_number","").strip() or None,
            supplier_name = request.form.get("supplier_name","").strip(),
            currency      = request.form.get("currency","USD").strip(),
            po_status     = request.form.get("po_status","Active"),
            notes         = request.form.get("notes","").strip() or None,
            created_by    = current_user.username,
        )
        db.session.add(po)
        db.session.commit()
        _log("CREATE","purchase_orders",po_number,
             f"PO {po_number} created for {po.supplier_name}")
        flash(f"PO {po_number} created.", "success")
        return redirect(url_for("po.detail", po_number=po_number))
    return render_template("po/form.html", po=None)

@po_bp.route("/<po_number>/edit", methods=["GET","POST"])
@supply_chain_required
def edit_po(po_number):
    po = db.session.get(PurchaseOrder, po_number)
    if not po:
        flash("PO not found.", "danger")
        return redirect(url_for("po.list_pos"))
    if request.method == "POST":
        old_status    = po.po_status
        po.pi_number  = request.form.get("pi_number","").strip() or None
        po.ci_number  = request.form.get("ci_number","").strip() or None
        po.supplier_name = request.form.get("supplier_name","").strip()
        po.currency   = request.form.get("currency","USD").strip()
        po.po_status  = request.form.get("po_status","Active")
        po.notes      = request.form.get("notes","").strip() or None
        po.updated_at = datetime.now(timezone.utc)
        if po.po_status != old_status:
            _log("UPDATE","purchase_orders",po_number,
                 f"PO status: {old_status} → {po.po_status} "
                 f"(cascades to {len(po.skus)} SKUs)")
        refresh_sku_statuses(po)
        db.session.commit()
        _log("UPDATE","purchase_orders",po_number,f"PO {po_number} updated")
        flash(f"PO {po_number} updated.", "success")
        return redirect(url_for("po.detail", po_number=po_number))
    return render_template("po/form.html", po=po)

@po_bp.route("/<po_number>/delete", methods=["POST"])
@supply_chain_required
def delete_po(po_number):
    po = db.session.get(PurchaseOrder, po_number)
    if not po:
        flash("PO not found.", "danger")
        return redirect(url_for("po.list_pos"))
    db.session.delete(po)
    db.session.commit()
    _log("DELETE","purchase_orders",po_number,
         f"PO {po_number} deleted")
    flash(f"PO {po_number} deleted.", "success")
    return redirect(url_for("po.list_pos"))

@po_bp.route("/<po_number>/skus/new", methods=["GET","POST"])
@supply_chain_required
def create_sku(po_number):
    po = db.session.get(PurchaseOrder, po_number)
    if not po:
        flash("PO not found.", "danger")
        return redirect(url_for("po.list_pos"))
    if request.method == "POST":
        buying_qty = int(request.form.get("buying_qty",0) or 0)
        sku = SKU(
            po_number        = po_number,
            jj_sku           = request.form.get("jj_sku","").strip() or None,
            supplier_sku     = request.form.get("supplier_sku","").strip() or None,
            product_name     = request.form.get("product_name","").strip(),
            shipment_type    = request.form.get("shipment_type","").strip() or None,
            hs_code          = request.form.get("hs_code","").strip() or None,
            buying_price     = _decimal(request.form.get("buying_price")),
            buying_qty       = buying_qty,
            total_order_qty  = buying_qty,
            ci_price         = _decimal(request.form.get("ci_price")),
            ci_qty           = _int(request.form.get("ci_qty")),
            outer_carton_qty = _int(request.form.get("outer_carton_qty")),
            length_cm        = _decimal(request.form.get("length_cm")),
            width_cm         = _decimal(request.form.get("width_cm")),
            height_cm        = _decimal(request.form.get("height_cm")),
            weight_kg        = _decimal(request.form.get("weight_kg")),
            cargo_ready_date = _date(request.form.get("cargo_ready_date")),
        )
        db.session.add(sku)
        db.session.flush()
        refresh_sku_statuses(po)
        db.session.commit()
        _log("CREATE","skus",str(sku.id),
             f"SKU {sku.jj_sku} added to PO {po_number} | "
             f"Status: {sku.sku_status}")
        flash(f"SKU added to {po_number}.", "success")
        return redirect(url_for("po.detail", po_number=po_number))
    return render_template("po/sku_form.html", po=po, sku=None)

@po_bp.route("/<po_number>/skus/<int:sku_id>/edit", methods=["GET","POST"])
@supply_chain_required
def edit_sku(po_number, sku_id):
    po  = db.session.get(PurchaseOrder, po_number)
    sku = db.session.get(SKU, sku_id)
    if not po or not sku:
        flash("Record not found.", "danger")
        return redirect(url_for("po.list_pos"))
    if request.method == "POST":
        old_status       = sku.sku_status
        old_buying_price = str(sku.buying_price or "")
        old_buying_qty   = sku.buying_qty
        old_product_name = sku.product_name
        old_crd          = str(sku.cargo_ready_date or "")

        buying_qty   = int(request.form.get("buying_qty",0) or 0)
        new_ci_qty   = _int(request.form.get("ci_qty"))
        new_ci_price = _decimal(request.form.get("ci_price"))
        ci_changed   = (new_ci_qty != sku.ci_qty or
                        str(new_ci_price or "") != str(sku.ci_price or ""))
        if ci_changed:
            sku.ci_variance_acknowledged = False

        sku.jj_sku           = request.form.get("jj_sku","").strip() or None
        sku.supplier_sku     = request.form.get("supplier_sku","").strip() or None
        sku.product_name     = request.form.get("product_name","").strip()
        sku.shipment_type    = request.form.get("shipment_type","").strip() or None
        sku.hs_code          = request.form.get("hs_code","").strip() or None
        sku.buying_price     = _decimal(request.form.get("buying_price"))
        sku.buying_qty       = buying_qty
        sku.ci_price         = new_ci_price
        sku.ci_qty           = new_ci_qty
        sku.outer_carton_qty = _int(request.form.get("outer_carton_qty"))
        sku.length_cm        = _decimal(request.form.get("length_cm"))
        sku.width_cm         = _decimal(request.form.get("width_cm"))
        sku.height_cm        = _decimal(request.form.get("height_cm"))
        sku.weight_kg        = _decimal(request.form.get("weight_kg"))
        sku.cargo_ready_date = _date(request.form.get("cargo_ready_date"))

        # CI acknowledgement — update working qty and force status refresh
        if request.form.get("acknowledge_ci"):
            old_working              = sku.total_order_qty
            sku.total_order_qty      = sku.ci_qty
            sku.ci_variance_acknowledged = True
            _log("UPDATE","skus",str(sku_id),
                 f"CI acknowledged: {sku.jj_sku} | "
                 f"Working QTY {old_working} → {sku.ci_qty}")

        # Always update working qty from buying_qty if no CI yet
        if not sku.ci_variance_acknowledged and sku.allocated_qty == 0:
            sku.total_order_qty = buying_qty

        # Recompute allocated_qty from active allocations for accuracy
        sku.allocated_qty = sum(
            a.allocated_units or 0
            for a in sku.allocations
            if a.is_active
        )

        # Status always recomputed — never manually set
        refresh_sku_statuses(po)

        changes = []
        if sku.product_name != old_product_name:
            changes.append(f"Name: '{old_product_name}' → '{sku.product_name}'")
        if str(sku.buying_price or "") != old_buying_price:
            changes.append(f"Price: {old_buying_price} → {sku.buying_price}")
        if sku.buying_qty != old_buying_qty:
            changes.append(f"Buying QTY: {old_buying_qty} → {sku.buying_qty}")
        if str(sku.cargo_ready_date or "") != old_crd:
            changes.append(
                f"CRD: {old_crd or 'none'} → {sku.cargo_ready_date or 'none'}")
        if ci_changed:
            changes.append(
                f"CI updated (price:{new_ci_price} qty:{new_ci_qty})"
                f" — acknowledgement reset")
        if sku.sku_status != old_status:
            changes.append(f"Status: {old_status} → {sku.sku_status}")

        db.session.commit()
        _log("UPDATE","skus",str(sku_id),
             f"SKU {sku.jj_sku} on PO {po_number} — " +
             (" | ".join(changes) if changes else "updated"))
        flash("SKU updated.", "success")
        return redirect(url_for("po.detail", po_number=po_number))
    return render_template("po/sku_form.html", po=po, sku=sku)

@po_bp.route("/<po_number>/skus/<int:sku_id>/delete", methods=["POST"])
@supply_chain_required
def delete_sku(po_number, sku_id):
    sku = db.session.get(SKU, sku_id)
    if not sku:
        flash("SKU not found.", "danger")
        return redirect(url_for("po.detail", po_number=po_number))
    jj_sku = sku.jj_sku
    _log("DELETE","skus",str(sku_id),
         f"SKU {jj_sku} deleted from PO {po_number}")
    db.session.delete(sku)
    db.session.commit()
    flash(f"SKU {jj_sku} deleted.", "success")
    return redirect(url_for("po.detail", po_number=po_number))

@po_bp.route("/import", methods=["GET","POST"])
@supply_chain_required
def import_pos():
    if request.method == "POST":
        f = request.files.get("csv_file")
        if not f or not f.filename.endswith(".csv"):
            flash("Please upload a valid .csv file.", "danger")
            return render_template("po/import.html")
        results = import_csv(f.stream, imported_by=current_user.username)
        _log("CREATE","purchase_orders","CSV",
             f"Import: {results['pos_created']} POs, "
             f"{results['skus_created']} SKUs created")
        return render_template("po/import_results.html", results=results)
    return render_template("po/import.html")

@po_bp.route("/csv-template")
@supply_chain_required
def csv_template():
    headers = (
        "po_number,pi_number,ci_number,supplier_name,currency,"
        "po_status,jj_sku,supplier_sku,product_name,shipment_type,"
        "hs_code,buying_price,buying_qty,outer_carton_qty,"
        "length_cm,width_cm,height_cm,weight_kg,cargo_ready_date,"
        "ci_price,ci_qty\r\n"
    )
    example = (
        "EXAMPLE-DO-NOT-IMPORT,PI-000,,Supplier Name,USD,"
        "Active,JJ-SKU-000,SUP-000,Product Name Here,FCL,"
        "9403.20,45.50,100,10,60,40,40,12.5,2026-04-15,,\r\n"
    )
    return Response(
        headers + example,
        mimetype="text/csv",
        headers={"Content-Disposition":
                 "attachment;filename=container_import_template.csv"}
    )

@po_bp.route("/<po_number>/skus/<int:sku_id>/acknowledge-ci",
             methods=["POST"])
@supply_chain_required
def acknowledge_ci(po_number, sku_id):
    po  = db.session.get(PurchaseOrder, po_number)
    sku = db.session.get(SKU, sku_id)
    if not po:
        flash(f"PO {po_number} not found.", "danger")
        return redirect(url_for("po.list_pos"))
    if not sku:
        flash(f"SKU {sku_id} not found.", "danger")
        return redirect(url_for("po.detail", po_number=po_number))
    try:
        old_qty                      = sku.total_order_qty
        sku.total_order_qty          = sku.ci_qty or sku.total_order_qty
        sku.ci_variance_acknowledged = True
        sku.allocated_qty = sum(
            a.allocated_units or 0
            for a in sku.allocations
            if a.is_active
        )
        refresh_sku_statuses(po)
        db.session.commit()
        _log("UPDATE","skus",str(sku_id),
             f"CI acknowledged: {sku.jj_sku} | "
             f"Working QTY {old_qty} → {sku.total_order_qty} | "
             f"New status: {sku.sku_status}")
        flash(f"CI acknowledged for {sku.jj_sku}. "
              f"Status: {sku.sku_status}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error acknowledging CI: {str(e)}", "danger")
        print(f"[ERROR] acknowledge_ci: {e}")
    return redirect(url_for("po.detail", po_number=po_number))

@po_bp.route("/<po_number>/skus/<int:sku_id>/history")
@supply_chain_required
def sku_history(po_number, sku_id):
    sku = db.session.get(SKU, sku_id)
    po  = db.session.get(PurchaseOrder, po_number)
    if not sku or not po:
        flash("Record not found.", "danger")
        return redirect(url_for("po.list_pos"))
    history = AuditLog.query.filter_by(
        table_name="skus", record_id=str(sku_id)
    ).order_by(AuditLog.timestamp.desc()).all()
    return render_template("po/sku_history.html",
                           sku=sku, po=po, history=history)

def _decimal(val):
    if not val or str(val).strip() == "": return None
    try: return float(str(val).replace(",","").strip())
    except ValueError: return None

def _int(val):
    if not val or str(val).strip() == "": return None
    try: return int(float(str(val).replace(",","").strip()))
    except ValueError: return None

def _date(val):
    if not val or str(val).strip() == "": return None
    from datetime import datetime
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"):
        try: return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError: continue
    return None