"""Photo routes. Authentication/CSRF are supplied by the existing application."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field


class SearchBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = ''
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=40, ge=1, le=100)
    cursor: str | None = None
    diverse: bool = True


class BeginBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    photo_ids: list[str] = Field(min_length=1, max_length=100)
    expected_revisions: dict[str, str]
    idempotency_key: str = Field(min_length=1, max_length=200)
    brief: str = Field(default='', max_length=4000)
    creative: bool = False


class ApplyBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: str
    operations: list[dict[str, Any]] = Field(min_length=1, max_length=12)
    idempotency_key: str = Field(min_length=1, max_length=200)


class FinishBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selections: list[dict[str, str]] = Field(min_length=1, max_length=100)
    collection: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


def router(lib, principal) -> APIRouter:
    r = APIRouter(prefix='/api/photos', tags=['photos'])

    @r.get('/status')
    def status(p=Depends(principal)):
        return lib.photos.status(p)

    @r.post('/connector/install')
    def install(p=Depends(principal)):
        return lib.photos.install_connector(p)

    @r.post('/sources/folder')
    def folder(body: dict = Body(...), p=Depends(principal)):
        return lib.photos.scan_folder(p, body['path'], body['idempotency_key'])

    @r.post('/sources/lightroom')
    def sync(body: dict = Body(...), p=Depends(principal)):
        return lib.photos.sync_catalog(p, body['idempotency_key'])

    @r.post('/analyse')
    def analyse(body: dict = Body(...), p=Depends(principal)):
        return lib.photos.analyse_pending(p, body['idempotency_key'])

    @r.post('/models/install')
    def install_models(body: dict = Body(...), p=Depends(principal)):
        return lib.photos.install_models(p, body['idempotency_key'])

    @r.post('/search')
    def search(body: SearchBody, p=Depends(principal)):
        return lib.photos.search(p, body.query, body.filters, body.limit, body.cursor, body.diverse)

    @r.get('/jobs')
    def jobs(p=Depends(principal)):
        return {'jobs': lib.photos.list_jobs(p)}

    @r.get('/jobs/{uid}')
    def job(uid: str, p=Depends(principal)):
        return lib.photos.job(p, uid)

    @r.post('/jobs/{uid}/cancel')
    def cancel(uid: str, p=Depends(principal)):
        return lib.photos.cancel(p, uid)

    @r.post('/jobs/{uid}/resume')
    def resume(uid: str, p=Depends(principal)):
        return lib.photos.resume(p, uid)

    @r.post('/edits')
    def begin(body: BeginBody, p=Depends(principal)):
        return lib.photos.begin(p, body.photo_ids, body.expected_revisions, body.idempotency_key, body.brief, body.creative)

    @r.post('/edits/finish')
    def finish(body: FinishBody, p=Depends(principal)):
        return lib.photos.finish(p, body.selections, body.collection, body.idempotency_key)

    @r.post('/edits/{session_id}/apply')
    def apply(session_id: str, body: ApplyBody, p=Depends(principal)):
        return lib.photos.apply(p, session_id, body.expected_revision, body.operations, body.idempotency_key)

    @r.post('/edits/{session_id}/restore')
    def restore(session_id: str, body: dict = Body(...), p=Depends(principal)):
        return lib.photos.restore(p, session_id, body['snapshot_id'], body['expected_revision'], body['idempotency_key'])

    @r.post('/faces/{face_id}/name')
    def name_face(face_id: int, body: dict = Body(...), p=Depends(principal)):
        return lib.photos.name_face(p, face_id, body['name'])

    @r.post('/faces/{face_id}/move')
    def move_face(face_id: int, body: dict = Body(...), p=Depends(principal)):
        return lib.photos.move_face(p, face_id, body.get('identity_id'))

    @r.get('/{uid}/context')
    def context(uid: str, families: list[str] | None = Query(None), p=Depends(principal)):
        return lib.photos.context(p, uid, families)

    @r.get('/{uid}/preview')
    def preview(uid: str, edge: int = Query(1600, ge=64, le=2048), region: str | None = None, native: bool = False,
                fresh: bool = False, revision: str | None = None, p=Depends(principal)):
        box = [float(x) for x in region.split(',')] if region else None
        data, info = lib.photos.preview(p, uid, edge, box, native, fresh, revision)
        return Response(data, media_type='image/jpeg', headers={'Cache-Control': 'no-store', 'X-Photo-Revision': info['revision'],
                        'X-Photo-Provenance': json.dumps(info['provenance'], ensure_ascii=True)})

    @r.post('/{uid}/feedback')
    def feedback(uid: str, body: dict = Body(...), p=Depends(principal)):
        return lib.photos.feedback(p, uid, body.get('favourite'), body.get('note', ''))

    @r.get('/{uid}')
    def get(uid: str, p=Depends(principal)):
        return lib.photos.get(p, uid)

    return r
