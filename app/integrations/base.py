"""
ERP Integration Base Class
--------------------------
All ERP integrations inherit from ERPBase.
Implement the required methods for each ERP connector.

Supported ERPs (Phase 6):
- Dear / Cin7 Core  → DearConnector
- Unleashed         → UnleashedConnector
- MYOB              → MYOBConnector
- SAP Business One  → SAPConnector
- NetSuite          → NetSuiteConnector
- Custom / Generic  → GenericAPIConnector
"""

from abc import ABC, abstractmethod
from datetime import datetime


class ERPBase(ABC):
    """
    Abstract base class for all ERP integrations.
    Every connector must implement these methods.
    """

    def __init__(self, config: dict):
        """
        config dict contains all credentials and settings
        for this ERP connection. Loaded from ERPConnection
        record in the database.
        """
        self.config     = config
        self.name       = config.get("erp_name", "Unknown ERP")
        self.base_url   = config.get("base_url", "")
        self.connected  = False
        self.last_sync  = None

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """
        Test the connection to the ERP.
        Returns (success: bool, message: str)
        """
        pass

    @abstractmethod
    def fetch_purchase_orders(self, since: datetime = None) -> list[dict]:
        """
        Fetch purchase orders from the ERP.
        Returns list of standardised PO dicts.
        since: only fetch POs updated after this datetime (optional)
        """
        pass

    @abstractmethod
    def fetch_purchase_order(self, erp_po_id: str) -> dict:
        """
        Fetch a single PO by ERP's own ID.
        Returns standardised PO dict.
        """
        pass

    def normalise_po(self, raw: dict) -> dict:
        """
        Convert ERP-specific PO format to app's standard format.
        Override in each connector.
        Standard format matches CSV import columns.
        """
        return raw

    def normalise_sku(self, raw: dict) -> dict:
        """
        Convert ERP-specific line item to app's standard SKU format.
        Override in each connector.
        """
        return raw


# ── Standard field mapping reference ─────────────────────────────────────────
# ERP data maps to these app fields:
STANDARD_PO_FIELDS = {
    "po_number":      "Your app PO reference",
    "pi_number":      "Proforma invoice number",
    "supplier_name":  "Supplier / vendor name",
    "currency":       "Currency code e.g. USD",
    "po_status":      "Active | On Hold | Cancelled",
    "notes":          "Free text notes",
}

STANDARD_SKU_FIELDS = {
    "jj_sku":          "Your internal SKU code",
    "supplier_sku":    "Supplier product code",
    "product_name":    "Product description",
    "shipment_type":   "FCL | LCL | BCN",
    "hs_code":         "Harmonised tariff code",
    "buying_price":    "Unit price",
    "buying_qty":      "Quantity ordered",
    "outer_carton_qty":"Units per carton",
    "length_cm":       "Carton length cm",
    "width_cm":        "Carton width cm",
    "height_cm":       "Carton height cm",
    "weight_kg":       "Carton weight kg",
    "cargo_ready_date":"Expected ready date YYYY-MM-DD",
}
