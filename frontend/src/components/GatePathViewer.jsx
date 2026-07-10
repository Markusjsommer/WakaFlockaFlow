import { useEffect, useState } from 'react';
import { getGatePaths } from '../api.js';
import BiaxialPlot from './BiaxialPlot.jsx';

// Per-population explainable gating path: the sequence of marker gates that
// reproduces each cluster, with a reconstruction-quality (F1) badge. Expanding a
// population shows a biaxial histogram per gate step.
function stepText(s) {
  const lo = s.lo == null ? null : s.lo.toFixed(2);
  const hi = s.hi == null ? null : s.hi.toFixed(2);
  if (lo != null && hi != null) return `${lo} < ${s.marker} ≤ ${hi}`;
  if (lo != null) return `${s.marker} > ${lo}`;
  if (hi != null) return `${s.marker} ≤ ${hi}`;
  return s.marker;
}

function f1Color(f1) {
  if (f1 >= 0.8) return '#228833';
  if (f1 >= 0.5) return '#CCBB44';
  return '#D55E00';
}

export default function GatePathViewer({ sid, rid, onHover, onLeave }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [openMc, setOpenMc] = useState(null);

  useEffect(() => {
    if (!sid || !rid) return;
    let cancelled = false;
    setData(null);
    setError(null);
    getGatePaths(sid, rid)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [sid, rid]);

  if (error) return <p className="field__hint">Gate paths unavailable: {error}</p>;
  if (!data) return <p className="field__hint">Deriving gating paths…</p>;

  return (
    <div>
      <p className="field__hint" style={{ marginTop: 0 }}>
        The shortest sequence of marker gates that reproduces each population (a
        one-vs-rest decision tree). The F1 badge is how faithfully the gate
        reconstructs the cluster. Expand a population to see each gate on a biaxial plot.
      </p>
      {data.populations.map((p) => {
        const open = openMc === p.metacluster_id;
        return (
          <div key={p.metacluster_id} style={{ borderTop: '1px solid var(--border)', padding: '10px 0' }}>
            <div
              style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', flexWrap: 'wrap' }}
              onClick={() => setOpenMc(open ? null : p.metacluster_id)}
              onMouseEnter={() => onHover && onHover(p.metacluster_id)}
              onMouseLeave={() => onLeave && onLeave()}
            >
              <span style={{ color: 'var(--muted)' }}>{open ? '▾' : '▸'}</span>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: p.color || '#888' }} />
              <strong>{p.name}</strong>
              <span
                title={`precision ${p.precision} · recall ${p.recall}`}
                style={{
                  background: f1Color(p.f1), color: '#fff', borderRadius: 5,
                  padding: '1px 7px', fontSize: '0.76rem', fontWeight: 700,
                }}
              >
                F1 {p.f1}
              </span>
              <span style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {p.steps.map((s, i) => (
                  <span key={i} style={chip}>{stepText(s)}</span>
                ))}
              </span>
            </div>
            {open && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12, marginTop: 10 }}>
                {p.steps.map((s, i) => (
                  <div key={i} style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 8 }}>
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
                      Gate {i + 1}: {stepText(s)}
                    </div>
                    <BiaxialPlot step={s} color={p.color} />
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

const chip = {
  display: 'inline-flex',
  alignItems: 'center',
  background: 'var(--bg)',
  border: '1px solid var(--border)',
  borderRadius: 5,
  padding: '1px 7px',
  fontSize: '0.78rem',
  whiteSpace: 'nowrap',
};
