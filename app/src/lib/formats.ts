/**
 * Formats, bit depths and colour (docs/guides/formats.md): camera-raw decoder commands, which failures a decoder
 * fixes, and the colour description of a file in plain names.
 */

/** A failure the core says a raw decoder (Settings → Formats) can fix. */
export function needsDecoder(error: string | null | undefined): boolean {
  return Boolean(error && /Settings\s*→\s*Formats/i.test(error))
}

/** The extension the core names in a raw-decoder message ("…command for .r3d in Settings → Formats…"), if any. */
export function decoderExtension(error: string | null | undefined): string | null {
  const m = error ? /for \.([a-z0-9]+) in Settings/i.exec(error) : null
  return m ? m[1].toLowerCase() : null
}

/**
 * The whole decoder map to save: `current` with `ext` set to `command`, or without it when the command is empty
 * (the core replaces the map, so removing one means sending the rest).
 */
export function decoderMap(current: Readonly<Record<string, string>>, ext: string, command: string | null): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(current)) if (k !== ext && v.trim()) out[k] = v
  if (command && command.trim()) out[ext] = command.trim()
  return out
}

/** Placeholders a command uses, in the order the core documents them. */
export function placeholdersIn(command: string, placeholders: readonly string[]): string[] {
  return placeholders.filter((p) => command.includes(p))
}

/** Unreadable files that are not camera raw already listed (with their format) in the raw table. */
export function unreadableOnly<T extends { uid: string }>(undecodable: readonly T[], raw: readonly { waiting: readonly { uid: string }[] }[]): T[] {
  const waiting = new Set(raw.flatMap((r) => r.waiting.map((w) => w.uid)))
  return undecodable.filter((u) => !waiting.has(u.uid))
}

// ---------------------------------------------------------------- colour

const PRIMARIES: Record<string, string> = {
  bt709: 'BT.709', bt470bg: 'BT.601 (PAL)', smpte170m: 'BT.601 (NTSC)', smpte240m: 'SMPTE 240M', bt470m: 'BT.470 M', film: 'Film',
  bt2020: 'BT.2020', smpte428: 'XYZ (DCI)', smpte431: 'DCI-P3', smpte432: 'Display P3', 'jedec-p22': 'EBU 3213',
}

const TRANSFERS: Record<string, string> = {
  bt709: 'BT.709', smpte170m: 'BT.601', bt470bg: 'Gamma 2.8', bt470m: 'Gamma 2.2', smpte240m: 'SMPTE 240M', linear: 'Linear',
  'iec61966-2-1': 'sRGB', 'iec61966-2-4': 'xvYCC', 'bt2020-10': 'BT.2020', 'bt2020-12': 'BT.2020', smpte2084: 'PQ (HDR10)',
  'arib-std-b67': 'HLG', smpte428: 'DCI (SMPTE 428)', log100: 'Log', log316: 'Log',
}

const UNSET = new Set(['', 'unknown', 'reserved', 'unspecified'])

/** "BT.709", "BT.601 (PAL)", or the raw tag when it has no common name; null when the file doesn't say. */
export function primariesName(v: unknown): string | null {
  if (typeof v !== 'string' || UNSET.has(v)) return null
  return PRIMARIES[v] ?? v
}

export function transferName(v: unknown): string | null {
  if (typeof v !== 'string' || UNSET.has(v)) return null
  return TRANSFERS[v] ?? v
}

/** "HDR10 (PQ)", "HLG", "Dolby Vision"… from the core's hdr_format / transfer. */
export function hdrName(format: unknown, transfer: unknown): string | null {
  const f = typeof format === 'string' ? format.toLowerCase() : ''
  if (f.includes('dolby') || f === 'dovi') return 'Dolby Vision'
  if (f.includes('hdr10+') || f.includes('hdr10plus')) return 'HDR10+'
  if (f.includes('hlg')) return 'HLG'
  if (f.includes('hdr10') || f.includes('pq')) return 'HDR10 (PQ)'
  if (f) return typeof format === 'string' ? format : null
  if (transfer === 'smpte2084') return 'HDR10 (PQ)'
  if (transfer === 'arib-std-b67') return 'HLG'
  return null
}

export interface ColourFacts {
  /** "10-bit 4:2:2" */
  depth: string | null
  /** "BT.2020 · HLG · limited range"; untagged parts are left out. */
  colour: string | null
  /** "HLG, tone-mapped to SDR for the preview" */
  hdr: string | null
}

/** A file's bit depth, chroma, colour description and HDR, in plain names (missing parts are left out). */
export function colourFacts(tech: Record<string, unknown>): ColourFacts {
  const bits = typeof tech.bit_depth === 'number' ? `${tech.bit_depth}-bit` : null
  const chroma = typeof tech.chroma === 'string' && tech.chroma ? tech.chroma : null
  const alpha = typeof tech.pix_fmt === 'string' && /^(yuva|rgba|bgra|argb|abgr|gbrap|ya)/.test(tech.pix_fmt) ? 'with alpha' : null
  const depth = [bits, chroma, alpha].filter(Boolean).join(' ') || null
  const prim = primariesName(tech.color_primaries)
  const trc = transferName(tech.color_transfer)
  const range = tech.color_range === 'pc' || tech.color_range === 'jpeg' ? 'full range' : tech.color_range === 'tv' || tech.color_range === 'mpeg' ? 'limited range' : null
  const colourParts = [prim ? `${prim} primaries` : null, trc ? `${trc} transfer` : null, range]
  const colour = colourParts.some(Boolean) ? colourParts.filter(Boolean).join(' · ') : null
  const isHdr = Boolean(tech.hdr) || tech.color_transfer === 'smpte2084' || tech.color_transfer === 'arib-std-b67'
  const name = isHdr ? hdrName(tech.hdr_format, tech.color_transfer) ?? 'HDR' : null
  return { depth, colour, hdr: name ? `${name}, tone-mapped to SDR for the preview` : null }
}

/** "Decoded from MotionCam RAW with cp {input} {output}" (null when the file wasn't decoded by a raw decoder). */
export function decodedFromText(tech: Record<string, unknown>): { format: string; decoder: string | null } | null {
  const d = tech.decoded_from
  if (!d || typeof d !== 'object') return null
  const o = d as { format?: unknown; decoder?: unknown }
  return { format: typeof o.format === 'string' ? o.format : 'camera raw', decoder: typeof o.decoder === 'string' && o.decoder ? o.decoder : null }
}

/** How many decode errors the preview step saw (0 when none or unknown). */
export function decodeErrors(fields: Record<string, { value: unknown } | undefined>): number {
  const v = fields['quality.decode_errors']?.value
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number(v) : Array.isArray(v) ? v.length : 0
  return Number.isFinite(n) && n > 0 ? n : 0
}
