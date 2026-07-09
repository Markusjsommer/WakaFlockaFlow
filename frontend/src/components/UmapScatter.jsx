import { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';

// UMAP embedding coloured by identified population.
//   umap:        [[x, y, metacluster_id], ...]
//   populations: [{ metacluster_id, name, color }, ...]
//   highlightMc: metacluster_id to emphasise (dims the rest), or null.
//
// One scattergl trace per population so the legend reads as named populations.
function buildTraces(umap, populations, highlightMc) {
  const byMc = new Map();
  for (const p of populations || []) {
    byMc.set(Number(p.metacluster_id), p);
  }

  const groups = new Map();
  for (const pt of umap || []) {
    const mc = Number(pt[2]);
    if (!groups.has(mc)) groups.set(mc, { x: [], y: [] });
    const g = groups.get(mc);
    g.x.push(pt[0]);
    g.y.push(pt[1]);
  }

  const mcs = Array.from(groups.keys()).sort((a, b) => a - b);
  const anyHighlight = highlightMc != null;

  return mcs.map((mc) => {
    const pop = byMc.get(mc);
    const g = groups.get(mc);
    const isHi = anyHighlight && Number(highlightMc) === mc;
    return {
      x: g.x,
      y: g.y,
      mode: 'markers',
      type: 'scattergl',
      name: (pop && pop.name) || `Population ${mc}`,
      marker: {
        size: isHi ? 5 : 3,
        opacity: anyHighlight ? (isHi ? 0.95 : 0.08) : 0.6,
        color: (pop && pop.color) || '#888888',
      },
      hovertemplate: `${(pop && pop.name) || 'Population ' + mc}<extra></extra>`,
    };
  });
}

export default function UmapScatter({ umap, populations, highlightMc }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    const data = buildTraces(umap, populations, highlightMc);
    const layout = {
      title: { text: 'UMAP — cells coloured by population' },
      margin: { t: 48, r: 16, b: 48, l: 48 },
      xaxis: { title: 'UMAP-1', zeroline: false, showgrid: false },
      yaxis: { title: 'UMAP-2', zeroline: false, showgrid: false },
      legend: { itemsizing: 'constant', font: { size: 11 } },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      hovermode: 'closest',
    };
    Plotly.react(ref.current, data, layout, { responsive: true, displaylogo: false });
  }, [umap, populations, highlightMc]);

  useEffect(
    () => () => {
      if (ref.current) Plotly.purge(ref.current);
    },
    []
  );

  return <div ref={ref} className="plot" style={{ width: '100%', height: 520 }} />;
}
