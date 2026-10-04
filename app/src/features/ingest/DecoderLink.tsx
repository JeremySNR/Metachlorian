import { Link } from '@tanstack/react-router'
import { Settings2 } from 'lucide-react'
import { Ic } from '../../components/Icon'
import { needsDecoder } from '../../lib/formats'

/** "Set up a decoder": shown next to a failure the core says a raw decoder fixes (Settings → Formats). */
export function DecoderLink({ error, className }: { error: string | null | undefined; className?: string }) {
  if (!needsDecoder(error)) return null
  return (
    <Link to="/settings/$section" params={{ section: 'formats' }} className={className} data-testid="set-up-decoder">
      <Ic icon={Settings2} size={14} />
      Set up a decoder
    </Link>
  )
}
