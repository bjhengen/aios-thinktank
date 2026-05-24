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
    assert "KNOWN LOCATIONS:" in prompt
    assert "office" in prompt
    assert "hallway" in prompt
    assert "kitchen" in prompt


def test_prompt_allows_proposing_new_location_name():
    cg = CommandGenerator()
    prompt = cg.build_prompt("Explore", known_locations=["office"])
    # Prompt should explicitly invite proposing a new name when in a new area
    assert "propose" in prompt.lower()
    # And should keep 'unknown' as a fallback for genuine uncertainty
    assert "unknown" in prompt.lower()


def test_prompt_without_known_locations_omits_section():
    cg = CommandGenerator()
    prompt = cg.build_prompt("Explore")
    assert "KNOWN LOCATIONS:" not in prompt


def test_validate_location_accepts_simple_names():
    from server.command_generator import is_valid_location_name
    for name in ["office", "kitchen", "bedroom2", "guest_room", "a"]:
        assert is_valid_location_name(name), f"should accept {name!r}"


def test_validate_location_rejects_garbage():
    from server.command_generator import is_valid_location_name
    bad = [
        "",
        "Office",                # uppercase
        "1room",                 # starts with digit
        "room with spaces",
        "a-b",                   # hyphen
        "room!",                 # punctuation
        "x" * 20,                # too long (>16 chars)
    ]
    for name in bad:
        assert not is_valid_location_name(name), f"should reject {name!r}"


if __name__ == "__main__":
    test_parse_location_from_response()
    test_parse_location_unknown()
    test_parse_no_location()
    test_prompt_includes_known_locations()
    test_prompt_allows_proposing_new_location_name()
    test_prompt_without_known_locations_omits_section()
    test_validate_location_accepts_simple_names()
    test_validate_location_rejects_garbage()
    print("All command generator tests passed!")
