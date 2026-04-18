"""File-scan rows for the upload→VT pipeline (§4.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.repositories.models import FileScan


class FileScanRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_sha256(self, sha256: str) -> FileScan | None:
        result = await self._s.execute(select(FileScan).where(FileScan.sha256 == sha256.lower()))
        return result.scalar_one_or_none()

    async def get(self, scan_id: UUID) -> FileScan | None:
        return await self._s.get(FileScan, scan_id)

    async def create(
        self,
        *,
        sha256: str,
        filename: str,
        size_bytes: int,
        uploaded_by: UUID | None = None,
    ) -> FileScan:
        row = FileScan(
            scan_id=uuid4(),
            sha256=sha256.lower(),
            filename=filename,
            size_bytes=size_bytes,
            uploaded_at=datetime.now(UTC),
            uploaded_by=uploaded_by,
            status="queued",
        )
        self._s.add(row)
        await self._s.flush()
        return row

    async def mark_complete(
        self,
        scan_id: UUID,
        *,
        vt_result: dict[str, Any],
        status: str = "complete",
    ) -> None:
        row = await self._s.get(FileScan, scan_id)
        if row is None:
            return
        row.vt_result = vt_result
        row.vt_scanned_at = datetime.now(UTC)
        row.status = status
        await self._s.flush()


__all__ = ["FileScanRepo"]
