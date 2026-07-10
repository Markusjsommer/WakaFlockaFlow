import { useState } from 'react';
import DsMarkerTable from './DsMarkerTable.jsx';

// Differential ABUNDANCE table (one row per population, ranked by adjusted p).
// Row hover highlights the population on the shared UMAP; expanding a row shows
// its differential-STATE marker table.
export default function DifferentialTable({ da = [], ds = [], onHover, onLeave, alpha = 0.05 }) {
  const [openMc, setOpenMc] = useState(null);
  const sorted = [...da].sort((a, b) => (a.p_adj ?? 1) - (b.p_adj ?? 1));
  const fmt = (v, d = 3) => (v == null || Number.isNaN(v) ? '-' : Number(v).toFixed(d));

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', fontSize: '0.86rem', width: '100%' }}>
        <thead>
          <tr>
            <th style={{ ...th, width: 28 }}></th>
            <th style={{ ...th, textAlign: 'left' }}>Population</th>
            <th style={thNum}>log2 FC</th>
            <th style={thNum}>p</th>
            <th style={thNum}>p (adj)</th>
            <th style={thNum}>log CPM</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const sig = r.p_adj != null && r.p_adj < alpha;
            const open = openMc === r.metacluster_id;
            return [
              <tr
                key={r.metacluster_id}
                style={{ borderBottom: '1px solid var(--border)', cursor: 'pointer' }}
                onMouseEnter={() => onHover && onHover(r.metacluster_id)}
                onMouseLeave={() => onLeave && onLeave()}
                onClick={() => setOpenMc(open ? null : r.metacluster_id)}
              >
                <td style={{ ...td, color: 'var(--muted)' }}>{open ? '▾' : '▸'}</td>
                <td style={td}>
                  <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: r.color || '#888', marginRight: 8 }} />
                  {r.name}
                </td>
                <td style={tdNum}>{fmt(r.log_fc)}</td>
                <td style={tdNum}>{fmt(r.p_value, 4)}</td>
                <td style={{ ...tdNum, fontWeight: sig ? 700 : 400, color: sig ? 'var(--accent-dark)' : 'inherit' }}>
                  {fmt(r.p_adj, 4)}
                </td>
                <td style={tdNum}>{fmt(r.log_cpm, 2)}</td>
              </tr>,
              open ? (
                <tr key={r.metacluster_id + '-ds'}>
                  <td />
                  <td colSpan={5} style={{ padding: '6px 10px 12px', background: 'var(--bg)' }}>
                    <DsMarkerTable
                      rows={ds.filter((d) => d.metacluster_id === r.metacluster_id)}
                      alpha={alpha}
                    />
                  </td>
                </tr>
              ) : null,
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}

const th = { textAlign: 'center', padding: '8px 10px', borderBottom: '2px solid var(--border)', color: 'var(--muted)', fontWeight: 600, whiteSpace: 'nowrap' };
const thNum = { ...th, textAlign: 'right' };
const td = { padding: '7px 10px', verticalAlign: 'middle' };
const tdNum = { ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' };
