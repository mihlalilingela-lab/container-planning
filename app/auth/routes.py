from datetime import datetime, timezone
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from app.models.supply_chain import AuditLog

auth_bp = Blueprint("auth", __name__)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("You do not have permission to access that page.", "danger")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)
    return login_required(decorated)

def supply_chain_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_supply_chain:
            flash("You do not have permission to access that page.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return login_required(decorated)

def _log(username, action, table_name=None, record_id=None, detail=None):
    entry = AuditLog(
        username=username,
        action=action,
        table_name=table_name,
        record_id=record_id,
        detail=detail,
    )
    db.session.add(entry)
    db.session.commit()

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            login_user(user, remember=False)
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            _log(user.username, "LOGIN", detail=f"Login from {request.remote_addr}")
            flash(f"Welcome back, {user.username}!", "success")
            if user.must_change_password:
                flash("Please change your password before continuing.", "warning")
                return redirect(url_for("auth.change_password"))
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.dashboard"))
        else:
            flash("Invalid username or password.", "danger")
    return render_template("auth/login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    _log(current_user.username, "LOGOUT")
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))

@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw     = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")
        if not current_user.check_password(current_pw):
            flash("Current password is incorrect.", "danger")
        elif len(new_pw) < 8:
            flash("New password must be at least 8 characters.", "danger")
        elif new_pw != confirm_pw:
            flash("New passwords do not match.", "danger")
        else:
            current_user.set_password(new_pw)
            current_user.must_change_password = False
            db.session.commit()
            _log(current_user.username, "UPDATE", table_name="users",
                 record_id=str(current_user.id), detail="Password changed")
            flash("Password updated successfully.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/change_password.html")
