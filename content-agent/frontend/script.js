const { API_BASE_URL, SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } = window.APP_CONFIG;
const supabaseLib = window.supabase;
let sbClient = null;
let currentSession = null;

const googleLoginBtn = document.getElementById("googleLoginBtn");
const logoutBtn = document.getElementById("logoutBtn");
const connectAccountsBtn = document.getElementById("connectAccountsBtn");
const topRunBtn = document.getElementById("topRunBtn");
const authState = document.getElementById("authState");
const tabNav = document.getElementById("tabNav");
const userChip = document.getElementById("userChip");
const userInitial = document.getElementById("userInitial");
const profileMenu = document.getElementById("profileMenu");
const profileMenuInitial = document.getElementById("profileMenuInitial");
const profileMenuEmail = document.getElementById("profileMenuEmail");
const profileMenuUserId = document.getElementById("profileMenuUserId");
const profileDashboardBtn = document.getElementById("profileDashboardBtn");
const profileDraftsBtn = document.getElementById("profileDraftsBtn");
const profileProfileBtn = document.getElementById("profileProfileBtn");
const profileLogoutBtn = document.getElementById("profileLogoutBtn");

const socialSection = document.getElementById("socialSection");
const generatorSection = document.getElementById("generatorSection");
const recentPlansSection = document.getElementById("recentPlansSection");
const researchSection = document.getElementById("researchSection");
const plansSection = document.getElementById("plansSection");
const draftsSection = document.getElementById("draftsSection");
const historySection = document.getElementById("historySection");
const schedulesSection = document.getElementById("schedulesSection");
const profileSection = document.getElementById("profileSection");
const profileDetailsSection = document.getElementById("profileDetailsSection");
const securitySection = document.getElementById("securitySection");

const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
const pageViews = {
  dashboard: document.getElementById("page-dashboard"),
  drafts: document.getElementById("page-drafts"),
  history: document.getElementById("page-history"),
  schedules: document.getElementById("page-schedules"),
  research: document.getElementById("page-research"),
  profile: document.getElementById("page-profile"),
};

const contentInput = document.getElementById("contentInput");
const businessNameInput = document.getElementById("businessNameInput");
const nicheInput = document.getElementById("nicheInput");
const audienceInput = document.getElementById("audienceInput");
const toneInput = document.getElementById("toneInput");
const regionInput = document.getElementById("regionInput");
const languagePrefInput = document.getElementById("languagePrefInput");
const generateBtn = document.getElementById("generateBtn");
const statusText = document.getElementById("statusText");

const researchList = document.getElementById("researchList");
const plansList = document.getElementById("plansList");
const recentPlansList = document.getElementById("recentPlansList");
const draftsList = document.getElementById("draftsList");
const historyList = document.getElementById("historyList");
const schedulesList = document.getElementById("schedulesList");

const refreshHistoryBtn = document.getElementById("refreshHistoryBtn");
const historyPlatformFilter = document.getElementById("historyPlatformFilter");
const historyDateFilter = document.getElementById("historyDateFilter");

const linkedinStatus = document.getElementById("linkedinStatus");
const connectLinkedInBtn = document.getElementById("connectLinkedInBtn");
const twitterStatus = document.getElementById("twitterStatus");
const connectTwitterBtn = document.getElementById("connectTwitterBtn");
const facebookStatus = document.getElementById("facebookStatus");
const instagramStatus = document.getElementById("instagramStatus");
const profileBigInitial = document.getElementById("profileBigInitial");
const profileDisplayName = document.getElementById("profileDisplayName");
const profileDisplayEmail = document.getElementById("profileDisplayEmail");
const profileFullNameInput = document.getElementById("profileFullNameInput");
const profileCompanyInput = document.getElementById("profileCompanyInput");
const profileRoleInput = document.getElementById("profileRoleInput");
const profileLocationInput = document.getElementById("profileLocationInput");
const profileWebsiteInput = document.getElementById("profileWebsiteInput");
const profileTimezoneInput = document.getElementById("profileTimezoneInput");
const profileBioInput = document.getElementById("profileBioInput");
const saveProfileBtn = document.getElementById("saveProfileBtn");
const profileStatusText = document.getElementById("profileStatusText");
const newPasswordInput = document.getElementById("newPasswordInput");
const confirmPasswordInput = document.getElementById("confirmPasswordInput");
const changePasswordBtn = document.getElementById("changePasswordBtn");
const sendResetEmailBtn = document.getElementById("sendResetEmailBtn");
const securityStatusText = document.getElementById("securityStatusText");
let profileMenuOpen = false;

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function refreshIcons() {
  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }
}

function renderStatusBadge(node, connected, label) {
  node.className = `status-badge ${connected ? "connected" : "disconnected"}`;
  node.innerHTML = `<span class="dot"></span>${escapeHtml(label)}`;
}

function setActiveTab(tabName) {
  Object.entries(pageViews).forEach(([name, section]) => {
    section.hidden = name !== tabName;
  });
  tabButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
}

function closeProfileMenu() {
  profileMenu.hidden = true;
  profileMenuOpen = false;
}

function openProfileMenu() {
  profileMenu.hidden = false;
  profileMenuOpen = true;
}

function setAuthedUI(isAuthed, email = "", userId = "") {
  googleLoginBtn.hidden = isAuthed;
  logoutBtn.hidden = !isAuthed;
  connectAccountsBtn.hidden = !isAuthed;
  topRunBtn.hidden = !isAuthed;
  userChip.hidden = !isAuthed;
  tabNav.hidden = !isAuthed;
  socialSection.hidden = !isAuthed;
  generatorSection.hidden = !isAuthed;
  recentPlansSection.hidden = !isAuthed;
  researchSection.hidden = !isAuthed;
  plansSection.hidden = !isAuthed;
  draftsSection.hidden = !isAuthed;
  historySection.hidden = !isAuthed;
  schedulesSection.hidden = !isAuthed;
  profileSection.hidden = !isAuthed;
  profileDetailsSection.hidden = !isAuthed;
  securitySection.hidden = !isAuthed;
  authState.textContent = isAuthed ? `Logged in as ${email}` : "Not logged in";
  userInitial.textContent = isAuthed ? (email[0] || "U").toUpperCase() : "U";
  profileMenuInitial.textContent = isAuthed ? (email[0] || "U").toUpperCase() : "U";
  profileMenuEmail.textContent = isAuthed ? email : "Not logged in";
  profileMenuUserId.textContent = isAuthed && userId ? `ID: ${userId}` : "-";
  profileBigInitial.textContent = isAuthed ? (email[0] || "U").toUpperCase() : "U";
  profileDisplayEmail.textContent = isAuthed ? email : "Not logged in";
  closeProfileMenu();
  setActiveTab("dashboard");
}

function applyProfileFromSession(session) {
  const email = session?.user?.email || "";
  const md = session?.user?.user_metadata || {};
  const fullName = md.full_name || md.name || "";
  profileDisplayName.textContent = fullName || "Your Profile";
  profileDisplayEmail.textContent = email || "Not logged in";
  profileMenuEmail.textContent = email || "Not logged in";
  profileFullNameInput.value = md.full_name || "";
  profileCompanyInput.value = md.company || "";
  profileRoleInput.value = md.role || "";
  profileLocationInput.value = md.location || "";
  profileWebsiteInput.value = md.website || "";
  profileTimezoneInput.value = md.timezone || "Asia/Karachi";
  profileBioInput.value = md.bio || "";
}

async function api(path, options = {}) {
  if (!currentSession?.access_token) throw new Error("Not authenticated");

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${currentSession.access_token}`,
      ...(options.headers || {}),
    },
  });

  const text = await res.text();
  let body = {};
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { raw: text };
  }

  if (!res.ok) {
    throw new Error(body.detail || body.message || `Request failed (${res.status})`);
  }
  return body;
}

function toLocalDateTimeInputValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const offset = d.getTimezoneOffset();
  const local = new Date(d.getTime() - offset * 60000);
  return local.toISOString().slice(0, 16);
}

function getSelectedPlatforms() {
  const boxes = Array.from(document.querySelectorAll('input[name="platform"]:checked'));
  return boxes.map((x) => x.value);
}

function getHistoryFilters() {
  return {
    platform: historyPlatformFilter.value || "all",
    date: historyDateFilter.value || "",
  };
}

function buildHistoryRows(posts) {
  if (!posts.length) {
    return "<p class='muted'>No matching history records.</p>";
  }

  const rows = posts
    .map(
      (post) => `
      <div class="history-item">
        <div class="history-row">
          <div>${new Date(post.created_at).toLocaleString()}</div>
          <div>${post.platform.toUpperCase()}</div>
          <div>${escapeHtml((post.edited_text || post.generated_text || "").slice(0, 85))}</div>
          <div>${post.status}</div>
          <button class="ghost view-draft-btn" data-id="${post.id}" type="button">View</button>
        </div>
      </div>
    `,
    )
    .join("");

  return `
    <div class="history-item history-head">
      <div class="history-row">
        <div>Date</div>
        <div>Platform</div>
        <div>Content</div>
        <div>Status</div>
        <div>Action</div>
      </div>
    </div>
    ${rows}
  `;
}

function renderDraft(post) {
  const isLinkedIn = post.platform === "linkedin";
  const isTwitter = post.platform === "twitter";
  const canPublish = isLinkedIn || isTwitter;
  const canSchedule = isLinkedIn;
  const canAttachMedia = isLinkedIn || isTwitter;
  const mediaAccept = isTwitter ? ".png,.jpg,.jpeg,.webp" : ".png,.jpg,.jpeg,.pdf";

  const wrapper = document.createElement("div");
  wrapper.className = "post-card";
  wrapper.innerHTML = `
    <div class="post-title">${post.platform}</div>
    <div class="post-meta">Status: ${post.status}</div>
    <textarea class="post-editor" id="editor-${post.id}">${escapeHtml(post.edited_text || post.generated_text)}</textarea>
    <div class="row">
      <button id="save-${post.id}" class="secondary" type="button">Save Edit</button>
      <button id="approve-${post.id}" type="button">Approve</button>
      <button id="reject-${post.id}" class="warn" type="button">Reject</button>
      <button id="publish-${post.id}" class="secondary" type="button" ${canPublish ? "" : "disabled"}>${isTwitter ? "Open in X" : "Publish Now"}</button>
      <input type="datetime-local" id="schedule-${post.id}" value="${toLocalDateTimeInputValue(post.scheduled_at)}" />
      <button id="set-schedule-${post.id}" class="secondary" type="button" ${canSchedule ? "" : "disabled"}>Schedule</button>
    </div>
    <div class="row">
      <input type="file" id="file-${post.id}" accept="${mediaAccept}" ${canAttachMedia ? "" : "disabled"} />
      <button id="upload-${post.id}" class="secondary" type="button" ${canAttachMedia ? "" : "disabled"}>Attach Media</button>
    </div>
    <div class="post-meta" id="media-${post.id}"></div>
    <div class="post-meta" id="feedback-${post.id}">${!canPublish ? "Publishing is only enabled for LinkedIn and Twitter." : (isTwitter ? "Twitter free mode: Open in X and post manually." : "")}</div>
    <div class="post-meta">${post.last_error ? `Error: ${escapeHtml(post.last_error)}` : ""}</div>
  `;

  const feedback = wrapper.querySelector(`#feedback-${post.id}`);
  const mediaBox = wrapper.querySelector(`#media-${post.id}`);
  const setFeedback = (text) => {
    feedback.textContent = text;
  };
  const setMedia = (text) => {
    mediaBox.textContent = text;
  };

  async function loadMedia() {
    try {
      const items = await api(`/api/posts/${post.id}/media`);
      if (!items.length) {
        setMedia("No media attached.");
        return;
      }
      setMedia(items.map((m) => `${m.file_name} (${m.mime_type})${m.platform_asset_id ? " [Asset ready]" : ""}`).join(" | "));
    } catch (err) {
      setMedia(`Media load failed: ${err.message}`);
    }
  }

  wrapper.querySelector(`#save-${post.id}`).addEventListener("click", async () => {
    try {
      setFeedback("Saving...");
      const editedText = wrapper.querySelector(`#editor-${post.id}`).value;
      await api(`/api/posts/${post.id}`, {
        method: "PATCH",
        body: JSON.stringify({ edited_text: editedText }),
      });
      setFeedback("Saved.");
      await loadDrafts();
      await loadHistory();
    } catch (err) {
      setFeedback(`Save failed: ${err.message}`);
    }
  });

  wrapper.querySelector(`#approve-${post.id}`).addEventListener("click", async () => {
    try {
      setFeedback("Approving...");
      await api(`/api/posts/${post.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: "approved" }),
      });
      setFeedback("Approved.");
      await refreshAllData();
    } catch (err) {
      setFeedback(`Approve failed: ${err.message}`);
    }
  });

  wrapper.querySelector(`#reject-${post.id}`).addEventListener("click", async () => {
    try {
      setFeedback("Rejecting...");
      await api(`/api/posts/${post.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: "rejected" }),
      });
      setFeedback("Rejected.");
      await refreshAllData();
    } catch (err) {
      setFeedback(`Reject failed: ${err.message}`);
    }
  });

  wrapper.querySelector(`#publish-${post.id}`).addEventListener("click", async () => {
    if (!canPublish) return;
    try {
      if (isTwitter) {
        const text = wrapper.querySelector(`#editor-${post.id}`).value.trim();
        if (!text) {
          setFeedback("Add text before publishing.");
          return;
        }
        const intentUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text.slice(0, 280))}`;
        window.open(intentUrl, "_blank", "noopener,noreferrer");
        await api(`/api/posts/${post.id}/manual-publish`, {
          method: "POST",
          body: JSON.stringify({ confirm: true }),
        });
        setFeedback("Opened X composer.");
      } else {
        setFeedback("Publishing to LinkedIn...");
        await api(`/api/posts/${post.id}/publish`, {
          method: "POST",
          body: JSON.stringify({ confirm: true }),
        });
        setFeedback("Published successfully.");
      }
      await refreshAllData();
    } catch (err) {
      setFeedback(`Publish failed: ${err.message}`);
    }
  });

  wrapper.querySelector(`#set-schedule-${post.id}`).addEventListener("click", async () => {
    if (!canSchedule) return;
    try {
      const value = wrapper.querySelector(`#schedule-${post.id}`).value;
      if (!value) {
        setFeedback("Choose date/time first.");
        return;
      }
      setFeedback("Scheduling...");
      await api(`/api/posts/${post.id}/schedule`, {
        method: "PATCH",
        body: JSON.stringify({ scheduled_at: new Date(value).toISOString() }),
      });
      setFeedback("Scheduled.");
      await refreshAllData();
    } catch (err) {
      setFeedback(`Schedule failed: ${err.message}`);
    }
  });

  wrapper.querySelector(`#upload-${post.id}`).addEventListener("click", async () => {
    if (!canAttachMedia) return;
    const input = wrapper.querySelector(`#file-${post.id}`);
    const file = input.files?.[0];
    if (!file) {
      setFeedback(isTwitter ? "Choose PNG/JPG/WEBP image first." : "Choose PNG/JPG/PDF first.");
      return;
    }
    try {
      setFeedback("Uploading media...");
      const b64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("Could not read file"));
        reader.readAsDataURL(file);
      });
      await api("/api/uploads", {
        method: "POST",
        body: JSON.stringify({
          post_id: post.id,
          file_name: file.name,
          mime_type: file.type || "application/octet-stream",
          content_base64: b64,
        }),
      });
      setFeedback("Media uploaded.");
      input.value = "";
      await loadMedia();
    } catch (err) {
      setFeedback(`Upload failed: ${err.message}`);
    }
  });

  loadMedia();
  return wrapper;
}

async function loadSocial() {
  const data = await api("/api/social-accounts");
  const linkedin = data.find((x) => x.platform === "linkedin");
  const twitter = data.find((x) => x.platform === "twitter");
  const facebook = data.find((x) => x.platform === "facebook");
  const instagram = data.find((x) => x.platform === "instagram");

  renderStatusBadge(linkedinStatus, !!linkedin?.connected, linkedin?.connected ? `Connected: ${linkedin.account_name || "LinkedIn"}` : "Not connected");
  renderStatusBadge(twitterStatus, !!twitter?.connected, twitter?.connected ? `Connected: ${twitter.account_name || "Twitter/X"}` : "Not connected");
  renderStatusBadge(facebookStatus, !!facebook?.connected, facebook?.connected ? `Connected: ${facebook.account_name || "Facebook"}` : "Not connected");
  renderStatusBadge(instagramStatus, !!instagram?.connected, instagram?.connected ? `Connected: ${instagram.account_name || "Instagram"}` : "Not connected");
}

async function loadResearch(limit = 20) {
  const data = await api(`/api/research?limit=${limit}`, { method: "GET" });
  researchList.innerHTML = "";
  if (!data.length) {
    researchList.innerHTML = "<p class='muted'>No research items yet. Run AI Agent to collect trends.</p>";
    return;
  }

  data.forEach((item, index) => {
    const node = document.createElement("div");
    node.className = "research-item";
    const relevance = Math.max(60, 98 - index * 5);
    const title = escapeHtml(item.title);
    const link = item.url
      ? `<a href="${item.url}" target="_blank" rel="noopener noreferrer">${title}</a>`
      : title;
    node.innerHTML = `
      <strong>${item.source.toUpperCase()}</strong><br/>
      ${link}<br/>
      <small>${escapeHtml(item.snippet || "")}</small><br/>
      <small>Relevance score: ${relevance}%</small><br/>
      <small>${new Date(item.created_at).toLocaleString()}</small>
    `;
    researchList.appendChild(node);
  });
}

async function loadPlans(limit = 30) {
  const data = await api(`/api/content-plans?limit=${limit}`, { method: "GET" });
  plansList.innerHTML = "";
  recentPlansList.innerHTML = "";

  if (!data.length) {
    plansList.innerHTML = "<p class='muted'>No plans yet. Run AI Agent to create schedule.</p>";
    recentPlansList.innerHTML = "<p class='muted'>No plans generated yet.</p>";
    return;
  }

  const recent = data.slice(0, 5);
  recent.forEach((item) => {
    const card = document.createElement("div");
    card.className = "plan-item";
    card.innerHTML = `
      <strong>${escapeHtml(item.theme)}</strong><br/>
      <small>Platform: ${item.platform.toUpperCase()}</small><br/>
      <small>Status: ${item.status}</small><br/>
      <small>Created: ${new Date(item.created_at).toLocaleString()}</small>
    `;
    recentPlansList.appendChild(card);
  });

  data.forEach((item) => {
    const node = document.createElement("div");
    node.className = "plan-item";
    const hasGeneratedImage = !!item.image_url && !item.image_url.includes("pollinations.ai/p/");
    node.innerHTML = `
      <strong>${item.platform.toUpperCase()}</strong> - ${item.status}<br/>
      <small>Planned: ${item.planned_for ? new Date(item.planned_for).toLocaleString() : "N/A"}</small><br/>
      <small>Theme: ${escapeHtml(item.theme)}</small><br/>
      <small>Angle: ${escapeHtml(item.post_angle)}</small><br/>
      <div class="plan-actions">
        <button class="secondary" id="gen-image-${item.id}" type="button">${hasGeneratedImage ? "Regenerate Visual" : "Generate Visual"}</button>
        ${hasGeneratedImage ? `<a href="${item.image_url}" target="_blank" rel="noopener noreferrer">Open Image</a>` : "<small>Image not generated yet.</small>"}
      </div>
      ${hasGeneratedImage ? `<img class="plan-preview" src="${item.image_url}" alt="Plan ${item.id} preview" />` : ""}
    `;
    plansList.appendChild(node);

    const btn = node.querySelector(`#gen-image-${item.id}`);
    if (btn) {
      btn.addEventListener("click", async () => {
        try {
          btn.disabled = true;
          btn.textContent = "Generating...";
          await api(`/api/content-plans/${item.id}/generate-image`, { method: "POST" });
          await loadPlans(limit);
        } catch (err) {
          statusText.textContent = `Image error: ${err.message}`;
          btn.disabled = false;
          btn.textContent = "Generate Visual";
        }
      });
    }
  });
}

async function loadDrafts() {
  const data = await api("/api/drafts");
  draftsList.innerHTML = "";

  const draftLike = data.posts.filter((x) => x.status !== "posted");
  if (!draftLike.length) {
    draftsList.innerHTML = "<p class='muted'>No drafts pending.</p>";
    return;
  }

  draftLike.forEach((post) => draftsList.appendChild(renderDraft(post)));
}

async function loadHistory() {
  const data = await api("/api/drafts");
  const filters = getHistoryFilters();

  const filtered = data.posts.filter((post) => {
    if (filters.platform !== "all" && post.platform !== filters.platform) return false;
    if (filters.date) {
      const postDay = new Date(post.created_at).toISOString().slice(0, 10);
      if (postDay !== filters.date) return false;
    }
    return true;
  });

  historyList.innerHTML = buildHistoryRows(filtered);
  historyList.querySelectorAll(".view-draft-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setActiveTab("drafts");
      statusText.textContent = `Viewing draft #${btn.dataset.id}`;
    });
  });
}

async function loadSchedules() {
  const data = await api("/api/drafts");
  schedulesList.innerHTML = "";
  const scheduled = data.posts.filter((x) => x.status === "scheduled");
  if (!scheduled.length) {
    schedulesList.innerHTML = "<p class='muted'>No scheduled posts yet.</p>";
    return;
  }

  scheduled.forEach((post) => {
    const node = document.createElement("div");
    node.className = "schedule-item";
    node.innerHTML = `
      <strong>${post.platform.toUpperCase()}</strong><br/>
      <small>Scheduled: ${post.scheduled_at ? new Date(post.scheduled_at).toLocaleString() : "N/A"}</small><br/>
      <small>${escapeHtml((post.edited_text || post.generated_text || "").slice(0, 130))}</small>
      <div class="row">
        <input type="datetime-local" id="edit-schedule-${post.id}" value="${toLocalDateTimeInputValue(post.scheduled_at)}" />
        <button class="secondary" id="save-schedule-${post.id}" type="button">Edit Schedule</button>
        <button class="warn" id="cancel-schedule-${post.id}" type="button">Cancel</button>
      </div>
    `;
    schedulesList.appendChild(node);

    node.querySelector(`#save-schedule-${post.id}`).addEventListener("click", async () => {
      try {
        const value = node.querySelector(`#edit-schedule-${post.id}`).value;
        if (!value) {
          statusText.textContent = "Select a valid date/time.";
          return;
        }
        await api(`/api/posts/${post.id}/schedule`, {
          method: "PATCH",
          body: JSON.stringify({ scheduled_at: new Date(value).toISOString() }),
        });
        statusText.textContent = "Schedule updated.";
        await refreshAllData();
      } catch (err) {
        statusText.textContent = `Schedule update failed: ${err.message}`;
      }
    });

    node.querySelector(`#cancel-schedule-${post.id}`).addEventListener("click", async () => {
      try {
        await api(`/api/posts/${post.id}/status`, {
          method: "PATCH",
          body: JSON.stringify({ status: "draft" }),
        });
        statusText.textContent = "Schedule canceled.";
        await refreshAllData();
      } catch (err) {
        statusText.textContent = `Cancel failed: ${err.message}`;
      }
    });
  });
}

async function refreshAllData() {
  await Promise.all([loadSocial(), loadResearch(), loadPlans(), loadDrafts(), loadHistory(), loadSchedules()]);
  refreshIcons();
}

generateBtn.addEventListener("click", async () => {
  const content = contentInput.value.trim();
  if (!content) {
    statusText.textContent = "Please enter content first.";
    return;
  }
  const platforms = getSelectedPlatforms();
  if (!platforms.length) {
    statusText.textContent = "Select at least one platform.";
    return;
  }

  const payload = {
    content,
    business_name: (businessNameInput.value || "").trim(),
    niche: (nicheInput.value || "").trim(),
    audience: (audienceInput.value || "").trim(),
    tone: (toneInput.value || "").trim(),
    region: (regionInput.value || "").trim(),
    platforms,
    language_pref: languagePrefInput.value || "english_urdu",
  };

  statusText.textContent = "Running workflow...";
  try {
    const result = await api("/api/agent/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    statusText.textContent = `Workflow complete. Run #${result.run_id}`;
    await refreshAllData();
    setActiveTab("drafts");
  } catch (err) {
    statusText.textContent = `Error: ${err.message}`;
  }
});

connectAccountsBtn.addEventListener("click", () => {
  setActiveTab("dashboard");
  socialSection.scrollIntoView({ behavior: "smooth", block: "start" });
});

topRunBtn.addEventListener("click", () => {
  setActiveTab("dashboard");
  contentInput.focus();
});

userChip.addEventListener("click", (event) => {
  event.stopPropagation();
  if (profileMenuOpen) {
    closeProfileMenu();
  } else {
    openProfileMenu();
  }
});

profileDashboardBtn.addEventListener("click", () => {
  setActiveTab("dashboard");
  closeProfileMenu();
});

profileDraftsBtn.addEventListener("click", () => {
  setActiveTab("drafts");
  closeProfileMenu();
});

profileProfileBtn.addEventListener("click", () => {
  setActiveTab("profile");
  closeProfileMenu();
});

refreshHistoryBtn.addEventListener("click", loadHistory);
historyPlatformFilter.addEventListener("change", loadHistory);
historyDateFilter.addEventListener("change", loadHistory);

connectLinkedInBtn.addEventListener("click", async () => {
  const data = await api("/api/linkedin/connect/start", { method: "GET" });
  window.location.href = data.authorization_url;
});

connectTwitterBtn.addEventListener("click", async () => {
  const data = await api("/api/twitter/connect/start", { method: "GET" });
  window.location.href = data.authorization_url;
});

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
});

googleLoginBtn.addEventListener("click", async () => {
  try {
    if (!sbClient) throw new Error("Supabase client failed to initialize.");
    authState.textContent = "Redirecting to Google...";
    const { error } = await sbClient.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
    if (error) throw error;
  } catch (err) {
    authState.textContent = `Login failed: ${err.message}`;
  }
});

logoutBtn.addEventListener("click", async () => {
  await sbClient.auth.signOut();
  currentSession = null;
  setAuthedUI(false);
});

profileLogoutBtn.addEventListener("click", async () => {
  await sbClient.auth.signOut();
  currentSession = null;
  setAuthedUI(false);
});

saveProfileBtn.addEventListener("click", async () => {
  if (!currentSession) return;
  try {
    profileStatusText.textContent = "Saving profile...";
    const data = {
      full_name: profileFullNameInput.value.trim(),
      company: profileCompanyInput.value.trim(),
      role: profileRoleInput.value.trim(),
      location: profileLocationInput.value.trim(),
      website: profileWebsiteInput.value.trim(),
      timezone: profileTimezoneInput.value.trim() || "Asia/Karachi",
      bio: profileBioInput.value.trim(),
    };
    const { data: updated, error } = await sbClient.auth.updateUser({ data });
    if (error) throw error;
    if (updated?.user) {
      currentSession = { ...currentSession, user: updated.user };
      applyProfileFromSession({ user: updated.user });
    }
    profileStatusText.textContent = "Profile updated.";
  } catch (err) {
    profileStatusText.textContent = `Save failed: ${err.message}`;
  }
});

changePasswordBtn.addEventListener("click", async () => {
  if (!currentSession) return;
  const pass = newPasswordInput.value.trim();
  const confirm = confirmPasswordInput.value.trim();
  if (pass.length < 8) {
    securityStatusText.textContent = "Password must be at least 8 characters.";
    return;
  }
  if (pass !== confirm) {
    securityStatusText.textContent = "Password confirmation does not match.";
    return;
  }
  try {
    securityStatusText.textContent = "Updating password...";
    const { error } = await sbClient.auth.updateUser({ password: pass });
    if (error) throw error;
    newPasswordInput.value = "";
    confirmPasswordInput.value = "";
    securityStatusText.textContent = "Password updated successfully.";
  } catch (err) {
    securityStatusText.textContent = `Password update failed: ${err.message}`;
  }
});

sendResetEmailBtn.addEventListener("click", async () => {
  if (!currentSession?.user?.email) return;
  try {
    securityStatusText.textContent = "Sending reset email...";
    const { error } = await sbClient.auth.resetPasswordForEmail(currentSession.user.email, {
      redirectTo: window.location.origin,
    });
    if (error) throw error;
    securityStatusText.textContent = "Reset email sent.";
  } catch (err) {
    securityStatusText.textContent = `Reset email failed: ${err.message}`;
  }
});

document.addEventListener("click", (event) => {
  if (!profileMenuOpen) return;
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (profileMenu.contains(target) || userChip.contains(target)) return;
  closeProfileMenu();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeProfileMenu();
  }
});

async function bootstrap() {
  if (!supabaseLib || typeof supabaseLib.createClient !== "function") {
    authState.textContent = "Supabase library failed to load. Refresh and try again.";
    return;
  }

  sbClient = supabaseLib.createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);

  sbClient.auth.onAuthStateChange(async (_event, session) => {
    currentSession = session;
    if (session) {
      setAuthedUI(true, session.user?.email || "", session.user?.id || "");
      applyProfileFromSession(session);
      await refreshAllData();
    } else {
      setAuthedUI(false);
    }
  });

  const { data } = await sbClient.auth.getSession();
  currentSession = data.session;

  if (!currentSession) {
    setAuthedUI(false);
    refreshIcons();
    return;
  }

  const email = currentSession.user?.email || "";
  setAuthedUI(true, email, currentSession.user?.id || "");
  applyProfileFromSession(currentSession);
  if (!toneInput.value) toneInput.value = "Professional";
  if (!regionInput.value) regionInput.value = "Pakistan";

  await refreshAllData();

  const params = new URLSearchParams(window.location.search);
  if (params.get("linkedin") === "connected") {
    statusText.textContent = "LinkedIn connected successfully.";
    await loadSocial();
    window.history.replaceState({}, "", window.location.pathname);
  }
  if (params.get("linkedin") === "error") {
    statusText.textContent = `LinkedIn error: ${params.get("message") || "Unknown"}`;
    window.history.replaceState({}, "", window.location.pathname);
  }
  if (params.get("twitter") === "connected") {
    statusText.textContent = "Twitter connected successfully.";
    await loadSocial();
    window.history.replaceState({}, "", window.location.pathname);
  }
  if (params.get("twitter") === "error") {
    statusText.textContent = `Twitter error: ${params.get("message") || "Unknown"}`;
    window.history.replaceState({}, "", window.location.pathname);
  }
}

bootstrap().catch((err) => {
  authState.textContent = `Startup error: ${err.message}`;
});
