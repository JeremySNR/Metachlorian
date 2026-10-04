# 011. MCP interface: transports, auth, and the minimum tool set

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context

Agents are first-class users of Metachlorian. An agent should be able to go
from a brief ("find 6 calm B-roll shots of hands on keyboards, cleared for
paid social in GB") to selected shots, a rights verdict and a handoff package
for Cutawan or an NLE ([ADR 012](012-interchange-and-cutawan-handoff.md))
without a human moving files. The MCP server is a thin layer over the same
service functions as the REST API, so the two can never disagree.
Constraints:

* Self-hosted, so it must work on a laptop (stdio, single user) and on a
  team server (HTTP, many users, SSO).
* Read-only by default. Anything that creates files or changes metadata needs
  an explicit scope and is audit-logged.
* Rights must not be bypassable by an agent.
* Commercial-friendly licences only.

### State of MCP (October 2026)

| Revision | Changes that matter here | Source |
|---|---|---|
| 2025-03-26 | OAuth 2.1 authorization. **Streamable HTTP** replaces HTTP+SSE. **Tool annotations** (read-only / destructive). Audio content | [changelog](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-03-26/changelog.mdx) |
| 2025-06-18 | **Structured tool output** (`outputSchema`, `structuredContent`). **Elicitation**. **Resource links** in tool results. Servers are OAuth resource servers; clients **must** use RFC 8707 resource indicators. `MCP-Protocol-Version` header. JSON-RPC batching removed | [changelog](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-06-18/changelog.mdx) |
| 2025-11-25 | Experimental **tasks** (durable requests with polling). URL-mode elicitation. Client ID Metadata Documents. Incremental scope consent via `WWW-Authenticate`. Icons. Tool-naming guidance. JSON Schema 2020-12 default. Input-validation errors returned as tool execution errors (so models can self-correct) | [changelog](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/changelog.mdx) |
| **2026-07-28** (current) | **Stateless**: no `initialize` handshake, no `Mcp-Session-Id`. Each request carries its version and capabilities in `_meta`. `server/discover`. **Multi round-trip requests** (`InputRequiredResult`, which carries elicitation). Tasks moved to the `io.modelcontextprotocol/tasks` extension (poll `tasks/get`). `subscriptions/listen`. `CacheableResult` (`ttlMs`, `cacheScope`). Tools listed in deterministic order. SSE resumability removed. RFC 9207 `iss` validation. Credentials keyed by issuer | [changelog](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx), [tools](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx), [schema.ts](https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/schema/2026-07-28/schema.ts) |

Key normative points (2026-07-28):

* **Tools** have `name` (1–128 chars of `[A-Za-z0-9_.-]`, unique per
  server), `title`, `description`, `inputSchema`, optional `outputSchema`,
  `annotations` and `icons`. If `outputSchema` is declared, results **must**
  conform, and for compatibility they should also return the serialised JSON
  as text. Protocol errors are JSON-RPC errors. Tool failures return
  `isError: true` with actionable text.
* **ToolAnnotations** are *hints* (clients must not trust them from
  untrusted servers). Defaults: `readOnlyHint=false`,
  `destructiveHint=true` (meaningful only if not read-only),
  `idempotentHint=false`, `openWorldHint=true`. So every Metachlorian tool
  must set them explicitly.
* **Pagination**: opaque `cursor` in, `nextCursor` out.
* **Authorization** (HTTP only): servers **must** publish OAuth 2.0
  Protected Resource Metadata (RFC 9728) and **must** validate that the token
  audience is this server (RFC 8707). Token passthrough is forbidden. PKCE is
  required. Insufficient scope returns HTTP 403 with
  `error="insufficient_scope"`, and the client then does step-up
  authorisation. Client registration preference order: Client ID Metadata
  Documents, then pre-registration, then DCR (DCR is now deprecated). For
  stdio, implementations should not use OAuth and should take credentials
  from the environment
  ([authorization](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/authorization/index.mdx)).
* **Streamable HTTP**: one endpoint, POST per message, `MCP-Protocol-Version`
  and method headers, and responses as JSON or SSE. Servers **must** validate
  `Origin` and should bind to localhost when running locally
  ([streamable-http](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx)).
* **Elicitation**: form mode (flat primitive schemas only) or URL mode.
  Servers **must not** request secrets in form mode
  ([elicitation](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/client/elicitation.mdx)).
* **Resources** are application-driven context (URI templates per RFC 6570,
  paginated listing, `audience`/`priority`/`lastModified` annotations)
  ([resources](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/resources.mdx)).
  Tools are model-driven actions. A model can only reach resources through
  host support, so anything an agent *must* be able to get is also exposed
  as a tool.

Tool-design guidance ([Anthropic, "Writing effective tools for agents"](https://www.anthropic.com/engineering/writing-tools-for-agents);
[AWS, MCP tool design](https://aws.amazon.com/blogs/machine-learning/mcp-tool-design-practical-approaches-and-tradeoffs/)):
build a few workflow-shaped tools rather than CRUD wrappers. Prefer search
over list-all. Return high-signal fields by default, with a
`response_format` switch for detail. Paginate and truncate with guidance in
the error text. Write descriptions that say when *not* to use a tool and how
natural-language values map onto parameters. Use namespaced, unambiguous
names.

### Python SDK status

* `mcp` (official SDK) **2.3.0, 2026-10-02**, MIT, Python ≥3.10. v2.0.0
  (2026-07-28) renamed `FastMCP` to **`MCPServer`**
  (`from mcp.server import MCPServer`). One server serves both the
  2025-11-25 and 2026-07-28 protocol eras. Sync tools run on worker threads,
  results are validated before sending, `MCPError` maps to protocol errors,
  OAuth `iss` is validated, and the client is first-class. v1.x is in
  maintenance (1.30.0)
  ([PyPI](https://pypi.org/project/mcp/), [repo](https://github.com/modelcontextprotocol/python-sdk),
  [releases](https://github.com/modelcontextprotocol/python-sdk/releases),
  [what's new in v2](https://py.sdk.modelcontextprotocol.io/whats-new/)).
* `fastmcp` (standalone, Prefect) **4.0.10, 2026-09-25**, Apache-2.0. It is a
  richer framework (proxying, composition, auth providers)
  ([PyPI](https://pypi.org/project/fastmcp/)).

## Options considered

| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **A. Official `mcp` v2 (`MCPServer`)**, mounted in our ASGI app | Spec-complete for both eras. Typed tools give `inputSchema`/`outputSchema` from type hints. Built-in token-verifier hooks | MIT | none | Adequate (I/O-bound; our search does the work) | Stable v2 since 2026-07, frequent releases | Anthropic + community, tracks the spec on the day it ships |
| B. Standalone `fastmcp` 4.x | More batteries (auth providers, server composition). Extra abstraction over the spec | Apache-2.0 | none | Same | Mature, very popular | Prefect + community. Can lag or diverge from spec semantics |
| C. Hand-rolled JSON-RPC | Full control | ours | none | Same | n/a | High burden, and the 2026 stateless changes would land on us |
| D. REST/OpenAPI only (no MCP) | Works with function-calling clients | n/a | none | Same | n/a | Misses MCP hosts (Claude, IDEs, Cutawan-side agents) |

## Evidence

Spec and SDK facts above were read from the spec repository and PyPI on
2026-10-04 (links inline). No benchmark is needed. Tool latency is dominated by
search (see the search ADRs), and MCP framing overhead is negligible.

## Decision

Use **option A**: the official `mcp` v2 SDK (`MCPServer`), pinned `mcp>=2.3,<3`.
Mount it at `/mcp` in the same ASGI app as the REST API. Offer `stdio` via
`metachlorian mcp`. Support protocol revisions **2025-11-25 and 2026-07-28**
(the SDK negotiates them). Tool handlers are thin adapters over
`core.metachlorian.services.*`. Re-evaluate `fastmcp` only if we need its
proxy or composition features.

### Transports and deployment

| Mode | Transport | Identity | Default scopes |
|---|---|---|---|
| Local single user (`metachlorian mcp`) | stdio | OS user. The stdio process talks to the solo-mode core on `127.0.0.1` using its per-launch token ([ADR 001](001-architecture-and-delivery.md)), or to a remote library via a `METACHLORIAN_TOKEN` env. No OAuth (per spec) | `library:read`. Write scopes only via explicit flags, e.g. `--allow export,tags` |
| Team server | Streamable HTTP at `https://<host>/mcp` | OAuth 2.1 bearer. Metachlorian is the **resource server** and publishes `/.well-known/oauth-protected-resource` | Whatever the token grants. Read-only by default |
| Headless agents / CI | Streamable HTTP | OAuth `client_credentials` for a service account, issued by the same authorisation server | Per service account |

* **Authorisation server**: bring-your-own OIDC (Keycloak Apache-2.0, ZITADEL
  Apache-2.0, Authentik, Entra ID, Google), or a minimal built-in AS for
  single-box installs. Audience is the canonical `/mcp` URL. Tokens are
  verified by JWKS or introspection. Tokens are never forwarded downstream.
* **Hardening**: validate `Origin`. Bind `127.0.0.1` unless
  `--public` is set. 4 MiB request cap (SDK default). Per-principal rate
  limits. Short-lived signed URLs for media.

### Scopes (least privilege; enforced server-side, never from annotations)

| Scope | Grants | Tools |
|---|---|---|
| `library:read` | Search and read metadata, transcripts, thumbnails and proxy previews in collections the principal can see | search_shots, get_shot, get_asset, find_similar, check_rights, library_stats, list_vocabularies, list_collections, get_job |
| `media:export` | Create derived files (trims, packages) in the export area. Never touches originals | export_clip, build_package |
| `tags:write` | Add or remove vocabulary tags and fix descriptions on shots | correct_tag |
| `rights:override` *(humans only; not grantable to client_credentials)* | Include shots whose rights verdict is not `allowed` in a package | build_package with `rights_override` |
| `admin` *(not exposed via MCP v1)* | Vocab extensions, collections, rights records, users | REST/UI only |

Collection-level ACLs apply on top of scopes: a principal only ever sees
assets in collections shared with them, and search filters on this before
ranking. When a call lacks scope, the HTTP request gets
`403 insufficient_scope` (step-up). On stdio the tool returns `isError` with
the flag needed.

### Audit log

Each `tools/call` with a write scope, each export and package, and each
rights check whose result is shown to a user is written to an append-only
`audit_events` table with these fields: `ts`, `principal`, `oauth_client_id`
and client name, `tool`, a hash of the arguments plus redacted arguments,
the ids touched, `scopes_used`, `outcome`, `latency_ms`, and for exports the
`rights_snapshot_hash` (the rights state used for the decision). Read-only
calls are sampled into metrics, not audited. Admins can view and export the
log in the UI. Retention is configurable (default 400 days).

### Tool set (v1)

Conventions for all tools:

* Names are `snake_case`. Hosts prefix with the server name, so no
  `metachlorian_` prefix is added.
* Every tool sets all four annotations explicitly.
* Every tool declares `outputSchema` and returns `structuredContent` plus a
  short text summary. Media goes out as `resource_link`s
  (`metachlorian://…` plus a signed `https` URL).
* List-like outputs take `limit` (default 10, max 50) and `cursor` and
  return `next_cursor`. Cursors are opaque, signed and expire after 1 h.
  This fits the stateless 2026 model with no server session.
* `response_format: "concise" | "detailed"` (default concise, about ≤150
  tokens per hit).
* Times are in seconds as float **and** as a rational `{value, rate}`, plus a
  SMPTE timecode string when the source has timecode.
* Filters use vocabulary ids from [ADR 010](010-controlled-vocabularies.md).
  `inputSchema` enums are generated from the loaded vocabularies including
  local extensions, and `list_vocabularies` gives synonyms. An unknown term
  returns `isError` with "did you mean" suggestions.

| Tool | Annotations (ro / destr / idem / open) | Input (sketch) | Output (sketch) | Notes |
|---|---|---|---|---|
| **search_shots** | T / – / T / F | `query?: str` (natural language; synonyms parsed into filters), `filters?: {shot_size[], camera_angle[], camera_movement[], speed_effect[], shot_role[], pace[], mood[], time_of_day[], weather[], season[], setting[], audio_class[], people_count[], lens_class[], quality_exclude[] (default: severity≥major), collections[], asset_ids[], edit_type[], source_type[], date_from/to, duration_min/max, orientation: landscape\|portrait\|square, min_height, has_speech, language, text_in_frame?, people[] (named entities), safe_crop?: "9:16"\|"1:1"\|"4:5"}`, `rights?: {usage[], channels[], territories[] (ISO 3166-1 α-2 / M49), start?, end?, require: "allowed"\|"not_blocked"}`, `sort?: relevance\|newest\|duration\|quality`, `diversity?: 0..1` (penalise many hits from one asset), `limit`, `cursor`, `response_format` | `{results: [{shot_id, asset_id, asset_name, in, out, duration, tc_in?, thumbnail: resource_link, preview: resource_link, description, tags (compact `vocab: [ids]`), score, why: [matched facets / transcript snippet], rights: {verdict, reasons[]}?, quality_flags[]}], next_cursor?, total_estimate, interpreted_as: {filters, free_text}, vocab_versions}` | Main entry point. `interpreted_as` lets the agent see and correct the parse. Rights filtering runs only when `rights` is given, otherwise only `rights.verdict` hints are shown |
| **get_shot** | T / – / T / F | `shot_id`, `include?: [tags_detail, transcript, rights, neighbours, provenance, technical, safe_crops, colours]` | Full shot record: tag assertions with confidence and source, transcript words in range, previous/next shot ids, `safe_crops` per aspect, palette, technical (fps, resolution, codec, colour space, log profile), rights summary, proxy and source `resource_link`s | Before choosing in/out points |
| **get_asset** | T / – / T / F | `asset_id`, `include?: [shots, transcript, technical, rights, markers]`, `shots_cursor?`, `shots_limit?` | Asset metadata (`edit_type`, `source_type`, collections, capture date and geo), paged shot list, transcript (paged by time), rights record (ODRL-style), markers | Context for a hit |
| **find_similar** | T / – / T / F | `shot_id?` or `image?: resource_link\|base64` or `text?`, `modality?: visual\|semantic\|audio\|motion`, `filters?` (as search_shots), `exclude_same_asset?: bool = true`, `limit`, `cursor` | Same shape as search_shots results, plus `similarity` | "More like this", alternative takes, coverage of the same moment |
| **check_rights** | T / – / T / F | `shot_ids[]` (≤200), `intended: {usage[], channels[], territories[], start, end, audience?}` | `{results: [{shot_id, verdict: allowed\|restricted\|blocked\|unknown, reasons: [{code, detail, source}], requirements: [credit line, notify, …], expires_at?, clearance_flags[]}], summary: {allowed, restricted, blocked, unknown}, rights_snapshot_hash}` | Pure function of the rights records. `unknown` release status or an unconfirmed clearance flag gives `unknown`, never `allowed` |
| **export_clip** | F / F / T / F | `shot_id` or `{asset_id, in, out}`, `handles?: sec = 0`, `preset: proxy_h264 \| mezzanine_prores \| original_trim \| still_jpeg \| audio_wav`, `crop?: {aspect: "9:16"\|..., mode: safe_crop\|centre}`, `burn_in?: none\|timecode\|watermark` | `{job_id}` or, when quick, `{file: resource_link, sha256, bytes, expires_at}` | Scope `media:export`. Idempotent: the same args return the cached artefact. Long jobs use the tasks extension when the client supports it, otherwise `get_job` |
| **build_package** | F / F / T / F | `name`, `brief?: str`, `items: [{shot_id \| asset_id+in/out, role?: a_roll\|b_roll\|…, in_override?, out_override?, note?}]` or `from_search: {query, filters, rights, count}`, `sequence?: {order: as_given\|by_role, target_duration?, rate?: "25/1"}`, `target: {consumer: cutawan\|nle\|generic, aspect?, channels[], usage[], territories[]}`, `media: none\|proxies\|trimmed_originals\|stringout`, `timelines: [otio, fcpxml, edl]`, `include_transcripts: bool = true`, `idempotency_key`, `rights_override?: {reason}` | `{package_id, job_id?, manifest: resource_link, download: resource_link (zip), rights_summary, warnings[]}` | Scope `media:export`. Produces the [Cutawan/NLE package](../integration/cutawan-contract.md). Runs `check_rights` first. Blocked or unknown items are dropped with warnings. If the user should decide, form-mode **elicitation** asks "include N restricted shots?". With no elicitation support and no `rights:override`, the call fails with `isError` listing the items |
| **library_stats** | T / – / T / F | `scope?: {collections[]}`, `group_by?: [collection, edit_type, source_type, year, shot_size, …]` | Counts (assets, shots, hours), index coverage per vocabulary (% tagged, mean confidence), processing backlog, vocab versions | Helps an agent judge whether "no results" means "not in library" or "not yet indexed" |
| **list_vocabularies** | T / – / T / F | `name?`, `include_synonyms?: bool` | Vocab name, version, multi/ordered, terms (id, label, definition, broader, synonyms?) including local extensions | Also a resource. Cacheable (`ttlMs` 1 h) |
| **list_collections** | T / – / T / F | `cursor`, `limit`, `query?` | `{collections: [{id, name, description, asset_count, hours, default_rights?}], next_cursor}` | Only collections visible to the principal |
| **correct_tag** | F / T / T / F | `shot_id` (or `shot_ids[]` ≤50), `vocabulary`, `add?: [term_id]`, `remove?: [term_id]`, `description?: str`, `range?: {in, out}`, `note: str` (required) | `{updated: [{shot_id, vocabulary, before, after}], audit_id}` | Scope `tags:write`. `destructiveHint=true` because it can remove tags. Writes human-sourced assertions and tombstones. Cannot change rights or release status |
| **get_job** | T / – / T / F | `job_id` | `{state: queued\|running\|done\|failed, progress 0..1, result?: {...}, error?}` | Fallback for clients without the tasks extension |

`search_shots.why` carries the per-retriever contributions from hybrid
ranking ([ADR 016](016-hybrid-ranking.md)). `interpreted_as` comes from the
deterministic vocabulary parser described there, so MCP clients never need
an LLM parse. Queue administration (list, pause, cancel, re-prioritise from
[ADR 009](009-job-queue.md)) requires the `admin` scope and is not part of
the agent tool set. `get_job` only shows jobs the caller started.

Deliberately **not** in v1: delete or move assets, edit rights or releases,
ingest from URLs, change users or ACLs, and arbitrary SQL. These are higher
risk with little agent value, and stay in the UI and admin REST API.

### Resources and prompts

* Resources (read-only, cacheable): `metachlorian://vocab/{name}`,
  `metachlorian://shot/{shot_id}` (JSON), `metachlorian://shot/{shot_id}/thumbnail.jpg`,
  `metachlorian://asset/{asset_id}`, `metachlorian://package/{package_id}/manifest.json`.
  Templates are listed with RFC 6570 URIs.
* Prompts (user-invoked):
  * `find_broll_for_script(script, channel, territory)`: search → check_rights → build_package
  * `rights_safe_selects(brief, usage, channels, territories)`

### Tool descriptions (style rules)

Each description states:

1. what the tool returns and the typical next tool
2. when *not* to use it (e.g. "do not page through all results to count
   them; use library_stats")
3. how vocabulary words map to filters, with two examples
4. limits (`limit` ≤50; transcripts truncated to 2,000 chars with a pointer
   to `get_asset`)
5. any rights caveat (e.g. "verdict `unknown` means do not use for
   commercial work without human sign-off")

These descriptions are evaluated in `eval/mcp/` with scripted agent tasks
(success rate, calls per task, tokens per task) before each release.

## Consequences

* **Easier**: any MCP host can use the library, and the same service layer
  backs REST, UI and MCP. Stateless 2026 semantics match our design (cursor
  and job handles in arguments, no session state). Enums from vocabularies
  make tool calls valid by construction.
* **Harder**: we must run or integrate an OAuth AS for team installs, keep
  tool descriptions tuned through evals, and keep two protocol eras working
  until 2025-era clients fade. Signed media URLs need key rotation.
* Rights decisions are server-side and audited, so an agent cannot export a
  blocked shot without a human `rights:override` grant.

## Revisit when

* MCP's next revision changes tasks, elicitation or auth again, or the SDK
  ships v3.
* Eval shows agents mis-using tools (e.g. >2 search calls per brief on
  average, or frequent `isError` from unknown terms). Then revise
  granularity or descriptions, or merge get_shot and get_asset.
* Customers need write tools beyond tags (rights edits from agents). That
  needs a separate ADR with approval workflow.
* The tasks extension is widely supported by hosts. Then retire `get_job`.
