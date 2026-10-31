#!/usr/bin/env python3
"""Regenerate docs/API_ENDPOINTS.md from the live route table: `python scripts/generate_api_docs.py`."""
import os
import sys
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.routing import APIRoute, APIWebSocketRoute

from app.core.security import ROLE_HIERARCHY, UserRole
from app.main import app

OUT = Path(__file__).parents[2] / "docs" / "API_ENDPOINTS.md"


def _minimum_role(dependant) -> str:
    roles: list[UserRole] = []

    def walk(dep) -> None:
        for cell in getattr(dep.call, "__closure__", None) or ():
            if isinstance(cell.cell_contents, UserRole):
                roles.append(cell.cell_contents)
        if getattr(dep.call, "__name__", "") == "get_current_user":
            roles.append(UserRole.READONLY)
        for sub in dep.dependencies:
            walk(sub)

    walk(dependant)
    if not roles:
        return "public"
    return str(max(roles, key=lambda r: ROLE_HIERARCHY[r]))


def main() -> None:
    sections: dict[str, list[str]] = {}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.include_in_schema:
            tag = route.tags[0] if route.tags else "Platform"
            summary = route.summary or (route.description or "").strip().split("\n")[0] or route.name.replace("_", " ")
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                sections.setdefault(tag, []).append(
                    f"| `{method}` | `{route.path}` | {_minimum_role(route.dependant)} | {summary} |"
                )
        elif isinstance(route, APIWebSocketRoute):
            sections.setdefault("WebSockets", []).append(
                f"| `WS` | `{route.path}` | ticket | Alert stream; connect with `?ticket=` from `POST /auth/ws-ticket` |"
            )

    lines = [
        "# API endpoints",
        "",
        "Generated from the route table by `backend/scripts/generate_api_docs.py`; do not edit by hand.",
        "Roles are hierarchical: readonly < analyst < police < admin. Interactive docs: `/docs` (when enabled).",
        "",
    ]
    for tag, rows in sections.items():
        lines += [f"## {tag}", "", "| Method | Path | Minimum role | Purpose |", "|---|---|---|---|", *rows, ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
