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
    # 1. PO-level blocks take absolute priority
    if po_status == "Cancelled":
        return "Cancelled"
    if po_status == "On Hold":
        return "On Hold"

    # 2. Allocation progress
    if total_order_qty > 0:
        if allocated_qty >= total_order_qty:
            return "Fully Allocated"
        if allocated_qty > 0:
            return "Partially Allocated"

    # 3. CRD-based readiness
    if not cargo_ready_date:
        return "Pending Date"

    today = date.today()
    if isinstance(cargo_ready_date, str):
        from datetime import datetime
        cargo_ready_date = datetime.strptime(cargo_ready_date, "%Y-%m-%d").date()

    return "Ready for Allocation" if cargo_ready_date <= today else "Awaiting Production"


def refresh_sku_statuses(po):
    """
    Recomputes status for all SKUs under a PO.

    Cascade rules:
    - PO On Hold / Cancelled → all SKUs reflect that status
    - PO returns to Active → each SKU recomputed individually from
      its own CRD and allocation data (not blanket reset)
    - SKU status changes never cascade back up to PO status
    """
    for sku in po.skus:
        sku.sku_status = calculate_sku_status(
            po_status        = po.po_status,
            cargo_ready_date = sku.cargo_ready_date,
            allocated_qty    = sku.allocated_qty or 0,
            total_order_qty  = sku.total_order_qty or 0,
        )


def check_sku_allocation_eligibility(sku, container=None):
    """
    Returns (allowed: bool, warning: str | None, block: str | None)

    allowed  — True if allocation can proceed
    warning  — shown to user but does not block (CI not yet acknowledged)
    block    — shown to user and blocks the action entirely
    """
    po = sku.purchase_order

    # Hard blocks
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
        return False, None, f"Container {container.container_id} is {container.status} — cannot allocate."

    # Warnings (allowed but flagged)
    warning = None
    if not sku.ci_variance_acknowledged:
        if sku.ci_qty is not None or sku.ci_price is not None:
            # CI has been entered but not acknowledged
            warning = (
                f"SKU {sku.jj_sku} has an unacknowledged CI variance. "
                f"Allocation is permitted at planning stage but this container "
                f"cannot be confirmed until CI is acknowledged."
            )
        else:
            # CI not yet received at all
            warning = (
                f"SKU {sku.jj_sku} has no CI receipt yet. "
                f"Allocation is permitted at planning stage but this container "
                f"cannot be confirmed until CI is acknowledged."
            )

    return True, warning, None


def check_container_confirmation_eligibility(container):
    """
    Hard block: container cannot be confirmed/shipped/closed
    until all allocated SKUs have acknowledged CI.

    Returns (allowed: bool, blocking_skus: list)
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
