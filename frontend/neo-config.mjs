/** Public HTTP settings. Configure the server origin here; never put credentials in browser code. */
export const TEAM_API = Object.freeze({
  baseUrl: "http://127.0.0.1:8000",
  suggestionsPath: "/api/v1/suggestion",
  askPath: "/api/v1/chat",
  documentPath: "/api/v1/documents/{source_ref_id}",
  maxMessages: 20,
  // No client-side character limit is assumed; the API validates its configured limits.
  maxContentLength: null,
  timeoutMs: 270000,
});
