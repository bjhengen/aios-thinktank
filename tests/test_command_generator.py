"""
Tests for CommandGenerator — LOCATION parsing and map-aware prompt building.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.command_generator import CommandGenerator


def test_parse_location_from_response():
    cg = CommandGenerator()
    response = """OBSERVATION: White cabinets, island, tile floor
ASSESSMENT: Clear path
LOCATION: kitchen
COMMAND: 190,190,1,1,2000
REASONING: Moving forward"""
    parsed = cg.parse_response(response)
    assert parsed.location == "kitchen"
    assert parsed.command is not None


def test_parse_location_unknown():
    cg = CommandGenerator()
    response = """OBSERVATION: Unfamiliar room
ASSESSMENT: New area
LOCATION: unknown
COMMAND: 0,0,2,2,0
REASONING: Stopping to identify"""
    parsed = cg.parse_response(response)
    assert parsed.location == "unknown"


def test_parse_no_location():
    cg = CommandGenerator()
    response = """OBSERVATION: Floor ahead
ASSESSMENT: Clear
COMMAND: 190,190,1,1,2000
REASONING: Forward"""
    parsed = cg.parse_response(response)
    assert parsed.location == ""


def test_prompt_includes_known_locations():
    cg = CommandGenerator()
    known = ["office", "hallway", "kitchen"]
    prompt = cg.build_prompt("Explore", known_locations=known)
    assert "LOCATION:" in prompt
    assert "office" in prompt
    assert "hallway" in prompt
    assert "kitchen" in prompt
    assert "unknown" in prompt.lower()


def test_prompt_without_locations():
    cg = CommandGenerator()
    prompt = cg.build_prompt("Explore")
    # Should not include LOCATION section when no locations known
    assert "KNOWN LOCATIONS:" not in prompt
