/**
 * Types mirroring the core's response shapes
 * (core/metachlorian/service.py, search/engine.py, records.py, rights.py).
 * Keep these in step with the backend; unknown extra keys are tolerated.
 */

export type Uid = string

// ---------------------------------------------------------------- health / me
export interface EgressAdapter {
  adapter: string
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

export interface SearchResult extends ShotSummary {
  score: number
  why: WhyItem[]
  in: number | null
  out: number | null
  moment: Moment | null
  rights_badge?: RightsBadge
  rights?: { verdict: Verdict; reasons: string[] }
}

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
}

export interface AssetListItem {
  uid: Uid
  filename: string
  path: string
  status: string
  duration: number | null
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
  base_url: string
  model: string
  api_key_env: string
  local: boolean
  timeout_s: number
  max_images: number
  temperature: number
  extra_body: Record<string, unknown>
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
    require_auth: boolean
    cors_origins: string[]
  }
  egress: Egress
  models: ModelInfo[]
  vlm_health: Record<string, unknown> | null
  llm_health: Record<string, unknown> | null
}
