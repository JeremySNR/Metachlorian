# Metachlorian controlled vocabularies, v1

These files are the canonical term lists that shot tags, search filters, query
parsing, the MCP tools and the Cutawan package manifest all use. The decision
record is [ADR 010](../../../../docs/decisions/010-controlled-vocabularies.md)
and the source research is in [docs/research/taxonomies.md](../../../../docs/research/taxonomies.md).

## Files

There is one YAML file per vocabulary. The file name equals `vocabulary`.

| Group | Vocabularies |
|---|---|
| Core shot description (in the spec) | `shot_size`, `camera_angle`, `camera_movement`, `speed_effect`, `shot_role`, `pace`, `mood`, `time_of_day`, `weather`, `season`, `setting`, `audio_class` |
| Asset / workflow | `edit_type`, `source_type`, `quality_flag` |
| Rights | `usage`, `channel`, `release_status`, `clearance_flag` (territory uses ISO 3166-1 alpha-2 and UN M49 region codes, not a file here) |
| Extra search signals (beyond the spec) | `lens_class`, `depth_of_field`, `lighting`, `colour_grade`, `people_count` |

## File shape

```yaml
vocabulary: camera_movement     # == file name
version: 1.0.0                  # SemVer of this vocabulary (not of the app)
description: ...
multi: true                     # may a shot hold several terms?
ordered: false                  # true => terms carry `rank` (supports "wider than")
applies_to: [shot, segment]     # shot | segment | asset | rights_grant | rights_request | package_target
extensible: true                # may admins add local terms (see below)?
terms:
  - id: pan                     # lowercase snake_case, stable forever
    label: Pan                  # display label (en-GB)
    definition: ...             # one or two sentences, written for both humans and the tagger prompt
    synonyms: [panning, pans]   # lower-case surface forms for query parsing; may include abbreviations
    broader: null               # id of the parent term in this vocabulary, or null
    mappings: {movielabs: ..., iptc: ..., xmpdm: ...}   # string, list of strings, map, or null
```

Optional term keys: `rank` (ordered vocabularies), `valence`/`arousal` (mood),
`deprecated: true`, `replaced_by: <id>`, `labels: {fr: ..., de: ...}`.

## Semantics

* **Hierarchy.** `broader` gives a one-parent tree, the SKOS `skos:broader`
  subset. When a narrower term is assigned, all its ancestors are implied at
  index time, so filtering on `pan` also finds `pan_left` and `whip_pan`.
  Ancestors are not stored as separate assertions.
* **Absence ≠ negative.** An unset vocabulary means "not assessed". Negative
  assertions are explicit, e.g. `people_count: none` or `release_status: none`.
  For rights, `release_status` defaults to `unknown`, which blocks commercial use.
* **Confidence.** Every tag carries `confidence` (0..1), `source`
  (`model:<name>@<ver>`, `human:<user>`, `import:<system>`) and optionally a
  sub-range `[in, out]` inside the shot. Human tags override model tags. A
  human removal is stored as a tombstone so re-indexing does not bring the tag
  back.
* **Synonyms.** Matching is case-insensitive, trims punctuation and handles
  simple plurals. Synonyms are unique within a vocabulary (CI-enforced). They
  may repeat across vocabularies where the ambiguity is real (`crowd` is both
  `people_count.crowd` and `clearance_flag.crowd`; `sync` is both
  `audio_class.sync_dialogue` and `shot_role.a_roll`). The query parser then
  returns every interpretation with a score and picks one by context, e.g.
  rights words nearby. `search_shots` echoes how it interpreted the query.
* **Mappings** are crosswalks for import/export, not identity claims. Mapping
  keys used:
  * `iptc`: IPTC NewsCodes QCodes (`scene:011800`, `genre:Interview`,
    `digitalsourcetype:screenCapture`), CC BY 4.0. Codes 010100, 010300, 011000,
    011100, 011200, 011300, 011400, 011600, 011700 and 011800 were checked
    against published lists. The others (010200, 010600, 010800, 010900) are
    to be confirmed by the CI crosswalk check against `cv.iptc.org`.
  * `xmpdm`: closed-choice values of Adobe XMP Dynamic Media
    `xmpDM:shotSize`, `xmpDM:cameraAngle` and `xmpDM:cameraMove`. Checked
    against Adobe's xmp-docs.
  * `movielabs`: preferred labels from the MovieLabs Creative Vocabulary v1.0
    (CC BY 4.0; categories Lens, Shot Size, Camera Movement, Camera Angle).
    These are label-level candidates only. The term pages
    (cv-mc.movielabs.com) could not be reached from the build environment.
    A follow-up task replaces each label with the term IRI and sets `null`
    where no term exists.
  * `audioset`: AudioSet ontology machine IDs (`/m/09x0r`). The ontology is
    CC BY-SA 4.0, so only IDs are referenced and no text is copied.
  * `plus`, `plus_model`, `plus_property`: PLUS LDF / IPTC Extension codes
    (`MR-UMR`, `PR-NAP`, `DMI-PROHIBITED-AIMLTRAINING`).
  * `getty`, `artgrid`, `places365`, `odrl`: filter values or classes in those
    systems, for importers and for documentation.

## Versioning rules

Each vocabulary is versioned independently with SemVer. The directory (`v1/`)
is the major *format* generation. A new directory only appears if this file
shape changes incompatibly.

| Change | Version bump | Notes |
|---|---|---|
| Add a synonym, translation or mapping; reword a definition without changing meaning | patch (1.0.x) | No re-index needed |
| Add a term; add a narrower term under an existing one | minor (1.x.0) | Taggers may need a re-run for the new term. Existing tags stay valid |
| Deprecate a term (`deprecated: true`, `replaced_by`) | minor | The term stays readable and searchable. New tagging stops. A migration rewrites stored tags in the background |
| Remove a term, change an `id`, change a definition's meaning, flip `multi` | major | Avoid. Needs a migration script in `core/metachlorian/vocab/migrations/` and a release note |

* **Ids are permanent.** An id is never reused for a different meaning, even
  after removal.
* Stored tags record `vocab@version` (e.g. `camera_movement@1.0.0`). Search
  works across versions through the `replaced_by` chain.
* Package manifests and MCP responses report the vocabulary versions they
  used (`vocab_versions`), so a consumer can tell which term set produced
  the data.
* The MCP tool `list_vocabularies` and the resource
  `metachlorian://vocab/{name}` serve these files with any local extensions
  merged in.

## Local extensions (admin-extensible)

If `extensible: true`, an instance admin can add terms without forking:

```yaml
# <data_dir>/vocab/local/setting.yaml
vocabulary: setting
extends: 1.0.0                 # base version the extension was written against
terms:
  - id: x_acme_store_front     # local ids MUST start with x_<org>_
    label: Acme store front
    definition: Exterior of an Acme retail store.
    synonyms: [acme shop, acme store]
    broader: retail            # may hang under any base term
    mappings: {movielabs: null, iptc: null}
```

Rules:

1. Local ids must start with `x_<org>_` so they can never collide with future
   upstream ids.
2. Admins may add synonyms and labels to base terms in a `synonyms_add:`
   block. They may not edit base definitions or ids.
3. If `extensible: false` (shot_size, pace, time_of_day, season,
   release_status, lens_class, depth_of_field, people_count), only synonyms
   and labels can be added. These are measured or legal scales whose meaning
   must stay fixed.
4. Each extension change is audit-logged with its author. The merged
   vocabulary version is reported as `1.0.0+local.<n>`.
5. A local term proposed upstream is renamed to a plain id in a minor
   release, and the old `x_` id becomes `replaced_by` the new one.

## Validation (CI)

`scripts/check_vocab` (to be written) enforces the following: file name equals
`vocabulary`; ids match `^[a-z][a-z0-9_]*$` and are unique; `broader` refers
to an id in the same file and has no cycles; ordered vocabularies have `rank`;
no synonym or label maps to two terms in one vocabulary; and every changed
file has a version bump that matches the table above.
