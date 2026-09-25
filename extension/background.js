const PORTS = [8766, 8767, 8768, 8769, 8770];
const HEADER = {"X-Local-Hands-Extension": "1"};
const STORAGE = {
  token: "lh_bridge_token",
  port: "lh_bridge_port",
  enabledTabs: "lh_enabled_tabs"
};

async function getStored(keys) {
  return await chrome.storage.local.get(keys);
}

async function setStored(values) {
  await chrome.storage.local.set(values);
}

async function request(port, path, {method = "GET", body, token, timeoutMs = 2500} = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = {...HEADER};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const response = await fetch(`http://127.0.0.1:${port}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store"
    });
    let data = null;
    try { data = await response.json(); } catch { data = null; }
    if (!response.ok) {
      const message = data?.error || `HTTP ${response.status}`;
      throw new Error(message);
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

async function discover() {
  const stored = await getStored([STORAGE.token, STORAGE.port]);
  const token = stored[STORAGE.token] || null;
  const preferred = Number(stored[STORAGE.port]);
  const ports = preferred && PORTS.includes(preferred)
    ? [preferred, ...PORTS.filter((p) => p !== preferred)]
    : PORTS;
  for (const port of ports) {
    try {
      const data = await request(port, "/v1/status", {token, timeoutMs: 900});
      await setStored({[STORAGE.port]: port});
      return {found: true, port, paired: Boolean(data.paired), info: data};
    } catch {
      // Try next supported port.
    }
  }
  return {found: false, paired: false};
}

async function pair(code) {
  const state = await discover();
  if (!state.found) throw new Error("Local Hands browser bridge was not found on ports 8766-8770");
  const data = await request(state.port, "/v1/pair", {
    method: "POST",
    body: {code: String(code || "").trim()},
    timeoutMs: 3000
  });
  if (!data?.token) throw new Error("Pairing response did not include a token");
  await setStored({[STORAGE.token]: data.token, [STORAGE.port]: state.port});
  return {paired: true, port: state.port, fingerprint: data.token_fingerprint};
}

async function bridgeBatch(command) {
  const stored = await getStored([STORAGE.token, STORAGE.port]);
  const token = stored[STORAGE.token];
  if (!token) throw new Error("Local Hands Companion is not paired");
  let port = Number(stored[STORAGE.port]);
  if (!PORTS.includes(port)) {
    const state = await discover();
    if (!state.found) throw new Error("Local Hands browser bridge is offline");
    port = state.port;
  }
  return await request(port, "/v1/batch", {
    method: "POST",
    token,
    body: {
      request_id: command.id,
      calls: command.calls,
      stop_on_error: command.stop_on_error !== false
    },
    timeoutMs: 305000
  });
}

async function tabMap() {
  const stored = await getStored([STORAGE.enabledTabs]);
  return stored[STORAGE.enabledTabs] || {};
}

async function setTabEnabled(tabId, enabled) {
  const map = await tabMap();
  if (enabled) map[String(tabId)] = {enabled: true, at: Date.now()};
  else delete map[String(tabId)];
  await setStored({[STORAGE.enabledTabs]: map});
  return Boolean(enabled);
}

async function isTabEnabled(tabId) {
  const map = await tabMap();
  return Boolean(map[String(tabId)]?.enabled);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    const type = message?.type;
    if (type === "lh-status") {
      const bridge = await discover();
      const tabId = message.tabId ?? sender.tab?.id;
      sendResponse({ok: true, bridge, tabEnabled: tabId ? await isTabEnabled(tabId) : false});
      return;
    }
    if (type === "lh-pair") {
      sendResponse({ok: true, ...(await pair(message.code))});
      return;
    }
    if (type === "lh-enable-tab") {
      const tabId = message.tabId ?? sender.tab?.id;
      if (!tabId) throw new Error("No ChatGPT tab was supplied");
      await setTabEnabled(tabId, Boolean(message.enabled));
      sendResponse({ok: true, enabled: Boolean(message.enabled)});
      return;
    }
    if (type === "lh-tab-state") {
      const tabId = message.tabId ?? sender.tab?.id;
      sendResponse({ok: true, enabled: tabId ? await isTabEnabled(tabId) : false});
      return;
    }
    if (type === "lh-execute") {
      const tabId = sender.tab?.id;
      if (!tabId || !(await isTabEnabled(tabId))) throw new Error("Local Hands is paused for this tab");
      sendResponse({ok: true, payload: await bridgeBatch(message.command)});
      return;
    }
    throw new Error(`Unknown Local Hands message: ${type}`);
  })().catch((error) => sendResponse({ok: false, error: error?.message || String(error)}));
  return true;
});
