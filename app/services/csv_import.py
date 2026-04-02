import csv
import io
from datetime import datetime
from app import db
from app.models.supply_chain import PurchaseOrder, SKU
from app.services.sku_status import refresh_sku_statuses

def parse_date(val):
    if not val or str(val).strip() == "":
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    return None

def parse_decimal(val):
    if not val or str(val).strip() == "":
        return None
    try:
        return float(str(val).replace(",", "").strip())
    except ValueError:
        return None

def parse_int(val):
    if not val or str(val).strip() == "":
        return None
    try:
        return int(float(str(val).replace(",", "").strip()))
    except ValueError:
        return None

def clean_headers(raw_headers):
    cleaned = []
    for h in raw_headers:
        h = h.strip().lower()
        h = h.split("(")[0].strip()
        h = h.replace(" ", "_").replace("-", "_")
        cleaned.append(h)
    return cleaned

def import_csv(file_stream, imported_by="system"):
    results = {
        "pos_created":    0,
        "pos_updated":    0,
        "skus_created":   0,
        "skus_updated":   0,
        "errors":         [],
        "rows_processed": 0,
    }
    try:
        content = file_stream.read().decode("utf-8-sig")
        reader  = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            results["errors"].append("CSV file is empty or has no headers.")
            return results

        raw_headers = list(reader.fieldnames)
        clean       = clean_headers(raw_headers)
        header_map  = dict(zip(raw_headers, clean))

        for i, raw_row in enumerate(reader, start=2):
            row = {header_map.get(k, k): str(v).strip() if v is not None else ""
                   for k, v in raw_row.items()}
            results["rows_processed"] += 1

            po_number = row.get("po_number", "").strip()
            if not po_number:
                results["errors"].append(f"Row {i}: Missing po_number — skipped.")
                continue

            # Skip example row
            if "EXAMPLE" in po_number.upper() or "DO-NOT-IMPORT" in po_number.upper():
                results["rows_processed"] -= 1
                continue

            # ── Upsert PO ─────────────────────────────────────────────────
            po = db.session.get(PurchaseOrder, po_number)
            if po is None:
                po = PurchaseOrder(
                    po_number     = po_number,
                    supplier_name = row.get("supplier_name","Unknown") or "Unknown"
                )
                db.session.add(po)
                results["pos_created"] += 1
            else:
                results["pos_updated"] += 1

            if row.get("supplier_name"): po.supplier_name = row["supplier_name"]
            if row.get("pi_number"):     po.pi_number     = row["pi_number"]
            if row.get("ci_number"):     po.ci_number     = row["ci_number"]
            if row.get("currency"):      po.currency      = row["currency"]
            if row.get("notes"):         po.notes         = row["notes"]
            po.created_by = imported_by

            if row.get("po_status") in ("Active","On Hold","Cancelled"):
                po.po_status = row["po_status"]

            # ── Upsert SKU ─────────────────────────────────────────────────
            product_name = row.get("product_name","").strip()
            if not product_name:
                db.session.flush()
                continue

            jj_sku       = row.get("jj_sku","").strip()
            supplier_sku = row.get("supplier_sku","").strip()

            sku = None
            if jj_sku:
                sku = SKU.query.filter_by(
                    po_number=po_number, jj_sku=jj_sku).first()

            if sku and supplier_sku and sku.supplier_sku and \
               sku.supplier_sku != supplier_sku:
                results["errors"].append(
                    f"Row {i}: Warning — JJ SKU {jj_sku} matched but "
                    f"supplier SKU differs (existing: {sku.supplier_sku}, "
                    f"imported: {supplier_sku}). Updated — please verify."
                )

            if sku is None:
                sku = SKU(po_number=po_number, product_name=product_name)
                db.session.add(sku)
                results["skus_created"] += 1
            else:
                results["skus_updated"] += 1

            sku.product_name = product_name
            if jj_sku:        sku.jj_sku        = jj_sku
            if supplier_sku:  sku.supplier_sku   = supplier_sku
            if row.get("shipment_type"):
                sku.shipment_type = row["shipment_type"]
            # HS code now at SKU level
            if row.get("hs_code"):
                sku.hs_code = row["hs_code"]

            buying_price = (row.get("buying_price") or
                            row.get("pi_unit_price") or "")
            if buying_price:
                sku.buying_price = parse_decimal(buying_price)

            buying_qty_raw = (row.get("buying_qty") or
                              row.get("pi_qty") or
                              row.get("total_order_qty") or "")
            if buying_qty_raw:
                bq = parse_int(buying_qty_raw) or 0
                sku.buying_qty = bq
                if sku.allocated_qty == 0:
                    sku.total_order_qty = bq

            if row.get("ci_price"):
                sku.ci_price = parse_decimal(row["ci_price"])
            if row.get("ci_qty"):
                sku.ci_qty = parse_int(row["ci_qty"])
            if row.get("cargo_ready_date"):
                sku.cargo_ready_date = parse_date(row["cargo_ready_date"])
            if row.get("outer_carton_qty"):
                sku.outer_carton_qty = parse_int(row["outer_carton_qty"])
            if row.get("length_cm"):  sku.length_cm = parse_decimal(row["length_cm"])
            if row.get("width_cm"):   sku.width_cm  = parse_decimal(row["width_cm"])
            if row.get("height_cm"):  sku.height_cm = parse_decimal(row["height_cm"])
            if row.get("weight_kg"):  sku.weight_kg = parse_decimal(row["weight_kg"])

            # SKU status always computed — never from CSV
            db.session.flush()
            refresh_sku_statuses(po)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        results["errors"].append(f"Import failed: {str(e)}")

    return results
