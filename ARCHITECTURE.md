# System Architecture

This document provides a detailed overview of how the AI Car Control System works.

## Design Philosophy

The core idea is to test whether AI can control hardware directly with minimal overhead. The key principles are:

1. **AI does all the thinking** - Server handles all intelligence and decision-making
2. **Pi is a "dumb" proxy** - Minimal code, just hardware interfacing
3. **Vision-only navigation** - No distance sensors, AI learns from camera
4. **Low-latency communication** - Target <200ms end-to-end
5. **Natural language goals** - Human gives high-level instructions

## System Components

### Server Side (AI Brain)

#### 1. Vision Model ([server/vision_model.py](server/vision_model.py))

**Purpose:** Wrapper for Qwen2-VL-7B vision-language model.

**Key Features:**
- Loads model with optimizations (bfloat16, flash attention)
- Processes camera frames + text prompts
- Maintains conversation history for context
- Returns text responses with reasoning

**Flow:**
```
JPEG bytes → PIL Image → Model input → Generate → Parse response
```

**Performance:**
- Model: ~7B parameters (quantized)
- VRAM: ~8-12GB
- Inference: 100-200ms per frame
- Context: 128k tokens (can remember long history)

#### 2. Command Generator ([server/command_generator.py](server/command_generator.py))

**Purpose:** Converts AI responses to motor commands.

**Responsibilities:**
1. **Prompt Engineering** - Constructs prompts with:
   - Current goal
   - Camera image
   - Previous actions and reasoning
   - Output format specification
   - Example commands

2. **Response Parsing** - Extracts:
   - Motor command (4 numbers)
   - Reasoning text
   - Falls back to safe stop on parse failure

3. **State Tracking** - Maintains:
   - Current goal
   - Command history
   - Step counter
   - Previous reasoning

**Example Interaction:**
```
Prompt: "Goal: Move forward. [Camera image]. What should the car do?"
AI Response: "COMMAND: 200,200,1,1\nREASONING: Path ahead is clear, moving forward"
Parsed: MotorCommand(left=200, right=200, left_dir=FORWARD, right_dir=FORWARD)
```

#### 3. Network Server ([server/network_server.py](server/network_server.py))

**Purpose:** TCP server that accepts connections from cars.

**Architecture:**
```
NetworkServer
  ├── Accept thread (handles new connections)
  └── CarConnection (per car)
        ├── Receive thread (frames from car)
        ├── Frame queue (buffered)
        └── Send method (commands to car)
```

**Features:**
- Non-blocking frame reception
- Automatic reconnection handling
- Thread-safe command sending
- Connection health monitoring

#### 4. Server Control ([server/server_control.py](server/server_control.py))

**Purpose:** Main orchestration loop.

**Two Modes:**

**Manual Mode:**
```
Keyboard input → Parse → Send to car
```

**AI Mode:**
```
Wait for frame → Process with AI → Parse response → Send command → Repeat
```

**Control Flow (AI Mode):**
```python
while running:
    1. Wait for car connection
    2. Get frame from car
    3. Build prompt with goal + frame
    4. Process with vision model
    5. Parse AI response → MotorCommand
    6. Send command to car
    7. Update state
    8. Repeat at target FPS
```

### Raspberry Pi Side (Hardware Proxy)

#### 1. Camera Streamer ([pi/camera_streamer.py](pi/camera_streamer.py))

**Purpose:** Capture and encode camera frames.

**Hardware:** Pi Camera Module 3 (12MP, 120° FOV)

**Process:**
```
Camera → RGB array → PIL Image → JPEG encode → bytes
```

**Settings:**
- Resolution: 640x480 (configurable)
- Quality: 80% JPEG compression
- FPS: 10 (configurable)

**Simulation Mode:** Generates test patterns when camera unavailable.

#### 2. Motor Controller ([pi/motor_controller.py](pi/motor_controller.py))

**Purpose:** Direct GPIO control of 4 DC motors.

**Hardware:**
- 2x L298N H-Bridge drivers
- 4x DC motors (mecanum wheels)
- Hardware PWM for speed control

**Architecture:**
```
MotorCommand → GPIO pins + PWM
  ├── Left group (FL + RL)
  └── Right group (FR + RR)
```

**Pin Control:**
- Direction: 2 GPIO pins per motor (forward/backward)
- Speed: 1 PWM pin per pair (duty cycle 0-100%)

**Safety Features:**
- Watchdog timer (stops if no command for 1s)
- Emergency stop method
- Graceful cleanup on exit

**Simulation Mode:** Logs commands without GPIO access.

#### 3. Network Client ([pi/network_client.py](pi/network_client.py))

**Purpose:** TCP client connecting to server.

**Responsibilities:**
1. Connect to server (with retry logic)
2. Send frames with protocol encoding
3. Receive commands with timeout
4. Handle disconnections gracefully

**Protocol Implementation:**
- Frames: `[4-byte size header][JPEG data]`
- Commands: `[4 bytes: speeds + directions]`
- Keep-alive through continuous frame sending

#### 4. Car Hardware ([pi/car_hardware.py](pi/car_hardware.py))

**Purpose:** Main orchestration on Pi side.

**Control Loop:**
```python
setup() → camera, motors, network
while running:
    1. Check connection (reconnect if needed)
    2. Capture frame
    3. Send frame to server
    4. Receive command (non-blocking)
    5. Execute command
    6. Check watchdog
    7. Sleep for FPS limiting
```

**Test Modes:**
- `--test-camera`: Verify camera capture
- `--test-motors`: Run motor sequence
- `--simulate`: Run without hardware

### Shared Components

#### Protocol ([shared/protocol.py](shared/protocol.py))

**MotorCommand:**
```python
@dataclass
class MotorCommand:
    left_speed: int      # 0-255
    right_speed: int     # 0-255
    left_dir: Direction  # FORWARD/BACKWARD/STOP
    right_dir: Direction # FORWARD/BACKWARD/STOP
```

**Helper Methods:**
- `forward(speed)` - Both motors forward
- `backward(speed)` - Both motors backward
- `rotate_left(speed)` - Left back, right forward
- `rotate_right(speed)` - Left forward, right back
- `stop()` - All motors stop

**Binary Format:**
```
Byte 0: left_speed (0-255)
Byte 1: right_speed (0-255)
Byte 2: left_dir (0/1/2)
Byte 3: right_dir (0/1/2)
```

## Data Flow

### Forward Path (Vision → Command)

```
1. Pi captures frame
   ↓ (JPEG encode)
2. Pi sends frame over TCP
   ↓ (network)
3. Server receives frame
   ↓ (queue)
4. Server builds prompt
   ↓ (text + image)
5. AI processes with Qwen2-VL
   ↓ (inference ~150ms)
6. AI generates text response
   ↓ (parse)
7. Extract MotorCommand
   ↓ (4 bytes)
8. Send command over TCP
   ↓ (network)
9. Pi receives command
   ↓ (GPIO)
10. Motors execute
```

**Total Latency:** ~200-300ms
- Capture: 10ms
- Network (up): 20ms
- AI inference: 150ms
- Network (down): 10ms
- GPIO: 1ms

### Backward Path (Error/Status)

Currently minimal - connection status is implicit through TCP. Future could add:
- Battery level
- Sensor readings
- Error codes

## Communication Protocol

### Frame Protocol

**Sending (Pi → Server):**
```python
frame_size = len(jpeg_data)
header = struct.pack('>I', frame_size)  # Big-endian uint32
packet = header + jpeg_data
socket.sendall(packet)
```

**Receiving (Server):**
```python
header = recv_exact(4)
frame_size = struct.unpack('>I', header)[0]
jpeg_data = recv_exact(frame_size)
```

### Command Protocol

**Sending (Server → Pi):**
```python
command_bytes = struct.pack('BBBB',
    left_speed, right_speed,
    left_dir.value, right_dir.value)
socket.sendall(command_bytes)
```

**Receiving (Pi):**
```python
data = recv_exact(4)
left_speed, right_speed, left_dir, right_dir = struct.unpack('BBBB', data)
```

## AI Prompt Engineering

### Prompt Structure

```
You are controlling a robot car with mecanum wheels via camera vision.

CURRENT GOAL: {goal}

You can see through the camera. Analyze the image and decide what motor action to take next.

MOTOR CONTROL:
[Explanation of motor values]

OUTPUT FORMAT (REQUIRED):
COMMAND: <left_speed>,<right_speed>,<left_dir>,<right_dir>
REASONING: <brief explanation>

EXAMPLES:
[Example commands with descriptions]

PREVIOUS COMMAND: {last_command}
PREVIOUS REASONING: {last_reasoning}
STEPS TAKEN: {steps}

Analyze the image and provide your decision in the required format.
```

### Design Rationale

1. **Structured Output** - Forces consistent format for parsing
2. **Examples** - Helps AI understand motor patterns
3. **Context** - Previous actions help with continuity
4. **Reasoning** - Provides debugging insight
5. **Mecanum Notes** - Encourages pattern discovery

### Future Improvements

- Add obstacle detection hints
- Include spatial memory
- Multi-step planning
- Failure recovery strategies

## Safety Mechanisms

### Server Side
- Emergency stop on parse failure
- Timeout on AI inference
- Connection monitoring
- Graceful shutdown (SIGINT/SIGTERM)

### Pi Side
- Motor watchdog (stops if no command)
- Connection loss detection (stops motors)
- Emergency stop button (GPIO optional)
- Hardware PWM limits
- Graceful GPIO cleanup

### Protocol Level
- Max frame size limit (10MB)
- Connection timeouts
- Automatic reconnection
- Frame queue bounds

## Performance Optimization

### Current Optimizations

**AI Model:**
- bfloat16 precision (faster than fp32)
- Flash attention 2 (memory efficient)
- Auto device mapping (multi-GPU if available)

**Network:**
- JPEG compression (quality=80)
- Frame queue (drop old frames)
- Non-blocking receives
- TCP keep-alive

**Pi:**
- Hardware PWM (smooth motor control)
- Dedicated threads for capture/network
- Low-resolution frames (640x480)

### Future Optimizations

- Model quantization (INT8)
- Predictive control (anticipate delays)
- Frame downsampling (320x240)
- H.264 video stream (vs JPEG)
- Edge inference on Pi (local emergency stop decisions)

## Testing Strategy

### Unit Tests
- Protocol encoding/decoding
- Command parsing
- Configuration validation

### Integration Tests
- Simulated car client
- Manual control mode
- Component isolation

### Hardware Tests
- Camera capture
- Motor movement
- GPIO functionality
- End-to-end latency

## Extension Points

### Easy Additions
1. Multiple goals in sequence
2. Goal completion detection
3. Battery monitoring
4. LED status indicators
5. Save debug frames

### Medium Complexity
1. Obstacle avoidance logic
2. Memory across sessions
3. Multi-car coordination
4. Custom motor patterns
5. Replay system

### Advanced
1. SLAM (mapping)
2. Reinforcement learning
3. Sim-to-real training
4. Bare-metal Pi OS
5. Custom hardware acceleration

## Configuration Files

### Server Config ([server/config.py](server/config.py))
- Network settings (host, port)
- Model settings (name, device)
- Vision settings (FPS, resolution)
- Control settings (timeouts, safety)
- Logging options

### Pi Config ([pi/config.py](pi/config.py))
- Server connection (host, port)
- Camera settings (resolution, quality)
- GPIO pin mapping
- PWM frequency
- Safety timeouts

Both configs use dataclasses for type safety and easy modification.

## Development Workflow

### Local Development (No Hardware)
```
1. Run protocol tests
2. Start server in manual mode
3. Run simulated car
4. Test keyboard control
5. Iterate on prompts/parsing
```

### Pi Development
```
1. Test camera in isolation
2. Test motors in isolation
3. Test network connection
4. Integrate components
5. Full system test
```

### AI Development
```
1. Test model loading
2. Test inference with sample images
3. Refine prompts
4. Test parsing robustness
5. Optimize latency
```

## Troubleshooting

See [GETTING_STARTED.md](GETTING_STARTED.md) for detailed troubleshooting steps.

## Future Architecture Changes

Potential evolution:

1. **Phase 1 (Current):** Server AI + Pi proxy
2. **Phase 2:** Add local safety AI on Pi
3. **Phase 3:** Hybrid inference (split model)
4. **Phase 4:** Custom hardware accelerator
5. **Phase 5:** Bare-metal "AI OS"

The goal is to progressively remove traditional OS abstractions while maintaining safety and functionality.
