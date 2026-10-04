# Video formats, bit depths and colour

**The short version:** anything FFmpeg can decode is analysed, at any bit depth and in any colour space, and plays in
the app. Camera raw that only the maker's software can read works through that software when you point Metachlorian at
it.

## How playback works

The app never plays your original files. Each file gets a small preview (proxy) made when it is added: H.264, 8-bit
4:2:0, 540p, which every browser and the desktop app can play instantly. So footage that ordinary players struggle with —
Sony XAVC HS (HEVC 4:2:2 10-bit), XAVC S-I All-Intra, ProRes 4444, DNxHR, 12-bit RAW-derived masters — plays without
MPV or a codec pack. Analysis also reads the preview, so it sees the same picture you do.

The preview is converted for display:

- **Any bit depth and chroma**: 8, 10, 12 and 16-bit, floating point, 4:2:0, 4:2:2, 4:4:4, RGB and alpha.
- **Colour space**: BT.709, BT.601 (PAL and NTSC), BT.2020, DCI-P3 and others are converted to BT.709 and labelled as such.
  Untagged files are read the way players read them (SD as BT.601, HD and up as BT.709, MJPEG as full-range BT.601).
- **HDR** (HLG and HDR10/PQ, including the A6700's HLG profiles) is tone-mapped to SDR: reference white (203 nits) becomes
  SDR white, and highlights up to the file's own peak brightness (or 1000 nits) roll off smoothly.
- **Interlaced** footage (XDCAM, AVCHD, DV) is deinterlaced for the preview.
- **Log** (S-Log3, V-Log, C-Log, LogC) is shown flat, as recorded, and detected and labelled as log. Picture profiles such as
  S-Cinetone (PP11 on Sony cameras) are ordinary Rec.709 and need nothing special.

## Your originals stay untouched

Exports and packages built from originals keep their quality: 10-bit or 4:2:2 footage becomes ProRes 422 HQ, and 4:4:4,
RGB, alpha or 12-bit footage becomes ProRes 4444. HDR, log and BT.2020 tags and interlacing are kept, and audio is PCM.
Ordinary 8-bit 4:2:0 footage stays H.264 at near-transparent quality. Timelines (OTIO, FCPXML, EDL) always point at
the original files themselves.

## Camera raw

| Format | Extension | Decoder you need |
|---|---|---|
| Blackmagic RAW | `.braw` | Blackmagic RAW SDK tools, or DaVinci Resolve |
| RED | `.r3d` | REDline (RED's command-line tool) |
| ARRIRAW / ARRIRAW HDE | `.ari`, `.arx` | ARRI Reference Tool (command line) |
| Canon Cinema RAW Light | `.crm` | Canon RAW Development, or DaVinci Resolve |
| Nikon N-RAW | `.nev` | Nikon's tools, or DaVinci Resolve |
| ProRes RAW, Sony X-OCN | inside `.mov` / `.mxf` | Apple / Sony tools, or DaVinci Resolve |

Two ways to bring raw footage in:

1. **A decoder command** (best when the maker has a command-line tool): Settings → Formats, or in `config.toml`:

   ```toml
   [raw_decoders]
   r3d = "REDline --i {input} --o {output_stem} <your REDline options for ProRes 4444>"
   ```

   `{input}` is the raw file and `{output}` the `.mov` to write (`{output_stem}` is the same without the extension;
   `{output_dir}` is its folder). Metachlorian runs the command once per file, keeps the result as the file's working
   master (in the library's media folder), and analyses and exports from it. Check your tool's options for its version;
   any output FFmpeg can read works, and ProRes 4444 or 422 HQ is a good choice. Changing the command reprocesses
   that format.
2. **Export a ProRes/DNx copy** from DaVinci Resolve or the camera maker's software into a watched folder.

Without either, raw files are listed with a clear message rather than skipped.

Some raw cameras also record a proxy alongside the raw file (for example H.264 proxies on Blackmagic and RED cameras).
Those are ordinary video files and are analysed straight away.

## Damaged files

If part of a file can't be decoded (an interrupted recording or a bad card copy), Metachlorian still makes what it can and
flags the file as "Damaged picture", rather than silently showing black or glitches.
