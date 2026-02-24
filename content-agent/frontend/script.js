const { API_BASE_URL, SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } = window.APP_CONFIG;
const supabaseLib = window.supabase;
let sbClient = null;

const googleLoginBtn = document.getElementById("googleLoginBtn");
const logoutBtn = document.getElementById("logoutBtn");
const authState = document.getElementById("authState");
const socialSection = document.getElementById("socialSection");
const generatorSection = document.getElementById("generatorSection");
const researchSection = document.getElementById("researchSection");
const plansSection = document.getElementById("plansSection");
const draftsSection = document.getElementById("draftsSection");
const historySection = document.getElementById("historySection");
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
const draftsList = document.getElementById("draftsList");
const historyList = document.getElementById("historyList");
const refreshHistoryBtn = document.getElementById("refreshHistoryBtn");
const linkedinStatus = document.getElementById("linkedinStatus");
const connectLinkedInBtn = document.getElementById("connectLinkedInBtn");
const twitterStatus = document.getElementById("twitterStatus");
const connectTwitterBtn = document.getElementById("connectTwitterBtn");
const facebookStatus = document.getElementById("facebookStatus");
const instagramStatus = document.getElementById("instagramStatus");

let currentSession = null;

function setAuthedUI(isAuthed, email = "") {
  googleLoginBtn.hidden = isAuthed;
  logoutBtn.hidden = !isAuthed;
  socialSection.hidden = !isAuthed;
  generatorSection.hidden = !isAuthed;
  researchSection.hidden = !isAuthed;
  plansSection.hidden = !isAuthed;
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
    <textarea class="post-editor" id="editor-${post.id}">${post.edited_text || post.generated_text}</textarea>
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
    <div class="post-meta" id="feedback-${post.id}">${!canPublish ? "Publishing is only enabled for LinkedIn and Twitter right now." : (isTwitter ? "Twitter free mode: Open in X and post manually." : "")}</div>
    <div class="post-meta">${post.last_error ? `Error: ${post.last_error}` : ""}</div>
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
      setMedia(
        items
          .map((m) => `${m.file_name} (${m.mime_type})${m.platform_asset_id ? " [Asset ready]" : ""}`)
          .join(" | "),
      );
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
      await loadDrafts();
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
      await loadDrafts();
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
          setFeedback("Add some text before publishing.");
          return;
        }

        const intentUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text.slice(0, 280))}`;
        window.open(intentUrl, "_blank", "noopener,noreferrer");
        await api(`/api/posts/${post.id}/manual-publish`, {
          method: "POST",
          body: JSON.stringify({ confirm: true }),
        });
        setFeedback("Opened X composer. Attach images there and click Post.");
      } else {
        setFeedback("Publishing to LinkedIn...");
        await api(`/api/posts/${post.id}/publish`, {
          method: "POST",
          body: JSON.stringify({ confirm: true }),
        });
        setFeedback("Published successfully.");
      }
      await loadDrafts();
      await loadHistory();
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
      const scheduledAt = new Date(value).toISOString();
      await api(`/api/posts/${post.id}/schedule`, {
        method: "PATCH",
        body: JSON.stringify({ scheduled_at: scheduledAt }),
      });
      setFeedback("Scheduled.");
      await loadDrafts();
    } catch (err) {
      setFeedback(`Schedule failed: ${err.message}`);
    }
  });

  wrapper.querySelector(`#upload-${post.id}`).addEventListener("click", async () => {
    if (!canAttachMedia) return;
    const input = wrapper.querySelector(`#file-${post.id}`);
    const file = input.files?.[0];
    if (!file) {
      setFeedback(isTwitter ? "Choose a PNG/JPG/WEBP image first." : "Choose a PNG, JPG, or PDF file first.");
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

function getSelectedPlatforms() {
  const boxes = Array.from(document.querySelectorAll('input[name="platform"]:checked'));
  return boxes.map((x) => x.value);
}

async function loadSocial() {
  const data = await api("/api/social-accounts");
  const linkedin = data.find((x) => x.platform === "linkedin");
  const twitter = data.find((x) => x.platform === "twitter");
  const facebook = data.find((x) => x.platform === "facebook");
  const instagram = data.find((x) => x.platform === "instagram");
  linkedinStatus.textContent = linkedin?.connected ? `Connected: ${linkedin.account_name || "LinkedIn"}` : "Not connected";
  twitterStatus.textContent = twitter?.connected ? `Connected: ${twitter.account_name || "Twitter"}` : "Not connected";
  facebookStatus.textContent = facebook?.connected ? `Connected: ${facebook.account_name || "Facebook"}` : "Not connected";
  instagramStatus.textContent = instagram?.connected ? `Connected: ${instagram.account_name || "Instagram"}` : "Not connected";
}

async function loadResearch(limit = 20) {
  const data = await api(`/api/research?limit=${limit}`, { method: "GET" });
  researchList.innerHTML = "";
  if (!data.length) {
    researchList.innerHTML = "<p class='muted'>No research items yet. Run workflow to collect trends.</p>";
    return;
  }
  data.forEach((item) => {
    const node = document.createElement("div");
    node.className = "research-item";
    const link = item.url ? `<a href="${item.url}" target="_blank" rel="noopener noreferrer">${item.title}</a>` : item.title;
    node.innerHTML = `
      <strong>${item.source.toUpperCase()}</strong><br/>
      ${link}<br/>
      <small>${item.snippet || ""}</small><br/>
      <small>${new Date(item.created_at).toLocaleString()}</small>
    `;
    researchList.appendChild(node);
  });
}

async function loadPlans(limit = 25) {
  const data = await api(`/api/content-plans?limit=${limit}`, { method: "GET" });
  plansList.innerHTML = "";
  if (!data.length) {
    plansList.innerHTML = "<p class='muted'>No plans yet. Run workflow to create weekly schedule.</p>";
    return;
  }
  data.forEach((item) => {
    const node = document.createElement("div");
    node.className = "plan-item";
    const hasGeneratedImage = !!item.image_url && !item.image_url.includes("pollinations.ai/p/");
    node.innerHTML = `
      <strong>${item.platform.toUpperCase()}</strong> - ${item.status}<br/>
      <small>Planned: ${item.planned_for ? new Date(item.planned_for).toLocaleString() : "N/A"}</small><br/>
      <small>Theme: ${item.theme}</small><br/>
      <small>Angle: ${item.post_angle}</small><br/>
      <div class="plan-actions">
        <button class="secondary" id="gen-image-${item.id}" type="button">Generate Image</button>
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
          btn.textContent = "Generate Image";
        }
      });
    }
  });
}

async function loadDrafts() {
  const data = await api("/api/drafts");
  draftsList.innerHTML = "";
  if (!data.posts.length) {
    draftsList.innerHTML = "<p class='muted'>No drafts yet.</p>";
    return;
  }

  const latestByPlatform = [];
  const seen = new Set();
  for (const post of data.posts) {
    if (seen.has(post.platform)) continue;
    seen.add(post.platform);
    latestByPlatform.push(post);
  }

  latestByPlatform.forEach((post) => draftsList.appendChild(renderDraft(post)));
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

  statusText.textContent = "Running research + planning + creation...";
  try {
    const result = await api("/api/agent/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    statusText.textContent = `Workflow complete. Run #${result.run_id}`;
    await loadResearch();
    await loadPlans();
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

connectTwitterBtn.addEventListener("click", async () => {
  const data = await api("/api/twitter/connect/start", { method: "GET" });
  window.location.href = data.authorization_url;
});

googleLoginBtn.addEventListener("click", async () => {
  try {
    if (!sbClient) {
      throw new Error("Supabase client failed to initialize. Refresh and try again.");
    }
    authState.textContent = "Redirecting to Google...";
    const { error } = await sbClient.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: window.location.origin,
      },
    });
    if (error) {
      throw error;
    }
  } catch (err) {
    authState.textContent = `Login failed: ${err.message}`;
  }
});

logoutBtn.addEventListener("click", async () => {
  await sbClient.auth.signOut();
  currentSession = null;
  setAuthedUI(false);
});

async function bootstrap() {
  if (!supabaseLib || typeof supabaseLib.createClient !== "function") {
    authState.textContent = "Supabase library failed to load. Check internet and reload.";
    return;
  }
  sbClient = supabaseLib.createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);

  sbClient.auth.onAuthStateChange(async (_event, session) => {
    currentSession = session;
    if (session) {
      setAuthedUI(true, session.user?.email || "");
      await loadSocial();
      await loadResearch();
      await loadPlans();
      await loadDrafts();
      await loadHistory();
    } else {
      setAuthedUI(false);
    }
  });

  const { data } = await sbClient.auth.getSession();
  currentSession = data.session;

  if (!currentSession) {
    setAuthedUI(false);
    return;
  }

  const email = currentSession.user?.email || "";
  setAuthedUI(true, email);
  if (!toneInput.value) toneInput.value = "Professional";
  if (!regionInput.value) regionInput.value = "Pakistan";

  await Promise.all([loadSocial(), loadResearch(), loadPlans(), loadDrafts(), loadHistory()]);

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
  statusText.textContent = `Startup error: ${err.message}`;
});
