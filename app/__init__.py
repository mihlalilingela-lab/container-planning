from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    from config import config
    app.config.from_object(config)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    from app.auth.routes import auth_bp
    from app.routes.main import main_bp
    from app.routes.admin import admin_bp
    from app.routes.purchase_orders import po_bp
    from app.routes.containers import container_bp
    from app.routes.vessels import vessel_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(auth_bp,       url_prefix="/auth")
    app.register_blueprint(main_bp,       url_prefix="/")
    app.register_blueprint(admin_bp,      url_prefix="/admin")
    app.register_blueprint(po_bp,         url_prefix="/purchase-orders")
    app.register_blueprint(container_bp,  url_prefix="/containers")
    app.register_blueprint(vessel_bp,     url_prefix="/vessels")
    app.register_blueprint(reports_bp,    url_prefix="/reports")

    with app.app_context():
        db.create_all()
        _seed_admin(app)
    return app

def _seed_admin(app):
    from app.models.user import User
    from config import config
    if User.query.count() == 0:
        admin = User(
            username=config.ADMIN_USERNAME,
            email=config.ADMIN_EMAIL,
            role="admin",
            must_change_password=True,
        )
        admin.set_password(config.ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()
        print(f"[SEED] Admin account created: {config.ADMIN_USERNAME}")
