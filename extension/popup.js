const $ = (id) => document.getElementById(id);
let currentTab = null;
let paired = false;
let enabled = false;

async function activeChatTab() {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  if (!tab?.id || !/^https:\/\/(chatgpt\.com|chat\.openai\.com)\//.test(tab.url || "")) {
    throw new Error("Open a ChatGPT tab first");
  }
  return tab;
}

function showError(message) {
  $("error").hidden = !message;
  $("error").textContent = message || "";
}

async function sendToContent(message) {
  return await chrome.tabs.sendMessage(currentTab.id, message);
}

async function refresh() {
  showError("");
  try {
    currentTab = await activeChatTab();
    const state = await chrome.runtime.sendMessage({type: "lh-status", tabId: currentTab.id});
    if (!state?.ok) throw new Error(state?.error || "Could not read Local Hands status");
    paired = Boolean(state.bridge?.found && state.bridge?.paired);
    enabled = Boolean(state.tabEnabled);
    if (!state.bridge?.found) {
      $("status").textContent = "Bridge offline — start Local Hands Browser Bridge";
      $("pairing").hidden = true;
      $("controls").hidden = true;
      return;
    }
    $("status").textContent = paired
      ? `Connected on 127.0.0.1:${state.bridge.port} · paired`
      : `Bridge found on 127.0.0.1:${state.bridge.port} · pairing required`;
    $("pairing").hidden = paired;
    $("controls").hidden = !paired;
    $("toggle").textContent = enabled ? "Pause this ChatGPT tab" : "Enable this ChatGPT tab";
  } catch (error) {
    showError(error?.message || String(error));
  }
}

$("pair").addEventListener("click", async () => {
  showError("");
  try {
    const code = $("code").value.trim();
    if (!/^\d{6}$/.test(code)) throw new Error("Enter the six-digit code printed by start-bridge");
    const response = await chrome.runtime.sendMessage({type: "lh-pair", code});
    if (!response?.ok) throw new Error(response?.error || "Pairing failed");
    await refresh();
  } catch (error) {
    showError(error?.message || String(error));
  }
});

$("toggle").addEventListener("click", async () => {
  showError("");
  try {
    enabled = !enabled;
    const response = await chrome.runtime.sendMessage({type: "lh-enable-tab", tabId: currentTab.id, enabled});
    if (!response?.ok) throw new Error(response?.error || "Could not change tab state");
    await sendToContent({type: "lh-content-enable", enabled});
    await refresh();
  } catch (error) {
    enabled = !enabled;
    showError(error?.message || String(error));
  }
});

$("init").addEventListener("click", async () => {
  showError("");
  try {
    if (!enabled) {
      const response = await chrome.runtime.sendMessage({type: "lh-enable-tab", tabId: currentTab.id, enabled: true});
      if (!response?.ok) throw new Error(response?.error || "Could not enable tab");
      enabled = true;
      await sendToContent({type: "lh-content-enable", enabled: true});
    }
    const response = await sendToContent({type: "lh-content-init"});
    if (!response?.ok) throw new Error(response?.error || "Chat initialization failed");
    $("hint").textContent = response.already ? "This chat was already initialized." : "Initialization sent. After ChatGPT acknowledges it, send your task normally.";
    await refresh();
  } catch (error) {
    showError(error?.message || String(error));
  }
});

refresh();
