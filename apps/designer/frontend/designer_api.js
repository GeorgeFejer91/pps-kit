export class DesignerApiError extends Error {
  constructor(message, { code = "request_failed", retryable = false, segmentKey = "", status = 0 } = {}) {
    super(message);
    this.name = "DesignerApiError";
    this.code = code;
    this.retryable = Boolean(retryable);
    this.segmentKey = segmentKey;
    this.status = Number(status || 0);
  }
}

export function createDesignerApi(request) {
  const post = (path, payload = {}) => request(path, { method: "POST", body: JSON.stringify(payload) });
  return Object.freeze({
    state: (options = {}) => request("/api/state", options),
    capabilities: () => request("/api/capabilities"),
    loadTemplate: (templateId) => post(`/api/templates/${encodeURIComponent(templateId)}/load`),
    loadProject: (projectId) => post(`/api/projects/${encodeURIComponent(projectId)}/load`),
    createCustomProject: (payload) => post("/api/project/new-custom", payload),
    customizeProject: (payload) => post("/api/project/customize", payload),
    saveDesign: (payload) => post("/api/design", payload),
    exportDataAcquisition: (payload) => post("/api/data-acquisition/export", payload),
    savePreparedProfile: (payload) => post("/api/profiles/save-prepared", payload),
    previewTrialRow: (payload) => post("/api/trials/preview-row", payload),
    previewAudioSource: (payload) => post("/api/audio/preview-source", payload),
    bakeStimulus: (payload) => post("/api/stimulus/bake", payload),
    acceptBlockCsv: (payload = {}) => post("/api/block-csv/accept", payload),
    editBlockCsv: () => post("/api/block-csv/edit"),
    previewRunSequence: (payload) => post("/api/run-sequence/preview", payload),
    prepareRunSequence: (payload) => post("/api/run-sequence/prepare", payload),
    exportRunSequenceBridge: (payload) => post("/api/run-sequence/export-bridge", payload),
    openRunner: (payload) => post("/api/run-sequence/open-runner", payload),
    openLocalFolder: (payload) => post("/api/local/open-folder", payload),
    importRunInstructions: (payload) => post("/api/run-instructions/import", payload),
    importAudio: (payload) => post("/api/audio/import", payload),
    job: (jobId) => request(`/api/jobs/${encodeURIComponent(jobId)}`),
    cancelJob: (jobId) => request(`/api/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" }),
  });
}
