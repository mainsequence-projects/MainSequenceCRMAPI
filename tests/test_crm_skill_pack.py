"""Keep the authored MCP usage pack complete as the actual catalogue evolves."""

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

from api.crm.mcp_tools import build_crm_tools

PACK = Path(__file__).resolve().parents[1] / ".agents/skills/mainsequence_crm"
ALLOCATION = json.loads((PACK / "crm-core/references/tool-map.json").read_text())["skills"]


@pytest.mark.parametrize("solution_selling", [True, False])
def test_every_advertised_tool_has_one_primary_skill(config_file, solution_selling):
    config_file(solution_selling=solution_selling)
    catalogue = {tool.definition.name for tool in build_crm_tools(lambda: None)}
    allocated = [
        name
        for skill, names in ALLOCATION.items()
        if solution_selling or not skill.startswith("solution-selling/")
        for name in names
    ]
    duplicates = {name for name, count in Counter(allocated).items() if count != 1}
    assert not duplicates, f"Tools assigned to multiple primary skills: {duplicates}"
    assert set(allocated) == catalogue, {
        "missing": sorted(catalogue - set(allocated)),
        "unadvertised": sorted(set(allocated) - catalogue),
    }


def test_skill_pack_contains_resolvable_guidance_for_its_tools(config_file):
    catalogue = {tool.definition.name for tool in build_crm_tools(lambda: None)}
    skill_files = set(PACK.rglob("SKILL.md"))
    assert skill_files == {PACK / skill / "SKILL.md" for skill in ALLOCATION}
    for skill, names in ALLOCATION.items():
        path = PACK / skill / "SKILL.md"
        text = path.read_text()
        frontmatter = yaml.safe_load(text.split("---", 2)[1])
        assert frontmatter["name"] == path.parent.name
        assert frontmatter["description"].strip()
        # A manifest entry alone is insufficient: its owning skill must explain
        # which concrete tools to select, without inventing new operations.
        mentioned = set(re.findall(r"`(crm_[a-z_]+)`", text))
        assert set(names) <= mentioned, (skill, set(names) - mentioned)
        assert mentioned <= catalogue, (skill, mentioned - catalogue)

    for path in PACK.rglob("*.md"):
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text()):
            if target.startswith("skill://"):
                uri = urlparse(target)
                destination = (PACK / uri.netloc / uri.path.lstrip("/")).resolve()
            else:
                destination = (path.parent / target.split("#", 1)[0]).resolve()
            assert destination.is_relative_to(PACK), (path, target)
            assert destination.is_file(), (path, target)
