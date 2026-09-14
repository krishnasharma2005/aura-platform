"""Maps tool name -> Tool instance. The agent runtime looks tools up here."""

from src.tools.base import Tool
from src.tools.calendar import CalendarTool
from src.tools.delegate import DelegateTool
from src.tools.gmail import GmailTool
from src.tools.hubspot import HubSpotTool
from src.tools.shopify import ShopifyTool
from src.tools.slack import SlackTool
from src.tools.whatsapp import WhatsAppTool

TOOL_REGISTRY: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        CalendarTool(),
        GmailTool(),
        WhatsAppTool(),
        SlackTool(),
        HubSpotTool(),
        ShopifyTool(),
        DelegateTool(),
    )
}


def get_tool(name: str) -> Tool | None:
    return TOOL_REGISTRY.get(name)
