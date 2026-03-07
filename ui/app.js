const api = {
  get: async (path) => {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`GET ${path} failed`);
    return r.json();
  },
  post: async (path, body) => {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.message || data.error || `POST ${path} failed`);
    return data;
  },
};

let state = { loaded: false };

function $(id) {
  return document.getElementById(id);
}

function pretty(obj) {
  return JSON.stringify(obj || {}, null, 2);
}

function renderTranscript(data) {
  const list = $("transcriptList");
  list.innerHTML = "";
  const search = ($("searchBox").value || "").toLowerCase();
  const mode = $("verbosity").value;
  const rows = (data.transcript || []).filter((row) => {
    if (!search) return true;
    return (
      String(row.call_taker || "").toLowerCase().includes(search) ||
      String(row.caller || "").toLowerCase().includes(search)
    );
  });

  rows.forEach((row) => {
    const ct = document.createElement("div");
    ct.className = "bubble ct";
    ct.id = `turn-${row.turn}`;
    ct.innerHTML = `<div class="meta">Turn ${row.turn} · Call-Taker</div><div>${escapeHtml(row.call_taker || "")}</div>`;
    list.appendChild(ct);

    const caller = document.createElement("div");
    caller.className = "bubble caller";
    caller.innerHTML = `<div class="meta">Turn ${row.turn} · Caller</div><div>${escapeHtml(row.caller || "")}</div>`;
    if (mode === "detailed" && row.caller_metadata) {
      caller.innerHTML += `<div class="meta">metadata: ${escapeHtml(JSON.stringify(row.caller_metadata))}</div>`;
    }
    list.appendChild(caller);
  });
}

function renderInbox(targetId, reqs, isEscalation = false) {
  const root = $(targetId);
  root.innerHTML = "";
  if (!reqs || reqs.length === 0) {
    root.innerHTML = "<div class='meta'>No pending requests.</div>";
    return;
  }
  reqs.forEach((req) => {
    const el = document.createElement("div");
    el.className = "req";
    const esc = isEscalation || String(req.source || "").startsWith("escalation");
    el.innerHTML = `
      <div><strong>${req.request_id}</strong> · ${escapeHtml(req.action_class || "unknown")}</div>
      <div class="meta">source=${escapeHtml(req.source || "checkpoint")} approver=${escapeHtml(req.approver_role || "")}</div>
      <pre>${escapeHtml(JSON.stringify(req.proposed_payload || {}, null, 2))}</pre>
      <div class="actions">
        <button data-id="${req.request_id}" data-decision="approved">Approve</button>
        <button class="deny" data-id="${req.request_id}" data-decision="denied">Deny</button>
        <button class="edit" data-id="${req.request_id}" data-decision="edited_approved">Edit+Approve</button>
        ${esc ? '<button class="edit" data-id="' + req.request_id + '" data-decision="re_escalated">Re-escalate</button>' : ""}
      </div>
    `;
    root.appendChild(el);
  });

  root.querySelectorAll("button[data-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const requestId = btn.dataset.id;
      const decision = btn.dataset.decision;
      let payload = { request_id: requestId, decision };
      if (decision === "edited_approved") {
        const editedRaw = prompt("Edited payload JSON:", "{\"edited\":true}");
        try {
          payload.edited_payload = JSON.parse(editedRaw || "{}");
        } catch {
          alert("Invalid JSON");
          return;
        }
      }
      if (decision === "re_escalated") {
        payload.re_escalate_to = prompt("Re-escalate target role:", "commander") || "commander";
      }
      try {
        await api.post("/api/checkpoint/submit", payload);
        await refresh();
      } catch (err) {
        alert(err.message);
      }
    });
  });
}

function renderSop(snippets) {
  const root = $("sopView");
  root.innerHTML = "";
  snippets.forEach((s) => {
    const div = document.createElement("div");
    div.className = "snippet";
    div.innerHTML = `<strong>${escapeHtml(s.title || "SOP")}</strong><div class="meta">${escapeHtml(s.step || "")}</div><div>${escapeHtml(s.text || "")}</div>`;
    root.appendChild(div);
  });
}

function render(data) {
  state = data;
  $("metricsView").textContent = pretty({
    loaded: data.loaded,
    scenario_id: data.scenario_id,
    incident_id: data.incident_id,
    phase: data.phase,
    turn_count: data.metrics?.turn_count || 0,
    queue_depth: data.metrics?.checkpoint_queue_depth || 0,
    escalation_depth: data.metrics?.escalation_queue_depth || 0,
    avg_checkpoint_latency_ms: data.metrics?.avg_checkpoint_latency_ms || 0,
    event_count: data.metrics?.event_count || 0,
  });
  $("locationView").textContent = pretty(data.location_panel || {});
  $("cadView").textContent = pretty({
    cad_state: data.cad_state || {},
    record_version: data.record_version,
    field_versions: data.field_versions || {},
  });
  renderTranscript(data);
  renderInbox("checkpointInbox", data.checkpoint_inbox || [], false);
  renderInbox("escalationInbox", data.escalation_inbox || [], true);
}

async function refresh() {
  try {
    const data = await api.get("/api/state");
    render(data);
  } catch (err) {
    $("setupStatus").textContent = err.message;
  }
}

async function setupEpisode() {
  try {
    const body = {
      scenario_id: $("scenarioId").value,
      caller_fixture: $("callerFixture").value,
      incident_fixture: $("incidentFixture").value,
      qa_fixture: $("qaFixture").value,
      max_turns: Number($("maxTurns").value || 20),
    };
    const out = await api.post("/api/admin/load_start", body);
    $("setupStatus").textContent = `Loaded ${out.loaded.incident_id} and started episode`;
    await refresh();
  } catch (err) {
    $("setupStatus").textContent = err.message;
  }
}

async function postCaller() {
  const text = $("callerText").value.trim();
  if (!text) return;
  try {
    await api.post("/api/caller_turn", { text, metadata: { ui: true } });
    $("callerText").value = "";
    await refresh();
  } catch (err) {
    alert(err.message);
  }
}

async function postCallTaker() {
  const text = $("ctText").value.trim();
  if (!text) return;
  let cad = {};
  try {
    cad = JSON.parse($("ctCadJson").value || "{}");
  } catch {
    alert("Invalid CAD updates JSON");
    return;
  }
  try {
    await api.post("/api/calltaker_turn", { text, cad_updates: cad });
    $("ctText").value = "";
    await refresh();
  } catch (err) {
    alert(err.message);
  }
}

async function endCall() {
  try {
    await api.post("/api/end_call", {
      reason: $("endReason").value,
      reason_detail: $("endReasonDetail").value || null,
    });
    await refresh();
  } catch (err) {
    alert(err.message);
  }
}

async function fetchSop() {
  const type = $("sopIncidentType").value;
  const step = $("sopStep").value;
  try {
    const out = await api.get(`/api/sop?incident_type=${encodeURIComponent(type)}&step=${encodeURIComponent(step)}`);
    renderSop(out.snippets || []);
    await refresh();
  } catch (err) {
    alert(err.message);
  }
}

function jumpToTurn() {
  const n = Number($("jumpTurn").value || "0");
  if (!n) return;
  const el = document.getElementById(`turn-${n}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function bind() {
  $("refreshBtn").addEventListener("click", refresh);
  $("loadStartBtn").addEventListener("click", setupEpisode);
  $("callerSendBtn").addEventListener("click", postCaller);
  $("ctSendBtn").addEventListener("click", postCallTaker);
  $("endCallBtn").addEventListener("click", endCall);
  $("sopFetchBtn").addEventListener("click", fetchSop);
  $("jumpBtn").addEventListener("click", jumpToTurn);
  $("searchBox").addEventListener("input", () => renderTranscript(state));
  $("verbosity").addEventListener("change", () => renderTranscript(state));
}

bind();
refresh();
setInterval(refresh, 1200);

