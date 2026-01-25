#!/bin/bash
# Helper script to run various tests

set -e

echo "================================"
echo "AI Car Control - Test Suite"
echo "================================"
echo ""

# Check if we're in the right directory
if [ ! -f "shared/protocol.py" ]; then
    echo "Error: Run this script from the robotcar directory"
    exit 1
fi

# Function to run a test
run_test() {
    echo "→ Running: $1"
    echo "---"
    $2
    echo ""
    echo "✓ $1 completed"
    echo ""
}

# Test 1: Protocol tests
run_test "Protocol Unit Tests" "python tests/test_protocol.py"

# Test 2: Import checks
run_test "Import Checks" "python -c 'import shared.protocol; import server.config; print(\"All imports successful\")'"

# Test 3: Config validation
run_test "Config Validation" "python -c 'from server.config import config; from pi.config import config as pi_config; print(f\"Server port: {config.port}\"); print(f\"Pi will connect to: {pi_config.server_host}:{pi_config.server_port}\")'"

echo "================================"
echo "All basic tests passed!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Test simulated car:"
echo "   Terminal 1: python -m server.server_control --manual"
echo "   Terminal 2: python tests/simulate_car.py"
echo ""
echo "2. When hardware is ready:"
echo "   On Pi: python3 -m pi.car_hardware --test-camera"
echo "   On Pi: python3 -m pi.car_hardware --test-motors"
echo ""
