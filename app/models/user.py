from datetime import datetime, timezone
from flask_login import UserMixin
import bcrypt
from app import db, login_manager

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id                   = db.Column(db.Integer,     primary_key=True)
    username             = db.Column(db.String(80),  unique=True, nullable=False)
    email                = db.Column(db.String(120), unique=True, nullable=False)
    password_hash        = db.Column(db.String(255), nullable=False)
    role                 = db.Column(db.String(20),  nullable=False, default="supply_chain")
    is_active            = db.Column(db.Boolean,     default=True, nullable=False)
    must_change_password = db.Column(db.Boolean,     default=False, nullable=False)
    created_at           = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))
    last_login           = db.Column(db.DateTime,    nullable=True)

    def set_password(self, plain_text: str):
        self.password_hash = bcrypt.hashpw(
            plain_text.encode("utf-8"),
            bcrypt.gensalt(rounds=12)
        ).decode("utf-8")

    def check_password(self, plain_text: str) -> bool:
        return bcrypt.checkpw(
            plain_text.encode("utf-8"),
            self.password_hash.encode("utf-8")
        )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_supply_chain(self) -> bool:
        return self.role in ("admin", "supply_chain")

    def __repr__(self):
        return f"<User {self.username} [{self.role}]>"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
