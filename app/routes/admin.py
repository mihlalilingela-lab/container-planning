from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user
from app import db
from app.models.user import User
from app.models.supply_chain import AuditLog
from app.auth.routes import admin_required, _log

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/users")
@admin_required
def users():
    all_users = User.query.order_by(User.username).all()
    return render_template("admin/users.html", users=all_users)

@admin_bp.route("/users/create", methods=["GET", "POST"])
@admin_required
def create_user():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        role     = request.form.get("role", "supply_chain")
        password = request.form.get("password", "")
        if User.query.filter_by(username=username).first():
            flash(f"Username '{username}' already exists.", "danger")
        elif User.query.filter_by(email=email).first():
            flash(f"Email '{email}' is already registered.", "danger")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
        else:
            new_user = User(
                username=username,
                email=email,
                role=role,
                must_change_password=True,
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            _log(current_user.username, "CREATE", table_name="users",
                 record_id=str(new_user.id), detail=f"Created user {username} [{role}]")
            flash(f"User '{username}' created. They must change password on first login.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/create_user.html")

@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.users"))
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    db.session.commit()
    action = "activated" if user.is_active else "deactivated"
    _log(current_user.username, "UPDATE", table_name="users",
         record_id=str(user.id), detail=f"User {user.username} {action}")
    flash(f"User '{user.username}' has been {action}.", "success")
    return redirect(url_for("admin.users"))

@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.users"))
    new_password = request.form.get("new_password", "")
    if len(new_password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return redirect(url_for("admin.users"))
    user.set_password(new_password)
    user.must_change_password = True
    db.session.commit()
    _log(current_user.username, "UPDATE", table_name="users",
         record_id=str(user.id), detail=f"Password reset for {user.username}")
    flash(f"Password for '{user.username}' has been reset.", "success")
    return redirect(url_for("admin.users"))

@admin_bp.route("/audit-log")
@admin_required
def audit_log():
    page = request.args.get("page", 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template("admin/audit_log.html", logs=logs)
