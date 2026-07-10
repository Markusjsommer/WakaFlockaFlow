import { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';

// One gate step as a 1-D biaxial view: the marker's distribution for the target
// population vs the background, each scaled to its own peak so both are visible,
// with the retained gate region shaded and its threshold(s) drawn.
export default function BiaxialPlot({ step, color = '#4477AA' }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current || !step) return;
    const edges = step.hist.edges;
    const centers = edges.slice(0, -1).map((e, i) => (e + edges[i + 1]) / 2);
    const norm = (arr) => {
      const m = Math.max(1, ...arr);
      return arr.map((v) => v / m);
    };
    const bg = {
      x: centers, y: norm(step.hist.background), type: 'bar', name: 'other cells',
      marker: { color: '#cccccc' }, opacity: 0.7,
    };
    const tgt = {
      x: centers, y: norm(step.hist.target), type: 'bar', name: 'this population',
      marker: { color }, opacity: 0.75,
    };
    const lo = step.lo == null ? step.axis_min : step.lo;
    const hi = step.hi == null ? step.axis_max : step.hi;
    const layout = {
      barmode: 'overlay',
      margin: { t: 10, r: 10, b: 40, l: 40 },
      height: 220,
      xaxis: { title: `${step.marker} (arcsinh)` },
      yaxis: { title: 'rel. freq.', range: [0, 1.05] },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      showlegend: true,
      legend: { orientation: 'h', y: 1.2, font: { size: 10 } },
      shapes: [
        { type: 'rect', xref: 'x', yref: 'paper', x0: lo, x1: hi, y0: 0, y1: 1,
          fillcolor: color, opacity: 0.08, line: { width: 0 } },
        ...(step.lo != null ? [{ type: 'line', x0: lo, x1: lo, yref: 'paper', y0: 0, y1: 1,
          line: { color, width: 1.5, dash: 'dash' } }] : []),
        ...(step.hi != null ? [{ type: 'line', x0: hi, x1: hi, yref: 'paper', y0: 0, y1: 1,
          line: { color, width: 1.5, dash: 'dash' } }] : []),
      ],
    };
    Plotly.react(ref.current, [bg, tgt], layout, { responsive: true, displaylogo: false });
  }, [step, color]);

  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);

  return <div ref={ref} style={{ width: '100%' }} />;
}
