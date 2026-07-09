import { useEffect, useRef, useState } from 'react';
import ProgressBar from './ProgressBar.jsx';

// Configuration card for the v2 "unmix raw -> analyze" path.
//   - raw detector FCS selector (from the passed-in files list)
//   - controls choice: bundled demo controls (default) vs. session ./fcs controls
//   - Run button -> onUnmix({ raw_file_id, control_source, cytometer:'aurora' })
//   - a ProgressBar bound to the unmix job
//   - on completion, a "ready" line + an "Analyze this file" button -> onAnalyze()
//
// The unmixed file it produces then feeds the existing population-ID pipeline.
const DEMO_RAW = '[demo] PBMC_spectral_MIXED_raw.fcs';

export default function UnmixPanel({
  files = [],
  bundledCount = 15,
  disabled = false,
  running = false,
  job = null,
  result = null,
  onUnmix,
  onAnalyze,
}) {
  const [rawId, setRawId] = useState('');
  const [controlSource, setControlSource] = useState('bundled');
  const rawInited = useRef(false);

  // Default the raw selector to the bundled demo raw if present, else the first
  // file (once, so we don't clobber a user's choice on re-render).
  useEffect(() => {
    if (rawInited.current || files.length === 0) return;
    rawInited.current = true;
    const demo = files.find((f) => f.filename === DEMO_RAW);
    setRawId(demo ? demo.id : files[0].id);
  }, [files]);

  function handleRun() {
    if (!rawId) return;
    onUnmix({ raw_file_id: rawId, control_source: controlSource, cytometer: 'aurora' });
  }

  return (
    <div className="controls card">
      <h2 className="card__title">Unmix raw spectral data</h2>

      <p className="field__hint" style={{ marginTop: 0, marginBottom: 16 }}>
        Raw spectral detector data + single-stain controls &rarr; per-marker abundances
        via AutoSpectral. The unmixed file then feeds population identification.
      </p>

      {/* Raw file selector ------------------------------------------------- */}
      <label className="field">
        <span className="field__label">Raw detector FCS</span>
        {files.length > 0 ? (
          <select
            value={rawId}
            onChange={(e) => setRawId(e.target.value)}
            disabled={disabled}
            style={selectStyle}
          >
            {files.map((f) => (
              <option key={f.id} value={f.id}>
                {f.filename}
                {f.n_events ? ` — ${Number(f.n_events).toLocaleString()} events` : ''}
              </option>
            ))}
          </select>
        ) : (
          <span className="field__hint">
            No files registered yet — drop a raw acquisition into <code>./fcs</code>.
          </span>
        )}
        <span className="field__hint">
          The bundled <code>{DEMO_RAW}</code> works out of the box.
        </span>
      </label>

      {/* Controls choice --------------------------------------------------- */}
      <div className="field">
        <span className="field__label">Single-stain controls</span>
        <label style={radioRow}>
          <input
            type="radio"
            name="unmix-controls"
            value="bundled"
            checked={controlSource === 'bundled'}
            onChange={() => setControlSource('bundled')}
            disabled={disabled}
          />
          <span>Use bundled demo controls ({bundledCount})</span>
        </label>
        <label style={radioRow}>
          <input
            type="radio"
            name="unmix-controls"
            value="session"
            checked={controlSource === 'session'}
            onChange={() => setControlSource('session')}
            disabled={disabled}
          />
          <span>
            Use controls I added to <code>./fcs</code>
          </span>
        </label>
        <span className="field__hint">
          Bundled controls cover the demo panel (beads, unstained, dead-cell). Session
          controls are matched by filename (bead / unstained / control / dead).
        </span>
      </div>

      <button
        type="button"
        className="run-btn"
        onClick={handleRun}
        disabled={disabled || !rawId}
      >
        {running ? 'Unmixing…' : 'Run unmixing'}
      </button>

      {(running || job) && (
        <div style={{ marginTop: 16 }}>
          <ProgressBar job={job} />
        </div>
      )}

      {result && result.unmixed_file_id && (
        <div
          className="card"
          style={{
            margin: '16px 0 0',
            borderColor: '#2f9e6f',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <span>
            Unmixed &rarr; <strong>{result.unmixed_filename || '[unmixed] file'}</strong>{' '}
            ready
          </span>
          <button
            type="button"
            className="run-btn"
            onClick={onAnalyze}
            disabled={disabled}
          >
            Analyze this file
          </button>
        </div>
      )}
    </div>
  );
}

const selectStyle = {
  width: '100%',
  padding: '9px 11px',
  border: '1px solid var(--border)',
  borderRadius: '7px',
  fontSize: '0.95rem',
  background: '#fff',
  color: 'var(--fg)',
};

const radioRow = {
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  fontSize: '0.92rem',
  marginBottom: '6px',
};
