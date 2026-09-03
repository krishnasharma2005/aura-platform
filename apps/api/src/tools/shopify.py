"""Shopify Admin API tool — used by the E-Commerce agent for order tracking,
inventory alerts, and sales summaries.

NEEDS FOUNDER INPUT: each customer's Shopify Admin API access token (from a
custom app on their store) plus their *.myshopify.com domain, stored in
metadata_json. See docs/needs-founder-input.md.
"""

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.tools.base import Tool, ToolResult
from src.tools.oauth_common import get_access_token, get_metadata, require_integration

SHOPIFY_PROVIDER = "shopify"
SHOPIFY_API_VERSION = "2024-10"


class ShopifyTool(Tool):
    name = "shopify"
    description = "Look up order status, inventory levels, or a sales summary from the business's Shopify store."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["get_order", "list_low_inventory", "sales_summary"]},
            "order_id": {"type": "string", "description": "Order id or order number (for get_order)."},
        },
        "required": ["action"],
    }

    async def execute(self, db: AsyncSession, org_id: uuid.UUID, **kwargs: Any) -> ToolResult:
        integration = await require_integration(db, org_id, SHOPIFY_PROVIDER)
        shop_domain = get_metadata(integration).get("shop_domain")
        if not shop_domain:
            return ToolResult(success=False, message="Shopify isn't fully connected yet — a store domain is missing.")

        headers = {"X-Shopify-Access-Token": get_access_token(integration)}
        base_url = f"https://{shop_domain}/admin/api/{SHOPIFY_API_VERSION}"
        action = kwargs.get("action")
        # Not schema-required (only get_order needs it), so check it explicitly.
        if action == "get_order" and not kwargs.get("order_id"):
            return ToolResult(success=False, message="I need an order number to look that up.")

        async with httpx.AsyncClient(timeout=10) as client:
            if action == "get_order":
                response = await client.get(f"{base_url}/orders/{kwargs['order_id']}.json", headers=headers)
            elif action == "list_low_inventory":
                response = await client.get(f"{base_url}/inventory_levels.json", headers=headers, params={"limit": 50})
            elif action == "sales_summary":
                response = await client.get(f"{base_url}/orders.json", headers=headers, params={"status": "any", "limit": 50})
            else:
                return ToolResult(success=False, message=f"Unknown Shopify action: {action}")

        if response.status_code >= 400:
            return ToolResult(success=False, message="We couldn't reach Shopify just now. Please try again.")
        return ToolResult(success=True, data=response.json())
