from datetime import date

def calculate_sku_status(po_status: str, cargo_ready_date,
                          allocated_qty: int, total_order_qty: int) -> str:
    """
    Computes SKU status from inputs. Never set manually.

    Priority order:
    1. PO-level blocks (Cancelled / On Hold)
    2. Allocation progress
    3. CRD-based readiness
    """
    if po_status == "Cancelled":
        return "Cancelled"
    if po_status == "On Hold":
        return "On Hold"

    if total_order_qty > 0:
        if allocated_qty >= total_order_qty:
            return "Fully Allocated"
        if allocated_qty > 0:
            return "Partially Allocated"

    if not cargo_ready_date:
        return "Pending Date"

    today = date.today()
    if isinstance(cargo_ready_date, str):
        from datetime import datetime
        cargo_ready_date = datetime.strptime(cargo_ready_date, "%Y-%m-%d").date()

    return "Ready for Allocation" if cargo_ready_date <= today else "Awaiting Production"


def auto_acknowledge_if_no_variance(sku):
    """
    Option B — Auto-acknowledge CI when it exactly matches the order.

    Rules:
    - CI price and CI qty must both be present
    - CI price must equal buying price exactly
    - CI qty must equal buying qty exactly
    - If all match → ci_variance_acknowledged set to True automatically
    - If any differ → leave for manual acknowledgement
    - If CI not yet entered → leave as is
    """
    if sku.ci_variance_acknowledged:
        return  # Already acknowledged — nothing to do

    if sku.ci_price is None and sku.ci_qty is None:
        return  # CI not yet received — nothing to do

    price_matches = (
        sku.ci_price is not None and
        sku.buying_price is not None and
        round(float(sku.ci_price), 4) == round(float(sku.buying_price), 4)
    )
    qty_matches = (
        sku.ci_qty is not None and
        sku.ci_qty == (sku.buying_qty or 0)
    )

    # Only auto-acknowledge if BOTH price and qty match exactly
    if price_matches and qty_matches:
        sku.ci_variance_acknowledged = True
        # Update working qty to CI qty
        sku.total_order_qty = sku.ci_qty


def refresh_sku_statuses(po):
    """
    Recomputes status for all SKUs under a PO.

    Cascade rules:
    - PO On Hold / Cancelled → all SKUs reflect that status
    - PO returns to Active → each SKU recomputed individually
    - SKU status changes never cascade back up to PO status

    Also runs auto-acknowledgement for zero-variance CI.
    """
    for sku in po.skus:
        # Auto-acknowledge if CI matches PI exactly (Option B)
        auto_acknowledge_if_no_variance(sku)

        sku.sku_status = calculate_sku_status(
            po_status        = po.po_status,
            cargo_ready_date = sku.cargo_ready_date,
            allocated_qty    = sku.allocated_qty or 0,
            total_order_qty  = sku.total_order_qty or 0,
        )


def check_sku_allocation_eligibility(sku, container=None):
    """
    Returns (allowed: bool, warning: str | None, block: str | None)
    """
    po = sku.purchase_order

    if po.po_status == "Cancelled":
        return False, None, f"PO {po.po_number} is Cancelled — allocation not permitted."
    if po.po_status == "On Hold":
        return False, None, f"PO {po.po_number} is On Hold — allocation not permitted."
    if sku.sku_status == "Cancelled":
        return False, None, f"SKU {sku.jj_sku} is Cancelled."
    if sku.sku_status == "On Hold":
        return False, None, f"SKU {sku.jj_sku} is On Hold."
    if sku.pending_qty <= 0:
        return False, None, f"SKU {sku.jj_sku} has no pending quantity to allocate."
    if container and container.status in ("Shipped", "Closed"):
        return False, None, (f"Container {container.container_id} is "
                             f"{container.status} — cannot allocate.")

    warning = None
    if not sku.ci_variance_acknowledged:
        if sku.ci_qty is not None or sku.ci_price is not None:
            warning = (
                f"SKU {sku.jj_sku} has an unacknowledged CI variance. "
                f"Allocation is permitted at planning stage but this "
                f"container cannot be confirmed until CI is acknowledged."
            )
        else:
            warning = (
                f"SKU {sku.jj_sku} has no CI receipt yet. "
                f"Allocation is permitted at planning stage but this "
                f"container cannot be confirmed until CI is acknowledged."
            )

    return True, warning, None


def check_container_confirmation_eligibility(container):
    """
    Hard block: container cannot be confirmed/shipped/closed
    until all allocated SKUs have acknowledged CI.
    """
    blocking = []
    for allocation in container.active_allocations:
        sku = allocation.sku
        if not sku.ci_variance_acknowledged:
            blocking.append({
                "jj_sku":       sku.jj_sku or "—",
                "product_name": sku.product_name,
                "po_number":    sku.po_number,
                "reason":       "CI not yet acknowledged",
            })
    return len(blocking) == 0, blocking
