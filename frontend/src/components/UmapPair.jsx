import { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';

const BATCH_COLORS = ['#3366cc', '#d64545', '#2f9e6f', '#f0a92b', '#8e5fd6'];

// Split [[x, y, batch], ...] into one scatter trace per batch label.
function buildTraces(points) {
  const groups = {};
  for (const p of points || []) {
    const key = String(p[2]);
    if (!groups[key]) groups[key] = { x: [], y: [] };
    groups[key].x.push(p[0]);
    groups[key].y.push(p[1]);
  }
  const labels = Object.keys(groups).sort();
  return labels.map((k, i) => ({
    x: groups[k].x,
    y: groups[k].y,
    mode: 'markers',
    type: 'scattergl',
    name: 'Batch ' + k,
    marker: { size: 3, opacity: 0.5, color: BATCH_COLORS[i % BATCH_COLORS.length] },
  }));
}

function UmapPlot({ points, title }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    const data = buildTraces(points);
    const layout = {
      title: { text: title },
      margin: { t: 48, r: 16, b: 64, l: 40 },
      xaxis: { title: 'UMAP-1', zeroline: false },
      yaxis: { title: 'UMAP-2', zeroline: false },
      legend: { orientation: 'h', y: -0.2, x: 0.5, xanchor: 'center' },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
    };
    Plotly.react(ref.current, data, layout, {
      responsive: true,
      displaylogo: false,
    });
  }, [points, title]);

  useEffect(
    () => () => {
      if (ref.current) Plotly.purge(ref.current);
    },
    []
  );

  return <div ref={ref} className="plot" style={{ width: '100%', height: 420 }} />;
}

// Side-by-side UMAP embeddings coloured by batch: before vs after correction.
export default function UmapPair({ before, after }) {
  return (
    <div className="umap-pair">
      <UmapPlot points={before} title="UMAP before correction" />
      <UmapPlot points={after} title="UMAP after correction" />
    </div>
  );
}
