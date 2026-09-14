/**
 * Typed shape of the AURA backend API contract.
 *
 * The backend is being built in parallel against this shape. Where a field
 * isn't strictly guaranteed yet (marked below), the UI treats it as
 * optional and degrades gracefully rather than crashing.
 */

export type AgentSlug =
  | "receptionist"
  | "sales"
  | "marketing"
  | "executive-assistant"
  | "support"
  | "ecommerce"
  | "chief-of-staff";

// ---- Auth ----------------------------------------------------------------

export interface SignupRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
}

// ---- Organizations ---------------------------------------------------------

export interface CreateOrganizationRequest {
  name: string;
  business_type: string;
  primary_goal?: string;
}

export interface Organization {
  id: string;
  name: string;
  business_type: string;
  created_at: string;
  /** The opaque id website chat is addressed by — not the internal id. */
  public_id?: string | null;
  public_chat_enabled?: boolean;
}

export type OrgRole = "owner" | "admin" | "member";

export interface OrganizationMember {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  role: OrgRole;
  joined_at: string;
}

// ---- Agents ----------------------------------------------------------------

export interface AgentConfig {
  slug: AgentSlug | string;
  display_name: string;
  /**
   * The only human-readable field the API exposes for an agent. The prompt
   * and tool allow-list are deliberately not published, so `description` is
   * what any UI shows.
   */
  description?: string;
}

// ---- Approvals -----------------------------------------------------------

/**
 * A consequential action an agent has queued instead of performing. The
 * compact form arrives attached to a chat response; the full form comes from
 * the approvals endpoints.
 */
export interface PendingApproval {
  id: string;
  /** The connected account involved, e.g. "gmail", "google_calendar". */
  tool: string;
  /** Machine name of the operation, e.g. "cancel_event". */
  action: string;
  /** Plain-language description written for the owner. */
  summary: string;
}

export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface Approval extends PendingApproval {
  agent_slug: string;
  agent_display_name: string;
  /** Optional extra context: who, when, which record. */
  details?: string | null;
  conversation_id?: string | null;
  status: ApprovalStatus;
  /** What happened after a decision, in plain language. */
  result_message?: string | null;
  created_at: string;
  decided_at?: string | null;
}

export interface ToolCall {
  name: string;
  label?: string;
  status?: "success" | "pending" | "error";
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  tool_calls?: ToolCall[];
  /** Rendered inline, directly under the message that requested them. */
  pending_approvals?: PendingApproval[];
}

export interface ChatRequest {
  conversation_id?: string;
  message: string;
  /**
   * Scripted-flow-only (see ChatOption below). `node_id` is the menu node the
   * caller is replying from; `option_id` is the button that was picked. Both
   * omitted for a normal typed message or when fetching the opening menu.
   */
  node_id?: string;
  option_id?: string;
}

/** One selectable reply on a scripted (predefined, menu-driven) turn. */
export interface ChatOption {
  id: string;
  label: string;
}

export interface ChatResponse {
  response: string;
  conversation_id: string;
  tool_calls?: ToolCall[];
  /** Actions the agent wants to take but is holding until the owner decides. */
  pending_approvals?: PendingApproval[];
  /**
   * Present only while an agent is running the temporary predefined menu flow
   * instead of the real AI pipeline (see the Receptionist). Empty/absent for
   * a normal free-form response — that's the signal to fall back to the text
   * composer instead of rendering buttons.
   */
  options?: ChatOption[];
  node_id?: string | null;
}

export interface Conversation {
  id: string;
  agent_slug: string;
  messages: ChatMessage[];
}

// ---- Conversations (list, transcript, takeover) ---------------------------

/** Who's currently answering a thread: "agent" (AURA replies automatically)
 * or "human" (an owner/admin has taken over — see the "Take over" action). */
export type ConversationMode = "agent" | "human";

export interface ConversationContact {
  id: string;
  name?: string | null;
  phone?: string | null;
  email?: string | null;
}

export interface ConversationSummary {
  id: string;
  agent_slug: string;
  agent_display_name: string;
  channel: string;
  status: "active" | "closed";
  mode: ConversationMode;
  contact?: ConversationContact | null;
  message_count: number;
  preview?: string | null;
  started_at: string;
  last_message_at: string;
}

export interface ConversationTurn {
  role: "user" | "assistant" | "human" | string;
  content: string;
  tool_calls?: unknown[];
  created_at?: string | null;
}

// ---- Knowledge ---------------------------------------------------------------

export type DocumentStatus = "processing" | "ready" | "error";

export interface KnowledgeDocument {
  id: string;
  filename: string;
  status: DocumentStatus;
  uploaded_at: string;
  size_bytes?: number;
}

export interface KnowledgeUploadResponse {
  document: KnowledgeDocument;
}

export interface KnowledgeSearchResult {
  id: string;
  document_filename: string;
  snippet: string;
  score?: number;
}

export interface KnowledgeSearchResponse {
  results: KnowledgeSearchResult[];
}

// ---- Integrations --------------------------------------------------------

export type IntegrationProvider =
  | "google_calendar"
  | "gmail"
  | "whatsapp"
  | "slack"
  | "hubspot"
  | "shopify";

export type IntegrationStatus = "connected" | "not_connected" | "coming_soon" | "error";

export interface Integration {
  provider: IntegrationProvider | string;
  display_name: string;
  status: IntegrationStatus;
  connected_at?: string;
  account_label?: string;
}

export interface ConnectIntegrationResponse {
  status: IntegrationStatus;
  redirect_url?: string;
}

// ---- Activity / Audit log ------------------------------------------------

export interface AuditLogEntry {
  id: string;
  agent_slug: string;
  action: string;
  summary?: string;
  customer_name?: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

// ---- Generic API envelope -------------------------------------------------

export interface ApiError {
  message: string;
  status?: number;
}

// ---- Analytics -----------------------------------------------------------

/** One day of the trend series. `date` is a plain `YYYY-MM-DD` calendar day. */
export interface AnalyticsDailyPoint {
  date: string;
  conversations: number;
  messages: number;
}

export interface AnalyticsAgentBreakdown {
  agent_slug: string;
  display_name: string;
  conversations: number;
  messages: number;
  actions: number;
}

export interface AnalyticsSummary {
  range_days: number;
  conversations_handled: number;
  messages_sent: number;
  /** Everything an agent actually *did* — booked, rebooked, chased, replied. */
  actions_taken: number;
  approvals_pending: number;
  approvals_approved: number;
  by_agent: AnalyticsAgentBreakdown[];
  daily: AnalyticsDailyPoint[];
  /**
   * Not in the agreed contract — the UI derives both of these from
   * `actions_taken` today (see `lib/analytics.ts`). Declared optional so that
   * the moment the backend can count real bookings and real recovered
   * revenue, it can send them and the estimate turns into a measurement with
   * no frontend change.
   */
  bookings_made?: number;
  /** Whole US dollars, not cents. */
  revenue_recovered?: number;
}

// ---- Business context ------------------------------------------------------

/**
 * The org's own business profile, grounding every agent's prompt in facts
 * about this specific business. Sections beyond what's below (offerings,
 * policies, operations, contacts) are genuinely open-ended JSON on the
 * backend — the UI edits the highest-value scalar fields for now and leaves
 * the rest reachable only via the API, rather than build a full nested
 * array editor before anyone's asked for one.
 */
export interface BusinessIdentity {
  business_name?: string;
  industry?: string;
  description?: string;
  location?: string;
  operating_hours?: string;
}

export interface BusinessBrand {
  tone?: string;
  communication_style?: string;
}

export interface BusinessCustomers {
  target_customer_description?: string;
}

export interface BusinessContext {
  identity: BusinessIdentity;
  offerings: Record<string, unknown>;
  customers: BusinessCustomers;
  brand: BusinessBrand;
  policies: Record<string, unknown>;
  operations: Record<string, unknown>;
  contacts: Record<string, unknown>;
  updated_at?: string | null;
}

export interface BusinessContextUpdateRequest {
  identity?: BusinessIdentity;
  customers?: BusinessCustomers;
  brand?: BusinessBrand;
}

// ---- Packs -----------------------------------------------------------------

/**
 * A vertical add-on (e.g. "Real Estate") that tunes the base agents with
 * extra prompt guidance, tool access, and approval requirements. `active`
 * reflects this organization's entitlement, not the pack's own definition —
 * see the backend's agents/entitlements.py. No billing is wired yet:
 * activating one is currently a free toggle (see settings/packs).
 */
export interface Pack {
  id: string;
  name: string;
  version: string;
  category: string;
  description: string;
  capability_requirements: string[];
  active: boolean;
}

// ---- Workflows -------------------------------------------------------------

export type WorkflowRunStatus = "success" | "failed" | "running";

export interface WorkflowStep {
  /** Machine-ish name ("send_reminder"); the UI prints a plain-language form. */
  name: string;
  status: WorkflowRunStatus | string;
  /** What happened, in whatever detail the backend has. May be absent. */
  detail?: string | null;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  status: WorkflowRunStatus;
  started_at: string;
  finished_at?: string | null;
  steps: WorkflowStep[];
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  /**
   * What sets it off, as a machine name. Never shown raw — `lib/workflows.ts`
   * turns it into a sentence an owner can read.
   */
  trigger: string;
  enabled: boolean;
  last_run_at?: string | null;
  run_count: number;
  success_count: number;
}
