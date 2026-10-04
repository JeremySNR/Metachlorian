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
| `list_people` | yes | People recognised by face and named in the app; put a name in `search_shots` to require that person. Agents cannot name, merge or forget people |
| `library_stats` | yes | What exists, coverage and gaps; tells "not in the library" from "not indexed yet" |
| `list_vocabularies` | yes | The controlled vocabularies (term ids for filters) |
| `list_collections` | yes | Collections and selects |
| `correct_tag` | no | Fix a tag with a note; survives re-processing |

## A typical flow: brief → rough cut in Cutawan

1. `search_shots(query="founder talking about remote work", require={"shot_role": ["interview"]})`
2. `search_shots(query="hands typing on a laptop, calm", intended_use={"use": "marketing", "channel": "organic_social", "territory": "GB"})`
3. `get_shot` on the candidates to choose in/out points (transcript words carry timings).
4. `check_rights(shot_ids=[...], use="marketing", channel="organic_social", territory="GB")`
5. `build_package(name="Remote work explainer", items=[{"shot_uid": "...", "role": "interview"}, {"shot_uid": "..."}],
   consumer="cutawan", aspect="9:16", usage=["marketing"], channels=["organic_social"], territories=["GB"])`
6. Run `cutawan --import-package <path>`: Cutawan opens the rough cut with the transcript and B-roll inserts in place.

Agents cannot package shots whose rights verdict is not `allowed`; a person can review and decide in the app.
