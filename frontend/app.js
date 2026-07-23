"use strict";

const API_BASE = "/api";
const POLL_INTERVAL_MS = 2000;
const POLL_LIMIT = 90;
const state = { tickets: [], polling: new Map(), loading: false };
let currentUser = null;

const elements = {
  form: document.querySelector("#ticket-form"), title: document.querySelector("#ticket-title"),
  description: document.querySelector("#ticket-description"), submit: document.querySelector("#submit-button"),
  titleCount: document.querySelector("#title-count"), descriptionCount: document.querySelector("#description-count"),
  titleError: document.querySelector("#title-error"), descriptionError: document.querySelector("#description-error"),
  list: document.querySelector("#tickets-list"), search: document.querySelector("#search-input"),
  filter: document.querySelector("#status-filter"), refresh: document.querySelector("#refresh-button"),
  status: document.querySelector("#system-status"), statusLabel: document.querySelector("#status-label"),
  updated: document.querySelector("#last-updated"), toasts: document.querySelector("#toast-region"),
  dialog: document.querySelector("#ticket-dialog"), dialogTitle: document.querySelector("#dialog-title"),
  dialogContent: document.querySelector("#dialog-content"), dialogClose: document.querySelector("#dialog-close"),
  total: document.querySelector("#stat-total"), pending: document.querySelector("#stat-pending"),
  processing: document.querySelector("#stat-processing"), complete: document.querySelector("#stat-complete")
};

function requestId() { return crypto.randomUUID ? crypto.randomUUID() : `web-${Date.now()}-${Math.random().toString(16).slice(2)}`; }

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Request-ID": requestId(), ...(options.headers || {}) }
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = body?.error?.message || body?.detail || `Request failed (${response.status})`;
    const error = new Error(message); error.status = response.status; error.body = body; throw error;
  }
  return body;
}

function node(tag, className, text) {
  const item = document.createElement(tag); if (className) item.className = className;
  if (text !== undefined && text !== null) item.textContent = String(text); return item;
}

function badge(value, extra = "") { return node("span", `badge ${String(value || "pending").toLowerCase()} ${extra}`.trim(), value || "pending"); }

function relativeTime(value) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`; if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`; return new Date(value).toLocaleDateString();
}

function renderStats() {
  elements.total.textContent = state.tickets.length;
  elements.pending.textContent = state.tickets.filter(t => t.status === "pending").length;
  elements.processing.textContent = state.tickets.filter(t => t.status === "processing").length;
  elements.complete.textContent = state.tickets.filter(t => t.status === "complete").length;
}

function renderTickets() {
  const query = elements.search.value.trim().toLowerCase(); const status = elements.filter.value;
  const tickets = state.tickets.filter(ticket => (status === "all" || ticket.status === status) &&
    (!query || `${ticket.title} ${ticket.description} ${ticket.category || ""} ${ticket.assigned_queue || ""}`.toLowerCase().includes(query)));
  elements.list.replaceChildren();
  if (!tickets.length) {
    const empty = node("div", "empty-state"); empty.append(node("span", "", "⌁"), node("h3", "", state.tickets.length ? "No matching tickets" : "No tickets yet"), node("p", "", state.tickets.length ? "Try a different search or filter." : "Create your first ticket to see AI routing in action.")); elements.list.append(empty); return;
  }
  tickets.forEach(ticket => {
    const row = node("button", "ticket-row"); row.type = "button"; row.dataset.ticketId = ticket.id;
    const content = node("div"); content.append(node("div", "ticket-title", ticket.title), node("div", "ticket-description", ticket.description));
    const meta = node("div", "ticket-meta"); meta.append(badge(ticket.status));
    if (ticket.urgency) meta.append(badge(ticket.urgency)); if (ticket.category) meta.append(badge(ticket.category, "category"));
    meta.append(node("span", "ticket-time", relativeTime(ticket.updated_at))); content.append(meta);
    row.append(content, node("span", "queue-tag", ticket.assigned_queue ? `→ ${ticket.assigned_queue}` : "View →"));
    row.addEventListener("click", () => showTicket(ticket)); elements.list.append(row);
  });
}

function upsertTicket(ticket) {
  const index = state.tickets.findIndex(item => item.id === ticket.id);
  if (index >= 0) state.tickets[index] = ticket; else state.tickets.unshift(ticket);
  state.tickets.sort((a, b) => new Date(b.created_at) - new Date(a.created_at)); renderStats(); renderTickets();
}

async function loadTickets({ silent = false } = {}) {
  if (state.loading) return; state.loading = true; elements.refresh.disabled = true;
  try {
    const result = await api("/tickets?limit=100&offset=0"); state.tickets = result.items;
    elements.updated.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    renderStats(); renderTickets();
  } catch (error) { if (!silent) toast("Could not load tickets", error.message, true); }
  finally { state.loading = false; elements.refresh.disabled = false; }
}

async function checkHealth() {
  try { const result = await api("/ready"); const healthy = result.status === "ready"; elements.status.className = `system-status ${healthy ? "healthy" : "unhealthy"}`; elements.statusLabel.textContent = healthy ? "All systems operational" : "Dependencies unavailable"; }
  catch { elements.status.className = "system-status unhealthy"; elements.statusLabel.textContent = "Service unavailable"; }
}

function validateForm() {
  const title = elements.title.value.trim(), description = elements.description.value.trim(); let valid = true;
  elements.title.classList.remove("invalid"); elements.description.classList.remove("invalid"); elements.titleError.textContent = ""; elements.descriptionError.textContent = "";
  if (!title) { elements.titleError.textContent = "Please enter a title."; elements.title.classList.add("invalid"); valid = false; }
  if (!description) { elements.descriptionError.textContent = "Please describe the issue."; elements.description.classList.add("invalid"); valid = false; }
  return valid;
}

async function submitTicket(event) {
  event.preventDefault(); if (!validateForm()) return;
  elements.submit.disabled = true; elements.submit.querySelector("span").textContent = "Saving ticket…";
  try {
    const ticket = await api("/tickets", { method: "POST", body: JSON.stringify({ title: elements.title.value.trim(), description: elements.description.value.trim() }) });
    upsertTicket(ticket); elements.form.reset(); updateCounts(); toast("Ticket accepted", "AI classification is running in the background."); pollTicket(ticket.id);
  } catch (error) { toast("Ticket was not created", error.message, true); }
  finally { elements.submit.disabled = false; elements.submit.querySelector("span").textContent = "Classify & route ticket"; }
}

function pollTicket(id) {
  if (state.polling.has(id)) return; let attempts = 0;
  const poll = async () => {
    try {
      const ticket = await api(`/tickets/${id}`); upsertTicket(ticket);
      if (["complete", "failed"].includes(ticket.status)) { state.polling.delete(id); if (ticket.status === "complete") toast("Classification complete", `Routed to ${ticket.assigned_queue}.`); return; }
    } catch (error) { if (error.status === 404) { state.polling.delete(id); return; } }
    attempts += 1; if (attempts < POLL_LIMIT) state.polling.set(id, setTimeout(poll, POLL_INTERVAL_MS)); else state.polling.delete(id);
  };
  state.polling.set(id, setTimeout(poll, POLL_INTERVAL_MS));
}

function detail(label, value) { const item = node("div", "detail-item"); item.append(node("span", "", label), node("b", "", value ?? "—")); return item; }

function showTicket(ticket) {
  elements.dialogTitle.textContent = ticket.title; const body = node("div", "dialog-body");
  body.append(node("p", "dialog-description", ticket.description)); const grid = node("div", "detail-grid");
  grid.append(detail("Status", ticket.status), detail("Urgency", ticket.urgency), detail("Category", ticket.category), detail("Assigned queue", ticket.assigned_queue), detail("Confidence", ticket.confidence == null ? null : `${Math.round(ticket.confidence * 100)}%`), detail("Model", ticket.llm_model), detail("Tokens", ticket.tokens_used), detail("Processing time", ticket.processing_time == null ? null : `${ticket.processing_time} ms`), detail("Estimated cost", ticket.estimated_cost_usd == null ? null : `$${Number(ticket.estimated_cost_usd).toFixed(6)}`), detail("Retries", ticket.retry_count));
  body.append(grid); elements.dialogContent.replaceChildren(body); elements.dialog.showModal();
}

function toast(title, message, isError = false) {
  const item = node("div", `toast${isError ? " error" : ""}`); item.append(node("b", "", title), node("span", "", message)); elements.toasts.append(item); setTimeout(() => item.remove(), 5000);
}

function updateCounts() { elements.titleCount.textContent = `${elements.title.value.length} / 255`; elements.descriptionCount.textContent = `${elements.description.value.length.toLocaleString()} / 50,000`; }

elements.form.addEventListener("submit", submitTicket); elements.title.addEventListener("input", updateCounts); elements.description.addEventListener("input", updateCounts);
elements.search.addEventListener("input", renderTickets); elements.filter.addEventListener("change", renderTickets);
elements.refresh.addEventListener("click", () => Promise.all([loadTickets(), checkHealth()])); elements.dialogClose.addEventListener("click", () => elements.dialog.close());
elements.dialog.addEventListener("click", event => { if (event.target === elements.dialog) elements.dialog.close(); });
document.querySelector("#logout-button").addEventListener("click", async () => { try { await api("/auth/logout", { method: "POST" }); } finally { location.replace("/login.html"); } });

async function bootstrap() {
  try {
    currentUser = await api("/auth/me");
    if (currentUser.role === "admin") return location.replace("/admin.html");
    if (currentUser.role === "support_agent") return location.replace("/agent.html");
    document.querySelector("#user-label").textContent = currentUser.full_name;
    updateCounts(); checkHealth(); loadTickets();
    setInterval(() => { checkHealth(); loadTickets({ silent: true }); }, 30000);
  } catch { location.replace("/login.html"); }
}
bootstrap();
