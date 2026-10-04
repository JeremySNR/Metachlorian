import { describe, expect, it } from 'vitest'
import { colourFacts, decodedFromText, decodeErrors, decoderExtension, decoderMap, hdrName, needsDecoder, placeholdersIn, primariesName, transferName, unreadableOnly } from './formats'

const RAW_MSG =
  "MotionCam RAW can only be decoded with the camera maker's software (MotionCam Tools). Set a raw decoder command for .mcraw in Settings → Formats, or export a ProRes/DNx copy into a watched folder."

describe('decoder failures', () => {
  it('spots messages that send people to Settings → Formats', () => {
    expect(needsDecoder(RAW_MSG)).toBe(true)
    expect(needsDecoder('FFmpeg cannot read this file (Invalid data found). If it is camera raw, set a raw decoder for its extension in Settings → Formats, or export…')).toBe(true)
    expect(needsDecoder('proxy failed')).toBe(false)
    expect(needsDecoder(null)).toBe(false)
  })
  it('finds the extension the message names', () => {
    expect(decoderExtension(RAW_MSG)).toBe('mcraw')
    expect(decoderExtension('Set a raw decoder in Settings → Formats')).toBeNull()
  })
})

describe('decoderMap', () => {
  const current = { r3d: 'REDline --i {input} --o {output_stem}', braw: 'braw-decode {input} {output}' }
  it('sets one command and keeps the others', () => {
    expect(decoderMap(current, 'mcraw', '  cp {input} {output} ')).toEqual({ ...current, mcraw: 'cp {input} {output}' })
    expect(decoderMap(current, 'r3d', 'new {input} {output}')).toEqual({ r3d: 'new {input} {output}', braw: current.braw })
  })
  it('removes one by sending the rest', () => {
    expect(decoderMap(current, 'r3d', null)).toEqual({ braw: current.braw })
    expect(decoderMap(current, 'braw', '   ')).toEqual({ r3d: current.r3d })
  })
  it('lists the placeholders a command uses', () => {
    expect(placeholdersIn('REDline --i {input} --o {output_stem}', ['{input}', '{output}', '{output_stem}', '{output_dir}'])).toEqual(['{input}', '{output_stem}'])
  })
})

describe('unreadableOnly', () => {
  it('leaves out raw files already listed under their format', () => {
    const und = [{ uid: 'a', filename: 'x.mcraw', error: '' }, { uid: 'b', filename: 'broken.mp4', error: '' }]
    expect(unreadableOnly(und, [{ waiting: [{ uid: 'a' }] }, { waiting: [] }]).map((u) => u.uid)).toEqual(['b'])
  })
})

describe('colour', () => {
  it('names primaries and transfers', () => {
    expect(primariesName('bt2020')).toBe('BT.2020')
    expect(primariesName('bt470bg')).toBe('BT.601 (PAL)')
    expect(primariesName('unknown')).toBeNull()
    expect(primariesName('weird')).toBe('weird')
    expect(transferName('arib-std-b67')).toBe('HLG')
    expect(transferName(null)).toBeNull()
  })
  it('names HDR formats', () => {
    expect(hdrName('PQ (HDR10)', 'smpte2084')).toBe('HDR10 (PQ)')
    expect(hdrName('HLG', 'arib-std-b67')).toBe('HLG')
    expect(hdrName(null, 'smpte2084')).toBe('HDR10 (PQ)')
    expect(hdrName(null, 'bt709')).toBeNull()
  })
  it('describes an SDR file', () => {
    expect(colourFacts({ bit_depth: 8, chroma: '4:2:0', pix_fmt: 'yuv420p', color_primaries: 'smpte170m', color_transfer: 'smpte170m', color_range: 'tv', hdr: false })).toEqual({
      depth: '8-bit 4:2:0',
      colour: 'BT.601 (NTSC) primaries · BT.601 transfer · limited range',
      hdr: null,
    })
  })
  it('describes an HLG 10-bit 4:2:2 file and alpha', () => {
    const f = colourFacts({ bit_depth: 10, chroma: '4:2:2', pix_fmt: 'yuv422p10le', color_primaries: 'bt2020', color_transfer: 'arib-std-b67', hdr: true, hdr_format: 'HLG' })
    expect(f.depth).toBe('10-bit 4:2:2')
    expect(f.colour).toBe('BT.2020 primaries · HLG transfer')
    expect(f.hdr).toBe('HLG, tone-mapped to SDR for the preview')
    expect(colourFacts({ bit_depth: 12, chroma: '4:4:4', pix_fmt: 'yuva444p12le' }).depth).toBe('12-bit 4:4:4 with alpha')
  })
  it('says nothing for an untagged file', () => {
    expect(colourFacts({})).toEqual({ depth: null, colour: null, hdr: null })
  })
})

describe('decoded files', () => {
  it('reads decoded_from', () => {
    expect(decodedFromText({ decoded_from: { format: 'MotionCam RAW', master: '/m/master.mov', decoder: 'cp {input} {output}' } })).toEqual({ format: 'MotionCam RAW', decoder: 'cp {input} {output}' })
    expect(decodedFromText({})).toBeNull()
  })
  it('counts decode errors', () => {
    expect(decodeErrors({ 'quality.decode_errors': { value: 3 } })).toBe(3)
    expect(decodeErrors({ 'quality.decode_errors': { value: 0 } })).toBe(0)
    expect(decodeErrors({})).toBe(0)
  })
})
