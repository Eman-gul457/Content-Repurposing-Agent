const { API_BASE_URL, SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } = window.APP_CONFIG;
const supabaseLib = window.supabase;
let supabase = null;

const googleLoginBtn = document.getElementById("googleLoginBtn");
const logoutBtn = document.getElementById("logoutBtn");
const authState = document.getElementById("authState");
const socialSection = document.getElementById("socialSection");
const generatorSection = document.getElementById("generatorSection");
const draftsSection = document.getElementById("draftsSection");
const historySection = document.getElementById("historySection");
const contentInput = document.getElementById("contentInput");
const generateBtn = document.getElementById("generateBtn");
const statusText = document.getElementById("statusText");
const draftsList = document.getElementById("draftsList");
const historyList = document.getElementById("historyList");
const refreshHistoryBtn = document.getElementById("refreshHistoryBtn");
const linkedinStatus = document.getElementById("linkedinStatus");
const connectLinkedInBtn = document.getElementById("connectLinkedInBtn");

let currentSession = null;

function setAuthedUI(isAuthed, email = "") {
  googleLoginBtn.hidden = isAuthed;
  logoutBtn.hidden = !isAuthed;
  socialSection.hidden = !isAuthed;
  generatorSection.hidden = !isAuthed;
  draftsSection.hidden = !isAuthed;
  historySection.hidden = !isAuthed;
  authState.textContent = isAuthed ? `Logged in: ${email}` : "Not logged in";
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

function renderDraft(post) {
  const wrapper = document.createElement("div");
  wrapper.className = "post-card";
  wrapper.innerHTML = `
    <div class="post-title">${post.platform}</div>
    <div class="post-meta">Status: ${post.status}</div>
    <textarea class="post-editor" id="editor-${post.id}">${post.edited_text || post.generated_text}</textarea>
    <div class="row">
      <button id="save-${post.id}" class="secondary">Save Edit</button>
      <button id="approve-${post.id}">Approve</button>
      <button id="reject-${post.id}" class="warn">Reject</button>
      <button id="publish-${post.id}" class="secondary">Publish Now</button>
      <input type="datetime-local" id="schedule-${post.id}" value="${toLocalDateTimeInputValue(post.scheduled_at)}" />
      <button id="set-schedule-${post.id}" class="secondary">Schedule</button>
    </div>
    <div class="post-meta">${post.last_error ? `Error: ${post.last_error}` : ""}</div>
  `;

  wrapper.querySelector(`#save-${post.id}`).addEventListener("click", async () => {
    const editedText = wrapper.querySelector(`#editor-${post.id}`).value;
    await api(`/api/posts/${post.id}`, {
      method: "PATCH",
      body: JSON.stringify({ edited_text: editedText }),
    });
    await loadDrafts();
  });

  wrapper.querySelector(`#approve-${post.id}`).addEventListener("click", async () => {
    await api(`/api/posts/${post.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: "approved" }),
    });
    await loadDrafts();
  });

  wrapper.querySelector(`#reject-${post.id}`).addEventListener("click", async () => {
    await api(`/api/posts/${post.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: "rejected" }),
    });
    await loadDrafts();
  });

  wrapper.querySelector(`#publish-${post.id}`).addEventListener("click", async () => {
    await api(`/api/posts/${post.id}/publish`, {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    });
    await loadDrafts();
    await loadHistory();
  });

  wrapper.querySelector(`#set-schedule-${post.id}`).addEventListener("click", async () => {
    const value = wrapper.querySelector(`#schedule-${post.id}`).value;
    if (!value) throw new Error("Choose date/time first");
    const scheduledAt = new Date(value).toISOString();
    await api(`/api/posts/${post.id}/schedule`, {
      method: "PATCH",
      body: JSON.stringify({ scheduled_at: scheduledAt }),
    });
    await loadDrafts();
  });

  return wrapper;
}

async function loadSocial() {
  const data = await api("/api/social-accounts");
  const linkedin = data.find((x) => x.platform === "linkedin");
  linkedinStatus.textContent = linkedin?.connected ? `Connected: ${linkedin.account_name || "LinkedIn"}` : "Not connected";
}

async function loadDrafts() {
  const data = await api("/api/drafts");
  draftsList.innerHTML = "";
  if (!data.posts.length) {
    draftsList.innerHTML = "<p class='muted'>No drafts yet.</p>";
    return;
  }
  data.posts.forEach((post) => draftsList.appendChild(renderDraft(post)));
}

async function loadHistory() {
  const data = await api("/api/drafts");
  historyList.innerHTML = "";
  data.posts.forEach((post) => {
    const item = document.createElement("div");
    item.className = "history-item";
    item.innerHTML = `
      <strong>#${post.id}</strong> ${post.platform.toUpperCase()} - ${post.status}<br/>
      <small>${new Date(post.created_at).toLocaleString()}</small>
    `;
    historyList.appendChild(item);
  });
}

generateBtn.addEventListener("click", async () => {
  const content = contentInput.value.trim();
  if (!content) {
    statusText.textContent = "Please enter content.";
    return;
  }

  statusText.textContent = "Generating drafts...";
  try {
    await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    statusText.textContent = "Drafts generated.";
    await loadDrafts();
    await loadHistory();
  } catch (err) {
    statusText.textContent = `Error: ${err.message}`;
  }
});

refreshHistoryBtn.addEventListener("click", loadHistory);

connectLinkedInBtn.addEventListener("click", async () => {
  const data = await api("/api/linkedin/connect/start", { method: "GET" });
  window.location.href = data.authorization_url;
});

googleLoginBtn.addEventListener("click", async () => {
  try {
    if (!supabase) {
      throw new Error("Supabase client failed to initialize. Refresh and try again.");
    }
    statusText.textContent = "Redirecting to Google...";
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: window.location.origin,
      },
    });
    if (error) {
      throw error;
    }
  } catch (err) {
    statusText.textContent = `Login failed: ${err.message}`;
  }
});

logoutBtn.addEventListener("click", async () => {
  await supabase.auth.signOut();
  currentSession = null;
  setAuthedUI(false);
});

async function bootstrap() {
  if (!supabaseLib || typeof supabaseLib.createClient !== "function") {
    statusText.textContent = "Supabase library failed to load. Check internet and reload.";
    return;
  }
  supabase = supabaseLib.createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);

  const { data } = await supabase.auth.getSession();
  currentSession = data.session;

  if (!currentSession) {
    setAuthedUI(false);
    return;
  }

  const email = currentSession.user?.email || "";
  setAuthedUI(true, email);

  await Promise.all([loadSocial(), loadDrafts(), loadHistory()]);

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
}

supabase.auth.onAuthStateChange(async (_event, session) => {
  currentSession = session;
  if (session) {
    setAuthedUI(true, session.user?.email || "");
    await loadSocial();
    await loadDrafts();
    await loadHistory();
  } else {
    setAuthedUI(false);
  }
});

bootstrap().catch((err) => {
  statusText.textContent = `Startup error: ${err.message}`;
});
