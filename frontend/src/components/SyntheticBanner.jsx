// MANDATORY integrity guardrail: a red banner visible on every screen making
// clear this is a synthetic mechanism demo, not real multi-batch data.
export default function SyntheticBanner({ text }) {
  const message =
    text || 'SYNTHETIC BATCH EFFECT — mechanism demo, not real multi-batch data';
  return (
    <div className="synthetic-banner" role="alert">
      <span className="synthetic-banner__icon" aria-hidden="true">
        ⚠
      </span>
      <span className="synthetic-banner__text">{message}</span>
    </div>
  );
}
