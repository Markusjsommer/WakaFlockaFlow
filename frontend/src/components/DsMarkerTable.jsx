// Per-population differential STATE: marker rows for one population, sorted by
// adjusted p. Shown inside an expanded differential-abundance row.
export default function DsMarkerTable({ rows = [], alpha = 0.05 }) {
  const sorted = [...rows].sort((a, b) => (a.p_adj ?? 1) - (b.p_adj ?? 1));
  if (sorted.length === 0) {
    return <span style={{ color: 'var(--muted)' }}>No differential-state results.</span>;
  }
  const fmt = (v, d = 3) => (v == null || Number.isNaN(v) ? '-' : Number(v).toFixed(d));
  return (
    <table style={{ borderCollapse: 'collapse', fontSize: '0.82rem', width: '100%' }}>
      <thead>
        <tr>
          <th style={{ ...th, textAlign: 'left' }}>Marker</th>
          <th style={thNum}>Δ (log2/arcsinh)</th>
          <th style={thNum}>p</th>
          <th style={thNum}>p (adj)</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((r) => {
          const sig = r.p_adj != null && r.p_adj < alpha;
          return (
            <tr key={r.marker} style={{ borderBottom: '1px solid var(--border)' }}>
              <td style={td}>{r.marker}</td>
              <td style={tdNum}>{fmt(r.log_fc)}</td>
              <td style={tdNum}>{fmt(r.p_value, 4)}</td>
              <td style={{ ...tdNum, fontWeight: sig ? 700 : 400, color: sig ? 'var(--accent-dark)' : 'inherit' }}>
                {fmt(r.p_adj, 4)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const th = { textAlign: 'center', padding: '5px 8px', color: 'var(--muted)', fontWeight: 600, whiteSpace: 'nowrap' };
const thNum = { ...th, textAlign: 'right' };
const td = { padding: '4px 8px' };
const tdNum = { ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' };
