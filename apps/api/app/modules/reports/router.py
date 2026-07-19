"""Router FastAPI para reportes (Fase 8).

Endpoints:
- ``GET /api/v1/reports/ejecutivo``             — snapshot con KPIs (JSON).
- ``GET /api/v1/reports/inventario``            — placeholder (Fase 6 ya
  expone ``/inventory/stock``; este endpoint existe para que el
  front pueda consumirlo si quiere un export independiente).
- ``GET /api/v1/reports/transferencias``        — placeholder (similar).
- ``GET /api/v1/reports/historial``             — placeholder (similar).

El PDF del reporte ejecutivo se genera en el cliente con ``jsPDF`` (~50KB),
evitando dependencia server-side (decision documentada en fase-8).
"""
from __future__ import annotations

from app.db.session import get_session
from app.modules.auth.router import get_current_user
from app.modules.reports.schemas import EjecutivoSnapshot
from app.modules.reports.service import ReportService, TOP_N_DEFAULT
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_report_service(
    session: AsyncSession = Depends(get_session),
) -> ReportService:
    return ReportService(session)


@router.get("/ejecutivo", response_model=EjecutivoSnapshot)
async def get_ejecutivo(
    top_n: int = Query(
        default=TOP_N_DEFAULT,
        ge=1,
        le=20,
        description="Cantidad de items en los rankings (mas/menos movidos).",
    ),
    _user=Depends(get_current_user),
    service: ReportService = Depends(get_report_service),
) -> EjecutivoSnapshot:
    """Snapshot ejecutivo: KPIs agregados, rankings, valor por bodega.

    El calculo es en SQL (no itera filas en Python). Pensado para ejecutarse
    en <100ms con 100k stock_levels.
    """
    return await service.get_ejecutivo_snapshot(top_n=top_n)


@router.get("/inventario")
async def get_reporte_inventario(
    _user=Depends(get_current_user),
) -> dict[str, str]:
    """Placeholder: el export CSV de inventario se hace client-side con
    ``downloadCsv`` desde ``/inventory/stock``. Este endpoint existe solo
    para que el front tenga un URL canonico si quiere.
    """
    return {
        "format": "csv",
        "endpoint_recomendado": "/api/v1/inventory/stock",
        "note": "El front debe consumir /inventory/stock y aplicar downloadCsv() con las columnas deseadas.",
    }


@router.get("/transferencias")
async def get_reporte_transferencias(
    _user=Depends(get_current_user),
) -> dict[str, str]:
    """Placeholder: el export de transferencias se hace client-side."""
    return {
        "format": "csv",
        "endpoint_recomendado": "/api/v1/solicitudes",
        "note": "El front debe consumir /solicitudes?estado=in_transit,partially_received y aplicar downloadCsv().",
    }


@router.get("/historial")
async def get_reporte_historial(
    _user=Depends(get_current_user),
) -> dict[str, str]:
    """Placeholder: el historial esta en ``/inventory/movements``."""
    return {
        "format": "csv",
        "endpoint_recomendado": "/api/v1/inventory/movements",
        "note": "El front debe consumir /inventory/movements y aplicar downloadCsv() con filtros.",
    }
