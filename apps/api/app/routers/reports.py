from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission
from ..services.reports import (
    ReportGenerationError,
    compile_report_snapshot,
    fallback_report_narrative,
    generate_report_narrative,
)


router = APIRouter(prefix="/workspaces/{workspace_id}/reports", tags=["reports"])


def _parse_date_or_400(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be YYYY-MM-DD") from exc


def _workspace_or_404(db: MongoStore, workspace_id: int):
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def _report_summary_out(report) -> schemas.ReportSummaryOut:
    return schemas.ReportSummaryOut(
        id=report.id,
        workspace_id=report.workspace_id,
        title=report.title,
        period_start=report.period_start,
        period_end=report.period_end,
        period_label=report.get("period_label"),
        status=report.get("status", "pending"),
        overall_score=report.get("overall_score"),
        overall_grade=report.get("overall_grade"),
        generated_at=report.get("generated_at"),
        pdf_url=report.get("pdf_url"),
        created_at=report.created_at,
    )


def _report_detail_out(report) -> schemas.ReportDetailOut:
    narrative = report.get("ai_narrative") or None
    return schemas.ReportDetailOut(
        **_report_summary_out(report).model_dump(),
        enabled_categories=report.get("enabled_categories", []),
        context_notes=report.get("context_notes"),
        generation_error=report.get("generation_error"),
        data_snapshot=report.get("data_snapshot", []),
        ai_narrative=narrative,
    )


@router.get("", response_model=list[schemas.ReportSummaryOut])
def list_reports(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("reports.view")),
):
    _workspace_or_404(db, workspace_id)
    reports = db.find_many("reports", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])
    return [_report_summary_out(report) for report in reports]


@router.get("/{report_id}", response_model=schemas.ReportDetailOut)
def get_report(
    workspace_id: int,
    report_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("reports.view")),
):
    report = db.find_one("reports", {"id": report_id, "workspace_id": workspace_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_detail_out(report)


@router.post("/generate", response_model=schemas.ReportDetailOut, status_code=201)
def generate_report(
    workspace_id: int,
    payload: schemas.ReportGenerateRequest,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("reports.generate")),
):
    workspace = _workspace_or_404(db, workspace_id)
    period_start = _parse_date_or_400(payload.period_start, "period_start")
    period_end = _parse_date_or_400(payload.period_end, "period_end")
    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end must be on or after period_start")

    report = db.insert(
        "reports",
        {
            "workspace_id": workspace_id,
            "title": payload.title.strip(),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "period_label": payload.period_label.strip() if payload.period_label else None,
            "status": "generating",
            "generated_by": membership.id,
            "enabled_categories": payload.enabled_categories,
            "context_notes": payload.context_notes.strip() if payload.context_notes else None,
            "generated_at": None,
            "pdf_url": None,
            "ai_narrative": None,
            "data_snapshot": [],
            "overall_score": None,
            "overall_grade": None,
            "generation_error": None,
        },
    )

    try:
        snapshot = compile_report_snapshot(
            db,
            workspace=workspace,
            period_start=period_start,
            period_end=period_end,
            enabled_categories=payload.enabled_categories,
        )
    except Exception as exc:
        report["status"] = "failed"
        report["generation_error"] = str(exc)[:240]
        report = db.save("reports", report)
        return _report_detail_out(report)

    generation_error = None
    try:
        narrative = generate_report_narrative(snapshot, payload.context_notes)
    except ReportGenerationError as exc:
        generation_error = str(exc)[:240]
        narrative = fallback_report_narrative(snapshot, payload.context_notes)

    report["status"] = "complete"
    report["period_label"] = payload.period_label.strip() if payload.period_label else snapshot["period"]["label"]
    report["data_snapshot"] = snapshot["categories"]
    report["ai_narrative"] = narrative
    report["overall_score"] = snapshot["overall_score"]
    report["overall_grade"] = snapshot["overall_grade"]
    report["generated_at"] = datetime.utcnow()
    report["generation_error"] = generation_error
    report = db.save("reports", report)
    return _report_detail_out(report)
