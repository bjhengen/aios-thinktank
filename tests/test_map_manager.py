#!/usr/bin/env python3
"""
Unit tests for MapManager — topological map data model, CRUD, persistence, and pathfinding.
"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.map_manager import MapManager, MapNode, MapEdge


# ---------------------------------------------------------------------------
# Task 1: Data Model
# ---------------------------------------------------------------------------

def test_map_node_creation():
    node = MapNode(id="kitchen", label="Kitchen",
                   landmarks=["white cabinets", "island"],
                   floor_type="tile")
    assert node.id == "kitchen"
    assert node.visit_count == 0
    assert "island" in node.landmarks


def test_map_edge_creation():
    breadcrumb = [
        {"left_speed": 190, "right_speed": 190, "left_dir": 1,
         "right_dir": 1, "duration_ms": 2000}
    ]
    edge = MapEdge(from_id="kitchen", to_id="hallway",
                   breadcrumb=breadcrumb)
    assert edge.from_id == "kitchen"
    assert edge.traversal_count == 0
    assert len(edge.breadcrumb) == 1


if __name__ == "__main__":
    test_map_node_creation()
    test_map_edge_creation()
    print("Task 1 tests passed!")
