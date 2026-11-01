import { Link } from '@tanstack/react-router'
import type { ShotDoc } from '../../api/types'
import { Section } from './ShotPanels'
import s from './Shot.module.css'

const levels = [
  ['destination', 'Destination'], ['venue', 'Park / resort'],
  ['area', 'Land / area'], ['attraction_or_show', 'Attraction / show'],
] as const

export function PlaceRecognition({ shot }: { shot: ShotDoc }) {
  const entries = levels.flatMap(([key, label]) => {
    const field = shot.fields[`content.${key}`]
    const place = shot.place_recognition?.[key]
    return place?.value ? [{ key, label, place, corrected: field?.corrected }] : []
  })
  if (!entries.length) return null
  return (
    <Section title="Place recognition" id={`places-${shot.uid}`}>
      {entries.map(({ key, label, place, corrected }) => (
        <div key={key} className={s.section}>
          <strong>{label}: {place.value}</strong>
          <p>{corrected ? 'Confirmed by a reviewer' : place.method === 'inherited' ? 'Inferred from a nearby clip' :
            place.relationship === 'visible_landmark' ? 'Visible landmark; camera location not established' :
            (place.confidence ?? 0) >= 0.85 ? 'Direct recognition · high confidence' : 'Direct recognition · probable'}</p>
          {!corrected && place.method === 'inherited' && place.anchor_shot_uid ? (
            <p><Link to="/shot/$shotId" params={{ shotId: place.anchor_shot_uid }}>View supporting shot</Link>
              {' · '}{place.gap_seconds ?? 0}s recording gap</p>
          ) : null}
          {!corrected && place.evidence?.length ? <ul>{place.evidence.map((text, i) => <li key={i}>{text}</li>)}</ul> : null}
        </div>
      ))}
    </Section>
  )
}
