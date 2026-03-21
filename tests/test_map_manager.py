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


# ---------------------------------------------------------------------------
# Task 3: Persistence — save and load
# ---------------------------------------------------------------------------

def test_save_and_load():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        mm = MapManager(map_file=path)
        mm.add_node("kitchen", "Kitchen", ["cabinets"], "tile")
        mm.add_node("hallway", "Hallway", ["mirror"], "tile")
        mm.add_edge("kitchen", "hallway",
                    [{"left_speed": 190, "right_speed": 190,
                      "left_dir": 1, "right_dir": 1, "duration_ms": 2000}])
        mm.save()

        # Load into fresh instance
        mm2 = MapManager(map_file=path)
        mm2.load()
        assert mm2.get_node("kitchen") is not None
        assert mm2.get_node("kitchen").label == "Kitchen"
        assert mm2.get_neighbors("kitchen") == ["hallway"]
    finally:
        os.unlink(path)


def test_load_missing_file():
    mm = MapManager(map_file="/tmp/nonexistent_robotcar_map.json")
    mm.load()  # Should not raise
    assert len(mm.nodes) == 0


# ---------------------------------------------------------------------------
# Task 4: BFS Pathfinding and Breadcrumb Reversal
# ---------------------------------------------------------------------------

def test_get_path_direct():
    mm = MapManager()
    mm.add_node("a", "A", [], "tile")
    mm.add_node("b", "B", [], "tile")
    crumbs = [{"left_speed": 190, "right_speed": 190,
               "left_dir": 1, "right_dir": 1, "duration_ms": 2000}]
    mm.add_edge("a", "b", crumbs)
    path = mm.get_path("a", "b")
    assert len(path) == 1
    assert path[0].from_id == "a"
    assert path[0].to_id == "b"


def test_get_path_multi_hop():
    mm = MapManager()
    for n in ["a", "b", "c"]:
        mm.add_node(n, n.upper(), [], "tile")
    mm.add_edge("a", "b", [{"left_speed": 190, "right_speed": 190,
                             "left_dir": 1, "right_dir": 1, "duration_ms": 1000}])
    mm.add_edge("b", "c", [{"left_speed": 190, "right_speed": 190,
                             "left_dir": 1, "right_dir": 1, "duration_ms": 1000}])
    path = mm.get_path("a", "c")
    assert len(path) == 2
    assert path[0].to_id == "b"
    assert path[1].to_id == "c"


def test_get_path_no_route():
    mm = MapManager()
    mm.add_node("a", "A", [], "tile")
    mm.add_node("b", "B", [], "tile")
    path = mm.get_path("a", "b")
    assert path is None


def test_reverse_breadcrumb():
    mm = MapManager()
    crumbs = [
        {"left_speed": 190, "right_speed": 190,
         "left_dir": 1, "right_dir": 1, "duration_ms": 2000},
        {"left_speed": 230, "right_speed": 230,
         "left_dir": 0, "right_dir": 1, "duration_ms": 1250},
    ]
    reversed_crumbs = mm.get_reverse_breadcrumb(crumbs)
    # Reversed order, directions flipped (1->0, 0->1, 2->2)
    assert len(reversed_crumbs) == 2
    # Second original command becomes first reversed
    assert reversed_crumbs[0]["left_dir"] == 1   # was 0
    assert reversed_crumbs[0]["right_dir"] == 0  # was 1
    # First original command becomes second reversed
    assert reversed_crumbs[1]["left_dir"] == 0   # was 1
    assert reversed_crumbs[1]["right_dir"] == 0  # was 1


if __name__ == "__main__":
    test_map_node_creation()
    test_map_edge_creation()
    test_add_and_get_node()
    test_get_node_missing()
    test_add_node_increments_visit()
    test_add_edge()
    test_get_neighbors_empty()
    test_save_and_load()
    test_load_missing_file()
    test_get_path_direct()
    test_get_path_multi_hop()
    test_get_path_no_route()
    test_reverse_breadcrumb()
    print("All map manager tests passed!")
