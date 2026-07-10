import { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';

// Volcano plot of differential abundance: one point per population.
//   x = log2 fold change, y = -log10(adjusted p). Significant points (p_adj <
//   alpha) keep their population colour; the rest are grey.
export default function VolcanoPlot({ da = [], alpha = 0.05 }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    const pts = (da || []).filter((r) => r.log_fc != null);
    const y = pts.map((r) => {
      const p = r.p_adj != null ? r.p_adj : r.p_value;
      return p != null && p > 0 ? -Math.log10(p) : 0;
    });
    const colors = pts.map((r) =>
      r.p_adj != null && r.p_adj < alpha ? r.color || '#EE6677' : '#bbbbbb'
    );
    const trace = {
      x: pts.map((r) => r.log_fc),
      y,
      text: pts.map((r) => r.name),
      mode: 'markers',
      type: 'scattergl',
      marker: { size: 10, color: colors, line: { width: 1, color: '#ffffff' } },
      hovertemplate: '%{text}<br>log2FC %{x:.2f}<br>-log10 p_adj %{y:.2f}<extra></extra>',
    };
    const layout = {
      title: { text: 'Differential abundance (volcano)' },
      margin: { t: 48, r: 16, b: 48, l: 54 },
      xaxis: { title: 'log2 fold change', zeroline: false },
      yaxis: { title: '-log10 adjusted p' },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      hovermode: 'closest',
      shapes: [
        { type: 'line', x0: 0, x1: 0, yref: 'paper', y0: 0, y1: 1,
          line: { dash: 'dot', color: '#999', width: 1 } },
        { type: 'line', xref: 'paper', x0: 0, x1: 1,
          y0: -Math.log10(alpha), y1: -Math.log10(alpha),
          line: { dash: 'dot', color: '#999', width: 1 } },
      ],
    };
    Plotly.react(ref.current, [trace], layout, { responsive: true, displaylogo: false });
  }, [da, alpha]);

  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);

  return <div ref={ref} style={{ width: '100%', height: 420 }} />;
}
