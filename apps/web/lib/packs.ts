import { Building2, Package, type LucideIcon } from "lucide-react";

/**
 * Unlike lib/integrations.ts, the pack catalog's real content (name,
 * description, capability_requirements) comes entirely from the backend —
 * see agents/runtime/pack_loader.py. This file only supplies what the API
 * doesn't: an icon per category, keyed loosely so a new pack category still
 * renders something reasonable instead of nothing.
 */
const CATEGORY_ICONS: Record<string, LucideIcon> = {
  real_estate: Building2,
};

export function iconForPackCategory(category: string): LucideIcon {
  return CATEGORY_ICONS[category] ?? Package;
}
