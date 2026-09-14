import type {
  AgentConfig,
  AnalyticsSummary,
  AuditLogEntry,
  AuthResponse,
  BusinessContext,
  BusinessContextUpdateRequest,
  ChatOption,
  ChatRequest,
  ChatResponse,
  Conversation,
  ConversationSummary,
  ConversationTurn,
  CreateOrganizationRequest,
  Integration,
  ConnectIntegrationResponse,
  KnowledgeDocument,
  KnowledgeSearchResponse,
  KnowledgeUploadResponse,
  LoginRequest,
  Approval,
  Pack,
  PendingApproval,
  OrgRole,
  Organization,
  OrganizationMember,
  SignupRequest,
  Workflow,
  WorkflowRun,
} from "./api-types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_BASE = `${API_URL}/api/v1`;
const TOKEN_KEY = "aura_token";
const ORG_ID_KEY = "aura_org_id";

export class ApiClientError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

/**
 * The active organization id. Every org-scoped endpoint resolves the tenant
 * from the X-Organization-Id header and checks it against the caller's
 * membership, so it has to travel with the token on every authenticated
 * request — without it those endpoints 404.
 */
export function getOrgId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ORG_ID_KEY);
}

export function setOrgId(orgId: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ORG_ID_KEY, orgId);
}

export function clearOrgId() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ORG_ID_KEY);
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  isFormData?: boolean;
  authenticated?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, isFormData = false, authenticated = true } = options;

  const headers: Record<string, string> = {};
  if (!isFormData) headers["Content-Type"] = "application/json";

  if (authenticated) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const orgId = getOrgId();
    if (orgId) headers["X-Organization-Id"] = orgId;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isFormData ? (body as BodyInit) : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiClientError(
      "Couldn't reach the AURA server. Check your connection and try again."
    );
  }

  if (!res.ok) {
    let message = `Something went wrong (${res.status}).`;
    try {
      const data = await res.json();
      // The API returns { error: "..." } with plain-language text written for
      // a non-technical owner. message/detail are kept as fallbacks for
      // anything that hasn't been migrated to that envelope yet.
      if (typeof data?.error === "string") message = data.error;
      else if (typeof data?.message === "string") message = data.message;
      else if (typeof data?.detail === "string") message = data.detail;
    } catch {
      // response wasn't JSON — keep default message
    }
    throw new ApiClientError(message, res.status);
  }

  if (res.status === 204) return undefined as T;

  try {
    return (await res.json()) as T;
  } catch {
    return undefined as T;
  }
}

interface BackendTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

interface BackendUser {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

// The backend issues { access_token, ... } with no embedded user (a
// deliberately thin auth response) and separately exposes GET /auth/me.
// Fetch both and assemble the { token, user } shape the rest of the app
// is written against, so callers don't need to know about this seam.
async function completeAuth(tokens: BackendTokenResponse): Promise<AuthResponse> {
  setToken(tokens.access_token);
  const me = await request<BackendUser>("/auth/me");

  // Resolve the active tenant. Signing up creates no organization, and signing
  // back in doesn't tell us which one you belong to — so without this step a
  // returning user has a valid token and no X-Organization-Id, and every
  // org-scoped request 404s ("That organization doesn't exist"). Onboarding
  // overwrites this when it creates an org.
  try {
    const orgs = await request<BackendOrganization[]>("/organizations");
    if (orgs.length > 0) setOrgId(orgs[0].id);
    else clearOrgId();
  } catch {
    // A failure here shouldn't block sign-in — the dashboard surfaces its own
    // inline error, which is more useful than bouncing the user back to login.
  }

  return {
    token: tokens.access_token,
    user: { id: me.id, email: me.email, full_name: me.name },
  };
}

interface BackendOrganization {
  id: string;
  name: string;
  business_type: string | null;
  created_at: string;
}

interface BackendMembership {
  id: string;
  user_id: string | null;
  organization_id: string;
  role: OrgRole;
  invited_email: string | null;
  accepted: boolean;
  created_at: string;
}

export const api = {
  auth: {
    signup: async (data: SignupRequest): Promise<AuthResponse> => {
      const tokens = await request<BackendTokenResponse>("/auth/signup", {
        method: "POST",
        body: { email: data.email, password: data.password, name: data.full_name },
        authenticated: false,
      });
      return completeAuth(tokens);
    },
    login: async (data: LoginRequest): Promise<AuthResponse> => {
      const tokens = await request<BackendTokenResponse>("/auth/login", {
        method: "POST",
        body: data,
        authenticated: false,
      });
      return completeAuth(tokens);
    },
  },
  organizations: {
    create: async (data: CreateOrganizationRequest): Promise<Organization> => {
      const org = await request<BackendOrganization>("/organizations", { method: "POST", body: data });
      // Becomes the active tenant immediately — every subsequent request has
      // to carry this id in X-Organization-Id.
      setOrgId(org.id);
      return { id: org.id, name: org.name, business_type: org.business_type ?? "", created_at: org.created_at };
    },
    // The org's own record, including the public web-chat id the "Add chat to
    // your website" panel needs. `organizations.list()` mints one org's worth
    // of public_id lazily too, but the embed panel wants the freshest value
    // (e.g. right after rotating it), hence a dedicated fetch.
    get: (orgId: string) =>
      request<Organization & { public_id: string | null; public_chat_enabled: boolean }>(
        `/organizations/${orgId}`
      ),
    rotatePublicChatId: (orgId: string) =>
      request<Organization>(`/organizations/${orgId}/public-chat/rotate`, { method: "POST" }),
    enablePublicChat: (orgId: string) =>
      request<Organization>(`/organizations/${orgId}/public-chat/enable`, { method: "POST" }),
    disablePublicChat: (orgId: string) =>
      request<Organization>(`/organizations/${orgId}/public-chat/disable`, { method: "POST" }),
    // The backend doesn't join user details onto membership rows (it only
    // knows user_id), so member name/email come back empty for now — the
    // members list still renders (role, join date), just without a name
    // until the backend adds that join.
    members: async (orgId: string): Promise<OrganizationMember[]> => {
      const rows = await request<BackendMembership[]>(`/organizations/${orgId}/members`);
      return rows.map((r) => ({
        id: r.id,
        user_id: r.user_id ?? r.invited_email ?? r.id,
        full_name: r.accepted ? "" : `${r.invited_email ?? ""} (invited)`,
        email: r.invited_email ?? "",
        role: r.role,
        joined_at: r.created_at,
      }));
    },
  },
  agents: {
    list: () => request<AgentConfig[]>("/agents"),
    // The backend requires conversation_id (it's how it scopes short-term
    // memory) — the UI treats it as optional for a brand-new thread, so mint
    // one client-side the first time a caller doesn't have one yet. The
    // backend also reports tool calls as plain names (tool_calls_made:
    // string[]); the UI wants a richer { name, status } shape per call.
    chat: async (slug: string, data: ChatRequest): Promise<ChatResponse> => {
      const res = await request<{
        response: string;
        conversation_id: string;
        tool_calls_made: string[];
        pending_approvals?: PendingApproval[];
        options?: ChatOption[];
        node_id?: string | null;
      }>(`/agents/${slug}/chat`, {
        method: "POST",
        body: { ...data, conversation_id: data.conversation_id ?? crypto.randomUUID() },
      });
      return {
        response: res.response,
        conversation_id: res.conversation_id,
        tool_calls: res.tool_calls_made.map((name) => ({ name, status: "success" as const })),
        // Anything consequential the agent wants to do stops here and waits
        // for the owner. Absent on older responses, so default to empty.
        pending_approvals: res.pending_approvals ?? [],
        // Present only while this agent runs the temporary predefined menu
        // flow (see the Receptionist) instead of the real AI pipeline.
        options: res.options ?? [],
        node_id: res.node_id ?? null,
      };
    },
    conversation: (slug: string, conversationId: string) =>
      request<Conversation>(`/agents/${slug}/conversations/${conversationId}`),
  },
  knowledge: {
    // Backend returns { chunks_stored }, not a document — the document itself
    // only becomes visible via knowledge.list() once ingestion finishes, since
    // storage is keyed by chunk, not by upload. Synthesize an optimistic
    // KnowledgeDocument here so the UI can show the file immediately.
    upload: async (file: File): Promise<KnowledgeUploadResponse> => {
      const form = new FormData();
      form.append("file", file);
      await request<{ chunks_stored: number }>("/knowledge/upload", {
        method: "POST",
        body: form,
        isFormData: true,
      });
      return {
        document: {
          id: `${file.name}-${Date.now()}`,
          filename: file.name,
          status: "ready",
          uploaded_at: new Date().toISOString(),
          size_bytes: file.size,
        },
      };
    },
    list: () => request<KnowledgeDocument[]>("/knowledge"),
    // Backend returns raw chunks ({ content, source, distance }[]), not the
    // { results } envelope — adapt here rather than in every caller.
    search: async (q: string): Promise<KnowledgeSearchResponse> => {
      const chunks = await request<{ content: string; source: string; distance: number }[]>(
        `/knowledge/search?q=${encodeURIComponent(q)}`
      );
      return {
        results: chunks.map((chunk, i) => ({
          id: `${chunk.source}-${i}`,
          document_filename: chunk.source,
          snippet: chunk.content,
          score: 1 - chunk.distance,
        })),
      };
    },
  },
  integrations: {
    // The backend groups Calendar + Gmail under one "google" OAuth
    // connection (they share the same consent grant); the UI shows them as
    // two cards since they're two distinct permissions from the owner's
    // point of view. Expand the backend's one row into both card slots.
    list: async (): Promise<Integration[]> => {
      const rows = await request<{ provider: string; connected: boolean; metadata: Record<string, unknown> }[]>(
        "/integrations"
      );
      const toFrontendProviders = (p: string) => (p === "google" ? ["google_calendar", "gmail"] : [p]);
      return rows.flatMap((r) =>
        toFrontendProviders(r.provider).map(
          (provider): Integration => ({
            provider,
            display_name: provider,
            status: r.connected ? "connected" : "not_connected",
            connected_at: typeof r.metadata?.connected_at === "string" ? r.metadata.connected_at : undefined,
          })
        )
      );
    },
    connect: (provider: string) => {
      const backendProvider = provider === "google_calendar" || provider === "gmail" ? "google" : provider;
      return request<ConnectIntegrationResponse>(`/integrations/${backendProvider}/connect`, { method: "POST" });
    },
  },
  // The org's own business facts, grounding every agent's prompt. GET is
  // open to any accepted member; PATCH/reset are owner/admin only on the
  // backend (a 403 there is expected for a member and handled at the call
  // site, same as integrations.connect).
  businessContext: {
    get: (orgId: string) => request<BusinessContext>(`/organizations/${orgId}/business-context`),
    update: (orgId: string, data: BusinessContextUpdateRequest) =>
      request<BusinessContext>(`/organizations/${orgId}/business-context`, { method: "PATCH", body: data }),
    reset: (orgId: string) =>
      request<BusinessContext>(`/organizations/${orgId}/business-context/reset`, { method: "POST" }),
  },
  // Vertical add-on packs. No billing yet — activate/deactivate are a free
  // toggle today (see lib/api-types.ts's Pack docstring).
  packs: {
    list: (orgId: string) => request<Pack[]>(`/organizations/${orgId}/packs`),
    activate: (orgId: string, packId: string) =>
      request<Pack>(`/organizations/${orgId}/packs/${packId}/activate`, { method: "POST" }),
    deactivate: (orgId: string, packId: string) =>
      request<Pack>(`/organizations/${orgId}/packs/${packId}/deactivate`, { method: "POST" }),
  },
  // Human-approval gate. Consequential actions queue here instead of running,
  // and stay queued until the owner decides. Owner/admin only — a 403 from
  // these endpoints is expected for members and is handled at the call site.
  approvals: {
    listPending: () => request<Approval[]>("/approvals?status=pending"),
    approve: (id: string) => request<Approval>(`/approvals/${id}/approve`, { method: "POST" }),
    reject: (id: string) => request<Approval>(`/approvals/${id}/reject`, { method: "POST" }),
  },
  // Every thread an org's agents have had, plus the ability for a human to
  // take one over and answer directly. See docs behind "Take over" in the
  // conversation view for the agent/human control states.
  conversations: {
    list: (agentSlug?: string) =>
      request<ConversationSummary[]>(`/conversations${agentSlug ? `?agent=${encodeURIComponent(agentSlug)}` : ""}`),
    transcript: (conversationId: string) =>
      request<ConversationTurn[]>(`/conversations/${encodeURIComponent(conversationId)}`),
    takeover: (conversationId: string) =>
      request<ConversationSummary>(`/conversations/${encodeURIComponent(conversationId)}/takeover`, {
        method: "POST",
      }),
    handback: (conversationId: string) =>
      request<ConversationSummary>(`/conversations/${encodeURIComponent(conversationId)}/handback`, {
        method: "POST",
      }),
    sendMessage: (conversationId: string, content: string) =>
      request<ConversationTurn>(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
        method: "POST",
        body: { content },
      }),
  },
  auditLogs: {
    list: (agentSlug?: string) =>
      request<AuditLogEntry[]>(`/audit-logs${agentSlug ? `?agent=${encodeURIComponent(agentSlug)}` : ""}`),
  },
  // What the work added up to, over a window the owner picks. No adapter here
  // — this endpoint is being built to the shape the UI already wants.
  analytics: {
    summary: (days: number) => request<AnalyticsSummary>(`/analytics/summary?days=${days}`),
  },
  // Standing automations. Enable/disable return the updated workflow, so the
  // caller can reconcile against the server's answer rather than guessing.
  workflows: {
    list: () => request<Workflow[]>("/workflows"),
    enable: (id: string) => request<Workflow>(`/workflows/${id}/enable`, { method: "POST" }),
    disable: (id: string) => request<Workflow>(`/workflows/${id}/disable`, { method: "POST" }),
    runs: (id: string, limit = 20) => request<WorkflowRun[]>(`/workflows/${id}/runs?limit=${limit}`),
  },
};
