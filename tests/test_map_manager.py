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


# ---------------------------------------------------------------------------
# Task 2: CRUD — add/get nodes and edges
# ---------------------------------------------------------------------------

def test_add_and_get_node():
    mm = MapManager()
    mm.add_node("kitchen", "Kitchen", ["white cabinets"], "tile")
    node = mm.get_node("kitchen")
    assert node is not None
    assert node.label == "Kitchen"
    assert node.visit_count == 1


def test_get_node_missing():
    mm = MapManager()
    assert mm.get_node("nonexistent") is None


def test_add_node_increments_visit():
    mm = MapManager()
    mm.add_node("kitchen", "Kitchen", ["cabinets"], "tile")
    mm.add_node("kitchen", "Kitchen", ["cabinets"], "tile")
    assert mm.get_node("kitchen").visit_count == 2


def test_add_edge():
    mm = MapManager()
    mm.add_node("kitchen", "Kitchen", [], "tile")
    mm.add_node("hallway", "Hallway", [], "tile")
    crumbs = [{"left_speed": 190, "right_speed": 190,
               "left_dir": 1, "right_dir": 1, "duration_ms": 2000}]
    mm.add_edge("kitchen", "hallway", crumbs)
    neighbors = mm.get_neighbors("kitchen")
    assert "hallway" in neighbors


def test_get_neighbors_empty():
    mm = MapManager()
    mm.add_node("kitchen", "Kitchen", [], "tile")
    assert mm.get_neighbors("kitchen") == []


if __name__ == "__main__":
    test_map_node_creation()
    test_map_edge_creation()
    test_add_and_get_node()
    test_get_node_missing()
    test_add_node_increments_visit()
    test_add_edge()
    test_get_neighbors_empty()
    print("Tasks 1-2 tests passed!")
