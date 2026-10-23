import {
  CalendarDays,
  Mail,
  MessageCircle,
  Slack,
  Building2,
  ShoppingBag,
  type LucideIcon,
} from "lucide-react";

/** One box on a "connect with a key" form. */
export interface CredentialField {
  name: string;
  label: string;
  placeholder: string;
  /** Rendered as a password field and never echoed back. */
  secret?: boolean;
  /** Where to find it in the other app, in plain words. */
  help: string;
}

/** For apps with no sign-in redirect: the owner creates a key in the other app and pastes it here. */
export interface CredentialForm {
  intro: string;
  /** Which field is the secret (the rest are saved as plain details like a store address). */
  tokenField: string;
  fields: CredentialField[];
}

export interface IntegrationDefinition {
  provider: string;
  displayName: string;
  icon: LucideIcon;
  canDo: string[];
  cannotDo: string[];
  availableNow: boolean;
  credentials?: CredentialForm;
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
    credentials: {
      intro: "Connect the WhatsApp Business number your customers message. You'll copy two things from your Meta developer account.",
      tokenField: "access_token",
      fields: [
        {
          name: "phone_number_id",
          label: "Phone number ID",
          placeholder: "109876543210987",
          help: "In Meta's WhatsApp setup it's the long number shown next to your business number. It is not the phone number itself.",
        },
        {
          name: "access_token",
          label: "Access token",
          placeholder: "EAAG…",
          secret: true,
          help: "Use a permanent token from a system user. A temporary token stops working after 24 hours.",
        },
      ],
    },
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
    credentials: {
      intro: "Let your agents post updates to your Slack workspace.",
      tokenField: "access_token",
      fields: [
        {
          name: "access_token",
          label: "Bot token",
          placeholder: "xoxb-…",
          secret: true,
          help: "Create a Slack app, give it the chat:write permission, install it to your workspace, then copy the Bot User OAuth Token.",
        },
      ],
    },
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
    availableNow: true,
    credentials: {
      intro: "Let your agents look up and update contacts and deals in your HubSpot CRM.",
      tokenField: "access_token",
      fields: [
        {
          name: "access_token",
          label: "Private app token",
          placeholder: "pat-…",
          secret: true,
          help: "In HubSpot, create a private app with read and write access to contacts and deals, then copy its token.",
        },
      ],
    },
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
    availableNow: true,
    credentials: {
      intro: "Let your agents look up orders, stock levels and sales from your store. They can read, never change.",
      tokenField: "access_token",
      fields: [
        {
          name: "shop_domain",
          label: "Store address",
          placeholder: "my-shop.myshopify.com",
          help: "The address ending in .myshopify.com, shown in your Shopify admin's settings.",
        },
        {
          name: "access_token",
          label: "Admin API access token",
          placeholder: "shpat_…",
          secret: true,
          help: "In your Shopify admin, create a custom app with read access to orders, products and inventory, install it, then reveal its Admin API access token.",
        },
      ],
    },
  },
];
