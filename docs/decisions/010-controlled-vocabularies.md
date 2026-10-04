# 010. Controlled vocabularies for shot description, workflow and rights

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context

Metachlorian tags every shot so that people and agents can filter precisely
("static wide exterior at golden hour, no people, cleared for paid social in
the UK") and so that query text can be parsed into filters. Embedding search
covers fuzzy similarity, but structured filters need a closed, documented term
set that:

* the tagging models can be prompted or trained with (definitions double as prompt text)
* the query parser can resolve from natural language (synonyms, abbreviations such as "MCU", "GVs", "PTC")
* exports losslessly to the formats editors and MAMs read (XMP, IPTC, OTIO/FCPXML metadata)
* evolves without breaking stored tags, MCP clients or Cutawan packages
* admins can extend for their organisation
* is commercial-friendly in licence, with no copyleft text copied into Apache-2.0 files

Research is in [docs/research/taxonomies.md](../research/taxonomies.md). In
short, no single standard covers shot-level search. MovieLabs Creative
Vocabulary v1.0 (CC BY 4.0) covers cinematography. xmpDM covers the shot
size, angle and movement values that NLEs read. IPTC NewsCodes (CC BY 4.0)
cover scene, genre and digital source type. PLUS/IPTC cover release and
data-mining codes. Stock libraries and MAMs only provide filters and pick-list
mechanics.

## Options considered

| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| A. Adopt IPTC VMH + NewsCodes as-is | Good for news scene, genre and rights. No camera movement, pace or mood. Scene codes are photo-centric | CC BY 4.0 | n/a | n/a | High (since 2010s) | Active, quarterly releases |
| B. Adopt MovieLabs Creative Vocabulary as-is | Excellent for lens, shot size, movement and angle. Nothing on roles, setting, rights or audio | CC BY 4.0 | n/a | n/a | New (v1.0, 2026) | Industry Forum, active |
| C. xmpDM closed choices only | Embeddable, NLE-readable. Small, flat, no synonyms or definitions | Open spec | n/a | n/a | Very high, static | Adobe, rarely changes |
| D. No vocabulary: free-text tags + embeddings | Flexible, but filters are fuzzy and not auditable, and rights checks cannot rely on them | n/a | GPU for embeddings | Fast to build | n/a | n/a |
| E. Full RDF/SKOS store (triple store, SPARQL) | Most expressive. Overkill for ~300 terms | Mixed | Extra service | Slower | High | Niche skills |
| **F. Own versioned YAML vocabularies (SKOS subset) with crosswalks to A–C and PLUS** | Covers every dimension the spec asks for. Definitions and synonyms tuned for tagging and parsing. Lossless export via mappings | Our files Apache-2.0. Only IDs referenced from CC BY / CC BY-SA sources | None | Loaded into memory at start (<1 ms lookups) | New, but built on mature standards | Us; small, reviewable diffs |

## Evidence

* Coverage gaps per standard: see the table in research §2. Every spec
  dimension (shot_size … release_status) is checked against sources in §2–4.
* Stock facets are coarse (Artgrid: Tripod/Handheld/Smooth;
  Day/Night/Sunrise/Sunset; Realtime/Slow/Super slow/Fast. Getty
  number_of_people: none/one/two/group). The vocabulary carries these values
  as mappings, so faceted UI can collapse fine terms into coarse ones.
* xmpDM closed choices were read directly from Adobe's xmp-docs and are
  mapped one to one.
* Licences: IPTC NewsCodes CC BY 4.0; MovieLabs Creative Vocabulary CC BY 4.0;
  AudioSet ontology CC BY-SA 4.0 (IDs only); Places365 annotations CC BY;
  ISO 3166 copyrighted by ISO (use Unicode CLDR data instead). Sources are
  in research §6.
* Validation: all 25 v1 files parse. Ids are unique snake_case, `broader`
  references resolve and there are no synonym collisions within a
  vocabulary. 35 deliberate cross-vocabulary ambiguities (e.g. `crowd`,
  `sync`) are left for the query parser to resolve by context. (Checked with
  a throwaway script at authoring time. CI script to be added; see the
  README.)

## Decision

Adopt **option F**: Metachlorian-owned vocabularies in
`core/metachlorian/vocab/v1/<name>.yaml`, one file per vocabulary, using a
SKOS-compatible shape (`id`, `label`, `definition`, `synonyms`, `broader`,
`mappings`). Each vocabulary is versioned with SemVer, and admins can
extend vocabularies under an `x_<org>_` id prefix. Format, versioning and
extension rules are in [the vocab README](../../core/metachlorian/vocab/v1/README.md).

### Design rules

1. **Stable ids.** Lowercase snake_case, never reused. Labels and synonyms
   may change in patch releases.
2. **One-parent hierarchy** (`broader`). Assigning a narrower term implies
   its ancestors at query time. Direction terms (pan_left) sit under motion
   terms (pan) so xmpDM export is lossless and search stays simple.
3. **multi / ordered flags per vocabulary.** Ordered vocabularies (shot_size,
   pace, lens_class, depth_of_field, people_count, edit_type) carry `rank`, so
   "tighter than MS" or "prefer raw" become range queries.
4. **Tag assertions, not bare labels.** Each stored tag is
   `{vocab, version, term, confidence, source, range?, bbox?, severity?}`.
   Human assertions beat model assertions, and human removals are kept as
   tombstones.
5. **Absence means unknown.** Negatives are explicit terms
   (`people_count.none`, `release_status.none`). `release_status` defaults to
   `unknown`, which blocks commercial use in `check_rights`.
6. **Crosswalks in `mappings`**: `movielabs`, `iptc` (QCodes), `xmpdm`,
   `audioset`, `plus*`, `getty`/`artgrid`/`places365`/`odrl`, used for import
   and export (XMP sidecars, OTIO/FCPXML metadata, VMH JSON) and to collapse
   fine terms into stock-style coarse facets.
7. **Rights in ODRL shape.** A rights record is a list of permissions and
   prohibitions whose constraint values come from `usage`, `channel`,
   territory (ISO 3166-1 alpha-2 + UN M49 regions, from CLDR) and a time
   window. Release status and clearance flags gate it. Export to
   RightsML/ODRL JSON-LD is mechanical.
8. **Free text stays free.** Named people, places, organisations, objects and
   topics are *entities* (linked to Wikidata or the org's own lists) or IPTC
   Media Topics, not vocabulary terms.

### v1 term lists

| Vocabulary | multi | Terms (ids) |
|---|---|---|
| shot_size | no, ordered | extreme_close_up, close_up, medium_close_up, medium_shot, medium_long_shot, long_shot, extreme_wide_shot |
| camera_angle | yes | eye_level, high_angle, birds_eye, low_angle, worms_eye, ground_level, dutch_angle, pov, over_the_shoulder, aerial_view |
| camera_movement | yes | static, pan (pan_left, pan_right, whip_pan), tilt (tilt_up, tilt_down), dolly (push_in, pull_out), truck (truck_left, truck_right), tracking, pedestal, crane, arc, roll, zoom (zoom_in, zoom_out, crash_zoom), dolly_zoom, rack_focus, handheld, gimbal, aerial (fpv), vehicle_mount |
| speed_effect | yes | real_time, slow_motion (super_slow_motion), fast_motion (time_lapse (hyperlapse)), speed_ramp, reverse, freeze_frame, stop_motion |
| shot_role | yes | a_roll (interview (vox_pop), piece_to_camera), b_roll (general_view, cutaway (reaction), insert), establishing, master, coverage, actuality, montage, transition, graphic (title_card, lower_third, end_card), slate |
| pace | no, ordered | still, slow, moderate, fast, frenetic (ASL thresholds >12 / 6–12 / 3–6 / 1.5–3 / <1.5 s) |
| mood | yes (≤3) | joyful, playful, humorous, energetic, inspirational (triumphant), epic, romantic, warm, calm, contemplative, nostalgic, melancholic, tense, dramatic, ominous, mysterious, chaotic, aggressive, luxurious, professional, neutral (each with valence/arousal) |
| time_of_day | no | day (morning, midday, afternoon), golden_hour (sunrise, sunset), blue_hour (dawn, dusk), night |
| weather | yes | clear, partly_cloudy, overcast, rain, storm, snowfall, snow_covered, frost_ice, fog, haze, windy, dust_storm, rainbow |
| season | no | spring, summer, autumn, winter, wet_season, dry_season |
| setting | yes | interior (home, office, studio, retail, hospitality, industrial, healthcare, education, venue, transport_hub, vehicle_interior), exterior (urban (street), suburban, park_garden, road, industrial_exterior, sports_ground, rural, nature (forest, mountain, desert, coast, open_water, freshwater, underwater), sky), synthetic (green_screen, screen_capture, animation_graphics) |
| audio_class | yes | speech (sync_dialogue, voice_over), crowd_speech, music (singing), ambience (nature_sound, traffic_urban), machinery, animal_sound, applause, laughter, sound_effect, silence |
| edit_type | no, ordered | raw, selects (stringout), assembly, rough_cut, fine_cut, locked_cut, finished (textless, cutdown, promo), programme_recording |
| quality_flag | yes, with severity | out_of_focus, motion_blur, camera_shake, rolling_shutter, underexposed, overexposed, colour_cast, noise, compression_artefacts, low_resolution, interlaced, dropped_frames, flicker, lens_obstruction, blocked_view, crew_in_shot, burned_in (burned_in_timecode, burned_in_captions, watermark), letterbox_pillarbox, audio_clipping, audio_wind_noise, audio_hum, audio_low_level, audio_background_noise, audio_missing, audio_out_of_sync |
| usage | yes | commercial (advertising, marketing, merchandise), editorial (news, documentary), entertainment, internal, educational, ai_training (genai_training) |
| channel | yes | social (organic_social, paid_social, creator_partnership), web, online_advertising, email, broadcast, streaming, cinema, ooh (dooh), retail_in_store, live_event, presentation, internal, press, in_product, print, audio_only |
| release_status | no (×2 fields) | unknown, not_applicable, none, pending, limited, unlimited (maps to MR-*/PR-*) |
| clearance_flag | yes | recognisable_person (public_figure, minor), crowd, third_party_brand, artwork, private_property, third_party_screen, third_party_music, personal_data, sensitive_content |
| source_type | no | own_production, commissioned, stock, archive, agency_feed, user_generated, off_air_capture, screen_recording, digital_creation, ai_generated, ai_edited |
| *extras:* lens_class, depth_of_field, lighting, colour_grade, people_count | see files | See research §5 for why each adds search value. Non-vocabulary extras (safe crop regions per aspect, subject position/screen direction, dominant colours, motion vectors, loopability, OCR text, LUFS) are numeric or geometric fields in the shot schema, not term lists |

## Consequences

* **Easier**: deterministic filters and facets. The query parser gets a
  synonym table for free. MCP tools can publish enums
  (`list_vocabularies`, JSON Schema `enum` in `search_shots`). XMP, IPTC and
  OTIO export is a lookup. Cutawan packages can name the vocab versions they
  used. Admins can extend without forking.
* **Harder**: we own term curation and definitions, which need periodic
  review against MovieLabs and IPTC updates. Mood, pace and setting are
  subjective, so inter-annotator agreement must be measured in `eval/` before
  they are exposed as hard filters (until then they only boost ranking).
  Migrations are needed whenever a term is deprecated.
* MovieLabs mappings are label-level until term IRIs are resolved. IPTC scene
  codes 010200/010600/010800/010900 need confirmation by the crosswalk CI
  check.
* AudioSet is CC BY-SA. We store IDs only. If its definitions are ever needed
  in the UI, fetch them at runtime and do not vendor them.

## Revisit when

* MovieLabs Creative Vocabulary publishes v1.x/v2 (composition, framing,
  depth of field). Re-map, and consider adopting its IRIs as primary ids for
  overlapping vocabularies.
* IPTC VMH or NewsCodes add shot-type or camera vocabularies.
* Measured agreement (κ) for any vocabulary in `eval/` is below 0.6. Merge or
  redefine terms, or demote that vocabulary to ranking-only.
* More than ~20% of an instance's tags use local `x_` terms in one
  vocabulary, which suggests the base list is missing something.
* A customer needs multilingual UI. Add `labels:` per language, with IPTC
  multilingual labels as a seed.
