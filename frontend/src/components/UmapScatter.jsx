import { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';

// UMAP embedding coloured by identified population.
//   umap:            [[x, y, metacluster_id], ...] (single-file)
//                    [[x, y, metacluster_id, sample_index], ...] (cohort)
//   populations:     [{ metacluster_id, name, color }, ...]
//   highlightMc:     metacluster_id to emphasise (dims the rest), or null.
//   highlightSample: sample_index to emphasise on a cohort embedding, or null.
//
// One scattergl trace per population so the legend reads as named populations.
// A point is bright iff it matches BOTH active highlights (AND-mask); dimming is
// applied per-point via the colour alpha (reliable under WebGL/scattergl).
function hexToRgb(hex) {
  const h = String(hex || '#888888').replace('#', '');
  const s = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(s, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function buildTraces(umap, populations, highlightMc, highlightSample) {
  const byMc = new Map();
  for (const p of populations || []) byMc.set(Number(p.metacluster_id), p);

  const mcHi = highlightMc != null ? Number(highlightMc) : null;
  const sHi = highlightSample != null ? Number(highlightSample) : null;
  const anyHi = mcHi != null || sHi != null;

  const groups = new Map(); // mc -> { x, y, alpha, size }
  for (const pt of umap || []) {
    const mc = Number(pt[2]);
    const s = pt.length > 3 ? Number(pt[3]) : null;
    if (!groups.has(mc)) groups.set(mc, { x: [], y: [], alpha: [], size: [] });
    const g = groups.get(mc);
    g.x.push(pt[0]);
    g.y.push(pt[1]);
    const bright = (mcHi == null || mc === mcHi) && (sHi == null || s === sHi);
    g.alpha.push(anyHi ? (bright ? 0.9 : 0.05) : 0.6);
    g.size.push(anyHi && bright ? 5 : 3);
  }

  const mcs = Array.from(groups.keys()).sort((a, b) => a - b);
  return mcs.map((mc) => {
    const pop = byMc.get(mc);
    const g = groups.get(mc);
    const [r, gr, b] = hexToRgb((pop && pop.color) || '#888888');
    return {
      x: g.x,
      y: g.y,
      mode: 'markers',
      type: 'scattergl',
      name: (pop && pop.name) || `Population ${mc}`,
      marker: {
        size: g.size,
        color: g.alpha.map((a) => `rgba(${r},${gr},${b},${a})`),
      },
      hovertemplate: `${(pop && pop.name) || 'Population ' + mc}<extra></extra>`,
    };
  });
}

export default function UmapScatter({ umap, populations, highlightMc, highlightSample }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    const data = buildTraces(umap, populations, highlightMc, highlightSample);
    const layout = {
      title: { text: 'UMAP: cells coloured by population' },
      margin: { t: 48, r: 16, b: 48, l: 48 },
      xaxis: { title: 'UMAP-1', zeroline: false, showgrid: false },
      yaxis: { title: 'UMAP-2', zeroline: false, showgrid: false },
      legend: { itemsizing: 'constant', font: { size: 11 } },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      hovermode: 'closest',
    };
    Plotly.react(ref.current, data, layout, { responsive: true, displaylogo: false });
  }, [umap, populations, highlightMc, highlightSample]);

  useEffect(
    () => () => {
      if (ref.current) Plotly.purge(ref.current);
    },
    []
  );

  return <div ref={ref} className="plot" style={{ width: '100%', height: 520 }} />;
}
