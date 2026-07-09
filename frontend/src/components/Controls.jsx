import { useEffect, useRef, useState } from 'react';

// Configuration card for a clustering run:
//   - file selector (from listFiles, default first)
//   - marker panel (checkbox list from panel/template, non-scatter pre-checked, all/none)
//   - metacluster-count presets (5/10/15/20/25, default 10)
//   - Run button
//
// Emits onRun({ fcs_file_id, markers: [channel names], n_clusters }).
const CLUSTER_PRESETS = [5, 10, 15, 20, 25];

export default function Controls({ onRun, disabled, files = [], channels = [] }) {
  const [fileId, setFileId] = useState('');
  const [selected, setSelected] = useState(() => new Set());
  const [nClusters, setNClusters] = useState(10);
  const fileInited = useRef(false);
  const markerInited = useRef(false);

  // Default the file selector to the first available file (once).
  useEffect(() => {
    if (!fileInited.current && files.length > 0) {
      fileInited.current = true;
      setFileId(files[0].id);
    }
  }, [files]);

  // Pre-check every non-scatter (clustering-eligible) channel once the panel loads.
  useEffect(() => {
    if (!markerInited.current && channels.length > 0) {
      markerInited.current = true;
      setSelected(
        new Set(
          channels
            .filter((c) => c.include_in_clustering)
            .map((c) => c.channel_name)
        )
      );
    }
  }, [channels]);

  function toggle(name) {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(channels.map((c) => c.channel_name)));
  }
  function selectNone() {
    setSelected(new Set());
  }
  function selectMarkersOnly() {
    setSelected(new Set(channels.filter((c) => !c.is_scatter).map((c) => c.channel_name)));
  }

  function handleRun() {
    const markers = channels
      .map((c) => c.channel_name)
      .filter((n) => selected.has(n));
    const payload = { markers, n_clusters: nClusters };
    if (fileId) payload.fcs_file_id = fileId;
    onRun(payload);
  }

  const nSelected = selected.size;
  const nMarkers = channels.length;

  return (
    <div className="controls card">
      <h2 className="card__title">Configure population identification</h2>

      {/* File selector ---------------------------------------------------- */}
      <label className="field">
        <span className="field__label">FCS file</span>
        {files.length > 0 ? (
          <select
            value={fileId}
            onChange={(e) => setFileId(e.target.value)}
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
            No files registered yet — the bundled demo acquisition will be used.
          </span>
        )}
        <span className="field__hint">
          Drop your own <code>.fcs</code> into <code>./fcs</code> (see README) or run the
          bundled demo panel out of the box. Nothing is uploaded anywhere — all analysis
          runs locally.
        </span>
      </label>

      {/* Marker panel ----------------------------------------------------- */}
      <div className="field">
        <span className="field__label">
          Markers for clustering — <strong>{nSelected}</strong> of {nMarkers} selected{' '}
          <button type="button" className="link-btn" onClick={selectAll} disabled={disabled} style={linkBtn}>
            all
          </button>{' '}
          /{' '}
          <button type="button" className="link-btn" onClick={selectNone} disabled={disabled} style={linkBtn}>
            none
          </button>{' '}
          /{' '}
          <button type="button" className="link-btn" onClick={selectMarkersOnly} disabled={disabled} style={linkBtn}>
            markers only
          </button>
        </span>
        <div style={markerGrid}>
          {channels.map((c) => (
            <label key={c.channel_name} style={markerRow}>
              <input
                type="checkbox"
                checked={selected.has(c.channel_name)}
                onChange={() => toggle(c.channel_name)}
                disabled={disabled}
              />
              <span>
                {c.channel_name}
                {c.marker_label && c.marker_label !== c.channel_name && (
                  <span style={{ color: 'var(--muted)' }}> · {c.marker_label}</span>
                )}
                {c.is_scatter && <span style={scatterTag}>scatter</span>}
              </span>
            </label>
          ))}
        </div>
        <span className="field__hint">
          Scatter / Time channels are excluded by default. FlowSOM clusters cells on the
          selected fluorophore markers.
        </span>
      </div>

      {/* Metacluster count ------------------------------------------------ */}
      <div className="field">
        <span className="field__label">
          Number of populations (metaclusters): <strong>{nClusters}</strong>
        </span>
        <div className="engine-toggle" style={{ flexWrap: 'wrap' }}>
          {CLUSTER_PRESETS.map((n) => (
            <button
              key={n}
              type="button"
              className={'engine-toggle__btn' + (nClusters === n ? ' is-active' : '')}
              onClick={() => setNClusters(n)}
              disabled={disabled}
            >
              {n}
            </button>
          ))}
        </div>
        <span className="field__hint">
          FlowSOM builds a self-organizing map then meta-clusters its nodes into this many
          populations.
        </span>
      </div>

      <button
        type="button"
        className="run-btn"
        onClick={handleRun}
        disabled={disabled || nSelected === 0}
      >
        {disabled ? 'Running…' : 'Run population identification'}
      </button>
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

const markerGrid = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))',
  gap: '2px 12px',
  maxHeight: '200px',
  overflowY: 'auto',
  border: '1px solid var(--border)',
  borderRadius: '6px',
  padding: '8px',
  marginTop: '4px',
};

const markerRow = {
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  fontSize: '13px',
};

const scatterTag = {
  marginLeft: '6px',
  fontSize: '10px',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  color: 'var(--muted)',
  border: '1px solid var(--border)',
  borderRadius: '4px',
  padding: '0 4px',
};

const linkBtn = {
  border: 'none',
  background: 'none',
  color: 'var(--accent)',
  cursor: 'pointer',
  fontSize: '0.85rem',
  padding: 0,
  textDecoration: 'underline',
};
