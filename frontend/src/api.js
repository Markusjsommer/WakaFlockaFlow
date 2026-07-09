// Thin fetch wrappers around the FastAPI backend (prefix /api/v1).
// In dev the Vite server proxies /api -> http://localhost:8001 (see vite.config.js).
// In the packaged image the SPA is served by the same backend, so these relative
// paths work unchanged.

const BASE = '/api/v1';

async function req(path, opts) {
  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    let detail = '';
    try {
      detail = await res.text();
    } catch (_) {
      /* ignore */
    }
    throw new Error(`${res.status} ${res.statusText}${detail ? ': ' + detail : ''}`);
  }
  return res.json();
}

// POST /sessions -> { session_id }
export async function createSession() {
  const data = await req('/sessions', { method: 'POST' });
  return data.session_id;
}

// GET /default-session -> { session_id }
// The single-user default session that owns the bundled demo + ./fcs files.
export async function getDefaultSession() {
  const data = await req('/default-session');
  return data.session_id;
}

// GET /sessions/{sid}/files -> [{ id, filename, n_events, n_channels }]
export async function listFiles(sid) {
  return req(`/sessions/${sid}/files`);
}

// GET /sessions/{sid}/panel/template
//   -> { channels: [{ channel_name, marker_label, is_scatter, include_in_clustering }] }
export async function getPanelTemplate(sid) {
  const data = await req(`/sessions/${sid}/panel/template`);
  return data.channels || [];
}

// POST /sessions/{sid}/clustering -> { job_id }
// params: { fcs_file_id?, xdim?, ydim?, n_clusters?, seed?, markers?: [channel names] }
export async function startClustering(sid, params) {
  const data = await req(`/sessions/${sid}/clustering`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return data.job_id;
}

// GET /jobs/{job_id} -> { id, type, status, progress, message, error, result }
export async function pollJob(jobId) {
  return req(`/jobs/${jobId}`);
}

// ---- Spectral unmixing (v2) --------------------------------------------------

// GET /sessions/{sid}/unmix/controls -> { bundled: [names], count }
// Lists the bundled demo single-stain controls so the UI can offer them.
export async function listUnmixControls(sid) {
  return req(`/sessions/${sid}/unmix/controls`);
}

// POST /sessions/{sid}/unmix -> { job_id }
// params: { raw_file_id, control_source: 'bundled'|'session', cytometer? }
// Kicks off AutoSpectral unmixing (raw detector FCS + single-stain controls ->
// a per-marker unmixed FCS registered back into the session). Poll with pollJob;
// the finished Job.result carries { unmixed_file_id, unmixed_filename }.
export async function startUnmix(sid, params) {
  const data = await req(`/sessions/${sid}/unmix`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return data.job_id;
}

// GET /sessions/{sid}/clustering -> [{ id, status, n_populations, created_at, is_active }]
export async function listClusteringRuns(sid) {
  return req(`/sessions/${sid}/clustering`);
}

// GET /sessions/{sid}/clustering/{rid}
//   -> { id, status, params, n_populations, umap: [[x,y,mc]], populations: [...] }
export async function getClusteringRun(sid, rid) {
  return req(`/sessions/${sid}/clustering/${rid}`);
}

// PATCH /sessions/{sid}/clustering/{rid}/populations/{pid} body { name?, color? }
//   -> updated population
export async function renamePopulation(sid, rid, pid, body) {
  return req(`/sessions/${sid}/clustering/${rid}/populations/${pid}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// Direct-download URL for the reproducibility .zip bundle (GET streams a zip).
export function exportUrl(sid, rid) {
  return `${BASE}/sessions/${sid}/clustering/${rid}/export`;
}
