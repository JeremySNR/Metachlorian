"""MCP server: the agent interface to the library.

Transports: stdio (``metachlorian mcp``) and Streamable HTTP mounted at
``/mcp`` on the core. Every tool runs through the same service layer as the
REST API and the app, so scopes, rights checks and the audit log apply
equally. Agents are read-only by default (see docs/decisions/011-mcp-interface.md).
"""
from __future__ import annotations

import base64
import contextvars
import os
from typing import Any, Literal, NoReturn

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..auth import AGENT_DEFAULT, Forbidden, Principal, authenticate_token
from ..search.engine import SearchRequest
from ..service import Library, NotFound
from ..vocab import registry

RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
EXPORT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
APPEND = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

INSTRUCTIONS = """Metachlorian is a video library indexed at the level of shots. Every shot has a time range inside a source file
and structured signals (camera movement, shot size, role, setting, time of day, people, transcript, on-screen text, quality),
each with a confidence and a source. Rights are recorded per file and can be checked for an intended use.

Start with library_stats, library_readiness and list_folders to understand coverage, failures and scope. list_files includes files still being
analysed; search_shots only finds indexed shots. An empty search is not proof that footage does not exist.
Follow next_cursor on shot searches and next_offset on file lists before claiming you have seen every result.

Typical flow: search_shots (describe the footage in plain language, add filters and an intended use) -> get_shot for
candidates (check in/out points, transcript, rights) -> create_collection / add_to_collection to save a shortlist
when collections:write is granted -> check_rights -> build_package (Cutawan or an editing timeline).
Only shots whose rights verdict is 'allowed' for the stated use should be used; build_package refuses anything else.
Collections store references and notes without copying source media or granting export rights. Creating a collection
or appending shots is not idempotent: inspect list_collections / get_collection after an uncertain response before retrying.
Vocabulary ids for filters come from list_vocabularies. Times are seconds from the start of the source file.
Use captured_asc / captured_desc for recording chronology; added_desc means import order. Unknown capture dates sort last.
Keep confidence and source with claims: an inferred flat/Log appearance is not a confirmed camera Log profile.
Never infer an input colour transform from appearance alone; inspect get_asset technical metadata and its evidence."""

stdio_principal: contextvars.ContextVar[Principal | None] = contextvars.ContextVar("stdio_principal", default=None)


def _principal(lib: Library, ctx: Context | None) -> Principal:
    if ctx is not None:
        try:
            headers = ctx.headers or {}
        except Exception:
            headers = {}
        auth = headers.get("authorization") or headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            p = authenticate_token(lib.db, auth[7:].strip(), via="mcp")
            if p is None:
                raise Forbidden("invalid or expired token")
            return p
    p = stdio_principal.get()
    if p is not None:
        return p
    raise Forbidden("authentication required: send 'Authorization: Bearer <token>'")


def _err(e: Exception) -> NoReturn:
    """Anticipated failures reach the client as MCP tool errors (isError), not as data."""
    raise ToolError(f"{type(e).__name__}: {e}") from e


def build_server(lib: Library) -> MCPServer:
    from ..photos.mcp import INSTRUCTIONS as PHOTO_INSTRUCTIONS, register as register_photos
    server = MCPServer(name="metachlorian", title="Metachlorian: photo and footage library for AI editors", instructions=INSTRUCTIONS + PHOTO_INSTRUCTIONS,
                       version=__import__("metachlorian").__version__)

    def call(ctx: Context | None, fn, *a, **kw):
        p = _principal(lib, ctx)
        return fn(p, *a, **kw)

    @server.tool(annotations=RO)
    def search_shots(query: str = "", filters: dict[str, Any] | None = None, require: dict[str, list[str]] | None = None,
                     exclude: dict[str, list[str]] | None = None, intended_use: dict[str, Any] | None = None,
                     asset_ids: list[str] | None = None, strict: bool = False, limit: int = 20, cursor: str | None = None,
                     folder: str | list[str] | None = None, collection: str | list[str] | None = None,
                     sort: Literal["relevance", "captured_desc", "captured_asc"] = "relevance",
                     ctx: Context | None = None) -> dict[str, Any]:
        """Find shots (not whole files) matching a plain-language description and/or structured filters.

        query: natural language, e.g. "slow wide drone shots of a coastline at golden hour, no people, at least 8 seconds, 4K".
          It is parsed into filters (duration, resolution, people, orientation, log, fps) and vocabulary preferences;
          the interpreted query is returned under query so you can see and correct it.
        filters: {min_duration, max_duration, min_height (e.g. 2160 for 4K), min_fps, orientation: vertical|horizontal,
          log: bool, hdr: bool, usable: bool, speech: bool, music: bool, min_people, max_people, edit_type: raw|selects|finished}.
        require / exclude: {vocabulary: [term ids]} hard term filters, e.g. {"camera_movement": ["aerial"]}. See list_vocabularies.
        intended_use: {use: usage term (e.g. marketing, editorial), channel: channel term (e.g. paid_social),
          territory: ISO 3166 alpha-2, date: YYYY-MM-DD, include: ["allowed"]}. When given, only shots cleared for it are returned.
        strict: treat vocabulary words in the query as hard filters instead of ranking preferences.
        folder: only footage from this folder or its subfolders — a name ("Disney 2026"), a relative path
          ("Holidays/Disney 2026") or an absolute path. See list_folders. A list means any of them.
        collection: only shots in this collection (uid or exact name). See list_collections.
          With folder or collection and an empty query you get every shot in it, best quality first.
          (The query may also contain folder:"..." or collection:"...".)
        sort: relevance (default), captured_desc (newest recorded first), or captured_asc (oldest first).
          Date ordering applies before pagination, unknown dates come last. Keep the same query, scope and sort
          when passing next_cursor as cursor. Use list_files to also see files without indexed shots.
        Returns results with uid (shot id), asset_uid, in/out seconds, caption, tags, why (which signals matched,
        with confidence), rights verdict when intended_use is given, and next_cursor for paging."""
        try:
            filters = dict(filters or {})
            if folder:
                filters["folder"] = folder
            if collection:
                filters["collection"] = collection
            return call(ctx, lib.search, SearchRequest(q=query, filters=filters, require=require or {}, exclude=exclude or {},
                                                       intended_use=intended_use, asset_uids=asset_ids, strict=strict,
                                                       limit=max(1, min(100, limit)), cursor=cursor, sort=sort))
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def get_shot(shot_id: str, intended_use: dict[str, Any] | None = None, ctx: Context | None = None) -> dict[str, Any]:
        """Full record for one shot: every signal with value, confidence, source and model version (human corrections
        marked), transcript with word timings, moments, technical metadata, rights (and a rights check when
        intended_use is given), neighbouring shot ids and media links."""
        try:
            d = call(ctx, lib.get_shot, shot_id, intended_use)
            for k in ("keyframes",):
                d.pop(k, None)
            return d
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def get_asset(asset_id: str, include_transcript: bool = True, include_processing: bool = False,
                  ctx: Context | None = None) -> dict[str, Any]:
        """Asset (source file) summary: technical metadata, structure (shot count, cuts per minute, single take,
        titles, music bed), classification as raw / selects / finished edit with confidence, story summary,
        the shot list with timecodes, rights, status and outstanding jobs. Set include_processing=true for detailed
        analyser runs, errors and completion times; include_transcript=false keeps long files compact."""
        try:
            d = call(ctx, lib.get_asset, asset_id)
            if not include_transcript:
                d.pop("transcript", None)
            if not include_processing:
                d.pop("processing", None)
            return d
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def find_similar(shot_id: str | None = None, image_base64: str | None = None, limit: int = 12,
                     modality: Literal["visual", "audio", "text"] = "visual",
                     intended_use: dict[str, Any] | None = None, filters: dict[str, Any] | None = None,
                     folder: str | list[str] | None = None, collection: str | list[str] | None = None,
                     ctx: Context | None = None) -> dict[str, Any]:
        """Shots similar to a given shot (shot_id) or a still image (image_base64, JPEG or PNG).
        modality: visual (looks like), audio (sounds like) or text (what is said/described means the same).
        Same result shape as search_shots. Optional intended_use, filters, folder and collection as in search_shots."""
        try:
            img = base64.b64decode(image_base64) if image_base64 else None
            filters = dict(filters or {})
            if folder:
                filters["folder"] = folder
            if collection:
                filters["collection"] = collection
            return call(ctx, lib.find_similar, shot_id, img, None, max(1, min(100, limit)), intended_use, filters, modality)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def check_rights(shot_ids: list[str] | None = None, asset_ids: list[str] | None = None, use: str | None = None,
                     channel: str | None = None, territory: str | None = None, date: str | None = None,
                     ctx: Context | None = None) -> dict[str, Any]:
        """Whether shots or assets are cleared for an intended use. use: usage term (commercial, advertising, marketing,
        editorial, internal...), channel: channel term (paid_social, organic_social, broadcast, web, ooh...),
        territory: ISO 3166-1 alpha-2, date: YYYY-MM-DD (default today). Verdicts: allowed | restricted (a person must
        decide) | blocked | unknown (nothing recorded; treat as not cleared). Every verdict lists its reasons."""
        try:
            return call(ctx, lib.check_rights, (shot_ids or [])[:200], (asset_ids or [])[:200], use, channel, territory, date)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=EXPORT)
    def export_clip(shot_id: str, in_seconds: float | None = None, out_seconds: float | None = None,
                    mode: Literal["reference", "proxy", "file", "otio", "fcpxml", "edl"] = "reference",
                    intended_use: dict[str, Any] | None = None, ctx: Context | None = None) -> dict[str, Any]:
        """Render or reference one clip. in/out are asset seconds (default: the whole shot). mode: reference (path and
        timecodes only), proxy (H.264 from the proxy), file (trimmed from the original), or a one-clip otio/fcpxml/edl.
        Needs the media:export scope. Agents can only export media that is cleared for intended_use."""
        try:
            return call(ctx, lib.export_clip, shot_id, in_seconds, out_seconds, mode, intended_use)
        except (Forbidden, NotFound, ValueError, KeyError, FileNotFoundError) as e:
            _err(e)

    @server.tool(annotations=EXPORT)
    def build_package(name: str, items: list[dict[str, Any]] | None = None, collection_id: str | None = None, brief: str = "",
                      consumer: Literal["cutawan", "nle", "generic"] = "cutawan", aspect: Literal["9:16", "1:1", "16:9", "original"] = "9:16",
                      usage: list[str] | None = None, channels: list[str] | None = None, territories: list[str] | None = None,
                      media: Literal["none", "proxies", "trimmed_originals", "stringout"] = "proxies",
                      mode: Literal["stringout", "a_roll_with_inserts", "broll_library"] | None = None,
                      ctx: Context | None = None) -> dict[str, Any]:
        """Bundle shots into a hand-off package for Cutawan or an editing app: manifest.json (schema in
        docs/integration/cutawan-package.schema.json), trimmed media with handles, a stringout and transcript,
        OTIO + FCPXML 1.10 + CMX 3600 EDL timelines, RIGHTS.md and checksums.
        items: [{shot_uid, in?, out?, role? (shot_role term, e.g. interview or b_roll), note?}] or collection_id.
        Rights are checked against usage/channels/territories; agents get an error if any item is not allowed.
        Open the result in Cutawan with: cutawan --import-package <path>."""
        try:
            target = {"consumer": consumer, "aspect": aspect, "usage": usage or [], "channels": channels or [], "territories": territories or []}
            res = call(ctx, lib.build_package, items, collection_id, name, brief, target, media, mode)
            res["manifest_summary"] = {k: res["manifest"].get(k) for k in ("package_id", "name", "media_policy", "cutawan", "stringout", "timelines")}
            res.pop("manifest", None)
            return res
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def library_readiness(limit: int = 10, ctx: Context | None = None) -> dict[str, Any]:
        """Check whether search and analysis are complete before claiming footage is absent.
        Reports searchable/unindexed files, missing active shots, preview readiness, per-analyser done/failed/unavailable
        counts, queue and scan state, plus bounded failure examples. No files are processed or sent to a provider.
        Indexed does not mean accurate or fully analysed; unavailable optional models mean reduced feature coverage.
        Use get_asset(include_processing=True) to inspect a reported file. limit bounds diagnostic examples (1–50)."""
        try:
            return call(ctx, lib.library_readiness, limit)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def library_stats(ctx: Context | None = None) -> dict[str, Any]:
        """What the library holds: files, hours, shots, processing state, raw/selects/finished counts, topics,
        places, per-vocabulary coverage counts and coverage gaps (terms with no confident shots), rights status.
        Use it to tell 'not in the library' from 'not indexed yet'."""
        try:
            return call(ctx, lib.library_stats)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def list_folders(query: str = "", parent: str | None = None, limit: int = 200, ctx: Context | None = None) -> dict[str, Any]:
        """Folders the footage was added from, with files, shots, hours and the recording date range of each
        (counts include subfolders). Use it to find "the holiday videos" and then pass the folder to search_shots or
        list_files. query filters by name or path (case-insensitive); parent lists one folder's direct subfolders."""
        try:
            return call(ctx, lib.folders, query, parent, max(1, min(1000, limit)))
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def list_files(folder: str | None = None, collection: str | None = None, query: str = "", limit: int = 100, offset: int = 0,
                   sort: Literal["added_desc", "captured_desc", "captured_asc", "name"] = "added_desc",
                   ctx: Context | None = None) -> dict[str, Any]:
        """Files (not shots) in a folder or collection, or whose name, path or summary contains query: uid, filename,
        path, duration, recording date, raw/selects/finished, shot count, summary and rights badge. Use get_asset for
        one file's shot list, or search_shots with the same folder to find moments. Includes files still being analysed.
        sort: added_desc (newest import, default), captured_desc / captured_asc (recording chronology, unknown last),
        or name. The response contains total, assets, offset, limit, has_more and next_offset. Repeat with next_offset
        and the same scope/sort until has_more=false; the first page is not the complete library."""
        try:
            limit, offset = max(1, min(500, limit)), max(0, offset)
            out = call(ctx, lib.list_assets, query, None, None, limit, offset, folder, collection, sort=sort)
            next_offset = offset + len(out["assets"])
            has_more = bool(out["assets"]) and next_offset < out["total"]
            return {**out, "offset": offset, "limit": limit, "has_more": has_more,
                    "next_offset": next_offset if has_more else None}
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=APPEND)
    def create_collection(name: str, description: str = "", brief: str = "", ctx: Context | None = None) -> dict[str, Any]:
        """Save a new, empty footage shortlist in the app. Needs collections:write. No source media is copied.
        name: a useful title; brief: the editorial goal. Returns uid for add_to_collection and build_package.
        Repeating this call creates another collection; inspect list_collections after an uncertain response."""
        try:
            if not name.strip():
                raise ValueError("name must not be empty")
            return call(ctx, lib.create_collection, name, description, brief=brief)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=APPEND)
    def add_to_collection(collection_id: str, shot_ids: list[str], note: str = "",
                          in_seconds: float | None = None, out_seconds: float | None = None,
                          ctx: Context | None = None) -> dict[str, Any]:
        """Append 1–200 shots to a saved shortlist, in the supplied order. Needs collections:write.
        Optional trims are source-file seconds and apply to every supplied shot; use one shot per call for distinct
        trims or selection notes. The result includes item_id for each entry. This stores references only, without
        copying media or changing rights. Repeated calls append duplicates; inspect get_collection before retrying."""
        try:
            if not 1 <= len(shot_ids) <= 200:
                raise ValueError("give between 1 and 200 shot_ids")
            return call(ctx, lib.add_to_collection, collection_id, shot_ids, in_seconds, out_seconds, note)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=WRITE)
    def update_collection(collection_id: str, name: str | None = None, description: str | None = None,
                          brief: str | None = None, ctx: Context | None = None) -> dict[str, Any]:
        """Rename a shortlist or update its description/editorial brief. Needs collections:write.
        Omitted fields stay unchanged; an empty description or brief clears that field. Items and media are unchanged."""
        try:
            if name is not None and not name.strip():
                raise ValueError("name must not be empty")
            return call(ctx, lib.update_collection, collection_id, name=name, description=description, brief=brief)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=WRITE)
    def update_collection_item(collection_id: str, item_id: int, note: str | None = None,
                               in_seconds: float | None = None, out_seconds: float | None = None,
                               reset_trim: bool = False, ctx: Context | None = None) -> dict[str, Any]:
        """Refine one shortlist entry's note or trim. Needs collections:write; item_id comes from get_collection.
        Times are source-file seconds. Omitted values stay unchanged; an empty note clears the note.
        reset_trim=true restores the full shot and cannot be combined with in_seconds/out_seconds.
        Source media is unchanged. Use reorder_collection to change the sequence."""
        try:
            if reset_trim and (in_seconds is not None or out_seconds is not None):
                raise ValueError("reset_trim cannot be combined with in_seconds or out_seconds")
            fields: dict[str, Any] = {}
            if note is not None:
                fields["note"] = note
            if reset_trim:
                fields.update({"in": None, "out": None})
            else:
                if in_seconds is not None:
                    fields["in"] = in_seconds
                if out_seconds is not None:
                    fields["out"] = out_seconds
            return call(ctx, lib.update_item, collection_id, item_id, **fields)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=WRITE)
    def reorder_collection(collection_id: str, item_ids: list[int], ctx: Context | None = None) -> dict[str, Any]:
        """Set the shortlist sequence. Needs collections:write. Pass every item_id returned by get_collection
        exactly once, in the desired order. Missing, repeated or foreign item ids are rejected without changing
        the collection. Trims, notes, source media and rights remain unchanged."""
        try:
            return call(ctx, lib.reorder, collection_id, item_ids)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=WRITE)
    def remove_from_collection(collection_id: str, item_id: int, ctx: Context | None = None) -> dict[str, Any]:
        """Remove one shortlist entry using item_id from get_collection. Needs collections:write.
        Only the collection entry is removed: the source video, its analysis and other entries remain."""
        try:
            return call(ctx, lib.remove_item, collection_id, item_id)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def get_collection(collection_id: str, ctx: Context | None = None) -> dict[str, Any]:
        """One collection in order: each item's shot (caption, timecodes, tags), trim in/out, note and rights badge,
        plus the brief. collection_id is the uid from list_collections."""
        try:
            return call(ctx, lib.collection, collection_id)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def list_people(query: str = "", named_only: bool = True, limit: int = 50, ctx: Context | None = None) -> dict[str, Any]:
        """People the library recognises by face (named by a person in the app, local only), with how many shots
        and files each appears in. Use a name in search_shots (e.g. "Maria laughing in the kitchen") to require
        that person. Agents can read names but cannot name, merge or forget people."""
        try:
            return call(ctx, lib.people, query, True if named_only else None, max(1, min(200, limit)))
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def list_vocabularies(name: str | None = None, ctx: Context | None = None) -> dict[str, Any]:
        """Controlled vocabularies used for filters and tags. Without a name: the list with versions. With a name: every
        term (id, label, definition, synonyms, broader) including local extensions."""
        try:
            return call(ctx, lib.vocabularies, name)
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=RO)
    def list_collections(ctx: Context | None = None) -> dict[str, Any]:
        """Collections and selects reels with item counts and total duration."""
        try:
            return {"collections": call(ctx, lib.collections)}
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.tool(annotations=WRITE)
    def correct_tag(shot_id: str, field: str, note: str, add: list[str] | None = None, remove: list[str] | None = None,
                    set_value: Any = None, ctx: Context | None = None) -> dict[str, Any]:
        """Correct a shot's tag or description. Needs the tags:write scope. field: e.g. camera.movement, camera.shot_size,
        shot.role, content.setting, content.time_of_day, content.caption, people.count, quality.usable. add/remove term ids
        for multi-valued fields, or set_value to replace. note (required) explains why. Human and agent corrections are
        stored separately from machine output and survive re-processing. Cannot change rights."""
        try:
            if not note.strip():
                raise ValueError("note is required")
            out = []
            for t in add or []:
                out.append(call(ctx, lib.correct, field, "add", t, shot_uid=shot_id, note=note)["correction_id"])
            for t in remove or []:
                out.append(call(ctx, lib.correct, field, "remove", t, shot_uid=shot_id, note=note)["correction_id"])
            if set_value is not None:
                out.append(call(ctx, lib.correct, field, "set", set_value, shot_uid=shot_id, note=note)["correction_id"])
            if not out:
                raise ValueError("give add, remove or set_value")
            rec = call(ctx, lib.get_shot, shot_id)
            return {"correction_ids": out, "field": rec["fields"].get(field)}
        except (Forbidden, NotFound, ValueError, KeyError) as e:
            _err(e)

    @server.resource("metachlorian://vocabularies/{name}", mime_type="application/json")
    def vocabulary_resource(name: str) -> str:
        import json

        return json.dumps(registry().get(name).as_dict())

    register_photos(server, lib, _principal, RO, EXPORT)
    return server


def run_stdio(lib: Library, token: str | None = None) -> None:
    import anyio

    if token:
        p = authenticate_token(lib.db, token, via="mcp")
        if p is None:
            raise SystemExit("METACHLORIAN_TOKEN is invalid or expired")
    else:
        # Local stdio without a token: read-only agent (agents are read-only by default).
        scopes = set(AGENT_DEFAULT)
        extra = [s.strip() for s in os.environ.get("METACHLORIAN_MCP_ALLOW", "").split(",") if s.strip()]
        allowed = {"media:export", "tags:write", "collections:write"}
        scopes |= {s for s in extra if s in allowed}
        p = Principal(None, "local-agent", "agent", scopes, "mcp")
    stdio_principal.set(p)
    server = build_server(lib)
    anyio.run(server.run_stdio_async)
