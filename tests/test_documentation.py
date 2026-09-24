"""Keep the hand-maintained MkDocs route index aligned with mounted FastAPI routes."""

import re
from pathlib import Path

from api.crm.main import create_app

INDEX = Path(__file__).resolve().parents[1] / "docs/api/route-index.md"
ROUTE_ROW = re.compile(r"^\| `(GET|POST|PUT|PATCH|DELETE)` \| `([^`]+)` \|")


def test_documented_route_index_matches_openapi():
    documented = {
        (match.group(1).lower(), match.group(2))
        for line in INDEX.read_text().splitlines()
        if (match := ROUTE_ROW.match(line))
    }
    mounted = {
        (method, path)
        for path, methods in create_app().openapi()["paths"].items()
        for method in methods
    }
    assert documented == mounted
