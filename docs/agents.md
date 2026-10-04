# Metachlorian for AI agents

Agents use the same core as people: an MCP server (recommended) or the REST API. They are never second-class users, and they
never get more than a person with the same scopes would.

## Connect

**Streamable HTTP (team or solo):**

```json
{
  "mcpServers": {
    "metachlorian": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp/",
      "headers": { "Authorization": "Bearer mc_xxxxxx_..." }
    }
  }
}
```

Create the token in **Settings → Agents** or with `metachlorian token my-agent --scopes library:read,media:export`.

**stdio (same machine):**

```json
{ "mcpServers": { "metachlorian": { "command": "metachlorian", "args": ["mcp"],
  "env": { "METACHLORIAN_DATA": "/path/to/library", "METACHLORIAN_TOKEN": "mc_..." } } } }
```

Without a token, stdio runs as a read-only local agent. `METACHLORIAN_MCP_ALLOW=media:export,tags:write` adds scopes for a
trusted local agent.

## Scopes

| Scope | Allows | Default for agents |
|---|---|---|
| `library:read` | search, read shots/assets/collections, check rights, stats | yes |
| `media:export` | export clips, build packages (only rights-cleared media) | no |
| `collections:write` | create and edit collections | no |
| `tags:write` | correct tags and descriptions (stored as corrections, audited) | no |
| `rights:write`, `admin` | never available to agent tokens | — |

Every agent call is written to the audit log (Settings → Audit log, filter "agents only").

## Tools

| Tool | Read-only | Purpose |
|---|---|---|
| `search_shots` | yes | Natural-language and/or structured search with optional `intended_use`; returns ranked shots with in/out, tags, confidences, *why* explanations and rights verdicts |
| `get_shot` | yes | Full record: every signal with value, confidence, source and model version; transcript with word timings; neighbours; rights |
| `get_asset` | yes | File summary: structure (shots, cuts/min, single take, titles, music bed), raw/selects/finished with confidence, shot list |
| `find_similar` | yes | Shots that look like a shot or a still image |
| `check_rights` | yes | Verdict (allowed / restricted / blocked / unknown) with reasons for a use, channel, territory and date |
| `export_clip` | no | A clip as a reference, proxy file, trimmed original or one-clip OTIO/FCPXML/EDL |
| `build_package` | no | A Cutawan / NLE hand-off package with manifest, media, transcript, timelines and rights summary |
| `list_folders` | yes | Folders the footage came from, with files, shots, hours and recording dates; find "the Disney holiday" and pass it as `folder` |
| `list_files` | yes | Files in a folder or collection (or matching a name), with duration, date, edit stage and summary |
| `get_collection` | yes | One collection in order, with trims, notes and rights |
| `list_people` | yes | People recognised by face and named in the app; put a name in `search_shots` to require that person. Agents cannot name, merge or forget people |
| `library_stats` | yes | What exists, coverage and gaps; tells "not in the library" from "not indexed yet" |
| `list_vocabularies` | yes | The controlled vocabularies (term ids for filters) |
| `list_collections` | yes | Collections and selects |
| `correct_tag` | no | Fix a tag with a note; survives re-processing |

## Scoping to a folder or collection

`search_shots` and `find_similar` take `folder` (a name like `"Disney 2026"`, a relative path like
`"Holidays/Disney 2026"`, or an absolute path; subfolders included) and `collection` (uid or exact name). Both can be
combined with everything else, and an empty query with a scope returns every shot in it, best quality first. People can
type the same thing in the app's search box: `folder:"Disney 2026" kids on rides`. A name that matches nothing comes back
with a note naming the closest folders, so an agent can correct itself.

Example: "Use my Disney holiday videos and make a 60-second cut of the kids on rides."

1. `list_folders(query="disney")` → `Videos/Holidays/Disney 2026` (41 files, 2.3 h, 3–14 Aug 2026)
2. `search_shots(query="kids on a ride, smiling", folder="Disney 2026", filters={"min_duration": 2})`
3. `find_similar(shot_id=<best one>, folder="Disney 2026")` for more like it
4. `build_package(items=[...], name="Disney rides 60s", brief="...")` → a package any editor or tool can open

## A typical flow: brief → rough cut in Cutawan

1. `search_shots(query="founder talking about remote work", require={"shot_role": ["interview"]})`
2. `search_shots(query="hands typing on a laptop, calm", intended_use={"use": "marketing", "channel": "organic_social", "territory": "GB"})`
3. `get_shot` on the candidates to choose in/out points (transcript words carry timings).
4. `check_rights(shot_ids=[...], use="marketing", channel="organic_social", territory="GB")`
5. `build_package(name="Remote work explainer", items=[{"shot_uid": "...", "role": "interview"}, {"shot_uid": "..."}],
   consumer="cutawan", aspect="9:16", usage=["marketing"], channels=["organic_social"], territories=["GB"])`
6. Run `cutawan --import-package <path>`: Cutawan opens the rough cut with the transcript and B-roll inserts in place.

Agents cannot package shots whose rights verdict is not `allowed`; a person can review and decide in the app.
