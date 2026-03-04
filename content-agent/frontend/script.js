const { API_BASE_URL, SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } = window.APP_CONFIG;
const supabaseLib = window.supabase;
const state = {
  sbClient: null,
  session: null,
  authed: false,
  activePage: "dashboard",
  clients: [],
  drafts: [],
  templates: [],
  payments: [],
  pendingApprovals: 0,
  analyticsTotals: { likes: 0, shares: 0, comments: 0, clicks: 0, follower_growth: 0 },
  dragPostId: null,
  analyticsChart: null,
};

const refs = {
  body: document.body,
  authBanner: document.getElementById("authBanner"),
  loginSection: document.getElementById("loginSection"),
  sidebar: document.getElementById("sidebar"),
  mobileMenuBtn: document.getElementById("mobileMenuBtn"),
  globalSearchInput: document.getElementById("globalSearchInput"),
  searchWrap: document.querySelector(".search-wrap"),
  navButtons: Array.from(document.querySelectorAll(".nav-btn")),
  pages: {
    dashboard: document.getElementById("page-dashboard"),
    clients: document.getElementById("page-clients"),
    calendar: document.getElementById("page-calendar"),
    generator: document.getElementById("page-generator"),
    analytics: document.getElementById("page-analytics"),
    payments: document.getElementById("page-payments"),
    settings: document.getElementById("page-settings"),
  },
  notifyBtn: document.getElementById("notifyBtn"),
  notifyCount: document.getElementById("notifyCount"),
  notificationPanel: document.getElementById("notificationPanel"),
  notificationList: document.getElementById("notificationList"),
  profileBtn: document.getElementById("profileBtn"),
  logoutBtn: document.getElementById("logoutBtn"),
  googleLoginBtn: document.getElementById("googleLoginBtn"),
  githubLoginBtn: document.getElementById("githubLoginBtn"),
  emailLoginBtn: document.getElementById("emailLoginBtn"),
  loginGoogleMainBtn: document.getElementById("loginGoogleMainBtn"),
  loginGithubMainBtn: document.getElementById("loginGithubMainBtn"),
  magicEmailInput: document.getElementById("magicEmailInput"),
  magicLinkSendBtn: document.getElementById("magicLinkSendBtn"),
  statClients: document.getElementById("statClients"),
  statScheduled: document.getElementById("statScheduled"),
  statEngagement: document.getElementById("statEngagement"),
  statRevenue: document.getElementById("statRevenue"),
  welcomeTitle: document.getElementById("welcomeTitle"),
  welcomeSubtitle: document.getElementById("welcomeSubtitle"),
  dashboardHealthText: document.getElementById("dashboardHealthText"),
  clientForm: document.getElementById("clientForm"),
  clientBusinessName: document.getElementById("clientBusinessName"),
  clientIndustry: document.getElementById("clientIndustry"),
  clientHandles: document.getElementById("clientHandles"),
  clientWebsite: document.getElementById("clientWebsite"),
  clientBrandVoice: document.getElementById("clientBrandVoice"),
  clientKeywords: document.getElementById("clientKeywords"),
  clientAvoid: document.getElementById("clientAvoid"),
  clientAudience: document.getElementById("clientAudience"),
  clientWhatsapp: document.getElementById("clientWhatsapp"),
  clientLogo: document.getElementById("clientLogo"),
  clientNotes: document.getElementById("clientNotes"),
  clientsList: document.getElementById("clientsList"),
  calendarForm: document.getElementById("calendarForm"),
  calendarClientSelect: document.getElementById("calendarClientSelect"),
  calendarSeedInput: document.getElementById("calendarSeedInput"),
  calendarBoard: document.getElementById("calendarBoard"),
  calendarPostsList: document.getElementById("calendarPostsList"),
  generatorForm: document.getElementById("generatorForm"),
  generatorClientSelect: document.getElementById("generatorClientSelect"),
  generatorContentInput: document.getElementById("generatorContentInput"),
  canvaTemplateSelect: document.getElementById("canvaTemplateSelect"),
  canvaTemplatePreview: document.getElementById("canvaTemplatePreview"),
  previewCard: document.getElementById("previewCard"),
  draftsList: document.getElementById("draftsList"),
  analyticsClientSelect: document.getElementById("analyticsClientSelect"),
  analyticsDaysSelect: document.getElementById("analyticsDaysSelect"),
  refreshAnalyticsBtn: document.getElementById("refreshAnalyticsBtn"),
  analyticsLikes: document.getElementById("analyticsLikes"),
  analyticsShares: document.getElementById("analyticsShares"),
  analyticsComments: document.getElementById("analyticsComments"),
  analyticsClicks: document.getElementById("analyticsClicks"),
  analyticsFollowers: document.getElementById("analyticsFollowers"),
  topPostsList: document.getElementById("topPostsList"),
  analyticsChart: document.getElementById("analyticsChart"),
  paymentForm: document.getElementById("paymentForm"),
  paymentClientSelect: document.getElementById("paymentClientSelect"),
  paymentPlanName: document.getElementById("paymentPlanName"),
  paymentAmount: document.getElementById("paymentAmount"),
  paymentCurrency: document.getElementById("paymentCurrency"),
  paymentStatus: document.getElementById("paymentStatus"),
  paymentDueDate: document.getElementById("paymentDueDate"),
  paymentAutoPause: document.getElementById("paymentAutoPause"),
  paymentsList: document.getElementById("paymentsList"),
  linkedinStatus: document.getElementById("linkedinStatus"),
  instagramStatus: document.getElementById("instagramStatus"),
  facebookStatus: document.getElementById("facebookStatus"),
  canvaStatus: document.getElementById("canvaStatus"),
  connectLinkedInBtn: document.getElementById("connectLinkedInBtn"),
  connectInstagramBtn: document.getElementById("connectInstagramBtn"),
  connectFacebookBtn: document.getElementById("connectFacebookBtn"),
  connectCanvaBtn: document.getElementById("connectCanvaBtn"),
};

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setBanner(text) {
  refs.authBanner.textContent = text;
}

function platformLabel(platform) {
  return String(platform || "").trim().toUpperCase();
}

function platformIcon(platform) {
  const key = String(platform || "").toLowerCase();
  if (key === "linkedin") return "in";
  if (key === "instagram") return "ig";
  if (key === "facebook") return "fb";
  if (key === "twitter") return "x";
  return "ai";
}

function setButtonLoading(button, loading, busyText = "Loading...") {
  if (!(button instanceof HTMLButtonElement)) return;
  if (loading) {
    if (!button.dataset.defaultText) button.dataset.defaultText = button.textContent || "";
    button.textContent = busyText;
    button.classList.add("is-loading");
    button.disabled = true;
    return;
  }
  button.classList.remove("is-loading");
  button.disabled = false;
  button.textContent = button.dataset.defaultText || button.textContent || "";
}

function closeNotificationPanel() {
  if (!refs.notificationPanel || !refs.notifyBtn) return;
  refs.notificationPanel.hidden = true;
  refs.notifyBtn.setAttribute("aria-expanded", "false");
}

function renderNotificationPanel() {
  if (!refs.notificationList) return;
  if (!state.authed) {
    refs.notificationList.innerHTML = "<p class='muted'>Log in to view notifications.</p>";
    return;
  }
  const notifications = [];
  if (state.pendingApprovals > 0) {
    notifications.push({
      title: `${state.pendingApprovals} approval request(s) pending`,
      detail: "Open Draft Workflow and send reminders or finalize approval.",
    });
  }
  const scheduled = state.drafts.filter((d) => d.status === "scheduled").length;
  if (scheduled > 0) {
    notifications.push({
      title: `${scheduled} post(s) scheduled`,
      detail: "Content is queued and ready for automatic publishing.",
    });
  }
  const dues = state.payments.filter((p) => p.subscription_status === "past_due" || p.subscription_status === "unpaid").length;
  if (dues > 0) {
    notifications.push({
      title: `${dues} payment account(s) need attention`,
      detail: "Review payment status to avoid service auto-pause.",
    });
  }
  if (!notifications.length) {
    refs.notificationList.innerHTML = "<p class='muted'>No new notifications.</p>";
    return;
  }
  refs.notificationList.innerHTML = notifications
    .map(
      (item) => `
        <article class="notification-item">
          <strong>${escapeHtml(item.title)}</strong>
          <p class="muted">${escapeHtml(item.detail)}</p>
        </article>
      `,
    )
    .join("");
}

function localDateInputValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const offset = d.getTimezoneOffset();
  const local = new Date(d.getTime() - offset * 60000);
  return local.toISOString().slice(0, 16);
}

async function api(path, options = {}) {
  if (!state.session?.access_token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${state.session.access_token}`,
      ...(options.headers || {}),
    },
  });
  const text = await res.text();
  let body = {};
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { message: text };
  }
  if (!res.ok) throw new Error(body.detail || body.message || `Request failed (${res.status})`);
  return body;
}

async function apiPublic(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, options);
  const text = await res.text();
  let body = {};
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { message: text };
  }
  if (!res.ok) throw new Error(body.detail || body.message || `Request failed (${res.status})`);
  return body;
}

function setActivePage(page) {
  state.activePage = page;
  Object.entries(refs.pages).forEach(([name, node]) => {
    node.hidden = name !== page || !state.authed;
  });
  refs.navButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.page === page));
  refs.body.dataset.page = page;
  refs.body.classList.remove("menu-open");
}

function setAuthedUI(isAuthed, email = "") {
  state.authed = isAuthed;
  refs.body.classList.toggle("logged-out", !isAuthed);
  refs.loginSection.hidden = isAuthed;
  refs.sidebar.hidden = !isAuthed;
  refs.mobileMenuBtn.hidden = !isAuthed;
  if (refs.searchWrap) refs.searchWrap.hidden = !isAuthed;
  refs.notifyBtn.hidden = !isAuthed;
  refs.googleLoginBtn.hidden = isAuthed;
  refs.githubLoginBtn.hidden = isAuthed;
  refs.emailLoginBtn.hidden = isAuthed;
  refs.logoutBtn.hidden = !isAuthed;
  refs.profileBtn.hidden = !isAuthed;
  closeNotificationPanel();
  refs.profileBtn.textContent = isAuthed ? (email[0] || "U").toUpperCase() : "U";
  if (!isAuthed) {
    Object.values(refs.pages).forEach((node) => {
      node.hidden = true;
    });
    setBanner("Not logged in");
    if (refs.welcomeTitle) refs.welcomeTitle.textContent = "Welcome back";
    if (refs.welcomeSubtitle) refs.welcomeSubtitle.textContent = "Track pipeline health, review pending approvals, and keep publishing momentum.";
    return;
  }
  const shortName = String(email || "").split("@")[0] || "there";
  if (refs.welcomeTitle) refs.welcomeTitle.textContent = `Welcome, ${shortName}`;
  if (refs.welcomeSubtitle) refs.welcomeSubtitle.textContent = "Your campaigns, approvals, and automation jobs are ready.";
  setActivePage(state.activePage);
  setBanner(`Logged in as ${email}`);
}

function selectedCheckboxValues(selector) {
  return Array.from(document.querySelectorAll(selector))
    .filter((el) => el.checked)
    .map((el) => el.value);
}

function selectedClientFrom(selectEl) {
  const id = Number(selectEl.value || 0);
  return state.clients.find((c) => c.id === id) || null;
}

function withSkeleton(node) {
  if (!node) return;
  node.classList.add("skeleton");
  setTimeout(() => node.classList.remove("skeleton"), 500);
}

function populateClientSelects() {
  const options = [
    '<option value="">Select client</option>',
    ...state.clients.map((c) => `<option value="${c.id}">${escapeHtml(c.business_name)}</option>`),
  ].join("");
  refs.calendarClientSelect.innerHTML = options;
  refs.generatorClientSelect.innerHTML = options;
  refs.analyticsClientSelect.innerHTML = `<option value="">All clients</option>${state.clients
    .map((c) => `<option value="${c.id}">${escapeHtml(c.business_name)}</option>`)
    .join("")}`;
  refs.paymentClientSelect.innerHTML = options;

  if (state.clients.length > 0) {
    const firstId = String(state.clients[0].id);
    if (!refs.generatorClientSelect.value) refs.generatorClientSelect.value = firstId;
    if (!refs.calendarClientSelect.value) refs.calendarClientSelect.value = firstId;
    if (!refs.paymentClientSelect.value) refs.paymentClientSelect.value = firstId;
  }
}

function renderClientCards() {
  if (!state.clients.length) {
    refs.clientsList.innerHTML = "<p class='muted'>No clients yet.</p>";
    return;
  }
  refs.clientsList.innerHTML = state.clients
    .map(
      (c) => `
        <article class="post-card" data-client-id="${c.id}">
          <div class="post-card-head">
            <strong>${escapeHtml(c.business_name)}</strong>
            <span class="post-status">${c.service_paused ? "Paused" : "Active"}</span>
          </div>
          <p class="muted">${escapeHtml(c.industry || "N/A")} | ${escapeHtml(c.website || "No website")}</p>
          <p class="muted">Connected: ${escapeHtml((c.connected_accounts || []).join(", ") || "None")}</p>
          <p class="muted">Next post: ${c.next_scheduled_post ? new Date(c.next_scheduled_post).toLocaleString() : "Not scheduled"}</p>
          <p class="muted">Engagement: Likes ${c.engagement_likes} | Shares ${c.engagement_shares} | Clicks ${c.engagement_clicks} | Followers +${c.follower_growth}</p>
          <p class="muted">Onboarding: ${escapeHtml(c.onboarding_status)}</p>
          <div class="row">
            <button class="secondary onboarding-btn" data-client-id="${c.id}" type="button">Complete Onboarding</button>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderDrafts() {
  if (!state.drafts.length) {
    refs.draftsList.innerHTML = "<p class='muted'>No drafts found.</p>";
    refs.previewCard.textContent = "No draft generated yet.";
    return;
  }
  const latest = state.drafts[0];
  refs.previewCard.innerHTML = `<span class="post-platform">${platformIcon(latest.platform)} ${escapeHtml(platformLabel(latest.platform))}</span><p>${escapeHtml(
    (latest.edited_text || latest.generated_text || "").slice(0, 450),
  )}</p>`;
  refs.draftsList.innerHTML = state.drafts
    .slice(0, 20)
    .map(
      (d) => `
        <article class="post-card" data-post-id="${d.id}">
          <div class="post-card-head">
            <span class="post-platform">${platformIcon(d.platform)} ${escapeHtml(platformLabel(d.platform))}</span>
            <span class="post-status">${escapeHtml(d.status)}</span>
          </div>
          <textarea class="draft-editor">${escapeHtml(d.edited_text || d.generated_text || "")}</textarea>
          <div class="row">
            <input class="schedule-input" type="datetime-local" value="${localDateInputValue(d.scheduled_at)}" />
            <button class="secondary save-btn" type="button">Save</button>
            <button class="secondary schedule-btn" type="button">Schedule</button>
          </div>
          <div class="row">
            <button class="secondary visual-btn" type="button">Generate Visual</button>
            <button class="secondary approval-btn" type="button">WhatsApp Approval</button>
            <button class="cta publish-btn" type="button">Publish</button>
          </div>
          <p class="muted">${escapeHtml(d.last_error || "")}</p>
        </article>
      `,
    )
    .join("");
}

function weekDates(days = 7) {
  const out = [];
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  for (let i = 0; i < days; i += 1) {
    const d = new Date(now);
    d.setDate(now.getDate() + i);
    out.push(d);
  }
  return out;
}

function dateKey(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

function renderCalendarBoard() {
  if (!refs.calendarBoard) return;
  const days = weekDates(7);
  const byDay = new Map(days.map((d) => [dateKey(d), []]));
  state.drafts
    .filter((d) => d.status === "scheduled" && d.scheduled_at)
    .forEach((d) => {
      const key = dateKey(d.scheduled_at);
      if (!byDay.has(key)) return;
      byDay.get(key).push(d);
    });

  refs.calendarBoard.innerHTML = days
    .map((day) => {
      const key = dateKey(day);
      const label = day.toLocaleDateString(undefined, { weekday: "short" });
      const dateLabel = day.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      const items = byDay.get(key) || [];
      return `
        <section class="calendar-day" data-date="${key}">
          <header class="calendar-day-header">
            <strong>${escapeHtml(label)}</strong>
            <span>${escapeHtml(dateLabel)}</span>
          </header>
          ${
            items.length
              ? items
                  .map(
                    (d) => `
                      <article class="calendar-post-card" draggable="true" data-post-id="${d.id}">
                        <span class="post-platform">${platformIcon(d.platform)} ${escapeHtml(platformLabel(d.platform))}</span>
                        <p>${escapeHtml((d.edited_text || d.generated_text || "").slice(0, 92))}</p>
                      </article>
                    `,
                  )
                  .join("")
              : "<p class='calendar-empty'>No posts</p>"
          }
        </section>
      `;
    })
    .join("");
}

function renderCalendarPosts() {
  const scheduled = state.drafts.filter((d) => d.status === "scheduled");
  renderCalendarBoard();
  if (!scheduled.length) {
    refs.calendarPostsList.innerHTML = "<p class='muted'>No scheduled posts yet.</p>";
    return;
  }
  refs.calendarPostsList.innerHTML = scheduled
    .slice(0, 25)
    .map(
      (d) => `
        <article class="post-card" data-post-id="${d.id}">
          <div class="post-card-head">
            <span class="post-platform">${platformIcon(d.platform)} ${escapeHtml(platformLabel(d.platform))}</span>
            <span class="post-status">scheduled</span>
          </div>
          <p class="muted">${d.scheduled_at ? new Date(d.scheduled_at).toLocaleString() : "No time set"}</p>
          <p>${escapeHtml((d.edited_text || d.generated_text || "").slice(0, 220))}</p>
        </article>
      `,
    )
    .join("");
}

function renderPayments() {
  if (!state.payments.length) {
    refs.paymentsList.innerHTML = "<p class='muted'>No payment records yet.</p>";
    return;
  }
  refs.paymentsList.innerHTML = state.payments
    .map(
      (p) => `
        <article class="post-card" data-payment-id="${p.id}">
          <strong>${escapeHtml(p.client_name)}</strong>
          <p class="muted">${escapeHtml(p.plan_name)} | ${p.currency} ${p.amount}</p>
          <p class="muted">Due: ${p.due_date ? new Date(p.due_date).toLocaleString() : "Not set"}</p>
          <div class="row">
            <select class="payment-status-select">
              ${["active", "past_due", "unpaid", "paused", "cancelled"]
                .map((s) => `<option value="${s}" ${p.subscription_status === s ? "selected" : ""}>${s}</option>`)
                .join("")}
            </select>
            <button class="secondary update-payment-btn" type="button">Update Status</button>
          </div>
        </article>
      `,
    )
    .join("");
}

function engagementScoreForPost(post) {
  const text = post.edited_text || post.generated_text || "";
  const hashBase = (post.id * 31 + text.length * 7 + String(post.platform || "").length * 13) % 100;
  let score = 30 + hashBase;
  if (post.status === "posted") score += 20;
  if (post.status === "scheduled") score += 8;
  return Math.min(99, score);
}

function renderTopPosts() {
  if (!refs.topPostsList) return;
  const shortlist = state.drafts
    .slice()
    .sort((a, b) => engagementScoreForPost(b) - engagementScoreForPost(a))
    .slice(0, 5);

  if (!shortlist.length) {
    refs.topPostsList.innerHTML = "<p class='muted'>No post performance data yet.</p>";
    return;
  }

  refs.topPostsList.innerHTML = shortlist
    .map(
      (d) => `
        <article class="post-card">
          <div class="post-card-head">
            <span class="post-platform">${platformIcon(d.platform)} ${escapeHtml(platformLabel(d.platform))}</span>
            <span class="post-status">Score ${engagementScoreForPost(d)}</span>
          </div>
          <p>${escapeHtml((d.edited_text || d.generated_text || "").slice(0, 160))}</p>
        </article>
      `,
    )
    .join("");
}

function renderSocialStatus(accounts) {
  const map = {};
  accounts.forEach((a) => {
    map[a.platform] = a;
  });
  refs.linkedinStatus.textContent = map.linkedin?.connected ? `Connected: ${map.linkedin.account_name || "LinkedIn"}` : "Not connected";
  refs.instagramStatus.textContent = map.instagram?.connected ? `Connected: ${map.instagram.account_name || "Instagram"}` : "Not connected";
  refs.facebookStatus.textContent = map.facebook?.connected ? `Connected: ${map.facebook.account_name || "Facebook"}` : "Not connected";
  refs.canvaStatus.textContent = map.canva?.connected ? `Connected: ${map.canva.account_name || "Canva"}` : "Not connected";
}

function renderTemplatePreview() {
  const selected = state.templates.find((t) => t.id === refs.canvaTemplateSelect.value) || state.templates[0];
  if (!selected) {
    refs.canvaTemplatePreview.textContent = "Template preview will appear here.";
    return;
  }
  refs.canvaTemplatePreview.innerHTML = `
    <strong>${escapeHtml(selected.name)}</strong>
    <p class="muted">${escapeHtml(selected.category)}</p>
    <p>${escapeHtml(selected.description || "")}</p>
  `;
}

async function loadDashboard() {
  const data = await api("/api/dashboard/overview");
  refs.statClients.textContent = String(data.total_clients || 0);
  refs.statScheduled.textContent = String(data.scheduled_posts || 0);
  const interactions = Number(state.analyticsTotals.likes || 0)
    + Number(state.analyticsTotals.shares || 0)
    + Number(state.analyticsTotals.comments || 0)
    + Number(state.analyticsTotals.clicks || 0);
  const basePosts = Math.max(1, state.drafts.length || Number(data.scheduled_posts || 1));
  const engagementRate = Math.min(99, Math.max(0, Math.round((interactions / (basePosts * 30)) * 100)));
  refs.statEngagement.textContent = `${engagementRate}%`;
  refs.statRevenue.textContent = `$${Number(data.revenue_total || 0).toFixed(2)}`;
  state.pendingApprovals = Number(data.pending_approvals || 0);
  refs.notifyCount.textContent = String(state.pendingApprovals);
  refs.dashboardHealthText.textContent = data.pending_approvals > 0
    ? `${data.pending_approvals} draft approval(s) pending`
    : "All systems healthy and queued posts are on track.";
  renderNotificationPanel();
}

async function loadClients() {
  state.clients = await api("/api/clients");
  populateClientSelects();
  renderClientCards();
}

async function loadDrafts() {
  const data = await api("/api/drafts");
  state.drafts = data.posts || [];
  renderDrafts();
  renderCalendarPosts();
  renderTopPosts();
  renderNotificationPanel();
}

async function loadPayments() {
  state.payments = await api("/api/payments");
  renderPayments();
  renderNotificationPanel();
}

async function loadCanvaTemplates() {
  state.templates = await api("/api/canva/templates");
  refs.canvaTemplateSelect.innerHTML = state.templates
    .map((t) => `<option value="${t.id}">${escapeHtml(t.name)} (${escapeHtml(t.category)})</option>`)
    .join("");
  renderTemplatePreview();
}

async function loadSocial() {
  const data = await api("/api/social-accounts");
  renderSocialStatus(data);
}

async function loadAnalytics() {
  const clientId = refs.analyticsClientSelect.value ? Number(refs.analyticsClientSelect.value) : null;
  const days = Number(refs.analyticsDaysSelect.value || 14);
  const query = clientId ? `?days=${days}&client_id=${clientId}` : `?days=${days}`;
  const data = await api(`/api/analytics/overview${query}`);
  state.analyticsTotals = data.totals || state.analyticsTotals;
  refs.analyticsLikes.textContent = String(data.totals.likes || 0);
  refs.analyticsShares.textContent = String(data.totals.shares || 0);
  if (refs.analyticsComments) refs.analyticsComments.textContent = String(data.totals.comments || 0);
  refs.analyticsClicks.textContent = String(data.totals.clicks || 0);
  refs.analyticsFollowers.textContent = String(data.totals.follower_growth || 0);

  const labels = data.series.map((x) => x.date);
  const likes = data.series.map((x) => x.likes);
  const shares = data.series.map((x) => x.shares);
  const comments = data.series.map((x) => x.comments);
  const clicks = data.series.map((x) => x.clicks);
  const followers = data.series.map((x) => x.follower_growth);

  if (state.analyticsChart) {
    state.analyticsChart.destroy();
  }
  state.analyticsChart = new Chart(refs.analyticsChart, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Likes", data: likes, borderColor: "#4f46e5", backgroundColor: "rgba(79,70,229,0.08)", tension: 0.35, fill: true },
        { label: "Shares", data: shares, borderColor: "#7c3aed", backgroundColor: "rgba(124,58,237,0.08)", tension: 0.35, fill: true },
        { label: "Comments", data: comments, borderColor: "#f59e0b", backgroundColor: "rgba(245,158,11,0.08)", tension: 0.35, fill: true },
        { label: "Clicks", data: clicks, borderColor: "#0ea5e9", backgroundColor: "rgba(14,165,233,0.08)", tension: 0.35, fill: true },
        { label: "Follower Growth", data: followers, borderColor: "#16a34a", backgroundColor: "rgba(22,163,74,0.08)", tension: 0.35, fill: true },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
      },
      scales: {
        x: { grid: { color: "rgba(148,163,184,0.12)" } },
        y: { grid: { color: "rgba(148,163,184,0.12)" }, beginAtZero: true },
      },
    },
  });
  renderTopPosts();
}

async function refreshAll() {
  withSkeleton(refs.statClients.parentElement);
  await Promise.all([loadClients(), loadDrafts(), loadPayments(), loadCanvaTemplates(), loadSocial()]);
  await Promise.all([loadAnalytics(), loadDashboard()]);
}

async function connectPlatform(path, label) {
  const data = await api(path, { method: "GET" });
  if (data.authorization_url) {
    window.location.href = data.authorization_url;
  } else {
    setBanner(`${label} connected.`);
    await loadSocial();
  }
}

async function signInWithProvider(provider) {
  const { error } = await state.sbClient.auth.signInWithOAuth({
    provider,
    options: { redirectTo: window.location.origin },
  });
  if (error) throw error;
}

async function sendMagicLink(email) {
  const normalized = String(email || "").trim().toLowerCase();
  if (!normalized || !normalized.includes("@")) throw new Error("Enter a valid email.");
  const { error } = await state.sbClient.auth.signInWithOtp({ email: normalized });
  if (error) throw error;
}

function handleSearchFilter() {
  const query = refs.globalSearchInput.value.trim().toLowerCase();
  const containers = refs.pages[state.activePage]?.querySelectorAll(".cards-list > *") || [];
  containers.forEach((node) => {
    const visible = !query || node.textContent.toLowerCase().includes(query);
    node.hidden = !visible;
  });
}

async function schedulePostToDate(postId, dateIso) {
  const target = new Date(`${dateIso}T09:00:00`);
  await api(`/api/posts/${postId}/schedule`, {
    method: "PATCH",
    body: JSON.stringify({ scheduled_at: target.toISOString() }),
  });
}

refs.navButtons.forEach((btn) => {
  btn.addEventListener("click", () => setActivePage(btn.dataset.page));
});

refs.mobileMenuBtn.addEventListener("click", () => refs.body.classList.toggle("menu-open"));
refs.globalSearchInput.addEventListener("input", handleSearchFilter);
refs.notifyBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  const shouldOpen = refs.notificationPanel.hidden;
  if (shouldOpen) {
    renderNotificationPanel();
    refs.notificationPanel.hidden = false;
    refs.notifyBtn.setAttribute("aria-expanded", "true");
    return;
  }
  closeNotificationPanel();
});
document.addEventListener("click", (event) => {
  if (refs.notificationPanel.hidden) return;
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (refs.notificationPanel.contains(target) || refs.notifyBtn.contains(target)) return;
  closeNotificationPanel();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeNotificationPanel();
});
refs.calendarBoard.addEventListener("dragstart", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const card = target.closest(".calendar-post-card");
  if (!(card instanceof HTMLElement)) return;
  const postId = Number(card.dataset.postId || 0);
  if (!postId) return;
  state.dragPostId = postId;
  card.classList.add("is-dragging");
});
refs.calendarBoard.addEventListener("dragend", () => {
  state.dragPostId = null;
  refs.calendarBoard.querySelectorAll(".calendar-day").forEach((node) => node.classList.remove("drag-over"));
});
refs.calendarBoard.addEventListener("dragover", (event) => {
  event.preventDefault();
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const day = target.closest(".calendar-day");
  if (!(day instanceof HTMLElement)) return;
  refs.calendarBoard.querySelectorAll(".calendar-day").forEach((node) => node.classList.remove("drag-over"));
  day.classList.add("drag-over");
});
refs.calendarBoard.addEventListener("drop", async (event) => {
  event.preventDefault();
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const day = target.closest(".calendar-day");
  if (!(day instanceof HTMLElement) || !state.dragPostId) return;
  const dateIso = day.dataset.date || "";
  if (!dateIso) return;
  refs.calendarBoard.querySelectorAll(".calendar-day").forEach((node) => node.classList.remove("drag-over"));
  try {
    await schedulePostToDate(state.dragPostId, dateIso);
    setBanner("Post rescheduled from calendar.");
    await Promise.all([loadDrafts(), loadDashboard()]);
  } catch (e) {
    setBanner(`Calendar drop failed: ${e.message}`);
  } finally {
    state.dragPostId = null;
  }
});

refs.googleLoginBtn.addEventListener("click", () => signInWithProvider("google").catch((e) => setBanner(`Login failed: ${e.message}`)));
refs.githubLoginBtn.addEventListener("click", () => signInWithProvider("github").catch((e) => setBanner(`Login failed: ${e.message}`)));
refs.loginGoogleMainBtn.addEventListener("click", () => signInWithProvider("google").catch((e) => setBanner(`Login failed: ${e.message}`)));
refs.loginGithubMainBtn.addEventListener("click", () => signInWithProvider("github").catch((e) => setBanner(`Login failed: ${e.message}`)));
refs.emailLoginBtn.addEventListener("click", async () => {
  const email = window.prompt("Email for magic link:", "") || "";
  try {
    await sendMagicLink(email);
    setBanner("Magic link sent.");
  } catch (e) {
    setBanner(`Magic link failed: ${e.message}`);
  }
});
refs.magicLinkSendBtn.addEventListener("click", async () => {
  try {
    await sendMagicLink(refs.magicEmailInput.value);
    setBanner("Magic link sent.");
  } catch (e) {
    setBanner(`Magic link failed: ${e.message}`);
  }
});
refs.magicEmailInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    refs.magicLinkSendBtn.click();
  }
});
refs.logoutBtn.addEventListener("click", async () => {
  if (!state.sbClient) return;
  await state.sbClient.auth.signOut();
  state.session = null;
  setAuthedUI(false);
});

refs.clientForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitBtn = refs.clientForm.querySelector('button[type="submit"]');
  setButtonLoading(submitBtn, true, "Saving...");
  try {
    await api("/api/clients", {
      method: "POST",
      body: JSON.stringify({
        business_name: refs.clientBusinessName.value,
        industry: refs.clientIndustry.value,
        social_handles: refs.clientHandles.value,
        website: refs.clientWebsite.value,
        brand_voice: refs.clientBrandVoice.value,
        keywords: refs.clientKeywords.value,
        topics_to_avoid: refs.clientAvoid.value,
        target_audience: refs.clientAudience.value,
        whatsapp_number: refs.clientWhatsapp.value,
        logo_url: refs.clientLogo.value,
        notes: refs.clientNotes.value,
      }),
    });
    refs.clientForm.reset();
    setBanner("Client saved.");
    await Promise.all([loadClients(), loadDashboard()]);
  } catch (e) {
    setBanner(`Client save failed: ${e.message}`);
  } finally {
    setButtonLoading(submitBtn, false);
  }
});

refs.clientsList.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.classList.contains("onboarding-btn")) return;
  const clientId = Number(target.dataset.clientId || 0);
  if (!clientId) return;
  try {
    await api(`/api/clients/${clientId}/onboarding/complete`, { method: "POST" });
    setBanner("Onboarding status updated.");
    await loadClients();
  } catch (e) {
    setBanner(`Onboarding update failed: ${e.message}`);
  }
});

refs.calendarForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitBtn = refs.calendarForm.querySelector('button[type="submit"]');
  const client = selectedClientFrom(refs.calendarClientSelect);
  if (!client) {
    setBanner("Select a client first.");
    return;
  }
  const platforms = selectedCheckboxValues(".calendarPlatform");
  setButtonLoading(submitBtn, true, "Building...");
  try {
    setBanner("Generating 7-day calendar...");
    await api("/api/content-calendar/generate", {
      method: "POST",
      body: JSON.stringify({
        client_id: client.id,
        content_seed: refs.calendarSeedInput.value,
        platforms,
        days: 7,
      }),
    });
    setBanner("7-day calendar generated.");
    await Promise.all([loadDrafts(), loadDashboard()]);
  } catch (e) {
    setBanner(`Calendar generation failed: ${e.message}`);
  } finally {
    setButtonLoading(submitBtn, false);
  }
});

refs.generatorForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitBtn = refs.generatorForm.querySelector('button[type="submit"]');
  const client = selectedClientFrom(refs.generatorClientSelect);
  const platforms = selectedCheckboxValues(".generatorPlatform");
  setButtonLoading(submitBtn, true, "Generating...");
  try {
    setBanner("Generating drafts...");
    const payload = {
      content: refs.generatorContentInput.value,
      business_name: client?.business_name || "",
      niche: client?.industry || "",
      audience: client?.target_audience || "",
      tone: client?.brand_voice || "",
      region: "Global",
      platforms,
    };
    if (client?.id) payload.client_id = client.id;

    await api("/api/agent/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setBanner("Drafts generated.");
    await Promise.all([loadDrafts(), loadDashboard()]);
  } catch (e) {
    setBanner(`Generation failed: ${e.message}`);
  } finally {
    setButtonLoading(submitBtn, false);
  }
});

refs.draftsList.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const card = target.closest(".post-card");
  if (!card) return;
  const postId = Number(card.dataset.postId || 0);
  if (!postId) return;
  const editor = card.querySelector(".draft-editor");
  const scheduleInput = card.querySelector(".schedule-input");
  const editedText = editor instanceof HTMLTextAreaElement ? editor.value : "";

  try {
    if (target.classList.contains("save-btn")) {
      await api(`/api/posts/${postId}`, { method: "PATCH", body: JSON.stringify({ edited_text: editedText }) });
      setBanner("Draft saved.");
      await loadDrafts();
      return;
    }
    if (target.classList.contains("schedule-btn")) {
      const value = scheduleInput instanceof HTMLInputElement ? scheduleInput.value : "";
      if (!value) throw new Error("Select schedule date/time first.");
      await api(`/api/posts/${postId}/schedule`, { method: "PATCH", body: JSON.stringify({ scheduled_at: new Date(value).toISOString() }) });
      setBanner("Post scheduled.");
      await Promise.all([loadDrafts(), loadDashboard()]);
      return;
    }
    if (target.classList.contains("approval-btn")) {
      await api(`/api/posts/${postId}/request-approval`, { method: "POST" });
      setBanner("WhatsApp approval request sent.");
      return;
    }
    if (target.classList.contains("visual-btn")) {
      const client = selectedClientFrom(refs.generatorClientSelect);
      const templateId = refs.canvaTemplateSelect.value;
      await api(`/api/posts/${postId}/generate-visual`, {
        method: "POST",
        body: JSON.stringify({
          template_id: templateId,
          caption_hint: editedText.slice(0, 220),
          brand_name: client?.business_name || "",
        }),
      });
      setBanner("Visual generated and attached.");
      return;
    }
    if (target.classList.contains("publish-btn")) {
      await api(`/api/posts/${postId}/publish`, { method: "POST", body: JSON.stringify({ confirm: true }) });
      card.classList.add("success-flash");
      setBanner("Post published.");
      await Promise.all([loadDrafts(), loadDashboard(), loadAnalytics()]);
    }
  } catch (e) {
    setBanner(`Action failed: ${e.message}`);
  }
});

refs.paymentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitBtn = refs.paymentForm.querySelector('button[type="submit"]');
  const client = selectedClientFrom(refs.paymentClientSelect);
  if (!client) {
    setBanner("Select a client for subscription.");
    return;
  }
  setButtonLoading(submitBtn, true, "Saving...");
  try {
    await api("/api/payments", {
      method: "POST",
      body: JSON.stringify({
        client_id: client.id,
        plan_name: refs.paymentPlanName.value,
        subscription_status: refs.paymentStatus.value,
        amount: Number(refs.paymentAmount.value || 0),
        currency: refs.paymentCurrency.value || "USD",
        due_date: refs.paymentDueDate.value ? new Date(refs.paymentDueDate.value).toISOString() : null,
        auto_pause_if_unpaid: refs.paymentAutoPause.checked,
      }),
    });
    setBanner("Subscription saved.");
    await Promise.all([loadPayments(), loadDashboard(), loadClients()]);
  } catch (e) {
    setBanner(`Subscription save failed: ${e.message}`);
  } finally {
    setButtonLoading(submitBtn, false);
  }
});

refs.paymentsList.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.classList.contains("update-payment-btn")) return;
  const card = target.closest(".post-card");
  if (!card) return;
  const paymentId = Number(card.dataset.paymentId || 0);
  const select = card.querySelector(".payment-status-select");
  const status = select instanceof HTMLSelectElement ? select.value : "";
  if (!paymentId || !status) return;
  try {
    await api(`/api/payments/${paymentId}`, { method: "PATCH", body: JSON.stringify({ subscription_status: status }) });
    setBanner("Payment status updated.");
    await Promise.all([loadPayments(), loadDashboard(), loadClients()]);
  } catch (e) {
    setBanner(`Payment update failed: ${e.message}`);
  }
});

refs.refreshAnalyticsBtn.addEventListener("click", () => loadAnalytics().catch((e) => setBanner(`Analytics failed: ${e.message}`)));
refs.analyticsClientSelect.addEventListener("change", () => loadAnalytics().catch((e) => setBanner(`Analytics failed: ${e.message}`)));
refs.analyticsDaysSelect.addEventListener("change", () => loadAnalytics().catch((e) => setBanner(`Analytics failed: ${e.message}`)));

refs.connectLinkedInBtn.addEventListener("click", () => connectPlatform("/api/linkedin/connect/start", "LinkedIn").catch((e) => setBanner(e.message)));
refs.connectInstagramBtn.addEventListener("click", () => connectPlatform("/api/instagram/connect/start", "Instagram").catch((e) => setBanner(e.message)));
refs.connectFacebookBtn.addEventListener("click", () => connectPlatform("/api/facebook/connect/start", "Facebook").catch((e) => setBanner(e.message)));
refs.connectCanvaBtn.addEventListener("click", () => connectPlatform("/api/canva/connect/start", "Canva").catch((e) => setBanner(e.message)));
refs.canvaTemplateSelect.addEventListener("change", renderTemplatePreview);

async function bootstrap() {
  const params = new URLSearchParams(window.location.search);
  const waToken = params.get("wa_approval_token");
  const waAction = params.get("wa_action");
  if (waToken && waAction) {
    try {
      setBanner("Applying WhatsApp approval action...");
      const response = await apiPublic(
        `/api/whatsapp/approval/resolve?token=${encodeURIComponent(waToken)}&action=${encodeURIComponent(waAction)}`,
        { method: "GET" },
      );
      setBanner(response.message || "Approval action completed.");
    } catch (e) {
      setBanner(`Approval action failed: ${e.message}`);
    }
    params.delete("wa_approval_token");
    params.delete("wa_action");
    const next = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname;
    window.history.replaceState({}, "", next);
  }

  if (!supabaseLib || typeof supabaseLib.createClient !== "function") {
    setBanner("Supabase library failed to load.");
    return;
  }

  state.sbClient = supabaseLib.createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
  state.sbClient.auth.onAuthStateChange(async (_event, session) => {
    state.session = session;
    if (!session) {
      setAuthedUI(false);
      return;
    }
    setAuthedUI(true, session.user?.email || "");
    try {
      await refreshAll();
    } catch (e) {
      setBanner(`Load failed: ${e.message}`);
    }
  });

  const { data } = await state.sbClient.auth.getSession();
  state.session = data.session;
  if (!state.session) {
    setAuthedUI(false);
    return;
  }

  setAuthedUI(true, state.session.user?.email || "");
  await refreshAll();

  if (params.get("linkedin") === "connected") setBanner("LinkedIn connected.");
  if (params.get("instagram") === "connected") setBanner("Instagram connected.");
  if (params.get("facebook") === "connected") setBanner("Facebook connected.");
  if (params.get("canva") === "connected") setBanner("Canva connected.");
  if (params.get("twitter") === "connected") setBanner("Twitter connected.");
  if (params.get("linkedin") === "error" || params.get("instagram") === "error" || params.get("facebook") === "error" || params.get("canva") === "error" || params.get("twitter") === "error") {
    setBanner(params.get("message") || "OAuth connection failed.");
  }
}

bootstrap().catch((e) => {
  setBanner(`Startup error: ${e.message}`);
});
