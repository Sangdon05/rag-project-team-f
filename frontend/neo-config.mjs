/** Public HTTP settings. Never put credentials in browser code.
 * baseUrl comes from runtime-config.mjs, generated from FRONTEND_API_BASE_URL by
 * scripts/frontend/write_runtime_config.py. Without that file the local default is used. */
const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
const runtime = await import("./runtime-config.mjs").catch(() => ({}));

export const TEAM_API = Object.freeze({
  baseUrl: typeof runtime.API_BASE_URL === "string" && runtime.API_BASE_URL ? runtime.API_BASE_URL : DEFAULT_BASE_URL,
  suggestionsPath: "/api/v1/suggestion",
  askPath: "/api/v1/chat",
  documentPath: "/api/v1/documents/{source_ref_id}",
  maxMessages: 20,
  // No client-side character limit is assumed; the API validates its configured limits.
  maxContentLength: null,
  timeoutMs: 270000,
});
