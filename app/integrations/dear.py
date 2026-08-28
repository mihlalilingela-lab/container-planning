"""
Dear / Cin7 Core Connector
--------------------------
REST API integration for Dear Inventory / Cin7 Core.

Authentication: Account ID + Application Key (generated in
Dear Settings → Integrations → API)

API Docs: https://dearinventory.docs.apiary.io/

Phase 6 implementation — credentials stored in ERPConnection
table, never hardcoded.
"""

import requests
from datetime import datetime
from app.integrations.base import ERPBase


class DearConnector(ERPBase):

    # Dear API base URL
    BASE_URL = "https://inventory.dearsystems.com/ExternalApi/v2"

    def __init__(self, config: dict):
        super().__init__(config)
        self.account_id  = config.get("account_id", "")
        self.app_key     = config.get("app_key", "")
        self.headers     = {
            "api-auth-accountid":    self.account_id,
            "api-auth-applicationkey": self.app_key,
            "Content-Type":          "application/json",
        }

    def test_connection(self) -> tuple[bool, str]:
        """Test Dear API credentials."""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/ref/supplier",
                headers=self.headers,
                timeout=10
            )
            if resp.status_code == 200:
                return True, "Connection successful"
            elif resp.status_code == 401:
                return False, "Invalid credentials — check Account ID and App Key"
            else:
                return False, f"API returned status {resp.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Cannot reach Dear API — check internet connection"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def fetch_purchase_orders(self, since: datetime = None) -> list[dict]:
        """
        Fetch confirmed POs from Dear.
        Filters to Status=Authorised (confirmed in Dear).
        """
        params = {
            "Status": "Authorised",
            "Limit":  100,
            "Page":   1,
        }
        if since:
            params["UpdatedSince"] = since.strftime("%Y-%m-%dT%H:%M:%S")

        all_pos = []
        while True:
            resp = requests.get(
                f"{self.BASE_URL}/purchase",
                headers=self.headers,
                params=params,
                timeout=30
            )
            resp.raise_for_status()
            data  = resp.json()
            pos   = data.get("PurchaseOrderList", [])
            if not pos:
                break
            all_pos.extend([self.normalise_po(po) for po in pos])
            if len(pos) < params["Limit"]:
                break
            params["Page"] += 1

        return all_pos

    def fetch_purchase_order(self, erp_po_id: str) -> dict:
        """Fetch a single PO by Dear's TaskID."""
        resp = requests.get(
            f"{self.BASE_URL}/purchase",
            headers=self.headers,
            params={"TaskID": erp_po_id},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        pos  = data.get("PurchaseOrderList", [])
        return self.normalise_po(pos[0]) if pos else {}

    def normalise_po(self, raw: dict) -> dict:
        """Map Dear PO fields to app standard fields."""
        lines = raw.get("Lines", []) or []
        skus  = [self.normalise_sku(line) for line in lines]
        return {
            "po_number":     raw.get("OrderNumber", ""),
            "pi_number":     raw.get("BlindReceipt", ""),
            "supplier_name": raw.get("SupplierName", ""),
            "currency":      raw.get("Currency", "USD"),
            "po_status":     self._map_status(raw.get("Status","")),
            "notes":         raw.get("Note", ""),
            "erp_id":        raw.get("TaskID", ""),
            "erp_source":    "Dear/Cin7 Core",
            "skus":          skus,
        }

    def normalise_sku(self, raw: dict) -> dict:
        """Map Dear line item fields to app standard SKU fields."""
        return {
            "jj_sku":          raw.get("SKU", ""),
            "supplier_sku":    raw.get("SupplierSKU", ""),
            "product_name":    raw.get("Name", ""),
            "buying_price":    raw.get("Price", 0),
            "buying_qty":      raw.get("Quantity", 0),
            "hs_code":         raw.get("HSCode", ""),
            "erp_line_id":     raw.get("ID", ""),
        }

    def _map_status(self, dear_status: str) -> str:
        """Map Dear status to app status."""
        mapping = {
            "Draft":       "Active",
            "Authorised":  "Active",
            "OnOrder":     "Active",
            "Receiving":   "Active",
            "Billed":      "Active",
            "Voided":      "Cancelled",
        }
        return mapping.get(dear_status, "Active")
