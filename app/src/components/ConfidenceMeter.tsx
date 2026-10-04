import s from './Data.module.css'

/** Five segments + number (§3.8). Never red/green: confidence is certainty, not quality. */
export function ConfidenceMeter({ value, label }: { value: number | null | undefined; label?: string }) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  const v = Math.max(0, Math.min(1, value))
  const pct = Math.round(v * 100)
  const filled = Math.round(v * 5)
  const band = v >= 0.85 ? 'high' : v >= 0.6 ? 'medium' : 'low'
  return (
    <span
      className={`${s.meter} ${band === 'low' ? s.low : ''}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      aria-valuetext={`${pct} percent, ${band} confidence`}
      aria-label={label ? `${label} confidence` : 'Confidence'}
    >
      <span className={s.segments} aria-hidden="true">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className={`${s.seg} ${i < filled ? s.on : ''}`} />
        ))}
      </span>
      <span className={s.meterValue} aria-hidden="true">
        {pct}
      </span>
      {band === 'low' && (
        <span className={s.lowWord} aria-hidden="true">
          low
        </span>
      )}
    </span>
  )
}
