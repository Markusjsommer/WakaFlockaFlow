import { useEffect, useMemo, useRef, useState } from 'react';
import {
  createSession,
  getDefaultSession,
  listFiles,
  uploadFiles,
  getPanelTemplate,
  startClustering,
  pollJob,
  listClusteringRuns,
  getClusteringRun,
  renamePopulation,
  exportUrl,
  flowjoUrl,
  listUnmixControls,
  startUnmix,
  reannotate,
} from './api.js';
import Controls from './components/Controls.jsx';
import ProgressBar from './components/ProgressBar.jsx';
import UmapScatter from './components/UmapScatter.jsx';
import PopulationTable from './components/PopulationTable.jsx';
import UnmixPanel from './components/UnmixPanel.jsx';
import PanelEditor from './components/PanelEditor.jsx';

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

// Resolve the ClusteringRun id from a finished job. Prefer the id the runner
// stashes in Job.result; fall back to the active/most-recent run in the list so
// we link regardless of the exact result key the backend uses.
async function resolveRunId(sid, finalJob) {
  const r = finalJob && finalJob.result;
  const fromResult =
    r && (r.clustering_run_id || r.run_id || r.clustering_run || r.id);
  if (fromResult) return fromResult;

  const runs = await listClusteringRuns(sid);
  if (Array.isArray(runs) && runs.length > 0) {
    const active = runs.find((x) => x.is_active);
    if (active) return active.id;
    const byDate = [...runs].sort(
      (a, b) => new Date(b.created_at) - new Date(a.created_at)
    );
    return byDate[0].id;
  }
  return null;
}

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [files, setFiles] = useState([]);
  const [channels, setChannels] = useState([]);
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState(null);
  const [run, setRun] = useState(null);
  const [error, setError] = useState(null);
  const [highlightMc, setHighlightMc] = useState(null);
  const initedRef = useRef(false);

  // v2 spectral-unmixing path -------------------------------------------------
  const [mode, setMode] = useState('analyze'); // 'analyze' (existing) | 'unmix'
  const [unmixJob, setUnmixJob] = useState(null);
  const [unmixRunning, setUnmixRunning] = useState(false);
  const [unmixResult, setUnmixResult] = useState(null);
  const [bundledCount, setBundledCount] = useState(15);
  const [selectedFileId, setSelectedFileId] = useState(null);

  // Drag-and-drop / browse FCS upload.
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [uploadNote, setUploadNote] = useState(null);

  async function handleFiles(fileList) {
    const fcs = [...(fileList || [])].filter((f) => /\.fcs$/i.test(f.name));
    if (!sessionId) return;
    if (fcs.length === 0) {
      setUploadNote('Only .fcs files are accepted.');
      return;
    }
    setUploading(true);
    setUploadNote(null);
    setError(null);
    try {
      const added = await uploadFiles(sessionId, fcs);
      setFiles((await listFiles(sessionId)) || []);
      if (added && added[0]) setSelectedFileId(added[0].id);
      const names = (added || []).map((a) => a.filename).join(', ');
      setUploadNote(`Added ${added.length} file${added.length === 1 ? '' : 's'}: ${names}`);
    } catch (e) {
      setError('Upload failed: ' + e.message);
    } finally {
      setUploading(false);
    }
  }

  // Create a session, load its files and the panel template on first mount.
  useEffect(() => {
    if (initedRef.current) return;
    initedRef.current = true;
    (async () => {
      try {
        let sid;
        try {
          sid = await getDefaultSession();
        } catch (_) {
          sid = await createSession();
        }
        setSessionId(sid);
        try {
          setFiles((await listFiles(sid)) || []);
        } catch (_) {
          /* files are informational; backend falls back to the demo file */
        }
        try {
          setChannels((await getPanelTemplate(sid)) || []);
        } catch (e) {
          setError('Could not read the FCS panel: ' + e.message);
        }
        try {
          const c = await listUnmixControls(sid);
          if (c && typeof c.count === 'number') setBundledCount(c.count);
        } catch (_) {
          /* controls listing is informational; default count stands */
        }
      } catch (e) {
        setError('Could not reach backend: ' + e.message);
      }
    })();
  }, []);

  async function pollUntilDone(jobId) {
    for (;;) {
      const j = await pollJob(jobId);
      setJob(j);
      if (j.status !== 'pending' && j.status !== 'running') return j;
      await delay(2000);
    }
  }

  async function handleRun({ fcs_file_id, markers, n_clusters }) {
    if (!sessionId) return;
    setError(null);
    setRun(null);
    setHighlightMc(null);
    setRunning(true);
    setJob({ status: 'pending', progress: 0, message: 'Submitting job…' });
    try {
      const params = {
        xdim: 10,
        ydim: 10,
        n_clusters,
        seed: 42,
        markers,
      };
      if (fcs_file_id) params.fcs_file_id = fcs_file_id;

      const jobId = await startClustering(sessionId, params);
      const finalJob = await pollUntilDone(jobId);
      if (finalJob.status === 'failed') {
        throw new Error(finalJob.error || 'Clustering job failed');
      }
      const rid = await resolveRunId(sessionId, finalJob);
      if (!rid) throw new Error('Job completed but no clustering run was found');
      const runData = await getClusteringRun(sessionId, rid);
      setRun(runData);
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  async function handlePatch(pid, body) {
    if (!run) return;
    try {
      const updated = await renamePopulation(sessionId, run.id, pid, body);
      setRun((prev) => ({
        ...prev,
        populations: prev.populations.map((p) =>
          p.id === pid ? { ...p, ...(updated || body) } : p
        ),
      }));
    } catch (e) {
      setError(e.message);
    }
  }

  // Called after the panel editor saves a new channel->marker mapping. If a run is
  // already on screen, re-annotate it in place so the population cell-type names
  // update instantly without re-clustering. Otherwise the mapping simply applies
  // on the next Run.
  async function handleMarkersApplied() {
    if (!sessionId || !run) return;
    try {
      const updated = await reannotate(sessionId, run.id);
      if (updated) setRun(updated);
    } catch (e) {
      setError(e.message);
    }
  }

  // Poll a job every 2s until it leaves the pending/running state.
  async function pollUnmixUntilDone(jobId) {
    for (;;) {
      const j = await pollJob(jobId);
      setUnmixJob(j);
      if (j.status !== 'pending' && j.status !== 'running') return j;
      await delay(2000);
    }
  }

  async function handleUnmix({ raw_file_id, control_source, cytometer }) {
    if (!sessionId) return;
    setError(null);
    setUnmixResult(null);
    setUnmixRunning(true);
    setUnmixJob({ status: 'pending', progress: 0, message: 'Submitting unmixing job…' });
    try {
      const jobId = await startUnmix(sessionId, {
        raw_file_id,
        control_source,
        cytometer,
      });
      const finalJob = await pollUnmixUntilDone(jobId);
      if (finalJob.status === 'failed') {
        throw new Error(finalJob.error || 'Unmixing job failed');
      }
      const result = finalJob.result || {};
      // Refetch files so the freshly-registered unmixed file is selectable.
      try {
        setFiles((await listFiles(sessionId)) || []);
      } catch (_) {
        /* non-fatal; the file still exists server-side */
      }
      if (result.unmixed_file_id) setSelectedFileId(result.unmixed_file_id);
      setUnmixResult(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setUnmixRunning(false);
    }
  }

  // Move from the unmix result to the existing analyze flow with the unmixed
  // file pre-selected.
  function handleAnalyzeUnmixed() {
    if (unmixResult && unmixResult.unmixed_file_id) {
      setSelectedFileId(unmixResult.unmixed_file_id);
    }
    setMode('analyze');
  }

  // Present the selected (e.g. just-unmixed) file first so the Controls card,
  // which defaults to files[0], picks it up when we remount it via `key`.
  const analyzeFiles = useMemo(() => {
    if (!selectedFileId) return files;
    const idx = files.findIndex((f) => f.id === selectedFileId);
    if (idx <= 0) return files;
    const copy = [...files];
    const [f] = copy.splice(idx, 1);
    copy.unshift(f);
    return copy;
  }, [files, selectedFileId]);

  const populations = run ? run.populations || [] : [];
  const totalCells = populations.reduce((s, p) => s + (Number(p.cell_count) || 0), 0);

  return (
    <div className="app">
      <header className="site-header">
        <div className="site-header__inner">
          <div className="wordmark">
            <span className="wordmark__mark" aria-hidden="true" />
            <span className="wordmark__name">WakaFlockaFlow</span>
            <span className="wordmark__tag">Spectral cytometry analysis</span>
          </div>
          {sessionId && (
            <div className="site-header__meta">
              <code title={sessionId}>session {String(sessionId).slice(0, 8)}</code>
            </div>
          )}
        </div>
      </header>

      <main className="app__body">
        <section className="page-intro">
          <h1>Automated cell population identification</h1>
          <p className="app__sub">
            Point at a spectral flow cytometry FCS file - WakaFlockaFlow transforms the
            events, clusters them with FlowSOM, embeds them with UMAP, and returns named
            cell populations with counts, frequencies, and median-marker profiles.
            Everything runs locally; no data leaves your machine.
          </p>
        </section>

        {/* Workflow tabs: population ID (v1) and raw→unmix→analyze (v2). */}
        <nav className="tabs" aria-label="Workflow">
          <button
            type="button"
            className={'tab' + (mode === 'analyze' ? ' is-active' : '')}
            onClick={() => setMode('analyze')}
            disabled={running || unmixRunning}
          >
            Analyze unmixed FCS
          </button>
          <button
            type="button"
            className={'tab' + (mode === 'unmix' ? ' is-active' : '')}
            onClick={() => setMode('unmix')}
            disabled={running || unmixRunning}
          >
            Unmix raw → analyze
          </button>
        </nav>

        {mode === 'analyze' ? (
          <>
            <div
              className={'dropzone' + (dragOver ? ' is-drag' : '')}
              onDragOver={(e) => {
                e.preventDefault();
                if (!dragOver) setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                handleFiles(e.dataTransfer.files);
              }}
            >
              <input
                id="fcs-input"
                type="file"
                accept=".fcs"
                multiple
                style={{ display: 'none' }}
                onChange={(e) => handleFiles(e.target.files)}
              />
              <label htmlFor="fcs-input" className="dropzone__label">
                {uploading
                  ? 'Uploading…'
                  : 'Drag & drop FCS files here, or click to browse'}
              </label>
              <span className="field__hint">
                Files are saved locally and registered for analysis. Nothing leaves your
                machine. (Browsers can't read a file's disk path, so the contents are
                uploaded and stored server-side.)
              </span>
              {uploadNote && <span className="dropzone__note">{uploadNote}</span>}
            </div>

            <PanelEditor
              sid={sessionId}
              fileId={selectedFileId || (analyzeFiles[0] && analyzeFiles[0].id)}
              onApplied={handleMarkersApplied}
            />

            <Controls
              key={selectedFileId || 'default'}
              onRun={handleRun}
              disabled={running || !sessionId}
              files={analyzeFiles}
              channels={channels}
            />

            {(running || job) && <ProgressBar job={job} />}
          </>
        ) : (
          <UnmixPanel
            files={files}
            bundledCount={bundledCount}
            disabled={unmixRunning || !sessionId}
            running={unmixRunning}
            job={unmixJob}
            result={unmixResult}
            onUnmix={handleUnmix}
            onAnalyze={handleAnalyzeUnmixed}
          />
        )}

        {error && (
          <div className="error card" role="alert">
            <strong>Error:</strong> {error}
          </div>
        )}

        {mode === 'analyze' && run && (
          <section className="results">
            <div className="headline card">
              <div className="headline__big">
                Identified <strong>{populations.length}</strong>{' '}
                {populations.length === 1 ? 'population' : 'populations'}
              </div>
              <div className="headline__detail">
                across {totalCells.toLocaleString()} clustered cells · FlowSOM +
                UMAP
              </div>
            </div>

            <div className="card">
              <UmapScatter
                umap={run.umap || []}
                populations={populations}
                highlightMc={highlightMc}
              />
            </div>

            <div className="card">
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 12,
                  gap: 12,
                  flexWrap: 'wrap',
                }}
              >
                <h2 className="card__title" style={{ margin: 0 }}>
                  Populations
                </h2>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <a
                    className="run-btn"
                    href={exportUrl(sessionId, run.id)}
                    style={{ textDecoration: 'none' }}
                  >
                    Export results (.zip)
                  </a>
                  <a
                    className="run-btn"
                    href={flowjoUrl(sessionId, run.id)}
                    title="Augmented FCS + workspace.wsp + GatingML — opens in FlowJo as named gates"
                    style={{
                      textDecoration: 'none',
                      background: '#fff',
                      color: 'var(--accent-dark)',
                      border: '1px solid var(--accent)',
                      boxShadow: 'none',
                    }}
                  >
                    Export for FlowJo (.wsp)
                  </a>
                </div>
              </div>
              <PopulationTable
                populations={populations}
                onPatch={handlePatch}
                onHover={setHighlightMc}
                onLeave={() => setHighlightMc(null)}
                disabled={running}
              />
              <p className="field__hint" style={{ marginTop: 10 }}>
                Click a colour swatch to recolour a population, or edit a name and press
                Enter. Hover a row to highlight its cells in the UMAP. The export bundle
                contains population tables, UMAP coordinates, the panel, and full run
                provenance for reproducibility.
              </p>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
