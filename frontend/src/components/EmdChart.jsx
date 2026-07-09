import { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';

// Grouped bar chart: per-marker Earth-Mover Distance before vs after correction.
export default function EmdChart({ perMarker }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current || !perMarker) return;
    const markers = Object.keys(perMarker);
    const before = markers.map((m) => perMarker[m].before);
    const after = markers.map((m) => perMarker[m].after);

    const data = [
      {
        x: markers,
        y: before,
        type: 'bar',
        name: 'Before',
        marker: { color: '#d64545' },
      },
      {
        x: markers,
        y: after,
        type: 'bar',
        name: 'After',
        marker: { color: '#2f9e6f' },
      },
    ];

    const layout = {
      barmode: 'group',
      title: { text: 'Per-marker EMD (A vs B)' },
      margin: { t: 48, r: 16, b: 90, l: 56 },
      xaxis: { title: '', tickangle: -45, automargin: true },
      yaxis: { title: 'Wasserstein distance' },
      legend: { orientation: 'h', y: 1.12 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
    };

    Plotly.react(ref.current, data, layout, {
      responsive: true,
      displaylogo: false,
    });
  }, [perMarker]);

  useEffect(
    () => () => {
      if (ref.current) Plotly.purge(ref.current);
    },
    []
  );

  return <div ref={ref} className="plot" style={{ width: '100%', height: 420 }} />;
}
