import math
from decimal import Decimal

def calculate_volumetric_cbm(length_cm, width_cm, height_cm):
    """
    CBM per single carton: (L x W x H) / 1,000,000
    Returns float or None if any dimension is missing.
    """
    if length_cm and width_cm and height_cm:
        return (float(length_cm) * float(width_cm) * float(height_cm)) / 1_000_000
    return None


def calculate_number_of_cartons(total_order_qty, outer_carton_qty):
    """
    Total cartons = ceil(total_order_qty / outer_carton_qty)
    """
    if not outer_carton_qty or outer_carton_qty == 0:
        return 0
    return math.ceil((total_order_qty or 0) / outer_carton_qty)


def calculate_total_cbm(length_cm, width_cm, height_cm, total_order_qty, outer_carton_qty):
    """
    Total CBM = volumetric_cbm x number_of_cartons
    This is the primary CBM formula used throughout the application.
    """
    vol = calculate_volumetric_cbm(length_cm, width_cm, height_cm)
    cartons = calculate_number_of_cartons(total_order_qty, outer_carton_qty)
    if vol is not None and cartons:
        return round(vol * cartons, 6)
    return None


def calculate_allocated_cbm(sku, allocated_qty):
    """
    CBM for a specific allocation quantity.
    Prorates total CBM by the fraction of qty being allocated.
    """
    if not sku.total_order_qty or sku.total_order_qty == 0:
        return None
    total = sku.total_cbm
    if total is None:
        return None
    return round(total * (allocated_qty / sku.total_order_qty), 6)
