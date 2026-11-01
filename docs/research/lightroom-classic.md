# Lightroom Classic photo selection and editing research

Research date: 1 November 2026. Repository inspected at `f22e108`.

Extend Metachlorian itself with photo ingestion, understanding, selection and Lightroom editing tools. The user connects Codex or another MCP-capable agent to Metachlorian, asks for photographs and a desired result, and the agent uses those tools to find and edit the images. Prioritise portraits, travel, and family photographs, especially a young child. Keep originals in place and make additional storage predictable.

Photo functionality belongs in the existing Metachlorian application, core service, database and MCP endpoint. Codex is the editing agent. Metachlorian supplies library knowledge, photographic evidence, editing guidance and tool execution. Lightroom remains the authority for its catalogue and rendered edits. A bundled Lightroom connector can provide access to Classic; its Lua plug-in component is only an application bridge, not another agent or a separate photo product. This is a proposed extension; no Lightroom integration or image-quality benchmark has been implemented here.

## Product and agent workflow

The intended request is: “Find the best 20 photos of my son from our holiday, include a variety of moments, and edit them naturally in Lightroom.” After source setup and granting the agent the appropriate edit scope, the user should not need to specify Lightroom sliders, manually export previews, transfer files between products, or install a second AI agent.

Photo folders should work directly as Metachlorian sources, without Lightroom. Connecting a Classic catalogue adds catalogue organisation, existing edits, preview access and a destination for editing. Both sources appear in the same library. Resolve the relationship between a folder image and its Lightroom entry rather than ingesting another copy; each virtual copy still has its own edit identity.

The agent workflow is:

1. **Find relevant photographs.** Metachlorian combines the request with metadata, semantic search and known people. It returns matching photos ranked for the stated purpose, with burst alternatives and explanations. A portrait for a frame and a family album should not use the same selection priorities. Relevance comes before a generic aesthetic score.
2. **Inspect the shortlist.** Codex requests actual image previews and, when needed, subject or eye details. Metachlorian reports which judgements are supported by the available resolution. Compare expression, focus, composition and editing potential while preserving different moments.
3. **Obtain editing context.** A proposed `get_photo_edit_context` tool returns current develop state, verified controls, relevant photographic guidance, existing style preferences and the target rendition. Codex decides the image-specific changes. Metachlorian's guidance describes when a control helps and what to inspect afterward, so every client does not have to rediscover Lightroom workflows.
4. **Apply and render a candidate.** Codex submits a validated edit plan through Metachlorian. The Lightroom adapter translates supported operations, applies them to a recoverable candidate variant and obtains a fresh Lightroom render. Keep this within a bounded job and storage budget.
5. **Evaluate the actual result.** Codex compares the original edit and candidate, checks relevant detail and refines within a limited number of attempts. Keep the baseline when changes do not improve the image. A successful settings write alone is not evidence of a better photograph.
6. **Deliver inside Lightroom.** Save selected edits as editable Lightroom variants in a named collection, return per-photo outcomes and make that collection easy to find. Retain final settings and compact evidence; expire temporary renders and unused candidates.

Metachlorian owns indexing, retrieval, ranking evidence, control validation, execution and job state. The connected agent owns conversational intent, selection trade-offs and visual editing decisions. Existing ingestion models remain useful, but the editing loop does not require a second autonomous agent or an additional hosted-model subscription. Visual verification requires an image-capable agent or an explicitly configured vision service; a text-only client must not claim to have inspected a render.

The preferred product exposes the workflow through the existing Metachlorian MCP. Lightroom integration should sit behind an internal adapter: capability discovery, catalogue access, rendering, develop changes and collection operations. The default adapter can be shipped with Metachlorian and enabled through a Connect Lightroom setup flow, including any activation Lightroom requires. Users should not manage a separate MCP endpoint for that bundled connector.

An agent can also connect to Metachlorian for discovery and an independent Lightroom MCP for execution. That is a valid alternative if its capabilities are verified; no particular external Lightroom MCP has been evaluated here. In that arrangement, fresh previews and changed develop state must return through the agent or a synchronization path before Metachlorian evaluates or re-indexes the result. Keeping the execution boundary explicit supports both arrangements.

Adobe's [Classic SDK](https://developer.adobe.com/lightroom-classic) provides the Lua extension route. A lightweight XMP handoff can support some offline interchange, but [reading external metadata into Classic](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/advanced-metadata-actions.html) changes catalogue settings and is not itself a render-and-verify loop. Current [XMP and ACR sidecar documentation](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/create-xmp-acr-files.html) also describes separate storage for heavier edits. Therefore, do not promise complete Lightroom automation simply by writing an XMP file.

The first complete milestone must demonstrate one collection going from a natural-language request to selected, visibly evaluated, editable results in Lightroom. Photo search alone is an intermediate milestone. Start with a narrow set of verified adjustments and expand control coverage after this complete workflow succeeds.

## What the existing project contributes

| Existing component | Reuse and required changes |
| --- | --- |
| [Ingestion](../../core/metachlorian/ingest/scan.py) | Existing paths, hashes, and duplicate tracking are useful. Discovery currently admits video extensions; still photography needs its own source adapter and format handling. |
| [Pipeline](../../core/metachlorian/pipeline.py) and [analyser contract](../../core/metachlorian/analysers/base.py) | Reuse resumable jobs, dependency ordering, versioned results, and atomic commits. Add a photo-specific dependency graph and include develop state in rendition-dependent cache keys. |
| [Quality measurements](../../core/metachlorian/media/quality.py) | Exposure, noise, sharpness, colour and saliency are useful raw signals. Current sharpness resizes to 640 pixels wide and measures the whole image. Its threshold is not a reliable judgement of eye focus. |
| [Quality analyser](../../core/metachlorian/analysers/quality.py) | Separate confidence in a measurement from confidence in its interpretation. A deterministic threshold does not make an out-of-focus classification certain. |
| [Image embeddings](../../core/metachlorian/analysers/embed.py) | Reuse the encoder for semantic retrieval; replace keyframe/shot plumbing with photo renditions. Avoid storing both a photo vector and an identical single-keyframe vector. |
| [Face analysis](../../core/metachlorian/analysers/faces.py) | Reuse local recognition infrastructure where suitable. Current code writes face JPEGs; the photo path should keep boxes/embeddings and regenerate crops on demand. Validate recognition across a child's changing appearance. |
| [Database](../../core/metachlorian/db.py), records and search | Reuse signal provenance and human corrections. Vectors, collections and search indexes currently reference shots; introduce genuine photo/variant entities rather than fake one-frame videos. |
| [MCP server](../../core/metachlorian/mcp_server/server.py) and service | Reuse authentication, scopes, audit and shared service logic. Add photo tools and a Lightroom adapter. Existing video exports and Cutawan packages are not a Lightroom edit protocol. |

Start with an additive photo subsystem in this repository, sharing infrastructure. Keep existing shot tools and video clients compatible. Photo scheduling needs distinct source/variant targets: the current asset-only analyser-run identity cannot independently track multiple Lightroom edits of the same source. Separate source-dependent facts from rendition-dependent analysis so an exposure adjustment does not re-read EXIF or re-hash the original. Lightroom integration runs on the user's Mac or Windows computer; the current Linux research environment cannot validate it end to end.

## Ingest without duplicating the library

### Use Classic as the source of truth

[Adobe's Classic SDK](https://developer.adobe.com/lightroom-classic) supports Lua plug-ins. Use that integration boundary to enumerate photographs, retrieve metadata and settings, obtain rendered previews, and perform supported catalogue operations. Prototype against the SDK bundled for the installed Lightroom version before committing to particular methods or settings.

Prefer a plug-in over writing the `.lrcat` database or decoding private preview-cache internals. A closed-catalogue snapshot reader could be an optional, read-only import path, but catalogue schemas and preview layouts are not the supported editing interface. Copying the whole catalogue is also unnecessary for routine indexing.

Index the catalogue identity plus photo identity, master/virtual-copy relationship, original path and availability, file type and dimensions, capture time and timezone confidence, camera/lens, focal length, aperture, shutter speed, ISO, orientation, GPS when present, captions, keywords, ratings, flags, collections, stacks, and current develop state. Preserve missing values as unknown. Do not infer family relationships from faces; use the user's labels.

Use Lightroom-returned identity within a catalogue namespace, with explicit relinking after catalogue migration. Paths and content hashes alone cannot identify virtual copies. RAW+JPEG companions should be linked, not silently collapsed. Full hashes can be computed lazily when originals are available; an offline placeholder must not trigger downloads or mass reads from sleeping disks.

### Choose the cheapest adequate image representation

[Smart Previews](https://helpx.adobe.com/lightroom-classic/desktop/viewing-photos/lightroom-smart-previews.html) are smaller lossy DNG representations that let Lightroom edit while originals are disconnected. Reuse those already present through Lightroom's rendering path. Do not build Smart Previews for the whole catalogue merely to run this feature.

| Representation | Suitable decisions | Limits |
| --- | --- | --- |
| Metadata only | Dates, lenses, ratings, collections, availability | Cannot judge image content |
| Small current Lightroom rendition | Search, scene, broad composition, grouping | Tiny faces and detail may be indeterminate |
| Larger rendition from an existing Smart Preview | Crop alternatives, expression, broad colour/light edits | Not authoritative for original pixel detail or RAW recovery |
| Temporary original-resolution view/crop | Close focus comparisons, sharpening, noise, final print detail | Needs original access and Lightroom rendering/decoding |

A cached or embedded camera JPEG can be stale or use a different rendering from Lightroom. Store representation type, actual dimensions, colour space, crop/orientation, develop fingerprint, renderer version, and freshness with every observation. A blown preview highlight is not proof that the RAW channel is unrecoverable.

When Lightroom is closed, the index can still answer textual searches; fresh rendering and edits wait for the plug-in. An optional thumbnail cache supports offline browsing. Missing originals produce qualified results, not invented full-resolution confidence.

### Storage budget

The promise should be **no duplicate originals and bounded derivative storage**, not zero extra bytes. Proposed default: a 256 MiB combined temporary-rendition and thumbnail cache, streamed analysis, one visual embedding per photo, and no retained face crops, segmentation bitmaps, contact sheets, or full-resolution edits.

Illustrative estimates below use decimal MB and an assumed 768-dimensional float16 embedding; they are budgeting calculations, not measured product performance.

| Stored data | 10,000 images | 100,000 images |
| --- | ---: | ---: |
| One embedding, 768 × 2 bytes | 15.36 MB | 153.6 MB |
| Compact records averaging an assumed 5–15 KB/image | 50–150 MB | 500–1,500 MB |
| Database indexes, vector search structure, face vectors, journals | Additional; measure on a real catalogue | Additional; measure on a real catalogue |
| Preview and temporary cache | At most the configured 256 MiB | At most the same configured 256 MiB |

For comparison, retaining a 200 KB JPEG for every image would add 2 GB at 10,000 images or 20 GB at 100,000. Avoid that design. A practical initial acceptance target is under 500 MB for 10,000 indexed photos including the bounded cache, excluding shared model weights and Lightroom-owned storage. Verify the target rather than presenting it as guaranteed.

Cache eviction must include failed jobs, temporary exports and worker concurrency. Reserve space before producing a rendition; refuse or downsize work if the budget cannot accommodate it. Bound retained analyses and audit history separately. Surface database, models, cache, and Lightroom-side growth individually. Local model downloads are a separate fixed cost; share Metachlorian's installed models and make a large VLM optional.

Lightroom may grow its own previews, AI edit data, catalogue history, and backups during rendering and editing. Measure that growth in the pilot. Avoid creating virtual copies for every candidate or automatically running Enhance/merge across the entire library. Exact derivative-file behaviour depends on Lightroom version and operation; current [Enhance documentation](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/enhance-details.html) places Denoise, Raw Details and Super Resolution in the Detail panel, so do not assume every operation always creates a separate enhanced DNG.

## What makes a photograph worth choosing

Use a multidimensional assessment, with separate current appearance, technical capture quality, editing potential, personal relevance, and evidence confidence. The following rubric is a proposed product policy, not an objective law of photography.

| Dimension | Evidence to inspect | Family and portrait judgement |
| --- | --- | --- |
| Moment and meaning | Gesture, interaction, gaze, expression, event context, uniqueness | Keep meaningful alternatives; a laugh with closed eyes is not automatically a reject |
| Focus and motion | Main subject and eye regions, intended focus plane, directional blur, full-resolution confirmation | Distinguish sharp background/soft child from deliberate shallow depth of field; moving hands need not spoil a face |
| Composition | Subject hierarchy, edge distractions, head/hand cuts, gaze space, balance, horizon, background mergers, negative space | Preserve the relationship and setting, not just a tightly cropped face |
| Light | Facial light, direction and softness, separation, harsh shadow transitions, important highlight detail | Bright skies and specular highlights need different treatment from clipped skin |
| Colour | White balance, mixed illumination, skin plausibility, distracting hues, palette | Avoid one universal skin-colour target and automatic orange warmth |
| Capture choices | Aperture, shutter, ISO, focal length, distance where available, lens behaviour | Judge the result and intent; high ISO or a wide aperture is not inherently bad |
| Editability | Remaining pixels after crop, likely recovery, noise cost, local correction feasibility | Prefer a recoverable exposure over an irretrievably missed focus when the moments are comparable |
| Set value | Burst similarity, distinct gestures, people and event coverage, relationship to already selected images | An album needs variety, including quieter moments and wider travel context |

[Nikon's composition guidance](https://www.nikonusa.com/learn-and-explore/c/tips-and-techniques/composing-photographs) illustrates background competition, subject separation and framing. Turn these into evidence and alternative crops, not rigid penalties for breaking the rule of thirds. Aperture is a capture parameter: editing cannot change the original focus plane or recover unseen detail. Synthetic blur can change appearance but cannot recreate a different capture faithfully.

Group likely bursts using capture time, visual similarity, camera identity and scene context, then compare candidates within each group. Preserve distinct moments rather than retaining one arbitrary winner per time window. Clock errors, screenshots, exported duplicates and similar-looking days need explicit handling.

Present explanations such as: “Best expression in this sequence; foreground eye appears sharp; bright background distracts; a modest crop could help. Original required for print-detail confirmation.” Never equate a broad aesthetic model score with the personal value of a photograph. Keep originals and existing user ratings intact; suggested selects belong in a named collection or separate recommendation field.

### Models and evidence

Use deterministic metadata and region measurements alongside subject/face detection, image embeddings, and optional vision-language critique. VLM output should use a structured rubric, cite image regions, and allow unknown. It is a hypothesis about the picture, not a calibrated focus sensor.

[NIMA](https://research.google/pubs/nima-neural-image-assessment/) is a research baseline distinguishing technical and aesthetic assessment. [MUSIQ](https://research.google/blog/musiq-assessing-image-aesthetic-and-technical-quality-with-multi-scale-transformers/) explores multi-scale quality assessment while preserving aspect ratio. Evaluate these approaches as supplementary ranking signals; model age, licence, runtime, domain bias and local performance still need assessment. Do not distort the frame to a square before evaluating composition merely because a retrieval encoder accepts square input.

Personalisation should learn from explicit pairwise choices, accepted edits and “keep this moment” feedback. Existing ratings provide a starting signal but may describe sentimental importance rather than technical quality. Keep those concepts separate. Sleeping children, profiles, glasses, darker skin, backlighting and motion should be represented in evaluation.

Adobe already provides [Assisted Culling](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/assisted-culling.html), including subject/eye focus, open eyes and exposure filters. Benchmark against it. Its UI availability does not establish that its scores are exposed through the SDK. The additional value here is contextual search, personal choices, album diversity and an explainable editing loop.

## Lightroom controls the editing system should understand

This is an inventory of relevant control families, not a claim that every control is exposed through a public API. Build the exact parameter registry from the installed Classic/SDK version, with type, units, bounds, defaults, applicable formats/process versions, dependencies, read/write support, and a verified render test. New controls must remain unavailable until verified.

| Family | Controls to represent | Intended use and judgement |
| --- | --- | --- |
| Rendering foundation | Process version; Colour/B&W treatment; Adobe, camera-matching, creative and adaptive profiles where available; profile amount | Establish the rendering before judging other adjustments; retain the existing profile as a baseline |
| White balance | As Shot/Auto/custom; temperature; tint; neutral sampling | Correct casts while retaining believable ambient warmth; mixed light may need local correction |
| Global tone | Exposure, contrast, highlights, shadows, whites, blacks; Auto as a candidate | Establish subject brightness and tonal endpoints; avoid flattening every image |
| Presence | Texture, clarity, dehaze, vibrance, saturation | Control local contrast and colour intensity without brittle skin, halos or excessive saturation |
| Tone curve | Parametric highlights/lights/darks/shadows and range boundaries; point curve; RGB channel curves | Shape contrast and colour relationships; avoid crushed detail and colour casts |
| Colour Mixer | Hue/saturation/luminance for red, orange, yellow, green, aqua, blue, purple and magenta; targeted adjustment | Reduce competing colours or refine a palette; global orange changes may affect both skin and surroundings |
| Point Color | Sampled colours; hue/saturation/luminance shifts; range and component ranges; Variance where available | Refine specific colours with tighter selection; isolate with a mask when other objects share the colour |
| Colour Grading | Shadows/midtones/highlights and global hue/saturation; luminance; blending; balance | Intentional tonal colour styling, evaluated against natural skin and the desired mood |
| Black and white | Monochrome profile, B&W mix and tonal controls | Offer an alternative when light and form support it; do not treat B&W as a universal rescue |
| Crop | Aspect, bounds, angle, straighten, rotate/flip, constrain behaviour | Improve framing while preserving gestures and sufficient output pixels; compare original and crop |
| Lens corrections | Profile enable/selection; distortion and vignetting amounts; chromatic aberration; manual distortion and defringe ranges | Correct optical defects before evaluating final geometry |
| Transform | Upright modes/guides; vertical, horizontal, rotate, aspect, scale, X/Y offsets; constrain crop | Straighten travel architecture without stretching people unnaturally |
| Capture sharpening | Amount, radius, detail, masking | Judge at original resolution; avoid sharpening skin texture or noise unnecessarily |
| Noise and enhancement | Luminance noise reduction/detail/contrast; colour noise reduction/detail/smoothness; AI Denoise; Raw Details; Super Resolution | Balance detail, noise and output size; test format/GPU requirements and storage consequences |
| Mask selection | Subject, sky, background, people/parts, objects, landscape categories where available; brush; linear/radial gradients; colour/luminance/depth ranges | Name what to affect, then inspect the actual mask and its boundaries |
| Mask refinement | Add, subtract, intersect, invert; feather, flow, density, brush size, auto mask; overall amount where available | Avoid spill onto hair, skin, clothing and edges; maintain coordinate transforms after cropping |
| Local adjustments | Available light, colour, curve, texture/clarity/dehaze, sharpness/noise, moiré and defringe controls | Use the per-version local registry: global controls are not all interchangeable with local ones |
| Removal and repair | Clone/heal/content-aware/generative modes; size, feather, opacity, source placement; dust/people/reflection tools where available; red-eye correction | Start with transient distractions; preserve family members and meaningful context; label generated content changes |
| Lens Blur | Blur amount, focus range, subject/point focus, bokeh shape/boost and applicable refinements | Optional creative variant; inspect hair, fingers and depth boundaries |
| Effects | Post-crop vignette style/amount/midpoint/roundness/feather/highlights; grain amount/size/roughness | Direct attention or create a chosen texture without automatically applying a heavy look |
| Calibration | Shadow tint; red/green/blue primary hue and saturation where available | Broad rendering changes require care; not a substitute for targeted skin correction |
| Multi-image operations | HDR merge, panorama, projections/boundary handling and deghosting as applicable | Separate jobs with new-asset/storage implications; not a default family portrait operation |
| Delivery | SDR/HDR choice; soft proof and gamut checks; output profile, pixel dimensions, file quality/bit depth, output sharpening and metadata | Judge the intended screen/print result, not just the Develop preview |
| Reversible workflow | Snapshots/history, virtual copies, reference comparison, presets and selective sync | Preserve the starting edit, compare alternatives and propagate only suitable settings |

Reference controls against Adobe's [tone and colour guide](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/image-tone-color.html), [Color Mixer guide](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/color-mixer.html), [retouching guide](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/retouch-photos.html), [masking guide](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/masking.html), [Lens Blur guide](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/lens-blur.html), and [Develop overview](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/develop-module-tools.html).

Cropping, geometry, local light and selective colour can radically change visual emphasis within Lightroom. They do not supply a new camera viewpoint, move limbs, or recover parts of the scene outside the capture. Content generation is a separate creative choice, not ordinary photographic correction.

## Teach decisions rather than memorised slider recipes

Tutorial knowledge should become a compact set of condition → action → expected effect → failure checks, with sources and Lightroom version. Avoid a universal “portrait preset” or thousands of copied transcripts. Store pointers and original summaries; evaluate rules on actual images.

| Source | Recommended use |
| --- | --- |
| [Julieanne Kost's Classic tutorial library](https://jkost.com/blog/lightroom-training-videos) | Primary practical syllabus: catalogue/previews, profiles, exposure, curves, HSL/Point Color/grading, crop, masking and output. The index includes newer AI material alongside fundamentals. |
| [Adobe MAX editing and masking session](https://www.adobe.com/max/2025/sessions/quick-fix-bold-impact-mastering-editing-masking-to-os420.html) | Study how edits and masks work together; derive candidate correction sequences. |
| [Adobe's AI editing workflow lesson](https://www.adobe.com/learn/lightroom-cc/web/lightroom-ai-order-of-operations) and [Kost's Classic AI edit order lesson](https://jkost.com/blog/2026/01/the-correct-order-for-ai-edits-in-lightroom-classic.html) | Handle AI dependencies and avoid repeated recomputation when earlier operations change. |
| [Ben Willmore's Complete Guide](https://www.creativelive.com/classes/adobe-lightroom-classic-the-complete-guide-ben-willmore) | Structured course candidate for deeper workflow study; supplement older lessons with current Adobe feature documentation. |
| [MIT–Adobe FiveK](https://data.csail.mit.edu/graphics/fivek/) | Research reference with multiple human retouches, Lightroom settings and adjustment histories. Demonstrates useful variation between editors; check research licences before training or redistribution. |

The public documentation and course descriptions were reviewed; this report does not claim that paywalled classes or all linked videos were watched. FiveK is roughly 50 GB as a full download, so it should not become a default application dependency. A small licensed research sample and the user's own chosen examples are more appropriate to this storage goal.

Suggested learning order: catalogue and rendering; photographic intent and culling; profiles/WB/tone; crop and geometry; colour; local masks; detail and output; advanced AI tools. For each family, include successful examples and cases where leaving the image alone is better.

The [Adobe AI workflow lesson](https://www.adobe.com/learn/lightroom-cc/web/lightroom-ai-order-of-operations) gives a concrete dependency example: enhancement and distraction repair precede finishing adjustments, with masking near the end. Its published sequence places lens/profile geometry work before adaptive profiles, global adjustments and masks. If an earlier operation is changed afterward, update affected AI edits before comparing results. The lesson covers Lightroom broadly, including features whose availability differs across products; use the installed Classic capability list rather than importing the entire lesson's tool list unchanged.

Example rule: if the child's face is too dark against a bright window, test a restrained subject-local light adjustment before lifting the entire frame. Inspect skin highlights, noise, mask spill and background balance after rendering. Slider values depend on the image and current edit; the rule should not invent fixed values.

## Editing loop and MCP design

1. Retrieve relevant photos and compare bursts using the user's goal, such as “20 favourites from our holiday, including quiet moments with my son.”
2. Separate selection from editing: retain strong moments even when a technical score is lower. Request original-resolution evidence only for decisions that need it.
3. Read current settings and renderer/profile information. Establish output intent and a baseline Lightroom rendition.
4. Propose a bounded set of operations with reasons, expected effects and verification requirements. Start with a natural family edit; offer a distinct creative variant only when useful.
5. Apply supported operations to a temporary candidate/selected virtual copy through the plug-in. Use Lightroom's current AI dependency guidance and refresh affected AI edits before judging the output.
6. Render in Lightroom, compare with baseline at the same dimensions/colour pipeline, then inspect relevant detail crops. Check skin, clipped important highlights, halos, masks, excessive blur, remaining crop pixels and whether the image still feels like the same moment.
7. Accept, revise within a small render budget, or keep the original edit. Persist settings and explanations; discard temporary image files. Save only selected variants into a clearly named Lightroom collection.

Proposed tools: `search_photos`, `get_photo`, `compare_burst`, `get_photo_preview`, `get_photo_edit_context`, `get_lightroom_capabilities`, `propose_photo_edit`, `apply_photo_edit`, `evaluate_photo_edit`, and `create_lightroom_collection`. These are proposed names, not existing endpoints. Document the complete workflow in MCP server instructions and supply compact edit guidance through tools/resources. Proposal and evaluation tools must distinguish agent judgements from measured checks; do not hide an unspecified second agent behind those names. Long-running writes/renders need job IDs, status, cancellation and per-photo outcomes so any compatible client can resume them.

Read tools should return source resolution, confidence, reasons, edit potential and availability. A preview tool must actually expose image content for visual inspection; text-only critiques cannot validate the edit. Keep original pixels and family face data local by default, with hosted-model use governed by the project's explicit remote-analysis setting. Photo ingestion must not inherit public contribution behaviour.

Write requests need catalogue/photo/variant identity, expected develop fingerprint, operations, target policy, and an idempotency key. If a human has edited since planning, return a conflict and re-plan rather than overwriting. Scope catalogue writes separately from search. Use authenticated local transport and expose only schema-validated operations, not arbitrary Lua execution. Preserve the full starting state where supported and a Lightroom recovery point; restoring a few global sliders is not sufficient rollback for masks or AI data.

Capabilities should be recorded per control as verified read/write, read-only, manual, or unsupported. Discovery must not imply that an arbitrary settings key is safe to write. Advanced masks, Generative Remove, Lens Blur, Enhance, crop transforms, and retrieval of Assisted Culling scores are explicit integration questions. When unavailable, return an actionable manual step rather than report success. XMP is useful for some interchange, but is not a substitute for complete catalogue state, virtual-copy identity and complex AI edits.

Lightroom's [cloud API](https://developer.adobe.com/lightroom/lightroom-api-docs/) targets cloud catalogues and is a separate adapter. Its [rendition documentation](https://developer.adobe.com/lightroom/lightroom-api-docs/getting-started/read-generate-renditions/) describes access restrictions for generated full-size renditions. It should not be treated as a local Classic control API or used to require uploading this family library.

## Implementation sequence and acceptance criteria

**First prove the Classic connection.** On the user's installed version, enumerate a small collection, retrieve current metadata/settings, render using existing previews with originals disconnected, and return a selected set to Lightroom. Verify supported basic changes on a disposable variant, render them, read back state, and restore it. Record exact supported capabilities. This resolves the highest integration risk before building advanced ranking.

**Then build storage-limited selection.** Add photo entities, rendition provenance, a bounded cache, semantic search, burst grouping, region-specific quality evidence, and named suggested-select collections. Selection and explanation are intermediate deliverables toward the complete agent-to-Lightroom workflow.

**Add a measured editing loop.** Begin with verified profile/WB/tone/crop/colour controls. Compare against the existing edit and Lightroom Auto on a representative sample. Add local masks and AI operations only after bridge support and render verification pass.

**Personalise with real choices.** Use a proposed pilot of 200–500 consented images across family, portraits and travel, including bursts, indoor low light, different skin tones, sleeping/laughing expressions, shallow depth of field, backlighting and deliberate motion. Split evaluation by event/burst so near-duplicates cannot leak across training and evaluation.

Measure favourite recall, pairwise preference, diversity of the selected set, unnecessary reject suggestions, editing preference versus original/Auto, correction time, and uncertainty calibration. Evaluate full-resolution judgements separately from preview-only results. Do not use the same aesthetic scorer as both editor objective and sole success judge; blind user comparisons matter more.

Engineering acceptance includes incremental re-indexing after a develop change, preserved virtual-copy identity, stale-preview detection, missing-original behaviour, conflict protection during human edits, idempotent retries, recovery after an interrupted render, and stable repeated-run disk use. Test cache limits with concurrent jobs and include Lightroom-side storage growth in the report. Keep source originals untouched and never delete family photographs automatically.

Before implementation, the remaining setup facts are the installed Classic version, operating system, catalogue size, typical RAW/JPEG/HEIC mix, and existing Smart Preview coverage. These determine compatibility and measured budgets; they do not change the recommendation to reference originals and bound all derivative storage.
