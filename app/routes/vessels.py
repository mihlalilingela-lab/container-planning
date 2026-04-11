from datetime import datetime, timezone
from flask import (Blueprint, render_template, redirect,
                   url_for, flash, request)
from flask_login import current_user
from app import db
from app.models.supply_chain import Vessel, Container, AuditLog
from app.auth.routes import supply_chain_required

vessel_bp = Blueprint("vessel", __name__)

def _log(action, table_name=None, record_id=None, detail=None):
    entry = AuditLog(
        username=current_user.username, action=action,
        table_name=table_name, record_id=record_id, detail=detail,
    )
    db.session.add(entry)
    db.session.commit()

# ── Vessel List ───────────────────────────────────────────────────────────────
@vessel_bp.route("/")
@supply_chain_required
def list_vessels():
    from datetime import date
    vessels = Vessel.query.order_by(Vessel.etd.desc().nullslast()).all()
    return render_template("vessel/list.html", vessels=vessels, today=date.today())

# ── Vessel Detail ─────────────────────────────────────────────────────────────
@vessel_bp.route("/<int:vessel_id>")
@supply_chain_required
def detail(vessel_id):
    vessel = db.session.get(Vessel, vessel_id)
    if not vessel:
        flash("Vessel not found.", "danger")
        return redirect(url_for("vessel.list_vessels"))
    return render_template("vessel/detail.html", vessel=vessel)

# ── Create Vessel ─────────────────────────────────────────────────────────────
@vessel_bp.route("/new", methods=["GET", "POST"])
@supply_chain_required
def create_vessel():
    containers = Container.query.order_by(
        Container.container_id).all()
    if request.method == "POST":
        vessel_name = request.form.get("vessel_name","").strip()
        if not vessel_name:
            flash("Vessel name is required.", "danger")
            return render_template("vessel/form.html",
                                   vessel=None,
                                   containers=containers)
        vessel = Vessel(
            vessel_name       = vessel_name,
            voyage_number     = request.form.get("voyage_number","").strip() or None,
            carrier           = request.form.get("carrier","").strip() or None,
            port_of_loading   = request.form.get("port_of_loading","").strip() or None,
            port_of_discharge = request.form.get("port_of_discharge","").strip() or None,
            etd               = _date(request.form.get("etd")),
            eta               = _date(request.form.get("eta")),
            bill_of_lading_no = request.form.get("bill_of_lading_no","").strip() or None,
            container_number  = request.form.get("container_number","").strip().upper() or None,
            container_id      = request.form.get("container_id","").strip() or None,
        )
        db.session.add(vessel)
        db.session.commit()
        _log("CREATE","vessels",str(vessel.id),
             f"Vessel {vessel_name} created | "
             f"Voyage: {vessel.voyage_number} | "
             f"Container: {vessel.container_id}")
        flash(f"Vessel {vessel_name} created.", "success")
        return redirect(url_for("vessel.detail", vessel_id=vessel.id))
    return render_template("vessel/form.html",
                           vessel=None, containers=containers)

# ── Edit Vessel ───────────────────────────────────────────────────────────────
@vessel_bp.route("/<int:vessel_id>/edit", methods=["GET", "POST"])
@supply_chain_required
def edit_vessel(vessel_id):
    vessel = db.session.get(Vessel, vessel_id)
    if not vessel:
        flash("Vessel not found.", "danger")
        return redirect(url_for("vessel.list_vessels"))
    containers = Container.query.order_by(Container.container_id).all()
    if request.method == "POST":
        old_etd = str(vessel.etd or "")
        old_eta = str(vessel.eta or "")
        vessel.vessel_name       = request.form.get("vessel_name","").strip()
        vessel.voyage_number     = request.form.get("voyage_number","").strip() or None
        vessel.carrier           = request.form.get("carrier","").strip() or None
        vessel.port_of_loading   = request.form.get("port_of_loading","").strip() or None
        vessel.port_of_discharge = request.form.get("port_of_discharge","").strip() or None
        vessel.etd               = _date(request.form.get("etd"))
        vessel.eta               = _date(request.form.get("eta"))
        vessel.bill_of_lading_no = request.form.get("bill_of_lading_no","").strip() or None
        vessel.container_number  = request.form.get("container_number","").strip().upper() or None
        vessel.container_id      = request.form.get("container_id","").strip() or None
        changes = []
        if str(vessel.etd or "") != old_etd:
            changes.append(f"ETD: {old_etd or 'none'} → {vessel.etd}")
        if str(vessel.eta or "") != old_eta:
            changes.append(f"ETA: {old_eta or 'none'} → {vessel.eta}")
        db.session.commit()
        _log("UPDATE","vessels",str(vessel_id),
             f"Vessel {vessel.vessel_name} updated" +
             (f" | {' | '.join(changes)}" if changes else ""))
        flash(f"Vessel {vessel.vessel_name} updated.", "success")
        return redirect(url_for("vessel.detail", vessel_id=vessel_id))
    return render_template("vessel/form.html",
                           vessel=vessel, containers=containers)

# ── Delete Vessel ─────────────────────────────────────────────────────────────
@vessel_bp.route("/<int:vessel_id>/delete", methods=["POST"])
@supply_chain_required
def delete_vessel(vessel_id):
    vessel = db.session.get(Vessel, vessel_id)
    if not vessel:
        flash("Vessel not found.", "danger")
        return redirect(url_for("vessel.list_vessels"))
    name = vessel.vessel_name
    _log("DELETE","vessels",str(vessel_id),
         f"Vessel {name} deleted")
    db.session.delete(vessel)
    db.session.commit()
    flash(f"Vessel {name} deleted.", "success")
    return redirect(url_for("vessel.list_vessels"))

def _date(val):
    if not val or str(val).strip() == "": return None
    from datetime import datetime as dt
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"):
        try: return dt.strptime(str(val).strip(), fmt).date()
        except ValueError: continue
    return None
