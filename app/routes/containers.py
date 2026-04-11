from datetime import datetime, timezone
from flask import (Blueprint, render_template, redirect,
                   url_for, flash, request, Response)
from flask_login import current_user
from app import db
from app.models.supply_chain import (Container, Vessel, Allocation,
                                      SKU, PurchaseOrder, AuditLog)
from app.auth.routes import supply_chain_required
from app.services.sku_status import (refresh_sku_statuses,
                                      check_sku_allocation_eligibility,
                                      check_container_confirmation_eligibility)

container_bp = Blueprint("container", __name__)

DEALLOCATION_REASONS = [
    ("DR-01", "Cargo not ready — CRD pushed out"),
    ("DR-02", "CI variance unresolved"),
    ("DR-03", "Payment issue — PO on hold"),
    ("DR-04", "Container space constraint"),
    ("DR-05", "Supplier delay"),
    ("DR-06", "Quantity amendment"),
    ("DR-07", "Container cancelled"),
    ("DR-08", "Shipped separately"),
    ("DR-09", "Customer / buyer request"),
]

CONTAINER_PRESETS = [
    ("", "— Select preset or enter manually —"),
    ("30.0",  "20ft FCL (30 CBM — max 32)"),
    ("60.0",  "40ft FCL (60 CBM — max 63)"),
    ("70.0",  "40ft HQ FCL (70 CBM)"),
    ("15.0",  "LCL (~15 CBM)"),
]

def _log(action, table_name=None, record_id=None, detail=None):
    entry = AuditLog(
        username=current_user.username, action=action,
        table_name=table_name, record_id=record_id, detail=detail,
    )
    db.session.add(entry)
    db.session.commit()

# ── Container List ────────────────────────────────────────────────────────────
@container_bp.route("/")
@supply_chain_required
def list_containers():
    status_filter = request.args.get("status", "")
    query = Container.query
    if status_filter:
        query = query.filter(Container.status == status_filter)
    containers = query.order_by(Container.created_at.desc()).all()
    return render_template("container/list.html",
                           containers=containers,
                           status_filter=status_filter)

# ── Container Detail ──────────────────────────────────────────────────────────
@container_bp.route("/<container_id>")
@supply_chain_required
def detail(container_id):
    container = db.session.get(Container, container_id)
    if not container:
        flash(f"Container {container_id} not found.", "danger")
        return redirect(url_for("container.list_containers"))

    # Group active allocations by PO → then by SKU
    # Each SKU appears ONCE per container — qtys summed across allocations
    po_groups = {}
    for alloc in container.active_allocations:
        sku     = alloc.sku
        po_num  = sku.po_number

        if po_num not in po_groups:
            po_groups[po_num] = {
                "po":         sku.purchase_order,
                "sku_rows":   {},   # keyed by sku.id
                "total_ctns": 0,
                "total_units":0,
                "total_cbm":  0.0,
            }

        # Aggregate by SKU within this PO
        if sku.id not in po_groups[po_num]["sku_rows"]:
            po_groups[po_num]["sku_rows"][sku.id] = {
                "sku":          sku,
                "allocations":  [],   # individual records for deallocation
                "total_ctns":   0,
                "total_units":  0,
                "total_cbm":    0.0,
            }

        row = po_groups[po_num]["sku_rows"][sku.id]
        row["allocations"].append(alloc)
        row["total_ctns"]  += alloc.allocated_ctns  or 0
        row["total_units"] += alloc.allocated_units or 0
        row["total_cbm"]   += float(alloc.allocated_cbm or 0)

        po_groups[po_num]["total_ctns"]  += alloc.allocated_ctns  or 0
        po_groups[po_num]["total_units"] += alloc.allocated_units or 0
        po_groups[po_num]["total_cbm"]   += float(alloc.allocated_cbm or 0)

    can_confirm, blocking_skus = check_container_confirmation_eligibility(container)

    return render_template("container/detail.html",
                           container=container,
                           po_groups=po_groups,
                           can_confirm=can_confirm,
                           blocking_skus=blocking_skus,
                           deallocation_reasons=DEALLOCATION_REASONS)

# ── Create Container ──────────────────────────────────────────────────────────
@container_bp.route("/new", methods=["GET", "POST"])
@supply_chain_required
def create_container():
    if request.method == "POST":
        container_id = request.form.get("container_id","").strip()
        if not container_id:
            flash("Container ID is required.", "danger")
            return render_template("container/form.html",
                                   container=None, presets=CONTAINER_PRESETS)
        if db.session.get(Container, container_id):
            flash(f"Container {container_id} already exists.", "danger")
            return render_template("container/form.html",
                                   container=None, presets=CONTAINER_PRESETS)
        cbm = _decimal(request.form.get("cbm_capacity"))
        c = Container(
            container_id      = container_id,
            shipment_type     = request.form.get("shipment_type","").strip() or None,
            cbm_capacity      = cbm,
            status            = "Planning",
            planned_departure = _date(request.form.get("planned_departure")),
            notes             = request.form.get("notes","").strip() or None,
        )
        db.session.add(c)
        db.session.commit()
        _log("CREATE","containers",container_id,
             f"Container {container_id} created | "
             f"Type: {c.shipment_type} | CBM: {cbm}")
        flash(f"Container {container_id} created.", "success")
        return redirect(url_for("container.detail", container_id=container_id))
    return render_template("container/form.html",
                           container=None, presets=CONTAINER_PRESETS)

# ── Edit Container ────────────────────────────────────────────────────────────
@container_bp.route("/<container_id>/edit", methods=["GET", "POST"])
@supply_chain_required
def edit_container(container_id):
    c = db.session.get(Container, container_id)
    if not c:
        flash("Container not found.", "danger")
        return redirect(url_for("container.list_containers"))
    if request.method == "POST":
        c.shipment_type     = request.form.get("shipment_type","").strip() or None
        c.cbm_capacity      = _decimal(request.form.get("cbm_capacity"))
        c.planned_departure = _date(request.form.get("planned_departure"))
        c.notes             = request.form.get("notes","").strip() or None
        c.updated_at        = datetime.now(timezone.utc)
        db.session.commit()
        _log("UPDATE","containers",container_id,
             f"Container {container_id} updated")
        flash(f"Container {container_id} updated.", "success")
        return redirect(url_for("container.detail", container_id=container_id))
    return render_template("container/form.html",
                           container=c, presets=CONTAINER_PRESETS)

# ── Change Status ─────────────────────────────────────────────────────────────
@container_bp.route("/<container_id>/status", methods=["POST"])
@supply_chain_required
def change_status(container_id):
    c          = db.session.get(Container, container_id)
    new_status = request.form.get("new_status","").strip()
    if not c:
        flash("Container not found.", "danger")
        return redirect(url_for("container.list_containers"))

    valid_transitions = {
        "Planning":  ["Confirmed"],
        "Confirmed": ["Shipped"],
        "Shipped":   ["Closed"],
        "Closed":    [],
    }
    if new_status not in valid_transitions.get(c.status, []):
        flash(f"Cannot change from {c.status} to {new_status}.", "danger")
        return redirect(url_for("container.detail", container_id=container_id))

    if new_status in ("Confirmed","Shipped","Closed"):
        can_confirm, blocking = check_container_confirmation_eligibility(c)
        if not can_confirm:
            skus_str = ", ".join(b["jj_sku"] for b in blocking)
            flash(f"Cannot confirm — unacknowledged CI on: {skus_str}.", "danger")
            return redirect(url_for("container.detail", container_id=container_id))

    old_status = c.status
    c.status   = new_status
    c.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    _log("UPDATE","containers",container_id,
         f"Status: {old_status} → {new_status}")
    flash(f"Container {container_id} → {new_status}.", "success")
    return redirect(url_for("container.detail", container_id=container_id))

# ── Allocate to Container ─────────────────────────────────────────────────────
@container_bp.route("/<container_id>/allocate", methods=["GET","POST"])
@supply_chain_required
def allocate(container_id):
    c = db.session.get(Container, container_id)
    if not c:
        flash("Container not found.", "danger")
        return redirect(url_for("container.list_containers"))

    if request.method == "POST":
        sku_id     = _int(request.form.get("sku_id"))
        alloc_ctns = _int(request.form.get("allocated_ctns"))
        if not sku_id or not alloc_ctns or alloc_ctns <= 0:
            flash("Select a SKU and enter valid carton count.", "danger")
            return redirect(url_for("container.allocate",
                                    container_id=container_id))

        sku = db.session.get(SKU, sku_id)
        if not sku:
            flash("SKU not found.", "danger")
            return redirect(url_for("container.allocate",
                                    container_id=container_id))

        allowed, warning, block = check_sku_allocation_eligibility(sku, c)
        if not allowed:
            flash(block, "danger")
            return redirect(url_for("container.allocate",
                                    container_id=container_id))

        if alloc_ctns > (sku.pending_ctns or 0):
            flash(f"Only {sku.pending_ctns} cartons pending — "
                  f"cannot allocate {alloc_ctns}.", "danger")
            return redirect(url_for("container.allocate",
                                    container_id=container_id))

        _do_allocate(sku, c, alloc_ctns, warning)
        return redirect(url_for("container.detail", container_id=container_id))

    eligible_skus = _get_eligible_skus()
    return render_template("container/allocate.html",
                           container=c, eligible_skus=eligible_skus)

# ── Allocate from SKU side ────────────────────────────────────────────────────
@container_bp.route("/allocate-sku/<int:sku_id>", methods=["GET","POST"])
@supply_chain_required
def allocate_from_sku(sku_id):
    sku = db.session.get(SKU, sku_id)
    if not sku:
        flash("SKU not found.", "danger")
        return redirect(url_for("po.list_pos"))

    if request.method == "POST":
        container_id = request.form.get("container_id","").strip()
        alloc_ctns   = _int(request.form.get("allocated_ctns"))
        if not container_id or not alloc_ctns or alloc_ctns <= 0:
            flash("Select a container and enter carton count.", "danger")
            return redirect(url_for("container.allocate_from_sku",
                                    sku_id=sku_id))

        c = db.session.get(Container, container_id)
        if not c:
            flash("Container not found.", "danger")
            return redirect(url_for("container.allocate_from_sku",
                                    sku_id=sku_id))

        allowed, warning, block = check_sku_allocation_eligibility(sku, c)
        if not allowed:
            flash(block, "danger")
            return redirect(url_for("container.allocate_from_sku",
                                    sku_id=sku_id))

        if alloc_ctns > (sku.pending_ctns or 0):
            flash(f"Only {sku.pending_ctns} cartons pending.", "danger")
            return redirect(url_for("container.allocate_from_sku",
                                    sku_id=sku_id))

        # Unit override — allows partial last carton
        units_override = _int(request.form.get("allocated_units_override"))
        _do_allocate(sku, c, alloc_ctns, warning,
                     units_override=units_override)
        return redirect(url_for("po.detail", po_number=sku.po_number))

    containers = Container.query.filter(
        Container.status.in_(["Planning","Confirmed"])
    ).order_by(Container.container_id).all()
    return render_template("container/allocate_from_sku.html",
                           sku=sku, containers=containers)

# ── Deallocate ────────────────────────────────────────────────────────────────
@container_bp.route("/deallocate/<int:alloc_id>", methods=["POST"])
@supply_chain_required
def deallocate(alloc_id):
    alloc = db.session.get(Allocation, alloc_id)
    if not alloc or not alloc.is_active:
        flash("Allocation not found.", "danger")
        return redirect(url_for("container.list_containers"))

    reason_code = request.form.get("reason_code","").strip()
    if not reason_code:
        flash("Please select a deallocation reason.", "danger")
        return redirect(url_for("container.detail",
                                container_id=alloc.container_id))

    reason_label = next(
        (label for code, label in DEALLOCATION_REASONS
         if code == reason_code), reason_code
    )

    sku          = alloc.sku
    container_id = alloc.container_id

    alloc.is_active           = False
    alloc.deallocated_at      = datetime.now(timezone.utc)
    alloc.deallocated_by      = current_user.username
    alloc.deallocation_reason = f"{reason_code} — {reason_label}"

    # Recalculate allocated_qty from remaining active allocations
    # (ensures accuracy after partial deallocations)
    remaining = sum(
        a.allocated_units or 0
        for a in sku.allocations
        if a.is_active and a.id != alloc_id
    )
    sku.allocated_qty = max(remaining, 0)

    po = sku.purchase_order
    refresh_sku_statuses(po)
    db.session.commit()

    _log("UPDATE","allocations",str(alloc_id),
         f"Deallocated SKU {sku.jj_sku} from {container_id} | "
         f"Reason: {reason_code} — {reason_label} | "
         f"{alloc.allocated_ctns} ctns | {alloc.allocated_units} units")
    flash(f"SKU {sku.jj_sku} deallocated. Reason: {reason_code}.", "success")
    return redirect(url_for("container.detail", container_id=container_id))

# ── Shared allocation logic ───────────────────────────────────────────────────
def _do_allocate(sku, container, alloc_ctns, warning=None,
                 units_override=None):
    outer_ctn_qty = sku.outer_carton_qty or 1
    # Use override if provided (partial last carton)
    # otherwise calculate from cartons x units per carton
    if units_override and 0 < units_override <= alloc_ctns * outer_ctn_qty:
        alloc_units = units_override
    else:
        alloc_units = alloc_ctns * outer_ctn_qty
    cbm_per_ctn   = sku.volumetric_cbm or 0
    alloc_cbm     = round(cbm_per_ctn * alloc_ctns, 6)

    alloc = Allocation(
        sku_id          = sku.id,
        container_id    = container.container_id,
        allocated_ctns  = alloc_ctns,
        allocated_units = alloc_units,
        allocated_cbm   = alloc_cbm,
        allocated_by    = current_user.username,
        is_active       = True,
    )
    db.session.add(alloc)

    # Always recompute allocated_qty from all active allocations
    db.session.flush()
    sku.allocated_qty = sum(
        a.allocated_units or 0
        for a in sku.allocations
        if a.is_active
    )
    po = sku.purchase_order
    refresh_sku_statuses(po)
    db.session.commit()

    msg = (f"Allocated {alloc_ctns} ctns / {alloc_units} units / "
           f"{alloc_cbm} CBM to {container.container_id}.")
    if warning:
        flash(f"{msg} ⚠ {warning}", "warning")
    else:
        flash(msg, "success")

    _log("CREATE","allocations",str(alloc.id),
         f"SKU {sku.jj_sku} (PO {sku.po_number}) → "
         f"{container.container_id} | "
         f"{alloc_ctns} ctns | {alloc_units} units | {alloc_cbm} CBM")

# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_eligible_skus():
    return (SKU.query
            .join(PurchaseOrder)
            .filter(
                SKU.sku_status.in_(["Ready for Allocation",
                                    "Partially Allocated"]),
                SKU.ci_variance_acknowledged == True,
                PurchaseOrder.po_status == "Active"
            )
            .order_by(PurchaseOrder.supplier_name, SKU.jj_sku)
            .all())

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
    from datetime import datetime as dt
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"):
        try: return dt.strptime(str(val).strip(), fmt).date()
        except ValueError: continue
    return None
