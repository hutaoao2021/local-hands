(() => {
  const MAX_CALLS = 8;

  function parseCommand(text) {
    if (typeof text !== "string") return null;
    const trimmed = text.trim();
    if (!trimmed.startsWith("{")) return null;
    let obj;
    try {
      obj = JSON.parse(trimmed);
    } catch {
      return null;
    }
    if (!obj || obj.local_hands !== 1) return null;
    if (typeof obj.id !== "string" || !obj.id.trim() || obj.id.length > 128) return null;
    if (!Array.isArray(obj.calls) || obj.calls.length < 1 || obj.calls.length > MAX_CALLS) return null;
    for (const call of obj.calls) {
      if (!call || typeof call.tool !== "string" || !call.tool.trim()) return null;
      if (call.arguments !== undefined && (call.arguments === null || typeof call.arguments !== "object" || Array.isArray(call.arguments))) return null;
    }
    return {
      local_hands: 1,
      id: obj.id.trim(),
      calls: obj.calls.map((call) => ({tool: call.tool.trim(), arguments: call.arguments || {}})),
      stop_on_error: obj.stop_on_error !== false
    };
  }

  function compactResult(payload) {
    const clean = {
      local_hands_result: 1,
      id: payload.request_id || null,
      ok: Boolean(payload.ok),
      results: Array.isArray(payload.results) ? payload.results : []
    };
    return `[LOCAL_HANDS_RESULT]\n${JSON.stringify(clean)}\n[/LOCAL_HANDS_RESULT]`;
  }

  globalThis.LocalHandsProtocol = {parseCommand, compactResult};
})();
