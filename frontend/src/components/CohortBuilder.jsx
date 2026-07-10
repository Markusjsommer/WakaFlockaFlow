import { useEffect, useMemo, useState } from 'react';
import { cohortPreview } from '../api.js';

// Build a multi-sample cohort: pick files, tag each with an experimental group
// (and optional batch), preview the shared marker set, and launch one pooled
// FlowSOM + UMAP run. Different panels are fine; clustering uses the markers
// common to every selected sample.
export default function CohortBuilder({ sid, files = [], onRun, disabled }) {
  const [rows, setRows] = useState({}); // fileId -> { include, group, batch }
  const [nClusters, setNClusters] = useState(15);
  const [preview, setPreview] = useState(null);
  const [previewErr, setPreviewErr] = useState(null);

  const included = useMemo(
    () => files.filter((f) => rows[f.id] && rows[f.id].include),
    [files, rows]
  );

  function setRow(fileId, patch) {
    setRows((prev) => ({ ...prev, [fileId]: { ...(prev[fileId] || {}), ...patch } }));
  }

  // Live shared/dropped-marker preview whenever the selection changes.
  useEffect(() => {
    const ids = included.map((f) => f.id);
    if (!sid || ids.length === 0) {
      setPreview(null);
      setPreviewErr(null);
      return;
    }
    let cancelled = false;
    cohortPreview(sid, ids)
      .then((p) => {
        if (!cancelled) {
          setPreview(p);
          setPreviewErr(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setPreviewErr(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [sid, included.map((f) => f.id).join(',')]);

  const droppedEntries = preview ? Object.entries(preview.dropped_markers || {}) : [];

  function run() {
    const samples = included.map((f) => ({
      fcs_file_id: f.id,
      sample_label: f.filename,
      group: (rows[f.id].group || '').trim() || null,
      batch: (rows[f.id].batch || '').trim() || null,
    }));
    onRun({ samples, n_clusters: Number(nClusters) || 15, seed: 42 });
  }

  return (
    <div className="card">
      <h2 className="card__title">Build a cohort</h2>
      <p className="field__hint" style={{ marginTop: 0 }}>
        Select the samples to analyze together. They are clustered on one shared
        UMAP so populations are directly comparable across samples. Tag each with a
        group (e.g. control vs treated) to enable differential testing.
      </p>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
          <thead>
            <tr>
              <th style={th}></th>
              <th style={{ ...th, textAlign: 'left' }}>Sample</th>
              <th style={thNum}>Events</th>
              <th style={{ ...th, textAlign: 'left' }}>Group</th>
              <th style={{ ...th, textAlign: 'left' }}>Batch (optional)</th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => {
              const r = rows[f.id] || {};
              return (
                <tr key={f.id} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={td}>
                    <input
                      type="checkbox"
                      checked={!!r.include}
                      disabled={disabled}
                      onChange={(e) => setRow(f.id, { include: e.target.checked })}
                      aria-label={`Include ${f.filename}`}
                    />
                  </td>
                  <td style={td}>{f.filename}</td>
                  <td style={tdNum}>{Number(f.n_events || 0).toLocaleString()}</td>
                  <td style={td}>
                    <input
                      type="text"
                      value={r.group || ''}
                      disabled={disabled || !r.include}
                      placeholder="e.g. control"
                      onChange={(e) => setRow(f.id, { group: e.target.value })}
                      style={textInput}
                    />
                  </td>
                  <td style={td}>
                    <input
                      type="text"
                      value={r.batch || ''}
                      disabled={disabled || !r.include}
                      placeholder="optional"
                      onChange={(e) => setRow(f.id, { batch: e.target.value })}
                      style={textInput}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {included.length > 0 && (
        <div style={{ marginTop: 12 }}>
          {previewErr ? (
            <span style={{ color: 'var(--danger, #b00)' }}>Preview error: {previewErr}</span>
          ) : preview ? (
            <span className="field__hint">
              <strong>{included.length}</strong> samples ·{' '}
              <strong>{(preview.shared_markers || []).length}</strong> shared markers to
              cluster on
              {droppedEntries.length > 0 && (
                <>
                  {' '}· dropped from some samples:{' '}
                  {droppedEntries
                    .map(([s, ms]) => `${s} (${ms.length})`)
                    .join(', ')}
                </>
              )}
            </span>
          ) : (
            <span className="field__hint">Reading panels…</span>
          )}
        </div>
      )}

      <div style={{ display: 'flex', gap: 14, alignItems: 'flex-end', marginTop: 14, flexWrap: 'wrap' }}>
        <label className="field" style={{ maxWidth: 220 }}>
          <span className="field__label">Number of populations (metaclusters)</span>
          <input
            type="number"
            min={2}
            max={60}
            value={nClusters}
            disabled={disabled}
            onChange={(e) => setNClusters(e.target.value)}
            style={textInput}
          />
        </label>
        <button
          type="button"
          className="run-btn"
          disabled={disabled || included.length < 1}
          onClick={run}
        >
          Run cohort analysis
        </button>
      </div>
    </div>
  );
}

const th = {
  textAlign: 'center',
  padding: '8px 10px',
  borderBottom: '2px solid var(--border)',
  color: 'var(--muted)',
  fontWeight: 600,
  whiteSpace: 'nowrap',
};
const thNum = { ...th, textAlign: 'right' };
const td = { padding: '7px 10px', verticalAlign: 'middle' };
const tdNum = { ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' };
const textInput = {
  width: '100%',
  padding: '6px 8px',
  border: '1px solid var(--border)',
  borderRadius: '6px',
  fontSize: '0.9rem',
  background: 'var(--bg)',
  color: 'var(--fg)',
};
