// Simple determinate progress bar driven by the polled Job payload.
export default function ProgressBar({ job }) {
  if (!job) return null;
  const progress = Math.max(0, Math.min(100, Number(job.progress) || 0));
  const failed = job.status === 'failed';
  return (
    <div className="progress">
      <div className="progress__header">
        <span className="progress__label">
          {failed ? 'Failed' : job.message || job.status || 'Working…'}
        </span>
        <span className="progress__pct">{progress}%</span>
      </div>
      <div className="progress__track">
        <div
          className={'progress__fill' + (failed ? ' progress__fill--error' : '')}
          style={{ width: progress + '%' }}
        />
      </div>
    </div>
  );
}
