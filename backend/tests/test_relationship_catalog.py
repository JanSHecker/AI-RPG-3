import json

import pytest

from relationship_catalog import (
    load_primary_relationship_catalog,
    load_relationship_catalog,
    load_secondary_relationship_catalog,
)
from world_generation.schemas import PRIMARY_RELATIONSHIP_TYPES, RELATIONSHIP_TYPES, SECONDARY_RELATIONSHIP_TYPES


def test_relationship_catalog_loads_primary_secondary_and_combined_views():
    primary = load_primary_relationship_catalog()
    secondary = load_secondary_relationship_catalog()
    combined = load_relationship_catalog()

    assert primary
    assert secondary
    assert combined == [*primary, *secondary]
    assert set(primary).isdisjoint(secondary)


def test_relationship_schema_exports_match_catalog_views():
    assert PRIMARY_RELATIONSHIP_TYPES
    assert SECONDARY_RELATIONSHIP_TYPES
    assert RELATIONSHIP_TYPES == [*PRIMARY_RELATIONSHIP_TYPES, *SECONDARY_RELATIONSHIP_TYPES]


def test_relationship_catalog_rejects_duplicate_entries(tmp_path):
    primary_path = tmp_path / "primary.json"
    secondary_path = tmp_path / "secondary.json"
    primary_path.write_text(json.dumps(["parent", "parent"]), encoding="utf-8")
    secondary_path.write_text(json.dumps(["alliance"]), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate relationship type"):
        load_relationship_catalog(primary_path, secondary_path)


def test_relationship_catalog_rejects_overlapping_categories(tmp_path):
    primary_path = tmp_path / "primary.json"
    secondary_path = tmp_path / "secondary.json"
    primary_path.write_text(json.dumps(["parent"]), encoding="utf-8")
    secondary_path.write_text(json.dumps(["parent"]), encoding="utf-8")

    with pytest.raises(ValueError, match="must not overlap"):
        load_relationship_catalog(primary_path, secondary_path)
