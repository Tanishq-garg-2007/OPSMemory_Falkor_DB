export const TENANTS = [
  { key: "key_acme_secret", id: "acme", label: "Acme Corp (acme)" },
  { key: "key_beta_secret", id: "beta", label: "Beta Labs (beta)" },
];

const ADMIN_KEY_STORAGE = "opsmemory-admin-key";

async function request(path, { key, adminKey, method = "GET", body } = {}) {
  const headers = {};
  if (key) headers["X-Tenant-Key"] = key;
  if (adminKey) headers["X-Admin-Key"] = adminKey;
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (!res.ok) throw new Error(`Error ${res.status}: ${res.statusText}`);
  return res.json();
}

// Asks for the admin key once per browser tab. It is kept in sessionStorage,
// which is cleared when the tab closes.
function getAdminKey() {
  let adminKey = sessionStorage.getItem(ADMIN_KEY_STORAGE);
  if (!adminKey) {
    adminKey = window.prompt("Enter the admin key (ADMIN_API_KEY in your .env file):");
    if (!adminKey) throw new Error("No admin key entered");
    sessionStorage.setItem(ADMIN_KEY_STORAGE, adminKey);
  }
  return adminKey;
}

async function adminPost(path) {
  const adminKey = getAdminKey();
  try {
    return await request(path, { adminKey, method: "POST" });
  } catch (e) {
    // Wrong key: forget it, so the next click asks again.
    if (/401|403/.test(e.message)) sessionStorage.removeItem(ADMIN_KEY_STORAGE);
    throw e;
  }
}

export const getHealth = () => request("/healthz");
export const sendChat = (key, message, conversationId) =>
  request("/v1/chat", { key, method: "POST", body: { message, conversation_id: conversationId } });
export const getTasks = (key) => request("/v1/tasks", { key });
export const getMemories = (key) => request("/v1/memories", { key });
export const seedTenant = (tenantId) => adminPost(`/v1/admin/seed?tenant_id=${tenantId}`);
export const resetTenant = (tenantId) => adminPost(`/v1/admin/reset?tenant_id=${tenantId}`);
export const getTopology = (key, maxNodes = 150) => request(`/v1/graph/topology?max_nodes=${maxNodes}`, { key });
export const getConversations = (key, limit = 20, offset = 0) =>
  request(`/v1/conversations?limit=${limit}&offset=${offset}`, { key });
export const getConversationTurns = (key, conversationId) =>
  request(`/v1/conversations/${encodeURIComponent(conversationId)}/turns`, { key });
export const getAgentHandoffs = (key, conversationId, limit = 10) => {
  const query = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}&limit=${limit}` : `?limit=${limit}`;
  return request(`/v1/agents/handoffs${query}`, { key });
};
export const getEntityTimeline = (key, entityId) =>
  request(`/v1/entities/${encodeURIComponent(entityId)}/timeline`, { key });