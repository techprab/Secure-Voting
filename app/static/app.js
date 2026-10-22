
"use strict";

let voterToken = null;
let candidates = [];
let previewToken = null;
let previewRanking = null;
let participationCode = null;
let submitting = false;

const $ = (id) => document.getElementById(id);

function show(id) {
  $(id).classList.remove("hidden");
}

function hide(id) {
  $(id).classList.add("hidden");
}

function setMessage(id, text, kind = "") {
  const el = $(id);
  el.textContent = text;
  el.className = `message ${kind}`;
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (voterToken) {
    headers.Authorization = `Bearer ${voterToken}`;
  }

  const response = await fetch(path, {
    ...options,
    headers,
    cache: "no-store"
  });

  const renewedToken = response.headers.get("X-Session-Token");
  if (renewedToken) voterToken = renewedToken;

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const error = new Error(
      data.error || data.msg || `Request failed (${response.status})`
    );
    error.status = response.status;
    throw error;
  }

  return data;
}

function explainError(error) {
  const descriptions = {
    unauthorized: "Credentials or session were rejected. Please sign in again.",
    ineligible_voter: "This account is not eligible to vote.",
    mission_access_denied: "This account does not meet the configured access requirements.",
    voting_closed: "The voting window is closed.",
    voting_window_unavailable: "The voting window is not configured correctly.",
    invalid_ranking: "The ranking is invalid. Please review the candidates.",
    confirmation_required: "Explicit confirmation is required.",
    invalid_preview_token: "Your preview has expired. Please preview the ballot again.",
    preview_mismatch: "The ranking differs from the preview. Please preview again.",
    invalid_nonce: "The submission nonce was rejected.",
    chain_broken: "Ballot integrity verification failed; counting is blocked.",
    already_voted: "This account has already participated."
  };

  if (error.status === 401) {
    voterToken = null;
    return "Your session expired or authentication failed. Sign in again.";
  }

  if (error.status === 503) {
    return "The service is unavailable. Check the server configuration and candidate approval.";
  }

  return descriptions[error.message] || error.message || "An unexpected error occurred.";
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();

  const button = $("login-button");
  button.disabled = true;
  setMessage("login-message", "Signing in…");

  try {
    const result = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("username").value.trim(),
        password: $("password").value
      })
    });

    voterToken = result.token;
    $("password").value = "";

    await loadBallot();

    hide("login-panel");
    hide("preview-panel");
    hide("receipt-panel");
    show("ballot-panel");
    setMessage("login-message", "");
  } catch (error) {
    voterToken = null;
    setMessage("login-message", explainError(error), "error");
  } finally {
    button.disabled = false;
  }
});

async function loadBallot() {
  const result = await api("/ballot");

  if (!Array.isArray(result.candidates) || result.candidates.length === 0) {
    throw new Error("No candidates are available for this ballot.");
  }

  candidates = result.candidates;
  $("division-label").textContent = `Assigned division: ${result.division}`;
  renderRanking();
}

function renderRanking() {
  const list = $("candidate-list");
  list.replaceChildren();

  candidates.forEach((candidate, index) => {
    const item = document.createElement("li");
    const row = document.createElement("div");
    row.className = "candidate-row";

    const info = document.createElement("div");
    info.className = "candidate-info";

    const name = document.createElement("div");
    name.className = "candidate-name";
    name.textContent = candidate.name;

    const position = document.createElement("span");
    position.className = "candidate-position";
    position.textContent = candidate.position;

    info.append(name, position);

    const up = document.createElement("button");
    up.type = "button";
    up.className = "move-button";
    up.textContent = "↑";
    up.disabled = index === 0;
    up.setAttribute("aria-label", `Move ${candidate.name} up`);
    up.addEventListener("click", () => moveCandidate(index, -1));

    const down = document.createElement("button");
    down.type = "button";
    down.className = "move-button";
    down.textContent = "↓";
    down.disabled = index === candidates.length - 1;
    down.setAttribute("aria-label", `Move ${candidate.name} down`);
    down.addEventListener("click", () => moveCandidate(index, 1));

    row.append(info, up, down);
    item.append(row);
    list.append(item);
  });
}

function moveCandidate(index, offset) {
  const target = index + offset;
  if (target < 0 || target >= candidates.length) return;

  [candidates[index], candidates[target]] =
    [candidates[target], candidates[index]];

  renderRanking();
}

$("preview-button").addEventListener("click", async () => {
  const button = $("preview-button");
  button.disabled = true;
  setMessage("ballot-message", "Preparing your ranking preview…");

  try {
    const preferences = candidates.map((candidate) => candidate.id);

    const result = await api("/ballot/preview", {
      method: "POST",
      body: JSON.stringify({ preferences })
    });

    previewToken = result.preview_token;
    previewRanking = preferences.slice();

    const list = $("preview-list");
    list.replaceChildren();

    result.summary.forEach((entry) => {
      const item = document.createElement("li");
      item.textContent = `${entry.rank}. ${entry.name}`;
      list.append(item);
    });

    $("confirm-checkbox").checked = false;
    $("submit-button").disabled = true;
    setMessage("ballot-message", "");
    setMessage("submit-message", "");

    hide("ballot-panel");
    show("preview-panel");
  } catch (error) {
    setMessage("ballot-message", explainError(error), "error");
  } finally {
    button.disabled = false;
  }
});

$("confirm-checkbox").addEventListener("change", () => {
  $("submit-button").disabled =
    !$("confirm-checkbox").checked || submitting;
});

$("back-button").addEventListener("click", () => {
  previewToken = null;
  previewRanking = null;
  $("confirm-checkbox").checked = false;

  hide("preview-panel");
  show("ballot-panel");
});

$("submit-button").addEventListener("click", async () => {
  if (
    submitting ||
    !$("confirm-checkbox").checked ||
    !previewToken ||
    !previewRanking
  ) {
    return;
  }

  submitting = true;
  $("submit-button").disabled = true;
  $("back-button").disabled = true;
  setMessage("submit-message", "Submitting your confirmed ballot…");

  try {
    const result = await api("/ballot/submit", {
      method: "POST",
      body: JSON.stringify({
        preferences: previewRanking,
        preview_token: previewToken,
        confirm: true,
        nonce: crypto.randomUUID()
      })
    });

    participationCode = result.participation_code;
    $("receipt-code").textContent = participationCode;

    voterToken = null;
    previewToken = null;
    previewRanking = null;

    hide("preview-panel");
    show("receipt-panel");
  } catch (error) {
    setMessage("submit-message", explainError(error), "error");
    $("submit-button").disabled = !$("confirm-checkbox").checked;
    $("back-button").disabled = false;
  } finally {
    submitting = false;
  }
});

$("check-receipt-button").addEventListener("click", async () => {
  if (!participationCode) return;

  const button = $("check-receipt-button");
  button.disabled = true;
  setMessage("receipt-message", "Verifying participation…");

  try {
    const result = await api(
      `/participation/${encodeURIComponent(participationCode)}`
    );

    setMessage(
      "receipt-message",
      result.voted
        ? "Participation confirmed. The receipt does not reveal your ranking."
        : "Participation could not be confirmed.",
      result.voted ? "success" : "error"
    );
  } catch (error) {
    setMessage("receipt-message", explainError(error), "error");
  } finally {
    button.disabled = false;
  }
});

$("logout-button").addEventListener("click", () => {
  voterToken = null;
  candidates = [];
  previewToken = null;
  previewRanking = null;
  participationCode = null;
  submitting = false;

  $("login-form").reset();
  $("candidate-list").replaceChildren();
  $("preview-list").replaceChildren();
  $("receipt-code").textContent = "";
  $("confirm-checkbox").checked = false;
  $("submit-button").disabled = true;
  $("back-button").disabled = false;

  setMessage("login-message", "");
  setMessage("ballot-message", "");
  setMessage("submit-message", "");
  setMessage("receipt-message", "");

  hide("ballot-panel");
  hide("preview-panel");
  hide("receipt-panel");
  show("login-panel");
});
