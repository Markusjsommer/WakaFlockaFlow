import { useMemo, useState } from 'react';

// Configure + launch a differential run on the current cohort. Groups come from
// the samples' tags; if there are more than two you pick the pair to contrast.
export default function DifferentialPanel({ samples = [], disabled, onRun }) {
  const groups = useMemo(() => {
    const counts = {};
    for (const s of samples) {
      const g = s.group;
      if (g) counts[g] = (counts[g] || 0) + 1;
    }
    return Object.entries(counts).map(([name, n]) => ({ name, n }));
  }, [samples]);

  const [engine, setEngine] = useState('python');
  const [gA, setGA] = useState('');
  const [gB, setGB] = useState('');

  const groupNames = groups.map((g) => g.name);
  const a = gA || groupNames[0] || '';
  const b = gB || groupNames[1] || '';
  const enough = groupNames.length >= 2;
  const needPick = groupNames.length > 2;

  function run() {
    const contrast = groupNames.length === 2 ? groupNames : needPick ? [a, b] : null;
    onRun({ group_field: 'group', engine, contrast, min_samples: 1 });
  }

  return (
    <div className="card">
      <h2 className="card__title">Differential analysis</h2>
      {!enough ? (
        <p className="field__hint" style={{ marginTop: 0 }}>
          Tag your samples with at least two groups (in the cohort builder) to test
          for differences. Currently: {groups.length === 0 ? 'no groups set' : groupNames.join(', ')}.
        </p>
      ) : (
        <>
          <p className="field__hint" style={{ marginTop: 0 }}>
            Groups: {groups.map((g) => `${g.name} (${g.n})`).join(', ')}. Tests which
            populations change in abundance and which markers shift within a population.
          </p>

          {needPick && (
            <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <label className="field" style={{ maxWidth: 180 }}>
                <span className="field__label">Reference group</span>
                <select value={a} disabled={disabled} onChange={(e) => setGA(e.target.value)} style={sel}>
                  {groupNames.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </label>
              <label className="field" style={{ maxWidth: 180 }}>
                <span className="field__label">Compared group</span>
                <select value={b} disabled={disabled} onChange={(e) => setGB(e.target.value)} style={sel}>
                  {groupNames.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </label>
            </div>
          )}

          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginTop: 10 }}>
            <label className="field" style={{ maxWidth: 260 }}>
              <span className="field__label">Engine</span>
              <select value={engine} disabled={disabled} onChange={(e) => setEngine(e.target.value)} style={sel}>
                <option value="python">Python rank tests (always available)</option>
                <option value="auto">diffcyt if available, else Python</option>
                <option value="diffcyt">diffcyt (edgeR + limma, needs R)</option>
              </select>
            </label>
            <button type="button" className="run-btn" disabled={disabled || !enough} onClick={run}>
              Run differential test
            </button>
          </div>
          <p className="field__hint" style={{ marginTop: 8 }}>
            Rank tests need several samples per group for significance (a 3-vs-3
            comparison floors at p = 0.1); diffcyt is recommended for real cohorts.
          </p>
        </>
      )}
    </div>
  );
}

const sel = {
  padding: '8px 10px',
  border: '1px solid var(--border)',
  borderRadius: '6px',
  fontSize: '0.9rem',
  background: 'var(--bg)',
  color: 'var(--fg)',
};
