"""Threat-intel endpoints (§4.3).

  GET  /threat-intel/iocs                          search the cache + on-demand lookup
  GET  /threat-intel/compromised-assets            reads compromised_assets_view
  POST /threat-intel/virustotal/scan               enqueue an Arq job; SSE result
  POST /threat-intel/files/scan                    multipart upload → SHA-256 → VT job

The routes use the same fall-through-to-empty pattern as the rest of the
API: when the DB session is None (unit-test sandbox), return empty/stub
responses instead of crashing.
"""

from __future__ import annotations

import hashlib
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.adapters.hibp_adapter import HibpAdapter
from strix_api.adapters.virustotal_adapter import VirusTotalAdapter
from strix_api.api.deps import SettingsDep, get_db_session
from strix_api.api.errors import StrixError
from strix_api.api.schemas.threat_intel import (
    CompromisedAsset,
    CompromisedAssetsResponse,
    FileScanResponse,
    IocItem,
    IocSearchResponse,
    JobAcceptedResponse,
    VtScanRequest,
)
from strix_api.observability import get_logger
from strix_api.repositories.file_scan_repo import FileScanRepo
from strix_api.repositories.ioc_repo import CompromisedAssetsRepo, IocRepo
from strix_api.services.threat_intel_service import (
    IocResult,
    ThreatIntelService,
    detect_indicator_type,
)

router = APIRouter(prefix="/threat-intel", tags=["threat-intel"])
log = get_logger("strix_api.api.routes.threat_intel")

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB cap per §5.12


class _BadRequestError(StrixError):
    status_code = 400
    title = "Bad Request"
    code = "BAD_REQUEST"


def _ioc_to_schema(r: IocResult) -> IocItem:
    return IocItem(
        indicator=r.indicator,
        type=r.indicator_type,
        reputation=r.reputation,
        source=r.source,
        last_checked=r.last_checked.isoformat(timespec="microseconds"),
        breach_count=r.breach_count,
        stale=r.stale,
        payload=r.payload,
    )


# ---- IOC search / lookup ---------------------------------------


@router.get(
    "/iocs",
    response_model=IocSearchResponse,
    summary="Search the IOC cache, with on-demand HIBP/VT lookup when q is exact",
)
async def search_iocs(
    settings: SettingsDep,
    q: str | None = Query(None),
    type: str | None = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> IocSearchResponse:
    if session is None:
        return IocSearchResponse(items=[], total=0, page=page, limit=limit)

    ioc_repo = IocRepo(session)
    hibp = HibpAdapter(settings.threat_intel)
    vt = VirusTotalAdapter(settings.threat_intel)
    service = ThreatIntelService(
        ioc_repo=ioc_repo,
        hibp=hibp,
        virustotal=vt,
        compromised=CompromisedAssetsRepo(session),
    )

    # If `q` looks like an exact indicator, do the live lookup (which
    # populates the cache as a side-effect). Otherwise return paginated
    # cache contents.
    if q and detect_indicator_type(q):
        try:
            result = await service.lookup(q, indicator_type=type)
            return IocSearchResponse(
                items=[_ioc_to_schema(result)],
                total=1,
                page=1,
                limit=1,
            )
        except StrixError:
            # Adapter explicitly raised — fall through to a cache-only search.
            pass
        finally:
            await hibp.aclose()
            await vt.aclose()

    rows, total = await service.search(query=q, indicator_type=type, page=page, limit=limit)
    await hibp.aclose()
    await vt.aclose()
    return IocSearchResponse(
        items=[_ioc_to_schema(r) for r in rows],
        total=total,
        page=page,
        limit=limit,
    )


# ---- compromised assets ----------------------------------------


@router.get(
    "/compromised-assets",
    response_model=CompromisedAssetsResponse,
)
async def compromised_assets(
    limit: int = Query(100, ge=1, le=500),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> CompromisedAssetsResponse:
    if session is None:
        return CompromisedAssetsResponse(items=[])
    rows = await CompromisedAssetsRepo(session).list(limit=limit)
    items = [
        CompromisedAsset(
            host_id=r["host_id"],
            agent_name=r.get("agent_name"),
            ip_address=str(r["ip_address"]) if r.get("ip_address") else None,
            last_seen_at=r["last_seen_at"].isoformat() if r.get("last_seen_at") else None,
            last_detection_at=r["last_detection_at"].isoformat()
            if r.get("last_detection_at")
            else None,
            detection_count=int(r.get("detection_count", 0)),
            max_vae_prob=r.get("max_vae_prob"),
            max_gnn_risk=r.get("max_gnn_risk"),
            last_action_int=r.get("max_action_int"),
        )
        for r in rows
    ]
    return CompromisedAssetsResponse(items=items)


# ---- on-demand VT scan -----------------------------------------


@router.post(
    "/virustotal/scan",
    response_model=JobAcceptedResponse,
    status_code=202,
)
async def virustotal_scan(
    body: VtScanRequest,
    settings: SettingsDep,
) -> JobAcceptedResponse:
    """Enqueue an Arq job. Result is pushed to SSE channel `strix:sse:job:{job_id}`."""
    sniffed = body.type or detect_indicator_type(body.indicator)
    if sniffed is None:
        raise _BadRequestError(f"unrecognized indicator: {body.indicator!r}")
    if sniffed == "email":
        raise _BadRequestError("email lookups go through HIBP, not VT")

    job_id = uuid4()
    try:
        from arq import create_pool

        from strix_api.workers.arq_tasks import _redis_settings_from

        pool = await create_pool(_redis_settings_from(settings))
        try:
            await pool.enqueue_job(
                "on_demand_vt_scan",
                job_id=str(job_id),
                indicator=body.indicator,
                indicator_type=sniffed,
            )
        finally:
            await pool.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("vt_scan_enqueue_failed", exc_info=exc)
        # Non-fatal — return the jobId so the UI can still subscribe to the SSE
        # channel (it'll never receive the completion event, which the UI
        # surfaces as a soft failure after a timeout).

    return JobAcceptedResponse(job_id=job_id, status="queued")


# ---- file upload scan ------------------------------------------


@router.post(
    "/files/scan",
    response_model=FileScanResponse,
    status_code=202,
)
async def file_scan_upload(
    settings: SettingsDep,
    file: UploadFile = File(...),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> FileScanResponse:
    """Compute SHA-256 of the uploaded file, persist a `file_scans` row,
    enqueue the VT lookup. Result pushed to `strix:sse:job:{scan_id}`."""
    contents = await file.read()
    if not contents:
        raise _BadRequestError("uploaded file is empty")
    if len(contents) > _MAX_UPLOAD_BYTES:
        raise _BadRequestError(f"upload too large ({len(contents)} bytes > {_MAX_UPLOAD_BYTES})")
    sha256 = hashlib.sha256(contents).hexdigest()

    if session is None:
        # Unit-test path — return a synthetic accepted response.
        return FileScanResponse(
            scan_id=uuid4(),
            sha256=sha256,
            size_bytes=len(contents),
            status="queued",
            filename=file.filename or "upload",
        )

    repo = FileScanRepo(session)
    existing = await repo.get_by_sha256(sha256)
    if existing is not None and existing.status in ("complete", "scanning"):
        return FileScanResponse(
            scan_id=existing.scan_id,
            sha256=sha256,
            size_bytes=existing.size_bytes,
            status=existing.status,
            filename=existing.filename,
        )

    row = await repo.create(
        sha256=sha256,
        filename=file.filename or "upload",
        size_bytes=len(contents),
    )

    try:
        from arq import create_pool

        from strix_api.workers.arq_tasks import _redis_settings_from

        pool = await create_pool(_redis_settings_from(settings))
        try:
            await pool.enqueue_job(
                "file_scan",
                job_id=str(row.scan_id),
                scan_id=str(row.scan_id),
                sha256=sha256,
            )
        finally:
            await pool.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("file_scan_enqueue_failed", exc_info=exc)

    return FileScanResponse(
        scan_id=row.scan_id,
        sha256=sha256,
        size_bytes=len(contents),
        status="queued",
        filename=row.filename,
    )
