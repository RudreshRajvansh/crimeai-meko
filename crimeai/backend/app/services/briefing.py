"""
Daily station briefing.

A one-page brief for morning roll call: what happened in the last 24 hours,
where risk is rising, which shifts and districts the forecast flags, which
custody deadlines fall due this week, and which crime series are active. It
is generated once a day, stored as a PDF, and summarised as JSON for the UI.
"""
from __future__ import annotations

import io
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ml import registry
from app.repositories.crime_repository import CrimeRepository
from app.services.custody_clock import compute_deadline

BRIEFING = "daily_briefing"
OPEN_STATUSES = ("reported", "under_investigation")


async def build_briefing(db: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    repo = CrimeRepository(db)
    last_day = await repo.get_records(since=now - timedelta(hours=24))

    risk = await registry.latest(db, registry.RISK_SCORES)
    risk_rows = sorted((risk.as_json() if risk else {}).items(), key=lambda kv: kv[1]["score"], reverse=True)
    forecast = await registry.latest(db, registry.HOTSPOT_FORECAST)
    series = await registry.latest(db, registry.CRIME_SERIES)
    active_cutoff = (now - timedelta(days=14)).isoformat()

    deadlines = [compute_deadline(c, now) for c in await repo.custody_cases(OPEN_STATUSES)]
    return {
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "last_24h": {
            "total": len(last_day),
            "by_type": dict(Counter(r.crime_type for r in last_day).most_common(8)),
            "by_district": dict(Counter(r.district or "Unknown" for r in last_day).most_common(8)),
            "serious": sum(1 for r in last_day if r.severity >= 4),
        },
        "risk_watchlist": [
            {"district": d, "score": v["score"], "level": v["level"], "trend": v.get("trend")}
            for d, v in risk_rows[:6]
        ],
        "shift_forecast": [
            {"shift": block["shift"], "block_start": block["block_start"], "top": block["predictions"][:3]}
            for block in (forecast.as_json() if forecast else [])
        ],
        "custody_due_7d": [d.to_dict() for d in sorted(deadlines, key=lambda d: d.days_remaining) if d.days_remaining <= 7],
        "active_series": [s for s in (series.as_json() if series else []) if s["last_seen"] >= active_cutoff][:5],
    }


def render_pdf(brief: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Daily briefing {brief['date']}", topMargin=36, bottomMargin=36)

    def table(rows: list[list[Any]]) -> Table:
        t = Table(rows, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ]))
        return t

    story = [
        Paragraph(f"Daily Station Briefing: {brief['date']}", styles["Title"]),
        Paragraph(
            f"Last 24 hours: {brief['last_24h']['total']} incidents, {brief['last_24h']['serious']} serious (severity 4-5).",
            styles["Normal"],
        ),
        Spacer(1, 10),
        Paragraph("Risk watchlist", styles["Heading2"]),
        table([["District", "Index", "Level", "Trend"]] + [
            [r["district"], f"{r['score']:.0f}", r["level"], r["trend"] or "-"] for r in brief["risk_watchlist"]
        ]),
        Paragraph("Shift forecast (top districts per shift)", styles["Heading2"]),
        table([["Shift", "Districts (probability)"]] + [
            [s["shift"], ", ".join(f"{p['district']} ({p['probability']:.0%})" for p in s["top"])]
            for s in brief["shift_forecast"]
        ]),
        Paragraph("Custody deadlines due within 7 days", styles["Heading2"]),
        table([["Case", "District", "Deadline", "Days left"]] + [
            [d["case_number"] or d["crime_id"][:8], d["district"] or "-", d["deadline"][:10], d["days_remaining"]]
            for d in brief["custody_due_7d"]
        ]) if brief["custody_due_7d"] else Paragraph("None.", styles["Normal"]),
        Paragraph("Active crime series", styles["Heading2"]),
        table([["Series", "Type", "Incidents", "Areas", "Last seen"]] + [
            [s["series_id"], s["crime_type"], s["size"], ", ".join(s["districts"]) or "-", s["last_seen"][:10]]
            for s in brief["active_series"]
        ]) if brief["active_series"] else Paragraph("None detected.", styles["Normal"]),
        Spacer(1, 12),
        Paragraph(
            "Forecasts describe places and shifts, never individuals. Treat them as prompts for supervisory judgement.",
            styles["Italic"],
        ),
    ]
    doc.build(story)
    return buffer.getvalue()
