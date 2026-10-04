# Research: taxonomies and controlled vocabularies for shot-level video search

Date: 2026-10-04. Status: input to [ADR 010](../decisions/010-controlled-vocabularies.md).
Output: [`core/metachlorian/vocab/v1/`](../../core/metachlorian/vocab/v1/).

Method: web search plus reading primary sources where the build environment
could reach them (GitHub, PyPI). Several standards sites (iptc.org,
cv.iptc.org, movielabs.com, cv-mc.movielabs.com, community.adobe.com) were
blocked by the egress proxy. Facts about them come from search-result
extracts of those pages and are marked *(via search)*. Each claim links its
source.

## 1. Summary

* No single standard covers what an editor or agent searches for at shot
  level. Professional systems combine four layers:
  1. technical metadata (codec, fps, timecode)
  2. descriptive *what/where/who* (topics, places, people, objects)
  3. cinematographic *how* (shot size, angle, movement, lens)
  4. rights (usage, channel, territory, releases)
* Layer 3 now has an authoritative open reference: the MovieLabs Creative
  Vocabulary v1.0 (Lens, Shot Size, Camera Movement, Camera Angle;
  CC BY 4.0, mid-2026). XMP Dynamic Media (`xmpDM:shotSize`, `cameraAngle`,
  `cameraMove`) is the only one widely embedded in files and read by NLEs.
* IPTC is the best open source for news-style scene, genre and rights
  semantics. Its NewsCodes are CC BY 4.0. Video Metadata Hub 1.7
  (Oct 2025) is the cross-format property model. PLUS supplies the release
  and data-mining codes.
* Stock libraries expose only small, filter-oriented subsets: camera
  movement as tripod/handheld/smooth, time of day, interior/exterior, speed,
  people count and model-released. Cinema terms such as rack focus and arc
  appear in keywords, not facets.
* MAMs (iconik, CatDV, Frame.io, Axle AI) ship no shared vocabulary. They
  provide pick-list and hierarchy field types and leave the terms to each
  customer. Metachlorian should ship good defaults *and* the pick-list
  mechanics: versioned files, local extension, crosswalks.

## 2. Standards and models

| Source | What it gives us | Licence / openness | Notes |
|---|---|---|---|
| **IPTC Video Metadata Hub** 1.7 (approved Oct 2025) | Cross-format property set: ~20 descriptive, ~15 rights, ~15 admin, ~25 technical. Includes *Shot Type*, *Visual Colour*, *Genre*, *Scene*, model/property release, plus 4 new AI-prompt properties in 1.7. Serialisable as XMP, JSON and C2PA | Free spec | [VMH 1.7 release](https://iptc.org/news/video-metadata-hub-v1-7-released/), [recommendation](https://iptc.org/standards/video-metadata-hub/recommendation/), [user guide](https://www.iptc.org/std/videometadatahub/userguide/) *(via search)*. Shot Type is free text in practice (example "Aerial, long shot"). Use VMH as the **export property model**, not as a term source |
| **IPTC NewsCodes**: Scene, Genre, Media Topics, Digital Source Type | Scene: 6-digit codes, e.g. 010100 headshot, 010300 full-length, 011000 general view, 011100 panoramic, 011200 aerial, 011300 under-water, 011400 night scene, 011600 exterior, 011700 interior, 011800 close-up. Genre: Actuality, Interview, Raw Sound… Media Topics: 1,200+ subject terms in 13 languages. Digital Source Type: 20 terms incl. `digitalCapture`, `screenCapture`, `trainedAlgorithmicMedia`, `compositeWithTrainedAlgorithmicMedia` | **CC BY 4.0** for all NewsCodes | [scene CV](https://cv.iptc.org/newscodes/scene), [code lookups](https://www.controlledvocabulary.com/help/iptc-codes.html), [genre CV](https://cv.iptc.org/newscodes/genre/), [Q2-2021 genre update](https://iptc.org/news/iptc-newscodes-q2-2021-update-released/), [Media Topics](https://iptc.org/standards/media-topics/), [licence](https://iptc.org/std-dev/NewsCodes/guidelines/newscodes-guidelines.html), [DST 2024 update](https://iptc.org/news/newscodes-2024-q3-release-including-media-topics-and-digital-source-type-updates/), [DST vocab](https://cv.iptc.org/newscodes/digitalsourcetype/) *(via search)*. Media Topics fits **topic** tagging (separate from these vocabularies). Scene codes map to our shot_size, setting and time_of_day |
| **MovieLabs Ontology for Media Creation (OMC)** v2.5/2.6 + **MovieLabs Creative Vocabulary** v1.0 | OMC: production entities (Asset, Shot, Camera metadata aligned to SMPTE RIS OSVP). Creative Vocabulary: cinematography terms in **Lens, Shot Size, Camera Movement, Camera Angle**, defined by creative intent (e.g. jib vs crane by effect, not equipment). Planned expansion to composition, framing and depth of field | Creative Vocabulary **CC BY 4.0** *(via search)* | [CV announcement](https://movielabs.com/news/movielabs-announces-the-movielabs-creative-vocabulary/), [CV site](https://cv-mc.movielabs.com/), [OMC camera metadata v2.5](https://mc.movielabs.com/omc/Asset/Camera/ML_Ontology_Pt3A_CameraMetadata_v2.5.pdf), [OMC v2.6](https://movielabs.com/news/movielabs-releases-v2-6-of-the-ontology-for-media-creation/). Best **mapping target** for shot_size, camera_angle, camera_movement and lens_class. Term IRIs still to be resolved (see vocab README) |
| **Adobe XMP Dynamic Media (xmpDM)** | Shot logging: `shotName`, `shotNumber`, `shotDate`, `shotLocation`, `scene`, `takeNumber`, `good`, `logComment`, `cameraLabel`, `cameraModel`, `startTimecode`, `altTimecode`, `tapeName`, `markers`, `Tracks`. Closed choices: **shotSize** ECU, MCU, CU, MS, WS, MWS, EWS. **cameraAngle** Low Angle, Eye Level, High Angle, Overhead Shot, Birds Eye Shot, Dutch Angle, POV, Over the Shoulder, Reaction Shot. **cameraMove** Aerial, Boom Up/Down, Crane Up/Down, Dolly In/Out, Pan Left/Right, Pedestal Up/Down, Tilt Up/Down, Tracking, Truck Left/Right, Zoom In/Out | Open spec (Adobe xmp-docs) | [xmpDM namespace](https://github.com/adobe/xmp-docs/blob/master/XMPNamespaces/xmpDM.md) (read directly), [Adobe page](https://developer.adobe.com/xmp/docs/xmp-namespaces/xmp-dm/). Premiere and Bridge read these. Our **write-back target** for embedding into proxies or sidecars |
| **Dublin Core (dc:)** via XMP | title, description, subject, creator, rights | Open | Baseline for sidecar export |
| **EBUCore 1.10 / EBU CCDM** (Tech 3293 / 3351) | CCDM `EditorialObject` typed Programme / Item / **Shot**. EBUCore gives the properties. EBU Classification Schemes in XML and SKOS (`ebu_ContentGenreCS`, `EditorialFormatCodeCS`, media-type CS). Tech 3336 defines the CS maintenance model | Free specs | [EBUCore 1.10](https://tech.ebu.ch/docs/tech/tech3293.pdf), [CCDM v2.2](https://tech.ebu.ch/docs/tech/tech3351.pdf), [EBU CS / Tech 3336](https://tech.ebu.ch/publications/tech3336), [MediaTypeCS](https://www.ebu.ch/metadata/ontologies/skos/ebu_MediaTypeCS.htm) *(via search)*. Use CCDM's asset → shot hierarchy as the object model. EBU CS is a model for publishing vocabularies as SKOS |
| **schema.org VideoObject / Clip** | `name`, `description`, `duration`, `contentUrl`, `thumbnailUrl`, `transcript`, `Clip` (`startOffset`/`endOffset`), `SeekToAction`, `acquireLicensePage`, `usageInfo` | Open | [Google video structured data](https://developers.google.com/search/docs/appearance/structured-data/video), [acquireLicensePage](https://schema.org/acquireLicensePage). Fits public share pages and JSON-LD on the REST API. A shot is a `Clip` of its asset |
| **PBCore 2.1** | Asset / instantiation / essence-track model. `pbcoreAssetType`, `pbcoreGenre` (points to IPTC genres and LoC MIGFG), `instantiationGeneration` | Open (public media archives) | [elements](https://pbcore.org/elements/pbcoregenre.html), [essence track](https://pbcore.org/elements/instantiationessencetrack.html), [VMH↔PBCore mapping](https://iptc.org/std/videometadatahub/recommendation/IPTC-VideoMetadataHub-mapping-PBCore21-Rec_1.7.html) *(via search)*. Archive export target. `instantiationGeneration` is similar to our edit_type |
| **PLUS** (LDF, Media Matrix, release and DMI codes) | Model Release Status MR-NON / MR-NAP / MR-UMR / MR-LMR. Property Release Status PR-NON / PR-NAP / PR-UPR / PR-LPR. **Data Mining** values DMI-UNSPECIFIED, DMI-ALLOWED, DMI-PROHIBITED-AIMLTRAINING, DMI-PROHIBITED-GENAIMLTRAINING… (IPTC Photo Metadata 2023.1). Media Matrix = standardised media-usage hierarchy and codes | PLUS standards free to use; LDF published as XMP spec | [IPTC Photo user guide](https://www.iptc.org/std/photometadata/documentation/userguide/), [LDF XMP spec](https://ns.useplus.org/LDF/ldf-XMPSpecification), [PLUS LDF](https://www.useplus.com/useplus/license.asp), [IPTC 2023.1 data mining](https://iptc.org/news/exclude-images-from-generative-ai-iptc-photo-metadata-standard-2023-1/), [values list](https://home.camerabits.com/new-in-photo-mechanic-data-mining-permissions-field/) *(via search)*. Our `release_status` and `usage.ai_training` map 1:1 |
| **IPTC RightsML 2.0 / W3C ODRL 2.2** | Policy = permissions / prohibitions / duties. Constraints by purpose, spatial (ISO 3166 or TGN URIs), time | ODRL is a W3C Rec (Feb 2018). RightsML is an IPTC profile | [ODRL model](https://www.w3.org/TR/odrl-model/), [RightsML 2.0](https://iptc.org/news/rightsml-2-0-is-now-published/), [ODRL profile BP](https://w3c.github.io/odrl/profile-bp/). Use the ODRL shape internally (permission/prohibition + constraints), with our vocabularies as the constraint values |
| **ISO 3166-1 / UN M49** | Country codes / region codes | ISO holds copyright and its licensing is unclear | [ISO 3166](https://www.iso.org/iso-3166-country-codes.html), [discussion](https://en.wikipedia.org/wiki/ISO_3166-1). Ship code data from **Unicode CLDR** (permissive Unicode licence, includes M49 containment) rather than copying ISO tables |
| **SKOS** (W3C) | `prefLabel`, `altLabel`, `definition`, `broader`, `exactMatch` / `closeMatch` | W3C Rec | Our YAML is a SKOS subset (label=prefLabel, synonyms=altLabel, broader, mappings≈closeMatch). Export to SKOS/JSON-LD is mechanical |
| **AudioSet ontology** | 632 sound-event classes with MIDs (/m/09x0r Speech…) | Ontology **CC BY-SA 4.0** (dataset CC BY 4.0) | [repo](https://github.com/audioset/ontology). Reference IDs only. Do not copy text into Apache-licensed files |
| **Places365** | 365 scene classes, macro classes indoor / outdoor natural / outdoor man-made | Annotations and models CC BY. Image copyright stays with owners | [repo](https://github.com/csailvision/places365), [licence](https://github.com/CSAILVision/places365/blob/master/LICENSE). Candidate classifier for `setting` (crosswalk table, not vocabulary) |

## 3. What products expose

### 3.1 Stock libraries (facets = what buyers actually filter on)

| Library | Video facets relevant to us | Source |
|---|---|---|
| **Shutterstock** API `GET /v2/videos/search` | `aspect_ratio` (4_3, 16_9, nonstandard), `resolution` (4k, high_definition, standard_definition), `fps_from/to`, `duration_from/to`, `license` (commercial, editorial), `people_number`, `people_age` (infants…older), `people_gender`, `people_ethnicity`, `people_model_released`, `safe`, `category` | [SDK docs](https://github.com/shutterstock/public-api-javascript-sdk/blob/master/docs/VideosApi.md) (read directly), [blog](https://www.shutterstock.com/blog/shutterstock-video-api-search-endpoints) |
| **Getty Images** API | Creative video `compositions` (incl. medium_shot, wide_shot, part_of_a_series), `number_of_people` (none, one, two, group), ethnicity, licence type, release status. Editorial video types **Raw** vs **Produced** | [release notes](https://developers.gettyimages.com/release-notes/), [editorial footage](https://www.gettyimages.com/editorial-footage) *(via search)* |
| **Pond5** | Resolution, duration, FPS (23.97–60+), price, usage rights, number and gender of people, aerial, greenscreen, loopable, has-sound, model/property released | [Pond5 blog](https://blog.pond5.com/80631-how-to-find-the-perfect-stock-assets/), [review](https://www.footagesecrets.com/agencies/pond5/) *(via search)* |
| **Storyblocks** | Resolution (HD/4K/8K), frame rate (23.98/24, 25, 29.97/30, 50, 59.94/60), duration, category | [search](https://www.storyblocks.com/video/search), [camera-movement tutorial](https://www.storyblocks.com/resources/tutorials/7-basic-camera-movements) *(via search)* |
| **Artgrid** | "Shot type" filter: **camera movement** (Tripod, Handheld, Smooth movement), **time** (Day, Night, Sunrise, Sunset), **location** (Interior/Exterior), **format** (4K+, RAW & LOG), **speed** (Realtime, Slow, Super slow, Fast), plus themes (Aerials, Abstract…) | [Artgrid help](https://artgrid.zendesk.com/hc/en-us/articles/8069563020701-How-to-Find-Download-and-Use-Footage), [review](https://www.benhammer.de/en/2024/07/22/artgrid-review-the-flat-rate-for-video-stock-footage/) *(via search)* |

What this means for us: buyers filter on support style (static, handheld,
smooth), on time of day, interior/exterior, speed, people count and releases.
Precise cinema terms (rack focus, arc) belong in the vocabulary for query
parsing and agents, but the UI should *facet* only on the coarse,
high-agreement ones.

### 3.2 MAM / review platforms

| Product | Vocabulary approach | Source |
|---|---|---|
| **iconik** | Admin-built *metadata views* (forms) grouped into *categories*. Dropdown taxonomies, hierarchical categories, conditional fields. AI enrichment fills customer-defined fields | [metadata categories](https://help.iconik.backlight.co/hc/en-us/articles/25304105868311-Metadata-Categories), [blog](https://www.iconik.io/blog/unleash-media-value-with-iconik-metadata-management) |
| **CatDV** | Unlimited user fields. *Grouping (picklist)*, *extensible picklist*, **Hierarchy** fields (`/`-separated paths), multi-hierarchy. Marker-level metadata. Field mapping to FCP keys | [CatDV 13 guide](https://www.squarebox.com/download/CatDV13.0.14Manual.html), [custom metadata](http://docs.squarebox.com/tutorials/getting-organised/Setting-up-Custom-Metadata.html), [FCP mapping](https://docs.squarebox.com/nle-panels/final-cut-pro-panel/Map-CatDV-Fields-to-Final-Cut-Pro-Metadata-Keys.html) |
| **Frame.io V4** | 33 built-in fields (Rating, Status, Keywords, Transcript, Frame Rate…) and 10 custom field types (select, date, toggle…) in an account-level library. *Collections* = saved, metadata-driven views | [metadata overview](https://help.frame.io/en/articles/9101037-metadata-overview), [V4 metadata blog](https://blog.frame.io/2024/04/23/frame-io-v4-beta-metadata-collections/) |
| **Axle AI** | AI Tags: faces, 300+ logos, 1,200+ objects, scene understanding, vector search, transcription. On-prem Docker. Panels for Premiere, Resolve and Media Composer | [Axle AI Tags API](https://www.axle.ai/blog/revolutionize-your-video-workflows-with-axle-ai-tags-api-20), [StorageReview](https://www.storagereview.com/review/smarter-media-anywhere-axle-ai-brings-intelligence-to-the-edge) |
| **Reuters Imagen** | Rights-aware MAM. Per-asset rights with territory/GEO-IP restrictions, licence framework (length, territory, duration, purpose). Reads embedded EXIF/IPTC/XMP | [rights management](https://imagen.io/rights-management), [metadata standards](https://imagen.io/resources/blog/metadata-standards) |
| **Premiere / Bridge** | XMP (xmpDM + DC) in files/sidecars, including Log Note, Good, Scene, Shot and markers | [xmpDM](https://github.com/adobe/xmp-docs/blob/master/XMPNamespaces/xmpDM.md) |
| **Avid Media Composer** | Bin columns (Scene, Take, Camroll, custom columns). 2025.6 added OTIO import. Plans for API access to transcription data | [Avid 2025.6](https://www.avid.com/resource-center/whats-new-avid-media-composer-20256), [2026.8](https://www.avid.com/resource-center/whats-new-avid-media-composer-2026-8) |

Lesson: the MAMs that succeed let admins define the field types (pick-list,
hierarchy, multi), let AI write *into* the customer's schema, and keep markers
and time ranges first-class. None ships a cinematography vocabulary, so ours
is a differentiator if it maps to MovieLabs, XMP and IPTC for export.

## 4. Domain vocabularies

* **Shot size** follows a standard 7-step ladder (ECU, CU, MCU, MS, MLS/MWS,
  LS/WS, EWS) in xmpDM and the trade literature
  ([wolfcrow](https://wolfcrow.com/15-essential-camera-shots-angles-and-movements/),
  [StudioBinder glossary](https://www.studiobinder.com/blog/movie-film-terms/),
  [Wikipedia: Shot](https://en.wikipedia.org/wiki/Shot_(filmmaking))). UK
  "BCU" folds into ECU as a synonym.
* **Camera movement**: pan, tilt, dolly, truck, pedestal, crane/jib, zoom,
  handheld, steadicam/gimbal, aerial, arc, push-in, whip pan, rack focus,
  dolly zoom
  ([Columbia Film Language Glossary](https://filmglossary.ccnmtl.columbia.edu/term/camera-movement/),
  [NFI](https://www.nfi.edu/camera-movement-terms/),
  [Storyblocks](https://www.storyblocks.com/resources/tutorials/7-basic-camera-movements)).
  xmpDM encodes direction (Pan Left/Right…), so direction is modelled as
  narrower terms to allow lossless export.
* **Editorial roles** (A-roll, B-roll, cutaway, insert, establishing, master,
  coverage, reaction/noddy, PTC, interview, vox pop, GVs) are not in any
  formal standard apart from IPTC genres (Interview, Actuality) and scene
  011000 *general view*. The definitions are synthesised from broadcast
  practice.
* **Pace**: the measurable proxy is average shot length (ASL = running time /
  shots). Feature-film ASL fell from 8–11 s (1930s) to ~4–5 s, with recent
  films near 2 s
  ([Cinemetrics](https://cinemetrics.uchicago.edu/article/27adf18a-21ad-442b-b186-0c7f3b8cb2d1),
  [cutting-rate study](https://widescreenjournal.org/wp-content/uploads/2022/08/formatted-cutting-rates.pdf)).
  Our pace bins use ASL thresholds for edits and motion energy for single
  shots, and store the raw number.
* **Mood**: there is no industry standard. Stock and music libraries use flat
  mood lists. Russell's circumplex (valence × arousal) is the standard
  psychological model
  ([overview](https://psu.pb.unizin.org/psych425/chapter/circumplex-models/)).
  We give every mood term a nominal valence/arousal point and store
  continuous scores, so labels stay coarse and queries can be numeric.
* **Rights**: PLUS release codes, PLUS/IPTC DMI codes, ODRL policy shape and
  ISO 3166 territories (above). Imagen and Getty show that *purpose*,
  *channel*, *territory* and *time window* are the dimensions buyers and
  legal teams reason with. Paid social vs organic social is a common split
  in licences and is kept as separate terms.

## 5. Extra signals beyond the spec, ranked by search value per unit of effort

| Signal | Why it matters | How to derive | Stored as |
|---|---|---|---|
| **People count** (none/one/two/small group/crowd + integer) | Most common facet in Getty and Shutterstock, and needed by rights checks | Person detector | `people_count` vocab + int |
| **Safe crop regions** for 9:16, 1:1, 4:5 (subject-aware) | Tells whether a 16:9 shot survives vertical reframing. Cutawan's core need | Face/saliency track, the same approach as Cutawan's `focusTrack` | per-aspect normalised rect + keyframes |
| **Subject position / screen direction** (left/centre/right third, facing/moving L→R) | Matching eyelines and screen direction across cuts. Space for text | Detector boxes + optical flow | x,y centroid; `moving_dir` enum |
| **Dominant colours** (palette of 3–5 + average luminance) | "Find warm orange shots to match brand", grade matching | k-means in Lab | hex + weight; CIEDE2000 queries |
| **Lens / focal-length class** | Look matching (telephoto compression), a MovieLabs category | EXIF/camera metadata, else a classifier | `lens_class` |
| **Depth of field** | Cinematic look. Text-over-bokeh friendly | Blur map | `depth_of_field` |
| **Lighting style** (high/low key, backlit, practical, neon) | Cut-ability and mood | Histogram + classifier | `lighting` |
| **Colour grade state** (log/HDR/display/graded/mono) | Whether a LUT is needed before reuse | Camera metadata + histogram stats | `colour_grade` |
| **Text present / burned-in graphics** with OCR | Reuse blocker, and searchable text (signs, slides) | OCR | `quality_flag.burned_in*` + text |
| **Logos / brands, recognisable faces, minors, screens, music ID** | Rights risk | Detectors | `clearance_flag` |
| **Motion energy & camera-motion vector** | Pace, whip-pan transitions, matching movement direction | Optical flow | floats |
| **Loopability** (seamless start/end) | Pond5 facet. Backgrounds | Frame similarity at the ends | bool + score |
| **Green screen / keyability** | Pond5 facet | Colour stats | `setting.green_screen` |
| **Sharpness, exposure and stability scores** (continuous) | Ranking ("best take") | IQA models | 0..1 floats; `quality_flag` above thresholds |
| **Speech presence, speaker count, language, loudness (LUFS)** | A/B-roll split, VO usability | VAD, diarisation, EBU R128 | per shot |
| **Digital source type / AI provenance** | Transparency and labelling law | C2PA manifests, IPTC DST | `source_type` |
| **Embedding vectors** (image, video, audio, transcript) | Semantic and similar search | Models (see ADR on embeddings) | vector index |

## 6. Sources (all accessed 2026-10-04)

IPTC VMH 1.7: <https://iptc.org/news/video-metadata-hub-v1-7-released/> ·
VMH recommendation: <https://iptc.org/standards/video-metadata-hub/recommendation/> ·
VMH user guide: <https://www.iptc.org/std/videometadatahub/userguide/> ·
VMH↔PBCore: <https://iptc.org/std/videometadatahub/recommendation/IPTC-VideoMetadataHub-mapping-PBCore21-Rec_1.7.html> ·
NewsCodes scene: <https://cv.iptc.org/newscodes/scene> ·
Scene code list: <https://www.controlledvocabulary.com/help/iptc-codes.html> ·
NewsCodes guidelines (CC BY 4.0): <https://iptc.org/std-dev/NewsCodes/guidelines/newscodes-guidelines.html> ·
Media Topics: <https://iptc.org/standards/media-topics/> ·
Genre CV: <https://cv.iptc.org/newscodes/genre/> ·
Digital source type: <https://cv.iptc.org/newscodes/digitalsourcetype/>, <https://iptc.org/news/newscodes-2024-q3-release-including-media-topics-and-digital-source-type-updates/> ·
IPTC Photo user guide (PLUS release codes): <https://www.iptc.org/std/photometadata/documentation/userguide/> ·
IPTC 2023.1 data mining: <https://iptc.org/news/exclude-images-from-generative-ai-iptc-photo-metadata-standard-2023-1/> ·
PLUS LDF: <https://ns.useplus.org/LDF/ldf-XMPSpecification>, <https://www.useplus.com/useplus/license.asp> ·
RightsML 2.0: <https://iptc.org/news/rightsml-2-0-is-now-published/> ·
ODRL 2.2: <https://www.w3.org/TR/odrl-model/> ·
MovieLabs Creative Vocabulary: <https://movielabs.com/news/movielabs-announces-the-movielabs-creative-vocabulary/>, <https://cv-mc.movielabs.com/> ·
OMC camera metadata v2.5: <https://mc.movielabs.com/omc/Asset/Camera/ML_Ontology_Pt3A_CameraMetadata_v2.5.pdf> ·
OMC v2.6: <https://movielabs.com/news/movielabs-releases-v2-6-of-the-ontology-for-media-creation/> ·
xmpDM: <https://github.com/adobe/xmp-docs/blob/master/XMPNamespaces/xmpDM.md> ·
EBUCore: <https://tech.ebu.ch/docs/tech/tech3293.pdf> ·
EBU CCDM: <https://tech.ebu.ch/docs/tech/tech3351.pdf> ·
EBU Tech 3336: <https://tech.ebu.ch/publications/tech3336> ·
schema.org video (Google): <https://developers.google.com/search/docs/appearance/structured-data/video> ·
PBCore: <https://pbcore.org/elements/pbcoregenre.html> ·
ISO 3166: <https://www.iso.org/iso-3166-country-codes.html> ·
AudioSet ontology: <https://github.com/audioset/ontology> ·
Places365: <https://github.com/csailvision/places365> ·
Shutterstock API: <https://github.com/shutterstock/public-api-javascript-sdk/blob/master/docs/VideosApi.md> ·
Getty API release notes: <https://developers.gettyimages.com/release-notes/> ·
Pond5 filters: <https://blog.pond5.com/80631-how-to-find-the-perfect-stock-assets/> ·
Storyblocks: <https://www.storyblocks.com/video/search> ·
Artgrid: <https://artgrid.zendesk.com/hc/en-us/articles/8069563020701-How-to-Find-Download-and-Use-Footage> ·
iconik: <https://help.iconik.backlight.co/hc/en-us/articles/25304105868311-Metadata-Categories> ·
CatDV: <https://www.squarebox.com/download/CatDV13.0.14Manual.html> ·
Frame.io: <https://help.frame.io/en/articles/9101037-metadata-overview> ·
Axle AI: <https://www.axle.ai/blog/revolutionize-your-video-workflows-with-axle-ai-tags-api-20> ·
Imagen: <https://imagen.io/rights-management> ·
Avid MC 2025.6: <https://www.avid.com/resource-center/whats-new-avid-media-composer-20256> ·
Cinemetrics: <https://cinemetrics.uchicago.edu/article/27adf18a-21ad-442b-b186-0c7f3b8cb2d1> ·
Russell circumplex: <https://psu.pb.unizin.org/psych425/chapter/circumplex-models/> ·
Columbia film glossary: <https://filmglossary.ccnmtl.columbia.edu/term/camera-movement/>
