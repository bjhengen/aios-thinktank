# AI-Native Hardware Control - Robot Car

An experimental project testing whether AI can directly control hardware with minimal OS overhead. A vision-language model (Qwen3-VL-8B) running on a server directly controls a robot car via WiFi, with the Raspberry Pi acting as a minimal hardware proxy.

## Architecture

```
┌─────────────────────────────────────┐
│  Server (RTX 5090 + Ryzen 9 7900)  │
│  • Qwen3-VL-8B (128k context)      │
│  • Vision processing                │
│  • Decision making                  │
│  • Motor command generation         │
└──────────────┬──────────────────────┘
               │ WiFi
┌──────────────▼──────────────────────┐
│   Raspberry Pi 4 2GB (Car)         │
│   • Minimal Python runtime          │
│   • Camera streaming                │
│   • Command execution               │
│   • Direct GPIO control             │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       │               │
   Camera          4x Motors
```

## Quick Start

### Server Setup (Linux with GPU)

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure server:**
   Edit [server/config.py](server/config.py) to set your model and network settings.

3. **Run in manual mode (keyboard control) for testing:**
   ```bash
   python -m server.server_control --manual
   ```

4. **Run in AI mode:**
   ```bash
   python -m server.server_control --goal "Explore forward and avoid obstacles"
   ```

### Raspberry Pi Setup

1. **Install Raspberry Pi OS Lite (64-bit)**

2. **Install dependencies:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y python3-picamera2 python3-rpi.gpio python3-opencv python3-pip
   pip3 install -r requirements-pi.txt
   ```

3. **Configure Pi:**
   Edit [pi/config.py](pi/config.py) to set your server's IP address:
   ```python
   server_host: str = "192.168.1.100"  # Your server's IP
   ```

4. **Test hardware:**
   ```bash
   # Test motors (careful - motors will move!)
   python3 -m pi.car_hardware --test-motors

   # Test camera
   python3 -m pi.car_hardware --test-camera
   ```

5. **Run car client:**
   ```bash
   python3 -m pi.car_hardware
   ```

### Testing Without Hardware

Simulate a car client on your development machine:

```bash
# In terminal 1: Start server in manual mode
python -m server.server_control --manual

# In terminal 2: Run simulated car
python tests/simulate_car.py --host localhost --fps 10
```

## Project Structure

```
robotcar/
├── server/              # Server-side (AI brain)
│   ├── server_control.py      # Main server entry point
│   ├── vision_model.py         # Qwen3-VL-8B wrapper
│   ├── command_generator.py    # AI → motor commands
│   ├── network_server.py       # TCP server
│   └── config.py               # Server configuration
│
├── pi/                  # Raspberry Pi (hardware proxy)
│   ├── car_hardware.py         # Main Pi entry point
│   ├── camera_streamer.py      # Camera capture
│   ├── motor_controller.py     # GPIO motor control
│   ├── network_client.py       # TCP client
│   └── config.py               # Pi configuration
│
├── shared/              # Shared code
│   ├── protocol.py             # Communication protocol
│   └── utils.py                # Utilities
│
└── tests/               # Testing tools
    ├── test_protocol.py        # Protocol unit tests
    └── simulate_car.py         # Simulated car client
```

## Hardware

### Components

- **Server:** Linux PC with NVIDIA RTX 5090, Ryzen 9 7900
- **Controller:** Raspberry Pi 4 Model B (2GB RAM)
- **Camera:** Raspberry Pi Camera Module 3 Wide (12MP, 120° FOV)
- **Motors:** 4x DC motors with mecanum wheels
- **Motor Drivers:** 2x L298N H-Bridge drivers
- **Power:** USB-C power bank (Pi), 6xAA batteries (motors)

### GPIO Pin Mapping

See [pi/config.py](pi/config.py) for the complete pin mapping. Default configuration:

- **Motor Driver 1:** GPIO 17, 27, 22, 23 (direction), GPIO 12, 13 (PWM)
- **Motor Driver 2:** GPIO 5, 6, 16, 26 (direction), GPIO 18, 19 (PWM)

## Communication Protocol

### Camera Frames (Pi → Server)

```
[4 bytes: frame_size (uint32, big-endian)]
[frame_size bytes: JPEG data]
```

### Motor Commands (Server → Pi)

```
[1 byte: left_speed (0-255)]
[1 byte: right_speed (0-255)]
[1 byte: left_direction (0=backward, 1=forward, 2=stop)]
[1 byte: right_direction (0=backward, 1=forward, 2=stop)]
```

## AI Control

The AI receives camera frames and natural language goals, then generates motor commands based on visual understanding:

**Prompt Structure:**
```
Goal: [Natural language goal]
Camera Image: [Vision input]
Previous Action: [Last command + reasoning]

→ Output: COMMAND: left_speed,right_speed,left_dir,right_dir
         REASONING: [Brief explanation]
```

**Example Goals:**
- "Explore forward and avoid obstacles"
- "Find the kitchen"
- "Navigate to the charging station"

## Development Workflow

### Phase 1: Basic Testing (Current)

1. **Test protocol:** `python tests/test_protocol.py`
2. **Simulate car:** `python tests/simulate_car.py`
3. **Manual control:** Test server → simulated car with keyboard

### Phase 2: Hardware Integration

1. Wire up motors and camera on Raspberry Pi
2. Test motors: `python3 -m pi.car_hardware --test-motors`
3. Test camera: `python3 -m pi.car_hardware --test-camera`
4. Connect Pi to server

### Phase 3: AI Control

1. Load vision model on server
2. Test simple goals: "move forward", "turn left"
3. Test complex goals: "explore and avoid obstacles"

### Phase 4: Optimization

1. Reduce latency (<200ms target)
2. Improve prompt engineering
3. Add obstacle detection
4. Enable mecanum wheel patterns

## Configuration

### Server Configuration

Edit [server/config.py](server/config.py):

```python
# Network
host = "0.0.0.0"
port = 5555

# Model
model_name = "Qwen/Qwen2-VL-7B-Instruct"
max_context_length = 128000

# Vision
target_fps = 10
frame_width = 640
frame_height = 480
```

### Pi Configuration

Edit [pi/config.py](pi/config.py):

```python
# Server connection
server_host = "192.168.1.100"  # Your server's IP
server_port = 5555

# Camera
camera_width = 640
camera_height = 480
camera_fps = 10
jpeg_quality = 80

# GPIO pins (see file for full mapping)
```

## Troubleshooting

### Server Issues

**Model won't load:**
- Check CUDA/GPU availability: `python -c "import torch; print(torch.cuda.is_available())"`
- Verify model name in config.py
- Check available VRAM

**Connection refused:**
- Check firewall settings
- Verify port is not in use: `netstat -an | grep 5555`

### Pi Issues

**Camera not working:**
- Enable camera: `sudo raspi-config` → Interface Options → Camera
- Check connection: `libcamera-hello`

**Motors not responding:**
- Verify GPIO pin numbers match your wiring
- Check motor driver power supply
- Test with simple GPIO script first

**Can't connect to server:**
- Verify server IP in [pi/config.py](pi/config.py)
- Check network connectivity: `ping <server-ip>`
- Ensure server is running and listening

## Safety Notes

⚠️ **Important Safety Reminders:**

- Always have an emergency stop button/method ready
- Test motors at low speeds initially
- Ensure adequate space for car movement
- Motors will stop automatically if connection is lost (watchdog timeout)
- Use `Ctrl+C` to safely stop both server and Pi clients

## License

This is an experimental project. Use at your own risk.

## Next Steps

- [ ] Test basic hardware connectivity
- [ ] Optimize AI inference latency
- [ ] Implement obstacle detection
- [ ] Enable mecanum wheel pattern discovery
- [ ] Add memory/learning across sessions
