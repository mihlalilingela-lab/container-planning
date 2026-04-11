from datetime import datetime, timezone
import math
from app import db

class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"
    po_number     = db.Column(db.String(50),  primary_key=True)
    pi_number     = db.Column(db.String(50),  nullable=True)
    ci_number     = db.Column(db.String(50),  nullable=True)
    supplier_name = db.Column(db.String(200), nullable=False)
    currency      = db.Column(db.String(10),  nullable=True, default="USD")
    po_status     = db.Column(db.String(20),  nullable=False, default="Active")
    notes         = db.Column(db.Text,        nullable=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))
    created_by    = db.Column(db.String(80),  nullable=True)

    skus = db.relationship("SKU", backref="purchase_order", lazy=True,
                           cascade="all, delete-orphan")

    @property
    def total_buying_qty(self):
        return sum(s.buying_qty or 0 for s in self.skus)

    @property
    def total_ci_qty(self):
        vals = [s.ci_qty for s in self.skus if s.ci_qty is not None]
        return sum(vals) if vals else None

    @property
    def total_order_qty(self):
        return sum(s.total_order_qty or 0 for s in self.skus)

    @property
    def total_allocated_qty(self):
        return sum(s.allocated_qty or 0 for s in self.skus)

    @property
    def total_pending_qty(self):
        return sum(s.pending_qty for s in self.skus)

    @property
    def total_no_of_ctns(self):
        vals = [s.no_of_ctns for s in self.skus if s.no_of_ctns is not None]
        return sum(vals) if vals else None

    @property
    def total_units(self):
        vals = [s.total_units for s in self.skus if s.total_units is not None]
        return sum(vals) if vals else None

    @property
    def total_cbm(self):
        vals = [s.total_cbm for s in self.skus if s.total_cbm is not None]
        return round(sum(vals), 6) if vals else None

    @property
    def total_amount(self):
        vals = [s.amount for s in self.skus if s.amount is not None]
        return round(sum(vals), 4) if vals else None

    @property
    def total_ci_amount(self):
        vals = [s.ci_total_amount for s in self.skus if s.ci_total_amount is not None]
        return round(sum(vals), 4) if vals else None

    @property
    def has_ci_variance(self):
        return any(s.has_ci_variance for s in self.skus)

    @property
    def derived_status(self):
        if self.po_status in ("On Hold", "Cancelled"):
            return self.po_status
        total     = self.total_order_qty
        allocated = self.total_allocated_qty
        if total == 0 or allocated == 0:
            return "Active"
        if allocated >= total:
            return "Fully Allocated"
        return "Partially Shipped"

    def __repr__(self):
        return f"<PO {self.po_number} | {self.supplier_name}>"


class SKU(db.Model):
    __tablename__ = "skus"
    id               = db.Column(db.Integer,       primary_key=True, autoincrement=True)
    po_number        = db.Column(db.String(50),    db.ForeignKey("purchase_orders.po_number"), nullable=False)
    supplier_sku     = db.Column(db.String(100),   nullable=True)
    jj_sku           = db.Column(db.String(100),   nullable=True)
    product_name     = db.Column(db.String(255),   nullable=False)
    shipment_type    = db.Column(db.String(20),    nullable=True)
    hs_code          = db.Column(db.String(20),    nullable=True)

    # Order fields
    buying_price     = db.Column(db.Numeric(12,4), nullable=True)
    buying_qty       = db.Column(db.Integer,       nullable=False, default=0)

    # Receipt fields
    ci_price         = db.Column(db.Numeric(12,4), nullable=True)
    ci_qty           = db.Column(db.Integer,       nullable=True)

    # Working qty
    total_order_qty  = db.Column(db.Integer,       nullable=False, default=0)
    allocated_qty    = db.Column(db.Integer,       nullable=False, default=0)

    # CI variance tracking
    ci_variance_acknowledged = db.Column(db.Boolean, default=False, nullable=False)

    # Dimensions
    outer_carton_qty = db.Column(db.Integer,       nullable=True)
    length_cm        = db.Column(db.Numeric(8,3),  nullable=True)
    width_cm         = db.Column(db.Numeric(8,3),  nullable=True)
    height_cm        = db.Column(db.Numeric(8,3),  nullable=True)
    weight_kg        = db.Column(db.Numeric(8,3),  nullable=True)

    # CRD at SKU level
    cargo_ready_date = db.Column(db.Date,          nullable=True)
    sku_status       = db.Column(db.String(30),    nullable=False, default="Pending Date")

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))

    allocations = db.relationship("Allocation", backref="sku", lazy=True,
                                  cascade="all, delete-orphan")

    @property
    def pending_qty(self):
        return max((self.total_order_qty or 0) - (self.allocated_qty or 0), 0)

    @property
    def no_of_ctns(self):
        if not self.outer_carton_qty or self.outer_carton_qty == 0:
            return None
        return math.ceil((self.buying_qty or 0) / self.outer_carton_qty)

    @property
    def total_units(self):
        n = self.no_of_ctns
        if n is not None and self.outer_carton_qty:
            return n * self.outer_carton_qty
        return None

    @property
    def pending_ctns(self):
        if not self.outer_carton_qty or self.outer_carton_qty == 0:
            return None
        return math.ceil(self.pending_qty / self.outer_carton_qty)

    @property
    def volumetric_cbm(self):
        if self.length_cm and self.width_cm and self.height_cm:
            return (float(self.length_cm) * float(self.width_cm) *
                    float(self.height_cm)) / 1_000_000
        return None

    @property
    def total_cbm(self):
        v = self.volumetric_cbm
        n = self.no_of_ctns
        if v is not None and n:
            return round(v * n, 6)
        return None

    @property
    def amount(self):
        if self.buying_price and self.buying_qty:
            return round(float(self.buying_price) * self.buying_qty, 4)
        return None

    @property
    def ci_total_amount(self):
        if self.ci_price and self.ci_qty:
            return round(float(self.ci_price) * self.ci_qty, 4)
        return None

    @property
    def display_amount(self):
        return self.ci_total_amount if self.ci_total_amount is not None else self.amount

    @property
    def price_variance(self):
        if self.ci_price is not None and self.buying_price is not None:
            return round(float(self.ci_price) - float(self.buying_price), 4)
        return None

    @property
    def qty_variance(self):
        if self.ci_qty is not None:
            return self.ci_qty - (self.buying_qty or 0)
        return None

    @property
    def has_ci_variance(self):
        if self.ci_variance_acknowledged:
            return False
        return (
            (self.price_variance is not None and self.price_variance != 0) or
            (self.qty_variance   is not None and self.qty_variance   != 0)
        )

    @property
    def ci_pending_acknowledgement(self):
        """CI has been entered but not yet acknowledged — regardless of variance."""
        return (
            not self.ci_variance_acknowledged and
            (self.ci_qty is not None or self.ci_price is not None)
        )

    def __repr__(self):
        return f"<SKU {self.jj_sku or self.supplier_sku} | PO {self.po_number}>"


class Container(db.Model):
    __tablename__ = "containers"
    container_id      = db.Column(db.String(50),   primary_key=True)
    shipment_type     = db.Column(db.String(20),   nullable=True)
    cbm_capacity      = db.Column(db.Numeric(8,3), nullable=True)
    status            = db.Column(db.String(20),   nullable=False, default="Planning")
    planned_departure = db.Column(db.Date,         nullable=True)
    notes             = db.Column(db.Text,         nullable=True)
    created_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                   onupdate=lambda: datetime.now(timezone.utc))
    allocations = db.relationship("Allocation", backref="container", lazy=True)
    vessels     = db.relationship("Vessel",     backref="container", lazy=True)

    @property
    def active_allocations(self):
        return [a for a in self.allocations if a.is_active]

    @property
    def total_cbm_used(self):
        return round(sum(float(a.allocated_cbm or 0)
                         for a in self.active_allocations), 6)

    @property
    def cbm_remaining(self):
        if self.cbm_capacity:
            return round(float(self.cbm_capacity) - self.total_cbm_used, 6)
        return None

    @property
    def cbm_utilisation_pct(self):
        if self.cbm_capacity and float(self.cbm_capacity) > 0:
            return round((self.total_cbm_used / float(self.cbm_capacity)) * 100, 1)
        return None

    def __repr__(self):
        return f"<Container {self.container_id}>"


class Vessel(db.Model):
    __tablename__ = "vessels"
    id                = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    vessel_name       = db.Column(db.String(200), nullable=False)
    voyage_number     = db.Column(db.String(100), nullable=True)
    carrier           = db.Column(db.String(200), nullable=True)
    port_of_loading   = db.Column(db.String(100), nullable=True)
    port_of_discharge = db.Column(db.String(100), nullable=True)
    etd               = db.Column(db.Date,        nullable=True)
    eta               = db.Column(db.Date,        nullable=True)
    bill_of_lading_no  = db.Column(db.String(100), nullable=True)
    container_number   = db.Column(db.String(20),  nullable=True)
    # Physical carrier container number e.g. MSCU1234567
    # Populated when booking is confirmed — same time as vessel details
    # One vessel links to one container per record.
    # To link multiple containers to same voyage,
    # create one vessel record per container — same vessel name + voyage number.
    container_id      = db.Column(db.String(50),
                                   db.ForeignKey("containers.container_id"), nullable=True)
    created_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def sister_vessels(self):
        """Other vessel records with same voyage number — different containers."""
        if not self.voyage_number:
            return []
        return Vessel.query.filter(
            Vessel.voyage_number == self.voyage_number,
            Vessel.id != self.id
        ).all()

    def __repr__(self):
        return f"<Vessel {self.vessel_name} | {self.voyage_number}>"


class Allocation(db.Model):
    __tablename__ = "allocations"
    id                  = db.Column(db.Integer,       primary_key=True, autoincrement=True)
    sku_id              = db.Column(db.Integer,       db.ForeignKey("skus.id"), nullable=False)
    container_id        = db.Column(db.String(50),    db.ForeignKey("containers.container_id"), nullable=False)
    allocated_ctns      = db.Column(db.Integer,       nullable=False)
    allocated_units     = db.Column(db.Integer,       nullable=True)
    allocated_cbm       = db.Column(db.Numeric(10,6), nullable=True)
    allocated_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    allocated_by        = db.Column(db.String(80),    nullable=True)
    is_active           = db.Column(db.Boolean,       default=True, nullable=False)
    deallocated_at      = db.Column(db.DateTime,      nullable=True)
    deallocated_by      = db.Column(db.String(80),    nullable=True)
    deallocation_reason = db.Column(db.Text,          nullable=True)
    notes               = db.Column(db.Text,          nullable=True)

    @property
    def allocated_qty(self):
        return self.allocated_units or 0

    def __repr__(self):
        return (f"<Allocation SKU#{self.sku_id} -> {self.container_id} "
                f"ctns={self.allocated_ctns} active={self.is_active}>")


class DeallocationReason(db.Model):
    __tablename__ = "deallocation_reasons"
    id          = db.Column(db.Integer,    primary_key=True, autoincrement=True)
    code        = db.Column(db.String(10), unique=True, nullable=False)
    label       = db.Column(db.String(200), nullable=False)
    is_active   = db.Column(db.Boolean,    default=True, nullable=False)
    created_at  = db.Column(db.DateTime,
                             default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<DeallocationReason {self.code} — {self.label}>"


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    timestamp  = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc), nullable=False)
    username   = db.Column(db.String(80),  nullable=False)
    action     = db.Column(db.String(50),  nullable=False)
    table_name = db.Column(db.String(50),  nullable=True)
    record_id  = db.Column(db.String(100), nullable=True)
    detail     = db.Column(db.Text,        nullable=True)

    def __repr__(self):
        return f"<Audit {self.action} on {self.table_name} by {self.username}>"
