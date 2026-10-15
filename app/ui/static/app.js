// OpsMemory UI Controller
let currentConversationId = null;

function getTenantKey() {
  return document.getElementById("tenant-select").value;
}

function getTenantId() {
  const key = getTenantKey();
  return key.includes("beta") ? "beta" : "acme";
}

async function checkHealth() {
  const ind = document.getElementById("health-indicator");
  const text = document.getElementById("health-text");
  try {
    const res = await fetch("/healthz");
    const data = await res.json();
    if (data.status === "ok") {
      ind.classList.add("connected");
      text.textContent = `${data.database.mode} (healthy)`;
    } else {
      ind.classList.remove("connected");
      text.textContent = "Degraded (Persistence Offline)";
    }
  } catch (e) {
    ind.classList.remove("connected");
    text.textContent = "Offline";
  }
}

async function sendChatMessage(message) {
  const chatMessages = document.getElementById("chat-messages");
  
  // Render user message
  const userDiv = document.createElement("div");
  userDiv.className = "message user-message";
  userDiv.textContent = message;
  chatMessages.appendChild(userDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  // Add thinking placeholder
  const placeholder = document.createElement("div");
  placeholder.className = "message assistant-message";
  placeholder.textContent = "Querying OpsMemory graph...";
  chatMessages.appendChild(placeholder);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const res = await fetch("/v1/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Key": getTenantKey()
      },
      body: JSON.stringify({
        message: message,
        conversation_id: currentConversationId
      })
    });

    if (!res.ok) {
      throw new Error(`Error ${res.status}: ${res.statusText}`);
    }

    const data = await res.json();
    currentConversationId = data.conversation_id;

    // Render assistant answer with citations
    let citationsHtml = "";
    if (data.citations && data.citations.length > 0) {
      citationsHtml = `<div style="margin-top:0.5rem;font-size:0.75rem;color:#38bdf8;"><strong>Citations:</strong> ${data.citations.join(", ")}</div>`;
    }
    placeholder.innerHTML = `<p>${data.answer}</p>${citationsHtml}`;
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Render evidence
    renderEvidence(data.evidence);

    // Refresh tasks
    loadTasks();
  } catch (err) {
    placeholder.textContent = `Error: ${err.message}`;
  }
}

function renderEvidence(evidence) {
  const container = document.getElementById("evidence-list");
  const countBadge = document.getElementById("evidence-count");
  if (!evidence || evidence.length === 0) {
    container.innerHTML = '<div class="empty-state">No evidence retrieved for this query.</div>';
    countBadge.textContent = "0 records";
    return;
  }

  countBadge.textContent = `${evidence.length} records`;
  container.innerHTML = "";

  evidence.forEach(item => {
    const card = document.createElement("div");
    card.className = `evidence-card ${item.status}`;
    card.innerHTML = `
      <div class="evidence-meta">
        <span><code>${item.memory_id}</code></span>
        <span>Conf: ${Math.round(item.confidence * 100)}% | Score: ${item.score}</span>
      </div>
      <div class="evidence-title">${item.title}</div>
      <div class="evidence-summary">${item.summary}</div>
      <div style="margin-top:0.35rem;font-size:0.7rem;color:#64748b;">
        Valid: ${item.valid_from} ${item.valid_to ? 'to ' + item.valid_to : '(active current)'} | Status: ${item.status}
      </div>
    `;
    card.onclick = () => {
      document.getElementById("memory-inspector").textContent = JSON.stringify(item, null, 2);
      document.getElementById("tab-graph").click();
    };
    container.appendChild(card);
  });
}

async function loadTasks() {
  const container = document.getElementById("tasks-list");
  try {
    const res = await fetch("/v1/tasks", {
      headers: { "X-Tenant-Key": getTenantKey() }
    });
    const tasks = await res.json();
    if (!tasks || tasks.length === 0) {
      container.innerHTML = '<div class="empty-state">No active coordination tasks.</div>';
      return;
    }
    container.innerHTML = "";
    tasks.forEach(t => {
      const card = document.createElement("div");
      card.className = `task-card ${t.status}`;
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;margin-bottom:0.25rem;">
          <strong>${t.task_type}</strong>
          <span class="badge">${t.status}</span>
        </div>
        <div style="font-size:0.75rem;color:#94a3b8;">ID: <code>${t.id}</code></div>
        <div style="font-size:0.75rem;color:#64748b;margin-top:0.25rem;">Lease Owner: ${t.lease_owner || 'None'}</div>
      `;
      container.appendChild(card);
    });
  } catch (e) {
    container.innerHTML = `<div class="empty-state">Error loading tasks: ${e.message}</div>`;
  }
}

async function loadAllMemories() {
  const inspector = document.getElementById("memory-inspector");
  inspector.textContent = "Loading memories from persistent graph...";
  try {
    const res = await fetch("/v1/memories", {
      headers: { "X-Tenant-Key": getTenantKey() }
    });
    const memories = await res.json();
    inspector.textContent = JSON.stringify(memories, null, 2);
  } catch (e) {
    inspector.textContent = `Error loading memories: ${e.message}`;
  }
}

async function seedData() {
  const tenantId = getTenantId();
  try {
    const res = await fetch(`/v1/admin/seed?tenant_id=${tenantId}`, { method: "POST" });
    const data = await res.json();
    alert(`Seeded ${tenantId}: ${data.stats.memories} memories, ${data.stats.entities} entities, ${data.stats.tasks} tasks.`);
    loadTasks();
    loadAllMemories();
  } catch (e) {
    alert(`Seeding failed: ${e.message}`);
  }
}

async function resetData() {
  const tenantId = getTenantId();
  if (!confirm(`Reset all persistent graph & memory state for tenant '${tenantId}'?`)) return;
  try {
    const res = await fetch(`/v1/admin/reset?tenant_id=${tenantId}`, { method: "POST" });
    const data = await res.json();
    alert(`Reset ${tenantId}: ${data.deleted_records} records cleared.`);
    loadTasks();
    loadAllMemories();
  } catch (e) {
    alert(`Reset failed: ${e.message}`);
  }
}

// Event Listeners
document.getElementById("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const msg = input.value.trim();
  if (msg) {
    sendChatMessage(msg);
    input.value = "";
  }
});

document.getElementById("btn-seed").addEventListener("click", seedData);
document.getElementById("btn-reset").addEventListener("click", resetData);
document.getElementById("btn-refresh-tasks").addEventListener("click", loadTasks);
document.getElementById("btn-refresh-memories").addEventListener("click", loadAllMemories);

// Tab switching
document.getElementById("tab-tasks").addEventListener("click", () => {
  document.getElementById("tab-tasks").classList.add("active");
  document.getElementById("tab-graph").classList.remove("active");
  document.getElementById("tasks-content").classList.add("active");
  document.getElementById("graph-content").classList.remove("active");
});

document.getElementById("tab-graph").addEventListener("click", () => {
  document.getElementById("tab-graph").classList.add("active");
  document.getElementById("tab-tasks").classList.remove("active");
  document.getElementById("graph-content").classList.add("active");
  document.getElementById("tasks-content").classList.remove("active");
});

// Initialization
checkHealth();
setInterval(checkHealth, 15000);
loadTasks();
