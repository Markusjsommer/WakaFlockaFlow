// Dropdown that highlights one sample's cells on the shared cohort UMAP.
// value is the sample_index (number) or null for "all samples".
export default function SampleHighlightSelector({ samples = [], value, onChange }) {
  if (!samples || samples.length === 0) return null;
  return (
    <label className="field" style={{ maxWidth: 320, marginBottom: 12 }}>
      <span className="field__label">Highlight sample on the embedding</span>
      <select
        value={value == null ? '' : String(value)}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        style={{
          padding: '8px 10px',
          border: '1px solid var(--border)',
          borderRadius: '6px',
          fontSize: '0.9rem',
          background: 'var(--bg)',
          color: 'var(--fg)',
        }}
      >
        <option value="">All samples</option>
        {[...samples]
          .sort((a, b) => a.sample_index - b.sample_index)
          .map((s) => (
            <option key={s.sample_index} value={s.sample_index}>
              {s.sample_label}
              {s.group ? ` (${s.group})` : ''}
            </option>
          ))}
      </select>
    </label>
  );
}
