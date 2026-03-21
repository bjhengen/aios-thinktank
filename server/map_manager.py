"""
Topological map manager for robot car navigation.

Stores a graph of rooms (nodes) connected by recorded motor command
sequences (edges). Persists to JSON for cross-session learning.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import deque

from shared.utils import setup_logging

logger = setup_logging(__name__)


@dataclass
class MapNode:
    """A room or area the car has visited."""
    id: str
    label: str
    landmarks: List[str] = field(default_factory=list)
    floor_type: str = "unknown"
    visit_count: int = 0
    last_visited: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label,
            "landmarks": self.landmarks, "floor_type": self.floor_type,
            "visit_count": self.visit_count, "last_visited": self.last_visited,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MapNode":
        return cls(**d)


@dataclass
class MapEdge:
    """A recorded transition between two rooms."""
    from_id: str
    to_id: str
    breadcrumb: List[dict] = field(default_factory=list)
    traversal_count: int = 0

    def to_dict(self) -> dict:
        return {
            "from": self.from_id, "to": self.to_id,
            "breadcrumb": self.breadcrumb,
            "traversal_count": self.traversal_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MapEdge":
        return cls(
            from_id=d["from"], to_id=d["to"],
            breadcrumb=d.get("breadcrumb", []),
            traversal_count=d.get("traversal_count", 0),
        )


class MapManager:
    """Manages the topological map graph."""

    def __init__(self, map_file: str = "./map_data.json"):
        self.map_file = map_file
        self.nodes: Dict[str, MapNode] = {}
        self.edges: List[MapEdge] = []

    def load(self) -> None:
        """Load map from JSON file. No-op if file doesn't exist."""
        try:
            with open(self.map_file, 'r') as f:
                data = json.load(f)
            self.nodes = {
                k: MapNode.from_dict(v)
                for k, v in data.get("nodes", {}).items()
            }
            self.edges = [
                MapEdge.from_dict(e)
                for e in data.get("edges", [])
            ]
            logger.info(f"Loaded map: {len(self.nodes)} nodes, {len(self.edges)} edges")
        except FileNotFoundError:
            logger.info(f"No map file found at {self.map_file}, starting fresh")
        except Exception as e:
            logger.error(f"Error loading map: {e}")

    def save(self) -> None:
        """Save map to JSON file."""
        data = {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
        }
        try:
            with open(self.map_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved map: {len(self.nodes)} nodes, {len(self.edges)} edges")
        except Exception as e:
            logger.error(f"Error saving map: {e}")

    def add_node(self, id: str, label: str,
                 landmarks: List[str] = None,
                 floor_type: str = "unknown") -> MapNode:
        """Add or update a node. Increments visit_count if it exists."""
        if id in self.nodes:
            self.nodes[id].visit_count += 1
            self.nodes[id].last_visited = time.strftime("%Y-%m-%dT%H:%M:%S")
            if landmarks:
                # Merge new landmarks
                existing = set(self.nodes[id].landmarks)
                for lm in landmarks:
                    existing.add(lm)
                self.nodes[id].landmarks = list(existing)
            return self.nodes[id]

        node = MapNode(
            id=id, label=label,
            landmarks=landmarks or [],
            floor_type=floor_type,
            visit_count=1,
            last_visited=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self.nodes[id] = node
        logger.info(f"New map node: {id} ({label})")
        return node

    def get_node(self, id: str) -> Optional[MapNode]:
        """Get a node by ID, or None if not found."""
        return self.nodes.get(id)

    def add_edge(self, from_id: str, to_id: str,
                 breadcrumb: List[dict]) -> MapEdge:
        """Record a transition between two nodes."""
        # Check if edge already exists, update breadcrumb
        for edge in self.edges:
            if edge.from_id == from_id and edge.to_id == to_id:
                edge.breadcrumb = breadcrumb  # Use latest recording
                edge.traversal_count += 1
                return edge

        edge = MapEdge(
            from_id=from_id, to_id=to_id,
            breadcrumb=breadcrumb, traversal_count=1,
        )
        self.edges.append(edge)
        logger.info(f"New map edge: {from_id} -> {to_id} ({len(breadcrumb)} commands)")
        return edge

    def get_neighbors(self, node_id: str) -> List[str]:
        """Get IDs of nodes reachable from this node."""
        return [e.to_id for e in self.edges if e.from_id == node_id]

    def get_known_locations(self) -> List[str]:
        """Get list of all known node IDs."""
        return list(self.nodes.keys())
