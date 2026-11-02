"""Photo tools registered on Metachlorian's existing MCP server."""
from __future__ import annotations

import base64
import json
from typing import Any

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, ImageContent, TextContent

from ..auth import Forbidden

INSTRUCTIONS = """
Photos: Codex/the connected agent is the editor; Metachlorian indexes locally and Lightroom renders.
Start Lightroom requests with get_photo_workflow_status. It verifies the connector, installed version, decoder
availability and your permissions. A copied plug-in folder does not mean Lightroom has loaded or connected it.
Use search_photos with person/date/folder filters, then get_photo and get_photo_previews to compare a shortlist.
Expand a burst with filters.burst_id and diverse=false. Prefer meaningful expressions and varied moments; never
treat closed eyes during laughter/sleep, wide aperture or a blurred background as automatic defects.
Inspect real images, not just scores. Previews do not prove original-resolution eye focus or RAW recovery.
For edits: get_photo_edit_context -> begin_photo_edits (virtual copies) -> get_photo_job -> apply_photo_edit ->
get_photo_job -> get_photo_previews for visual comparison -> finish_photo_edits with each reviewed_revision.
Use natural style unless creative changes were requested. The context includes available controls, units and
editing guidance. Only use advertised capabilities. Three refinement rounds per session; restore_photo_edit
can recover an earlier owned snapshot. Never claim a job succeeded until it is done and the render was inspected.
Folder-indexed photos are matched to existing Lightroom masters by path when inspected. If an import is needed,
begin_photo_edits imports only selected originals in place; read the new virtual copy's context for its controls.
If previews or editing are blocked, report the concrete reason and next step from workflow status/context.
Do not silently treat metadata-only search as visual selection or imply that a direct UI edit used Metachlorian.
Report the selected filename, virtual copy/session, visible changes, render review and any unverified detail.
Use stable idempotency keys for retries. Resume waiting jobs after Lightroom reconnects; conflicts require a fresh
context and a new request. Editing needs photos:edit; delivery also needs collections:write. Originals remain in place.
Use Streamable HTTP /mcp on the running desktop core so all agents share one Lightroom connection and queue.
"""


def register(server, lib, principal, ro, write):
    def call(ctx, method, *args, **kwargs):
        try:
            return getattr(lib.photos, method)(principal(lib, ctx), *args, **kwargs)
        except (ValueError, KeyError, Forbidden) as exc:
            raise ToolError(f'{type(exc).__name__}: {exc}') from exc

    @server.tool(annotations=ro)
    def get_photo_workflow_status(ctx: Context | None = None) -> dict:
        """Check Lightroom connection, version compatibility, RAW/HEIC support, indexing and agent scopes.
        Call this before photo editing and after a preview/connection failure. Does not edit/import photographs.
        """
        return call(ctx, 'check_connection')

    @server.tool(annotations=ro)
    def search_photos(query: str = '', filters: dict[str, Any] | None = None, limit: int = 40,
                      cursor: str | None = None, diverse: bool = True, ctx: Context | None = None) -> dict:
        """Find photographs. Filters: catalog_uid, folder, person_id/person, date_from/date_to (ISO),
        min_rating, camera, lens, burst_id, availability, collection, virtual_copies.
        Returns reasons and uncertainty. Diverse results represent separate bursts; inspect a burst separately.
        """
        return call(ctx, 'search', query, filters, limit, cursor, diverse)

    @server.tool(annotations=ro)
    def get_photo(photo_id: str, ctx: Context | None = None) -> dict:
        """Photo metadata, measured evidence, face regions, related variants and availability; no face embeddings leave."""
        return call(ctx, 'get', photo_id)

    @server.tool(annotations=ro)
    def get_photo_previews(photo_ids: list[str], edge: int = 1600, regions: dict[str, list[float]] | None = None,
                           native: bool = False, ctx: Context | None = None) -> CallToolResult:
        """Return actual JPEG image content for 1–8 photos. Regions are normalised [left,top,right,bottom]
        in the oriented rendered frame. native=true requires regions and accessible originals, and reports
        whether returned detail really is native resolution. Respect the reported source and uncertainty.
        """
        if not 1 <= len(photo_ids) <= 8:
            raise ToolError('Request 1 to 8 previews at a time')
        content = []
        for uid in photo_ids:
            data, info = call(ctx, 'preview', uid, edge, (regions or {}).get(uid), native)
            content.append(TextContent(type='text', text=json.dumps(info)))
            content.append(ImageContent(type='image', data=base64.b64encode(data).decode(), mimeType='image/jpeg'))
        return CallToolResult(content=content)

    @server.tool(annotations=ro)
    def get_photo_edit_context(photo_id: str, families: list[str] | None = None, ctx: Context | None = None) -> dict:
        """Current develop revision/settings, exact supported control ranges, capability limits and editing guidance.
        Read this before edits. Existing catalogue masters are matched by path, preserving their Lightroom look.
        For a file not yet in the catalogue, import_required means begin_photo_edits can import it in place;
        exact controls become available on the new virtual copy. A blocked workflow includes a reason.
        """
        return call(ctx, 'context', photo_id, families)

    @server.tool(annotations=write)
    def begin_photo_edits(photo_ids: list[str], expected_revisions: dict[str, str], idempotency_key: str,
                          brief: str = '', creative: bool = False, ctx: Context | None = None) -> dict:
        """Create recoverable virtual copies of 1–100 selected photos, preserving existing edits. Returns a job.
        expected_revisions maps each photo_id to the revision from get_photo_edit_context. creative defaults false.
        """
        return call(ctx, 'begin', photo_ids, expected_revisions, idempotency_key, brief, creative)

    @server.tool(annotations=write)
    def apply_photo_edit(session_id: str, expected_revision: str, operations: list[dict[str, Any]],
                         idempotency_key: str, ctx: Context | None = None) -> dict:
        """Apply validated operations to an owned virtual copy and render it. Returns a job, not a success claim.
        Operations: {op:'settings',values:{Exposure2012:0.3,...}},
        {op:'mask',type:'subject'|'sky'|'background',adjustments:{local_Exposure:0.2,...}},
        {op:'auto',tone:true,white_balance:false}. Only advertised capabilities are allowed. Inspect the result.
        """
        return call(ctx, 'apply', session_id, expected_revision, operations, idempotency_key)

    @server.tool(annotations=write)
    def restore_photo_edit(session_id: str, snapshot_id: str, expected_revision: str, idempotency_key: str,
                            ctx: Context | None = None) -> dict:
        """Restore a baseline/candidate snapshot belonging to this session, then freshly render it. Never global Undo."""
        return call(ctx, 'restore', session_id, snapshot_id, expected_revision, idempotency_key)

    @server.tool(annotations=write)
    def finish_photo_edits(selections: list[dict[str, str]], collection: str, idempotency_key: str,
                           ctx: Context | None = None) -> dict:
        """Save visually accepted virtual copies in a Lightroom collection under Metachlorian.
        selections: [{session_id, reviewed_revision}]. Requires photos:edit and collections:write.
        """
        return call(ctx, 'finish', selections, collection, idempotency_key)

    @server.tool(annotations=ro)
    def get_photo_job(job_id: str, ctx: Context | None = None) -> dict:
        """Read progress, per-photo results, revisions and recoverable failures for a photo job."""
        return call(ctx, 'job', job_id)

    @server.tool(annotations=write)
    def resume_photo_job(job_id: str, ctx: Context | None = None) -> dict:
        """Resume a waiting/interrupted job using its original operation IDs. Conflicts require a new plan."""
        return call(ctx, 'resume', job_id)

    @server.tool(annotations=write)
    def cancel_photo_job(job_id: str, ctx: Context | None = None) -> dict:
        """Stop at the next safe operation boundary. Owned virtual copies and recovery snapshots remain available."""
        return call(ctx, 'cancel', job_id)

    @server.resource('metachlorian://photos/editing-guide', mime_type='application/json')
    def editing_guide() -> str:
        from .controls import guidance
        return json.dumps(guidance())
