# Specific places and continuity

The caption analyser now recognises four independent levels: destination,
venue (park/resort), area (land/neighbourhood), and attraction/show. Each name
has visible/audible evidence and a high, probable or unknown assessment.
Probable results remain candidates. The model is prompted to distinguish
productions with similar characters and to leave ambiguous levels empty.
These assessments and the continuity scores are heuristics, not calibrated
probabilities or verified facts.

Contact-sheet tiles are 640 pixels wide; the model receives sheets up to 1280
pixels wide rather than shrinking them to 768. Configure an appropriate VLM
in Settings; a stronger model can help with distinctive landmarks and sets.
No particular provider or holiday destination is hardcoded.

An optional `logging_context` in the library's `config.toml` narrows the search,
for example `logging_context = "Family holiday around Orlando, September 2026"`.
It is included in the caption input key, so changing it refreshes captioning
and its dependants. Context is a clue and does not establish a particular venue.
It applies to this whole library: use a separate library for unrelated trips.

Optional `place-references.json` in the library directory accepts an `entries`
array of objects with `name`, `venue`, `destination`, `area`, `period`,
`evidence` and `source_url`. Only `name` is required. Include the dates and
official source for renamed shows; these notes narrow candidates without
asserting what a clip depicts. Keep the catalogue concise (40 entries,
64 KB maximum). Its contents also participate in the caption input key.
The scanner does not fetch URLs or browse automatically. Reference text is
treated as source data, never instructions.

## Nearby camera clips

Confirm a source contains continuous camera originals when adding it:

```sh
metachlorian --data /path/to/library add --camera-originals /path/to/videos
```

Only these sources permit temporal inference. The system does not assume
that arbitrary files or finished edits are continuous takes. It uses camera
capture timestamps and durations, never file modification times. The gap is
the next take's start minus the preceding take's end. Timezone-aware and naive
camera clocks, different cameras and different folders are kept separate.
Unknown camera identities share a folder group; use separate folders for
different cameras with unidentified metadata.

High direct recognition with explicit evidence, or a reviewer's place
correction, can anchor a nearby unclear shot. The default maximum gap is 30
seconds; confidence decays with the gap. Only immediate neighbouring files
are considered. Long take-to-shot distances, overlaps, intervening conflicting
places and conflicting neighbouring anchors prevent inheritance. Inherited
labels never become anchors, so a guess cannot spread through a chain.
Specific attraction/show labels can anchor only when evidence places the
camera there (on the ride, in its queue, or watching the show). A landmark
merely seen from elsewhere remains a direct observation and cannot lend a
ride/show location to nearby family shots. Older unscoped attraction records
also cannot act as anchors. Each observation retains this relationship.
Within a confirmed camera take, nearby shots can share evidence even if a
camera timestamp is missing.

Each label retains its method, supporting shot/asset IDs, evidence and gap.
Search indexes the recognised names. The inspector and shot page show direct
recognition separately from inheritance, with a link to the supporting shot.
Human corrections always win. Empty corrections block inheritance for that
level. Correcting or reverting a place, deleting an anchor, and completing
caption analysis refresh derived labels.

To explicitly refresh after changing source flags or other metadata:

```sh
metachlorian --data /path/to/library place-context --max-gap 30
```

## Native Windows setup

The request ledger uses `filelock` so the shared Codex cap works on Windows
and Unix. Native Windows source paths retain their actual filename. Install
FFmpeg, Python and `core[analysis]`, build `app` with `npm ci && npm run build`,
and use `metachlorian serve` on loopback. Docker is optional.

Proxy generation also extracts the original 16 kHz analysis audio in the
same FFmpeg read. Background workers reserve one lane for source decoding,
so competing camera-original reads do not overload a hard drive. With three
or more workers, model work has its own lane and can overlap local analysis
and decoding. A single CLI worker still handles all resource types.

For NVIDIA inference on Windows, use a separate Python environment with a
compatible driver. Install the application's dependencies first, then replace
the CPU ONNX Runtime distribution (do not keep both distributions installed):

```sh
python -m pip uninstall onnxruntime
python -m pip install "onnxruntime-gpu[cuda,cudnn]"
```

The model loader preloads the optional CUDA runtime DLLs before inference.
SigLIP and RapidOCR use available GPU providers, with CPU fallback. Inspect
each session's `get_providers()` and benchmark actual inference; listing CUDA
as available is not proof that a model ran on it. CUDA acceleration does not
accelerate remote model requests or imply hardware decode support for every
camera codec. Keep the CPU environment as a rollback option.

If the SigLIP release asset is unavailable, its export is reproducible using
`scripts/export_siglip.py` with the original Google weights. Install torch,
transformers, onnx and sentencepiece in an export environment and follow that
script's instructions. Place its four required output files in the library's
`models/siglip-base-multilingual` folder; analysis then resumes. No weights or
personal media should be committed to the source repository.

Shot segmentation 1.1.1 enforces the configured minimum length at both ends of a clip. A final single-frame camera glitch is folded into the preceding shot rather than becoming an unextractable segment. Frame requests beyond the decoder's last frame report a controlled decode error. Existing libraries automatically refresh segmentation and its dependent analysis when upgraded.

After proxies are prepared, an optional second recognition worker can consume model jobs with `metachlorian --data LIBRARY process --resources model`. It exits when its lane is idle and shares the same leases and Codex daily request ledger. This overlaps remote recognition without adding an original-decoding lane; it does not reduce the total requests or bypass account limits. Start conservatively and check available RAM because speech models are loaded per process.

Audio analysis 1.0.1 retains FFmpeg's 100 ms EBU R128 momentary curve. Frame log verbosity matches the command's log level, so per-shot loudness is measured rather than returning empty values while the asset-level integrated summary succeeds.

Caption analysis 1.2.3 reads detector count, optical flow, transcript and OCR from their original analyser sources. A prior fused interpretation can no longer feed back into measured facts or change otherwise identical request cache keys on re-analysis.
