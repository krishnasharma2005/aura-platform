import {
  CalendarDays,
  Mail,
  MessageCircle,
  Slack,
  Building2,
  ShoppingBag,
  type LucideIcon,
} from "lucide-react";

export interface IntegrationDefinition {
  provider: string;
  displayName: string;
  icon: LucideIcon;
  canDo: string[];
  cannotDo: string[];
  availableNow: boolean;
}

export const INTEGRATIONS: IntegrationDefinition[] = [
  {
    provider: "google_calendar",
    displayName: "Calendar",
    icon: CalendarDays,
    canDo: [
      "See your open and busy times so it can offer real appointment slots",
      "Create, move, or cancel bookings your agents make on your behalf",
    ],
    cannotDo: [
      "Delete events it didn't create without asking you first",
      "See calendars you don't explicitly connect",
    ],
    availableNow: true,
  },
  {
    provider: "gmail",
    displayName: "Gmail",
    icon: Mail,
    canDo: [
      "Read incoming messages so agents can reply to customers",
      "Draft or send replies from the inbox you connect",
    ],
    cannotDo: [
      "Access other Google services (Drive, Photos, etc.)",
      "Send anything without a reply pattern you've approved",
    ],
    availableNow: true,
  },
  {
    provider: "whatsapp",
    displayName: "WhatsApp",
    icon: MessageCircle,
    canDo: [
      "Receive and reply to messages sent to your business number",
      "Log every conversation to Activity so you can review it",
    ],
    cannotDo: [
      "Message your personal contacts or start unsolicited conversations",
      "Access your personal WhatsApp, only your Business number",
    ],
    availableNow: true,
  },
  {
    provider: "slack",
    displayName: "Slack",
    icon: Slack,
    canDo: [
      "Post updates and hand-off notices to a channel you choose",
      "Notify your team when an agent needs a human decision",
    ],
    cannotDo: [
      "Read channels you haven't shared with it",
      "Post to channels outside the one you connect",
    ],
    availableNow: true,
  },
  {
    provider: "hubspot",
    displayName: "HubSpot",
    icon: Building2,
    canDo: [
      "Look up and update contact and deal records agents reference",
      "Log new leads and conversation summaries to your CRM",
    ],
    cannotDo: [
      "Delete contacts, deals, or historical records",
      "Change your HubSpot account settings or billing",
    ],
    availableNow: false,
  },
  {
    provider: "shopify",
    displayName: "Shopify",
    icon: ShoppingBag,
    canDo: [
      "Read order, inventory, and sales data for your store",
      "Flag trends like low stock or slow-moving products",
    ],
    cannotDo: [
      "Change prices, issue refunds, or edit your storefront",
      "Access customer payment details",
    ],
    availableNow: false,
  },
];
