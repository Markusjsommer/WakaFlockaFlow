import { useEffect, useMemo, useRef, useState } from 'react';
import {
  createSession,
  getDefaultSession,
  listFiles,
  getPanelTemplate,
  startClustering,
  pollJob,
  listClusteringRuns,
  getClusteringRun,
  renamePopulation,
  exportUrl,
  listUnmixControls,
  startUnmix,
} from './api.js';
import Controls from './components/Controls.jsx';
import ProgressBar from './components/ProgressBar.jsx';
import UmapScatter from './components/UmapScatter.jsx';
import PopulationTable from './components/PopulationTable.jsx';
import UnmixPanel from './components/UnmixPanel.jsx';

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
      <main className="app__body">
        <header className="app__header">
          <h1>WakaFlakaFlow — Automated Cell Population Identification</h1>
          <p className="app__sub">
            Point at an FCS file, transform, and let FlowSOM cluster and UMAP-embed the
            cells into named populations with counts, percentages and median-marker
            profiles. Everything runs locally — no data leaves your machine.
          </p>
          {sessionId && (
            <p className="app__meta">
              Session <code>{sessionId}</code>
              {channels.length > 0 && (
                <>
                  {' · '}
                  {channels.length} channels
                  {' · '}
                  {channels.filter((c) => !c.is_scatter).length} markers
                </>
              )}
            </p>
          )}
        </header>

        {/* Mode switch: keep the existing flow under the first tab, add the
            v2 unmixing path under the second. */}
        <div
          className="engine-toggle"
          style={{ display: 'flex', margin: '16px 0 0', flexWrap: 'wrap' }}
        >
          <button
            type="button"
            className={'engine-toggle__btn' + (mode === 'analyze' ? ' is-active' : '')}
            onClick={() => setMode('analyze')}
            disabled={running || unmixRunning}
          >
            Analyze unmixed FCS
          </button>
          <button
            type="button"
            className={'engine-toggle__btn' + (mode === 'unmix' ? ' is-active' : '')}
            onClick={() => setMode('unmix')}
            disabled={running || unmixRunning}
          >
            Unmix raw → analyze
          </button>
        </div>

        {mode === 'analyze' ? (
          <>
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
                <a
                  className="run-btn"
                  href={exportUrl(sessionId, run.id)}
                  style={{ textDecoration: 'none' }}
                >
                  Export results (.zip)
                </a>
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
