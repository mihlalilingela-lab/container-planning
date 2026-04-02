from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from app.models.supply_chain import PurchaseOrder, SKU, Container, AuditLog

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
@main_bp.route("/dashboard")
@login_required
def dashboard():
    stats = {
        "total_pos":         PurchaseOrder.query.count(),
        "total_skus":        SKU.query.count(),
        "total_containers":  Container.query.count(),
        "active_containers": Container.query.filter(
            Container.status.in_(["Planning", "Confirmed"])
        ).count(),
    }
    recent_activity = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
    return render_template("main/dashboard.html", stats=stats, activity=recent_activity)

@main_bp.route("/health")
def health():
    try:
        from app import db
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "ok", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500
