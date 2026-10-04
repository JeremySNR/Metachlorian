/**
 * Types mirroring the core's response shapes
 * (core/metachlorian/service.py, search/engine.py, records.py, rights.py).
 * Keep these in step with the backend; unknown extra keys are tolerated.
 */

export type Uid = string

// ---------------------------------------------------------------- health / me
export interface EgressAdapter {
  adapter: string
  /** custom | openai | openrouter | codex (see ProviderId). */
  provider?: ProviderId
  base_url: string
  model: string
  active: boolean
  sends: string
}

export interface Egress {
  content_leaves_machine: boolean
  adapters: EgressAdapter[]
}

export interface Health {
  name: string
  version: string
  auth_required: boolean
  egress: Egress
  vlm: boolean
  llm: boolean
  models: Record<string, boolean>
}

export type Scope = 'admin' | 'collections:write' | 'ingest:write' | 'library:read' | 'media:export' | 'rights:write' | 'tags:write'

export interface Me {
  user_id: number | null
  username: string
  role: string
  scopes: Scope[]
  via: string
  solo: boolean
}

// ---------------------------------------------------------------- vocab
export interface VocabTerm {
  id: string
  label: string
  definition: string
  synonyms: string[]
  broader: string | null
  custom?: boolean
}

export interface Vocabulary {
  name: string
  version: string
  description: string
  multi: boolean
  ordered?: boolean
  terms: VocabTerm[]
}

// ---------------------------------------------------------------- rights
export type RightsBadge = 'cleared' | 'restricted' | 'expiring' | 'expired' | 'not_cleared' | 'unknown'
export type Verdict = 'allowed' | 'restricted' | 'blocked' | 'unknown'
export type RightsStatus = 'cleared' | 'restricted' | 'not_cleared' | 'unknown'

export interface RightsRecord {
  status: RightsStatus
  source: string
  owner: string
  licence: string
  permitted_uses: string[]
  channels: string[]
  territories: string[]
  excluded_territories: string[]
  starts: string | null
  expires: string | null
  model_release: string
  property_release: string
  brand_safety: string
  attribution: string
  notes?: string
  level: 'none' | 'asset' | 'shot'
  updated_by?: string
  updated_at?: number
  badge?: RightsBadge
}

export interface RightsCheckItem {
  shot_uid?: Uid
  asset_uid?: Uid
  verdict: Verdict
  reasons: string[]
  rights: RightsRecord
}

export interface RightsCheck {
  verdict: Verdict
  items: RightsCheckItem[]
}

export interface IntendedUse {
  use?: string | null
  channel?: string | null
  territory?: string | null
  date?: string | null
  include?: Verdict[]
}

// ---------------------------------------------------------------- search
export interface TermScore {
  term: string
  confidence: number | null
}

export interface ShotSummary {
  uid: Uid
  asset_uid: Uid
  filename: string
  idx: number
  start: number
  end: number
  duration: number
  fps: number | null
  thumb: string | null
  poster: string | null
  proxy: string
  caption: string | null
  summary: string | null
  shot_size: string | null
  camera_movement: TermScore[]
  role: TermScore[]
  setting: TermScore[]
  time_of_day: string | null
  pace: string | null
  people: number | null
  usable: boolean | null
  resolution: string | null
  resolution_class: string | null
  log_profile: boolean | null
  hdr: boolean | null
  edit_type: string | null
  corrected: string[]
}

export interface WhyItem {
  signal: string
  detail: string
  score?: number
  snippet?: string | null
  term?: string
  confidence?: number | null
  source?: string
  missing?: boolean
  filter?: string
}

export interface Moment {
  kind: string
  start: number
  end: number
  text: string | null
  confidence: number | null
  source: string
  data?: Record<string, unknown>
}

/** A search hit. */
export interface SearchResult extends ShotSummary {
  score: number
  why: WhyItem[]
  in: number | null
  out: number | null
  moment: Moment | null
  rights_badge?: RightsBadge
  rights?: { verdict: Verdict; reasons: string[] }
  /** Absolute match strength 0..1, comparable across queries (null when nothing was scored). */
  strength?: number | null
  /** Recognised people in the shot (face identity), largest face first. */
  identities?: PersonRef[]
  /** At or above the strictness threshold; strong results come first. */
  strong?: boolean
  /** Absolute directory of the file. */
  folder?: string
}

export type Strictness = 'loose' | 'balanced' | 'strict'

export interface SearchFilters {
  min_duration?: number | null
  max_duration?: number | null
  min_fps?: number | null
  max_fps?: number | null
  min_people?: number | null
  max_people?: number | null
  min_quality?: number | null
  min_height?: number | null
  orientation?: 'vertical' | 'horizontal' | 'square' | null
  log?: boolean | null
  hdr?: boolean | null
  usable?: boolean | null
  speech?: boolean | null
  music?: boolean | null
  edit_type?: string[] | string | null
  captured_after?: string | null
  captured_before?: string | null
  /** Only footage in this folder or its subfolders: a name, a relative path or an absolute path (a list means any). */
  folder?: string | string[] | null
  /** Only shots in this collection: uid or exact name (a list means any). */
  collection?: string | string[] | null
}

export type TermMap = Record<string, string[]>

export interface SearchRequest {
  q?: string
  filters?: SearchFilters
  require?: TermMap
  exclude?: TermMap
  prefer?: TermMap
  intended_use?: IntendedUse | null
  asset_uids?: Uid[] | null
  similar_to?: Uid | null
  limit?: number
  cursor?: string | null
  strict?: boolean
  /** Hide shots that are blocked for every use (not cleared, or expired). Default true. */
  hide_blocked?: boolean
  strictness?: Strictness
  facets?: boolean
  parse_query?: boolean
}

export interface ParsedQuery {
  text: string
  semantic: string
  keywords: string[]
  prefer: TermMap
  require: TermMap
  exclude: TermMap
  filters: SearchFilters
  rights: IntendedUse
  place: string[]
  notes: string[]
  limit: number | null
  prefer_people: number | null
  context: string
}

export interface FacetValue {
  term: string
  label: string
  count: number
}

export interface SearchResponse {
  query: {
    text: string
    parsed: ParsedQuery
    filters: SearchFilters
    require: TermMap
    exclude: TermMap
    prefer: TermMap
    intended_use: IntendedUse | null
    limit: number
  }
  total: number
  results: SearchResult[]
  facets: Record<string, FacetValue[]>
  notes: string[]
  excluded_by_rights: number
  /** Blocked shots hidden by hide_blocked (also counted in excluded_by_rights). */
  hidden_blocked?: number
  /** Results at or above the strictness threshold; they come first. */
  strong_count?: number
  /** Null when the query has nothing to score (filter-only browse): every result is strong. */
  strictness?: Strictness | null
  strength_thresholds?: Record<Strictness, number>
  next_cursor: string | null
  timings_ms: Record<string, number>
}

// ---------------------------------------------------------------- shot record
export interface FieldValue {
  value: unknown
  source: string
  confidence: number | null
  model_version: string
  corrected?: boolean
  corrected_by?: string
  corrected_at?: number
  correction_id?: number
  note?: string
  machine?: unknown
  alternatives?: { source: string; confidence: number | null; value: unknown }[]
}

export interface Keyframe {
  t: number
  file: string
  w: number
  h: number
  poster: boolean
}

export interface TechnicalSummary {
  width: number | null
  height: number | null
  fps: number | null
  aspect_ratio: number | null
  orientation: string | null
  resolution_class: string | null
  video_codec: string | null
  bit_depth: number | null
  hdr: boolean | null
  hdr_format: string | null
  color_transfer: string | null
  camera_make: string | null
  camera_model: string | null
  lens: string | null
  capture_date: string | null
  gps: unknown
  audio_channels: number | null
  log_profile?: boolean
  log_confidence?: number
}

export interface EditType {
  term: string
  confidence: number
  scores?: Record<string, number>
}

export interface TranscriptWord {
  w?: string
  word?: string
  text?: string
  s?: number
  e?: number
  start?: number
  end?: number
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
  speaker: number | string | null
  words?: TranscriptWord[]
}

export interface ShotDoc {
  uid: Uid
  id: number
  asset_uid: Uid
  asset_id: number
  filename: string
  path: string
  idx: number
  start: number
  end: number
  duration: number
  start_frame: number
  end_frame: number
  kind: string
  transition_in: string | null
  keyframes: Keyframe[]
  poster: string | null
  thumb: string | null
  technical: TechnicalSummary
  edit_type: EditType | string | null
  fields: Record<string, FieldValue>
  moments: Moment[]
  rights: RightsRecord
  rights_check?: { verdict: Verdict; reasons: string[] }
  transcript: TranscriptSegment[]
  media: { proxy: string; sprites: string; poster: string | null; thumb: string | null }
  neighbours: { previous?: Uid; next?: Uid }
  summary: ShotSummary
  /** Recognised people in the shot (face identity), largest face first. */
  people_identities?: PersonRef[]
  /** Every folder the file was found in (a duplicate lives in several). */
  folders?: string[]
  /** Imported from a web link: where it came from (null otherwise). */
  origin?: Omit<Origin, 'description'> | null
}

// ---------------------------------------------------------------- assets
export interface Sprites {
  interval: number
  tile_w: number
  tile_h: number
  cols: number
  rows: number
  count: number
  sheets: string[]
  base: string
}

export interface AssetStructure {
  duration?: number
  shot_count?: number
  hard_boundaries?: number
  gradual_transitions?: number
  cuts_per_minute?: number
  avg_shot_length?: number
  median_shot_length?: number
  titles?: boolean
  lower_thirds?: boolean
  captions?: boolean
  music_bed?: boolean
  music_share?: number
  speech_share?: number
  loudness_normalised?: boolean
  integrated_lufs?: number | null
  camera_metadata?: boolean
  timecode?: boolean
  log_likeness?: number
  starts_or_ends_black?: boolean
  single_take?: boolean
  transitions?: Record<string, number>
  edit_type?: EditType
  pace?: string
  top_settings?: string[]
  time_of_day?: string[]
  topics?: string[]
  roles?: Record<string, number>
  camera_movements?: Record<string, number>
  locations?: string[]
  people_shots?: number
  summary?: { text?: string; story?: string; source?: string; confidence?: number }
}

export interface AnalysisRun {
  analyser: string
  version: string
  status: string
  error: string | null
  seconds: number | null
  finished_at: number | null
}

export interface AssetJob {
  analyser: string
  status: string
  attempts: number
  error: string | null
}

export interface AssetShot extends Partial<ShotSummary> {
  uid: Uid
  idx: number
  start: number
  end: number
  duration: number
}

export interface AssetDoc {
  uid: Uid
  id: number
  filename: string
  path: string
  status: string
  size: number
  duration: number
  width: number | null
  height: number | null
  fps: number | null
  created_at: number
  updated_at: number
  technical: Record<string, unknown>
  structure: AssetStructure
  edit_type: EditType | null
  fields: Record<string, FieldValue>
  title: string | null
  location: string | null
  shots: AssetShot[]
  rights: RightsRecord
  processing: AnalysisRun[]
  jobs: AssetJob[]
  media: { proxy: string | null; poster: string | null; sprites: Sprites | null }
  transcript: TranscriptSegment[]
  paths: string[]
  /** Imported from a web link: where it came from (null otherwise). */
  origin?: Origin | null
}

export interface AssetListItem {
  uid: Uid
  filename: string
  path: string
  status: string
  duration: number | null
  /** Shoot date (ISO) when the file carries one. */
  captured?: string | null
  width: number | null
  height: number | null
  fps: number | null
  size: number | null
  created_at: number
  edit_type: EditType | null
  shot_count: number | null
  cuts_per_minute: number | null
  summary: string | null
  poster: string
  rights_badge: RightsBadge
  pace: string | null
  topics: string[]
}

export interface AssetList {
  total: number
  assets: AssetListItem[]
}

/** GET /api/folders: every folder holding footage; counts include subfolders. */
export interface Folder {
  path: string
  name: string
  /** From the source root's name: "Videos/Holidays/Disney 2026". */
  relative: string
  /** The watched folder (source) it belongs to. */
  source: string
  /** 0 = a source root. */
  depth: number
  files: number
  shots: number
  hours: number
  captured_from: string | null
  captured_to: string | null
  subfolders: number
  /** Files per edit stage term; "unclassified" until the file is analysed. */
  edit_types?: Record<string, number>
}

export interface FolderList {
  total: number
  folders: Folder[]
}

// ---------------------------------------------------------------- library
export interface LibraryStats {
  assets: number
  hours: number
  bytes: number
  shots: number
  status: Record<string, number>
  edit_types: Record<string, number>
  topics: [string, number][]
  places: [string, number][]
  facets: Record<string, FacetValue[]>
  gaps: { vocab: string; term: string; label: string }[]
  rights: Partial<Record<RightsBadge, number>>
  jobs: Record<string, number>
  throughput: Throughput
}

export interface Throughput {
  footage_hours: number
  wall_hours: number
  ratio: number | null
  analyser_seconds?: Record<string, number>
}

// ---------------------------------------------------------------- corrections
export type CorrectionKind = 'term' | 'terms' | 'text' | 'int' | 'bool'

export interface Correction {
  id: number
  level: 'shot' | 'asset'
  asset_uid: Uid
  shot_uid: Uid | null
  anchor_start: number | null
  anchor_end: number | null
  field: string
  op: 'set' | 'add' | 'remove'
  value: unknown
  note: string
  user_id: number | null
  actor: string
  created_at: number
  active: number
  filename?: string
  /** The shot the correction applies to (number is 1-based). */
  shot?: { idx: number; number: number; start: number; end: number; fps: number | null; timecode: string } | null
  /** What the model said before the correction. */
  model_value?: { value: unknown; source: string; confidence: number | null } | null
}

export interface CorrectionsResponse {
  corrections: Correction[]
  correctable: { shot: Record<string, CorrectionKind>; asset: Record<string, CorrectionKind> }
}

// ---------------------------------------------------------------- collections
export interface CollectionSummary {
  uid: Uid
  name: string
  description: string
  kind: string
  brief: string
  owner: string
  items: number
  duration: number
  updated_at: number
}

export interface CollectionItem {
  item_id: number
  position: number
  in: number | null
  out: number | null
  note: string
  shot: ShotSummary
  rights_badge: RightsBadge
}

export interface Collection {
  uid: Uid
  name: string
  description: string
  kind: string
  brief: string
  owner: string
  items: CollectionItem[]
  created_at: number
  updated_at: number
}

export interface PackageTarget {
  consumer: 'cutawan' | 'nle'
  aspect?: string
  usage?: string[]
  channels?: string[]
  territories?: string[]
}

export type MediaPolicy = 'none' | 'proxies' | 'trimmed_originals' | 'stringout'
export type CutawanMode = 'a_roll_with_inserts' | 'stringout' | 'broll_library'

export interface PackageResult {
  package_id: string
  path: string
  verdict: Verdict
  counts: Record<Verdict, number>
  zip?: string
  download: string
  manifest?: Record<string, unknown>
}

export type ExportMode = 'reference' | 'proxy' | 'file' | 'otio' | 'fcpxml' | 'edl'

export interface ExportClipResult {
  mode: ExportMode
  file?: string
  bytes?: number
  reference?: Record<string, unknown>
  download?: string
}

// ---------------------------------------------------------------- ingest
export interface Source {
  id: number
  uri: string
  kind: string
  watch: number
  priority: number
  options: Record<string, unknown>
  last_scan: number | null
  created_at: number
  assets: number
}

export interface QueueJob {
  id: number
  analyser: string
  worker?: string
  updated_at: number
  filename: string
  uid: Uid
  error?: string | null
  attempts?: number
}

export interface ProcessingAsset {
  uid: Uid
  filename: string
  status: string
  duration: number | null
  priority: number
  updated_at: number
  queued: number
  running: number
  done: number
  failed: number
  unavailable: number
  /** Analysers queued or running for this file, in queue order. */
  pending: string[]
}

export interface AnalyserInfo {
  name: string
  version: string
  description: string
  requires: string[]
  available: boolean
  reason: string | null
}

export interface Processing {
  queue: {
    by_status: Record<string, number>
    by_analyser: Record<string, Record<string, number>>
    running: QueueJob[]
    failed: QueueJob[]
  }
  assets: ProcessingAsset[]
  analysers: AnalyserInfo[]
  throughput: Throughput
}

// ---------------------------------------------------------------- admin
export interface User {
  id: number
  username: string
  display_name: string
  role: string
  disabled: number
  created_at: number
}

export interface ApiToken {
  id: number
  name: string
  prefix: string
  scopes: Scope[]
  kind: string
  created_at: number
  last_used: number | null
  expires_at: number | null
  revoked: number
  username: string
  role: string
}

export interface TokensResponse {
  tokens: ApiToken[]
  scopes: Record<Scope, string>
  role_scopes: Record<string, Scope[]>
}

export interface AuditEntry {
  id: number
  at: number
  user_id: number | null
  actor: string
  role: string
  via: string
  action: string
  target: string
  detail: Record<string, unknown>
  ok: number
}

export interface ModelEndpoint {
  provider: ProviderId
  base_url: string
  model: string
  api_key_env: string
  local: boolean
  timeout_s: number
  max_images: number
  temperature: number
  extra_body: Record<string, unknown>
  /** Parallel requests; 0 = the provider's default. */
  concurrency: number
  /** Shots per request; 0 = the provider's default. */
  batch: number
  /** Requests per UTC day (Codex); 0 = the provider's default. */
  daily_limit: number
  codex_path: string
}

// ---------------------------------------------------------------- model providers
export type ProviderId = 'custom' | 'openai' | 'openrouter' | 'codex'

export interface ProviderKey {
  name: 'openai_api_key' | 'openrouter_api_key'
  present: boolean
  /** "sk-…abcd"; the key itself is never returned. */
  masked: string
  from: 'stored' | 'environment' | ''
}

export interface CodexStatus {
  ok: boolean
  installed: boolean
  path?: string
  reason?: string | null
}

export interface Provider {
  id: ProviderId
  label: string
  hosted: boolean
  base_url: string
  default_models: { vlm: string; llm: string }
  concurrency: number
  batch: number
  key?: ProviderKey
  status?: CodexStatus
  daily_limit?: number
  remaining_today?: number | null
}

export interface ProvidersResponse {
  providers: Provider[]
  active: { vlm: ProviderId; llm: ProviderId }
  allow_remote: boolean
  egress: Egress
}

export interface ProviderTest {
  ok: boolean
  status?: number
  reason?: string | null
  limit_remaining?: number | null
  free_tier?: boolean | null
  installed?: boolean
  path?: string
}

export interface OpenRouterModel {
  id: string
  name: string
  vision: boolean
  context: number | null
  /** US dollars per million tokens. */
  input_per_m: number | null
  output_per_m: number | null
  structured: boolean
}

// ---------------------------------------------------------------- people (face identity)
export interface PersonRef {
  id: number
  name: string | null
  /** The name, or "Person 12" when unnamed. */
  label: string
}

export interface PersonSummary extends PersonRef {
  named: boolean
  faces: number
  shots: number
  files: number
  /** /media/… face crop. */
  cover: string | null
}

export interface PeopleList {
  total: number
  people: PersonSummary[]
  /** The face-identity analyser is switched on (Settings → Privacy and analysis). */
  enabled: boolean
}

export interface Face {
  id: number
  /** Seconds into the file. */
  t: number
  /** Normalised [x0, y0, x1, y1]. */
  box: [number, number, number, number]
  score: number
  size_px: number
  thumb: string
  /** A person put it here (named, merged or moved); automatic assignment leaves it alone. */
  confirmed: boolean
  shot_uid: Uid
  shot_number: number
  asset_uid: Uid
  filename: string
}

export interface PersonDetail extends PersonRef {
  named_by: string
  faces: Face[]
  shot_uids: Uid[]
}

export interface ModelInfo {
  name: string
  purpose: string
  licence: string
  source: string
  size_mb: number
  default: boolean
  tier: string
  installed: boolean
  path?: string
}

export interface AdminSettings {
  settings: {
    data_dir: string
    models_dir: string
    host: string
    port: number
    workers: number
    proxy_height: number
    proxy_crf: number
    sprite_interval: number
    max_segment_s: number
    vlm: ModelEndpoint
    llm: ModelEndpoint
    allow_remote: boolean
    face_identity: boolean
    /** Imports: borrow this browser's login ("" = none). */
    import_cookies_browser?: string
    /** Imports: default quality cap (height in pixels). */
    import_max_height?: number
    /** Imports: yt-dlp program to use ("" = PATH, else the copy Metachlorian downloads). */
    ytdlp_path?: string
    require_auth: boolean
    cors_origins: string[]
  }
  egress: Egress
  models: ModelInfo[]
  vlm_health: EndpointHealth | null
  llm_health: EndpointHealth | null
}

/** Health of a configured endpoint (no model request is spent). */
export interface EndpointHealth {
  ok: boolean
  status?: number
  reason?: string | null
  installed?: boolean
  path?: string
  limit_remaining?: number | null
  free_tier?: boolean | null
}

// ---------------------------------------------------------------- imports from web links (yt-dlp)
export type ImportStatus = 'queued' | 'probing' | 'downloading' | 'done' | 'duplicate' | 'failed' | 'cancelled' | 'expanded'

/** Where an imported file came from (GET /api/assets/{uid}; shot docs omit `description`). */
export interface Origin {
  url: string
  title: string | null
  site: string | null
  uploader: string | null
  upload_date: string | null
  license: string | null
  tags: string[]
  description?: string
  imported_at: number
}

/** One row of GET /api/imports: a video, or a playlist (`expanded`) whose videos are rows with its `parent_id`. */
export interface ImportRow {
  id: number
  url: string
  parent_id: number | null
  status: ImportStatus
  /** 0..1, or -1 while it can't be measured (e.g. downloading yt-dlp). */
  progress: number
  message: string
  error: string | null
  /** Under imports/ in the library; empty = the site's name. */
  folder: string
  playlist: boolean
  max_height: number
  origin_key: string | null
  title: string | null
  site: string | null
  uploader: string | null
  duration: number | null
  info: Record<string, unknown>
  /** The file, once imported. */
  path: string | null
  asset_uid: string | null
  actor: string
  created_at: number
  updated_at: number
  children?: ImportRow[]
}

export interface ImportList {
  imports: ImportRow[]
  counts: Partial<Record<ImportStatus, number>>
}

export interface ImportTool {
  installed: boolean
  path: string | null
  version: string | null
  /** Downloaded by Metachlorian into <library>/bin (rather than a system copy). */
  managed: boolean
  cookies_browser: string | null
  /** A cookies.txt is stored (its contents are never returned). */
  cookies_file: boolean
  max_height: number
  browsers: string[]
}
