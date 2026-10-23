"""Connecting an app by pasting a key (WhatsApp, Slack, HubSpot, Shopify).

Each of these has no sign-in redirect at SMB scale — the owner creates a key in
the other app and gives it to us. This module's job is the part that makes that
safe and kind:

* **Check it works before saving.** One harmless read against the other app, so
  a mistyped key is caught on the connect screen and not in the middle of a
  patient reminder at 9am.
* **Validate what we are about to call.** A Shopify store address and a WhatsApp
  phone-number id are interpolated into a URL we then request from the server.
  Left unchecked, a "store address" of `169.254.169.254` or
  `shop.myshopify.com.evil.com` would turn this into a request-forgery hole, so
  both are validated against a strict pattern *before* any request is made.
* **Store only what we know.** Only the whitelisted, non-secret metadata keys
  below are kept; the client can't smuggle arbitrary data into the row.

Nothing here is written to the database — see api/v1/integrations.py.
"""

import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.core.exceptions import ValidationError
from src.core.logging import get_logger

logger = get_logger(__name__)

CREDENTIAL_PROVIDERS = ("whatsapp", "slack", "hubspot", "shopify")

_SHOPIFY_API_VERSION = "2024-10"
_GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
_SHOP_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}\.myshopify\.com$")
_PHONE_NUMBER_ID = re.compile(r"^\d{5,30}$")


@dataclass
class VerifiedConnection:
    """What a successful check produced: the metadata worth keeping, and a
    human label so the card can say *which* account is connected."""

    metadata: dict[str, Any] = field(default_factory=dict)
    account_label: str | None = None


async def _request(method: str, url: str, **kwargs: Any) -> httpx.Response:
    """The one place this module touches the network, so tests can replace it."""
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        return await client.request(method, url, **kwargs)


def normalize_shop_domain(raw: str) -> str:
    """`https://My-Shop.myshopify.com/admin` -> `my-shop.myshopify.com`. Anything
    that isn't a plain myshopify.com store is refused."""
    value = (raw or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/")[0].split("?")[0].split("#")[0]
    if not _SHOP_DOMAIN.match(value):
        raise ValidationError(
            "That doesn't look like a Shopify store address. It should end in .myshopify.com "
            "(for example my-shop.myshopify.com)."
        )
    return value


def _clean(value: Any) -> str:
    return str(value or "").strip()


async def _verify_slack(token: str, metadata: dict[str, Any]) -> VerifiedConnection:
    try:
        response = await _request(
            "POST", "https://slack.com/api/auth.test", headers={"Authorization": f"Bearer {token}"}
        )
    except httpx.HTTPError as exc:
        raise ValidationError("We couldn't reach Slack just now. Please try again in a moment.") from exc
    body = _json(response)
    if not body.get("ok"):
        raise ValidationError(
            "Slack didn't accept that token. Check you copied the whole Bot User OAuth Token "
            "(it starts with xoxb-) and that the app is installed in your workspace."
        )
    team = _clean(body.get("team")) or None
    return VerifiedConnection(metadata={"team": team} if team else {}, account_label=team)


async def _verify_hubspot(token: str, metadata: dict[str, Any]) -> VerifiedConnection:
    try:
        response = await _request(
            "GET",
            "https://api.hubapi.com/crm/v3/objects/contacts",
            params={"limit": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        raise ValidationError("We couldn't reach HubSpot just now. Please try again in a moment.") from exc
    if response.status_code == 401:
        raise ValidationError(
            "HubSpot didn't accept that token. Check you copied the whole private app token."
        )
    if response.status_code == 403:
        raise ValidationError(
            "That token works, but it isn't allowed to read contacts. In HubSpot, give the private "
            "app the contacts read and write permissions, then try again."
        )
    if response.status_code >= 400:
        raise ValidationError("HubSpot didn't accept that connection. Please check the token and try again.")
    return VerifiedConnection(account_label="HubSpot account")


async def _verify_shopify(token: str, metadata: dict[str, Any]) -> VerifiedConnection:
    domain = normalize_shop_domain(_clean(metadata.get("shop_domain")))
    try:
        response = await _request(
            "GET",
            f"https://{domain}/admin/api/{_SHOPIFY_API_VERSION}/shop.json",
            headers={"X-Shopify-Access-Token": token},
        )
    except httpx.HTTPError as exc:
        raise ValidationError("We couldn't reach that Shopify store. Check the address and try again.") from exc
    if response.status_code in (401, 403):
        raise ValidationError(
            "Shopify didn't accept that access token for this store. Check you copied the whole "
            "Admin API access token (it starts with shpat_) and that the app has read access to "
            "orders and products."
        )
    if response.status_code >= 400:
        raise ValidationError("We couldn't find that Shopify store. Check the address and try again.")
    name = _clean((_json(response).get("shop") or {}).get("name")) or domain
    return VerifiedConnection(metadata={"shop_domain": domain}, account_label=name)


async def _verify_whatsapp(token: str, metadata: dict[str, Any]) -> VerifiedConnection:
    phone_number_id = _clean(metadata.get("phone_number_id"))
    if not _PHONE_NUMBER_ID.match(phone_number_id):
        raise ValidationError(
            "The phone number ID should be just digits. It's the long number Meta shows next to "
            "your WhatsApp number — not the phone number itself."
        )
    try:
        response = await _request(
            "GET",
            f"{_GRAPH_API_BASE}/{phone_number_id}",
            params={"fields": "display_phone_number,verified_name"},
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        raise ValidationError("We couldn't reach WhatsApp just now. Please try again in a moment.") from exc
    if response.status_code >= 400:
        raise ValidationError(
            "WhatsApp didn't accept that token and phone number ID together. Check both were copied "
            "from the same WhatsApp app in Meta, and that the token hasn't expired."
        )
    body = _json(response)
    label = _clean(body.get("verified_name")) or _clean(body.get("display_phone_number")) or None
    metadata_kept = {"phone_number_id": phone_number_id}
    if body.get("display_phone_number"):
        metadata_kept["display_phone_number"] = _clean(body["display_phone_number"])
    return VerifiedConnection(metadata=metadata_kept, account_label=label)


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


_VERIFIERS = {
    "slack": _verify_slack,
    "hubspot": _verify_hubspot,
    "shopify": _verify_shopify,
    "whatsapp": _verify_whatsapp,
}


async def verify_credentials(provider: str, token: str, metadata: dict[str, Any] | None) -> VerifiedConnection:
    """Raises ValidationError (plain-language, safe to show) if the key is wrong
    or the other app can't be reached; otherwise returns what to store."""
    token = _clean(token)
    if not token:
        raise ValidationError("Please paste the key or token first.")
    if len(token) > 2000:
        raise ValidationError("That key looks too long to be right. Please check what you pasted.")
    verifier = _VERIFIERS.get(provider)
    if verifier is None:
        raise ValidationError("That app can't be connected with a key.")
    return await verifier(token, metadata or {})
