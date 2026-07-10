import { useState } from 'react';

// population x sample matrix for a cohort run. Rows are populations, columns are
// samples. Hovering a row highlights that population on the shared UMAP; hovering
// a column header highlights that sample. Toggle between % (of sample) and counts.
export default function BreakdownTable({
  breakdown,
  onHoverPopulation,
  onHoverSample,
  onLeave,
}) {
  const [showPct, setShowPct] = useState(true);
  if (!breakdown || !breakdown.samples) return null;
  const { samples, populations } = breakdown;

  const cell = (ps) =>
    showPct
      ? `${Number(ps.percentage_of_sample || 0).toFixed(1)}`
      : Number(ps.cell_count || 0).toLocaleString();

  return (
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
          Population abundance per sample
        </h2>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            type="button"
            className={'chip-btn' + (showPct ? ' is-active' : '')}
            onClick={() => setShowPct(true)}
            style={toggleStyle(showPct)}
          >
            % of sample
          </button>
          <button
            type="button"
            className={'chip-btn' + (!showPct ? ' is-active' : '')}
            onClick={() => setShowPct(false)}
            style={toggleStyle(!showPct)}
          >
            cell count
          </button>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: '0.85rem', width: '100%' }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: 'left', position: 'sticky', left: 0 }}>
                Population
              </th>
              {samples.map((s) => (
                <th
                  key={s.sample_index}
                  style={{ ...thNum, cursor: 'pointer' }}
                  onMouseEnter={() => onHoverSample && onHoverSample(s.sample_index)}
                  onMouseLeave={() => onLeave && onLeave()}
                  title={s.group ? `group: ${s.group}` : ''}
                >
                  {s.sample_label}
                  {s.group ? (
                    <div style={{ fontWeight: 400, color: 'var(--muted)' }}>{s.group}</div>
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {populations.map((p) => (
              <tr
                key={p.metacluster_id}
                style={{ borderBottom: '1px solid var(--border)' }}
                onMouseEnter={() => onHoverPopulation && onHoverPopulation(p.metacluster_id)}
                onMouseLeave={() => onLeave && onLeave()}
              >
                <td style={{ ...td, whiteSpace: 'nowrap' }}>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 10,
                      height: 10,
                      borderRadius: 2,
                      background: p.color || '#888',
                      marginRight: 8,
                    }}
                  />
                  {p.name}
                </td>
                {p.per_sample.map((ps) => (
                  <td key={ps.sample_index} style={tdNum}>
                    {cell(ps)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="field__hint" style={{ marginTop: 10 }}>
        Hover a row to highlight that population, or a column header to highlight that
        sample, on the shared UMAP above.
      </p>
    </div>
  );
}

function toggleStyle(active) {
  return {
    padding: '4px 10px',
    borderRadius: 6,
    border: '1px solid var(--border)',
    background: active ? 'var(--accent)' : 'transparent',
    color: active ? '#fff' : 'var(--fg)',
    cursor: 'pointer',
    fontSize: '0.8rem',
  };
}

const th = {
  textAlign: 'center',
  padding: '8px 10px',
  borderBottom: '2px solid var(--border)',
  color: 'var(--muted)',
  fontWeight: 600,
  whiteSpace: 'nowrap',
  background: 'var(--card, #fff)',
};
const thNum = { ...th, textAlign: 'right' };
const td = { padding: '7px 10px', verticalAlign: 'middle' };
const tdNum = { ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' };
