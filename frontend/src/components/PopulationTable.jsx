import { useEffect, useState } from 'react';

// Sortable-by-metacluster table of identified populations.
//   - color swatch (editable via <input type=color>, PATCHes color)
//   - editable name (PATCHes on blur / Enter)
//   - metacluster_id, cell_count, percentage
//   - top-3 median markers
//   - row hover -> onHover(metacluster_id) to highlight matching UMAP points
//
// onPatch(pid, body) performs the PATCH and updates parent state.
function topMarkers(medianExpression, n = 3) {
  if (!medianExpression) return [];
  return Object.entries(medianExpression)
    .map(([marker, value]) => [marker, Number(value)])
    .filter(([, value]) => Number.isFinite(value))
    .sort((a, b) => b[1] - a[1])
    .slice(0, n);
}

function NameCell({ pop, onPatch, disabled }) {
  const [value, setValue] = useState(pop.name || '');

  // Keep the input in sync if the population is renamed elsewhere.
  useEffect(() => {
    setValue(pop.name || '');
  }, [pop.name]);

  function commit() {
    const trimmed = value.trim();
    if (trimmed && trimmed !== pop.name) {
      onPatch(pop.id, { name: trimmed });
    } else {
      setValue(pop.name || '');
    }
  }

  return (
    <input
      type="text"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur();
        if (e.key === 'Escape') {
          setValue(pop.name || '');
          e.currentTarget.blur();
        }
      }}
      disabled={disabled}
      aria-label={`Rename population ${pop.metacluster_id}`}
      style={nameInput}
    />
  );
}

export default function PopulationTable({ populations = [], onPatch, onHover, onLeave, disabled }) {
  const sorted = [...populations].sort((a, b) => a.metacluster_id - b.metacluster_id);

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={table}>
        <thead>
          <tr>
            <th style={th}></th>
            <th style={{ ...th, textAlign: 'left' }}>Population</th>
            <th style={thNum}>Cluster</th>
            <th style={thNum}>Cells</th>
            <th style={thNum}>%</th>
            <th style={{ ...th, textAlign: 'left' }}>Top median markers</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((pop) => {
            const pct = Number(pop.percentage_of_parent);
            const tops = topMarkers(pop.median_expression);
            return (
              <tr
                key={pop.id}
                onMouseEnter={() => onHover && onHover(pop.metacluster_id)}
                onMouseLeave={() => onLeave && onLeave()}
                style={row}
              >
                <td style={td}>
                  <input
                    type="color"
                    value={pop.color || '#4DBBD5'}
                    onChange={(e) => onPatch(pop.id, { color: e.target.value })}
                    disabled={disabled}
                    aria-label={`Recolor population ${pop.metacluster_id}`}
                    title="Change colour"
                    style={swatch}
                  />
                </td>
                <td style={td}>
                  <NameCell pop={pop} onPatch={onPatch} disabled={disabled} />
                </td>
                <td style={tdNum}>{pop.metacluster_id}</td>
                <td style={tdNum}>{Number(pop.cell_count).toLocaleString()}</td>
                <td style={tdNum}>{Number.isFinite(pct) ? pct.toFixed(1) : '—'}</td>
                <td style={td}>
                  {tops.length === 0 ? (
                    <span style={{ color: 'var(--muted)' }}>—</span>
                  ) : (
                    <span style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {tops.map(([marker, value]) => (
                        <span key={marker} style={chip}>
                          {marker}
                          <strong style={{ marginLeft: 4 }}>{value.toFixed(2)}</strong>
                        </span>
                      ))}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const table = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: '0.88rem',
};
const th = {
  textAlign: 'center',
  padding: '8px 10px',
  borderBottom: '2px solid var(--border)',
  color: 'var(--muted)',
  fontWeight: 600,
  whiteSpace: 'nowrap',
};
const thNum = { ...th, textAlign: 'right' };
const row = { borderBottom: '1px solid var(--border)', cursor: 'default' };
const td = { padding: '7px 10px', verticalAlign: 'middle' };
const tdNum = { ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' };
const nameInput = {
  width: '100%',
  minWidth: '160px',
  padding: '6px 8px',
  border: '1px solid transparent',
  borderRadius: '6px',
  fontSize: '0.9rem',
  fontWeight: 600,
  background: 'transparent',
  color: 'var(--fg)',
};
const swatch = {
  width: '26px',
  height: '26px',
  padding: 0,
  border: '1px solid var(--border)',
  borderRadius: '6px',
  background: 'none',
  cursor: 'pointer',
};
const chip = {
  display: 'inline-flex',
  alignItems: 'center',
  background: 'var(--bg)',
  border: '1px solid var(--border)',
  borderRadius: '5px',
  padding: '1px 7px',
  fontSize: '0.8rem',
  whiteSpace: 'nowrap',
};
