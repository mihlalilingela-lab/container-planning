"""
Generic API Connector
---------------------
For ERPs without a dedicated connector.
User configures field mappings via the admin panel.

Supports:
- REST APIs returning JSON
- Basic Auth, API Key, Bearer Token authentication
- Custom field mapping per ERP
"""

import requests
from app.integrations.base import ERPBase


class GenericAPIConnector(ERPBase):

    def __init__(self, config: dict):
        super().__init__(config)
        self.auth_type    = config.get("auth_type", "api_key")
        self.api_key      = config.get("api_key", "")
        self.api_key_header = config.get("api_key_header", "X-API-Key")
        self.bearer_token = config.get("bearer_token", "")
        self.username     = config.get("username", "")
        self.password     = config.get("password", "")
        self.po_endpoint  = config.get("po_endpoint", "")
        self.field_map    = config.get("field_map", {})

    def _get_headers(self) -> dict:
        if self.auth_type == "api_key":
            return {self.api_key_header: self.api_key,
                    "Content-Type": "application/json"}
        elif self.auth_type == "bearer":
            return {"Authorization": f"Bearer {self.bearer_token}",
                    "Content-Type": "application/json"}
        return {"Content-Type": "application/json"}

    def _get_auth(self):
        if self.auth_type == "basic":
            return (self.username, self.password)
        return None

    def test_connection(self) -> tuple[bool, str]:
        try:
            resp = requests.get(
                self.po_endpoint,
                headers=self._get_headers(),
                auth=self._get_auth(),
                timeout=10
            )
            if resp.status_code in (200, 201):
                return True, "Connection successful"
            return False, f"API returned status {resp.status_code}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def fetch_purchase_orders(self, since=None) -> list[dict]:
        resp = requests.get(
            self.po_endpoint,
            headers=self._get_headers(),
            auth=self._get_auth(),
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        # Handle both list response and nested response
        if isinstance(data, list):
            raw_pos = data
        else:
            # Try common wrapper keys
            for key in ["data","results","orders","purchase_orders","items"]:
                if key in data:
                    raw_pos = data[key]
                    break
            else:
                raw_pos = []
        return [self.normalise_po(po) for po in raw_pos]

    def fetch_purchase_order(self, erp_po_id: str) -> dict:
        resp = requests.get(
            f"{self.po_endpoint}/{erp_po_id}",
            headers=self._get_headers(),
            auth=self._get_auth(),
            timeout=15
        )
        resp.raise_for_status()
        return self.normalise_po(resp.json())

    def normalise_po(self, raw: dict) -> dict:
        """Apply user-configured field mapping."""
        fm = self.field_map
        skus_key = fm.get("skus_key", "lines")
        raw_skus = raw.get(skus_key, [])
        return {
            "po_number":     raw.get(fm.get("po_number","po_number"),""),
            "pi_number":     raw.get(fm.get("pi_number","pi_number"),""),
            "supplier_name": raw.get(fm.get("supplier_name","supplier_name"),""),
            "currency":      raw.get(fm.get("currency","currency"),"USD"),
            "po_status":     "Active",
            "notes":         raw.get(fm.get("notes","notes"),""),
            "erp_source":    self.name,
            "skus":          [self.normalise_sku(s) for s in raw_skus],
        }

    def normalise_sku(self, raw: dict) -> dict:
        fm = self.field_map.get("sku_fields", {})
        return {
            "jj_sku":       raw.get(fm.get("jj_sku","sku"),""),
            "supplier_sku": raw.get(fm.get("supplier_sku","supplier_sku"),""),
            "product_name": raw.get(fm.get("product_name","name"),""),
            "buying_price": raw.get(fm.get("buying_price","price"),0),
            "buying_qty":   raw.get(fm.get("buying_qty","quantity"),0),
            "hs_code":      raw.get(fm.get("hs_code","hs_code"),""),
        }
