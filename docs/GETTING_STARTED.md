# Getting Started Guide

This guide will walk you through setting up and running the AI Car Control System.

## Prerequisites

### Server Requirements
- Linux system (Ubuntu 20.04+ recommended)
- NVIDIA GPU with CUDA support (RTX 5090 or similar)
- Python 3.10 or later
- 16GB+ RAM
- 50GB+ free disk space (for model)

### Raspberry Pi Requirements
- Raspberry Pi 4 Model B (2GB+ RAM)
- Raspberry Pi OS Lite (64-bit)
- Pi Camera Module 3
- L298N motor drivers (x2)
- DC motors (x4)
- Power supplies (separate for Pi and motors)

## Step-by-Step Setup

### Part 1: Server Setup

#### 1. Install Python and Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and pip
sudo apt install python3 python3-pip python3-venv -y

# Install CUDA (if not already installed)
# Follow NVIDIA's official guide for your system
```

#### 2. Create Virtual Environment

```bash
cd /path/to/robotcar
python3 -m venv venv
source venv/bin/activate
```

#### 3. Install Python Packages

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Note:** Installing PyTorch with CUDA support may take a while. Ensure you have the correct CUDA version:

```bash
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

#### 4. Download the Vision Model

The model will be downloaded automatically on first run, but you can pre-download it:

```bash
python -c "from transformers import Qwen2VLForConditionalGeneration; \
Qwen2VLForConditionalGeneration.from_pretrained('Qwen/Qwen2-VL-7B-Instruct')"
```

This downloads ~22GB of model files.

#### 5. Test Server Setup

```bash
# Test with simulated car (no AI)
python -m server.server_control --manual
```

Keep this running and proceed to testing in a new terminal.

### Part 2: Testing Without Hardware

Before setting up the Raspberry Pi, test the system with a simulated car:

#### 1. Run Simulated Car

In a new terminal:

```bash
cd /path/to/robotcar
source venv/bin/activate
python tests/simulate_car.py --host localhost --fps 5
```

You should see:
- Server: "New connection from..."
- Simulator: "Connected successfully"
- Frames being sent and received

#### 2. Test Manual Control

In the server terminal, you can now send commands:

```
> forward 200
> left 150
> stop
```

The simulator will log received commands.

### Part 3: Raspberry Pi Setup

#### 1. Install Raspberry Pi OS

1. Download Raspberry Pi Imager
2. Choose "Raspberry Pi OS Lite (64-bit)"
3. Configure WiFi and SSH before flashing
4. Flash to SD card and boot

#### 2. Initial Pi Configuration

```bash
# SSH into Pi
ssh pi@raspberrypi.local

# Update system
sudo apt update && sudo apt upgrade -y

# Enable camera
sudo raspi-config
# Navigate to: Interface Options → Camera → Enable
# Reboot when prompted
```

#### 3. Install Dependencies

```bash
# Install required packages
sudo apt install -y python3-pip python3-picamera2 python3-rpi.gpio python3-opencv git

# Install Python packages
pip3 install Pillow
```

#### 4. Copy Project Files to Pi

From your computer:

```bash
# Copy the robotcar directory to Pi
rsync -av --exclude 'venv' --exclude '.git' \
  /path/to/robotcar/ pi@raspberrypi.local:~/robotcar/
```

Or clone from git if you're using version control:

```bash
# On the Pi
git clone <your-repo-url> ~/robotcar
```

#### 5. Configure Pi Settings

Edit the configuration file on the Pi:

```bash
cd ~/robotcar
nano pi/config.py
```

Update the server IP address:

```python
server_host: str = "192.168.1.100"  # Your server's actual IP
```

Save and exit (Ctrl+O, Enter, Ctrl+X).

### Part 4: Hardware Assembly

#### 1. Connect Motors to L298N Drivers

**Driver 1 (Front wheels):**
- IN1 → GPIO 17 (FL forward)
- IN2 → GPIO 27 (FL backward)
- IN3 → GPIO 22 (FR forward)
- IN4 → GPIO 23 (FR backward)
- ENA → GPIO 12 (FL PWM)
- ENB → GPIO 13 (FR PWM)

**Driver 2 (Rear wheels):**
- IN1 → GPIO 5 (RL forward)
- IN2 → GPIO 6 (RL backward)
- IN3 → GPIO 16 (RR forward)
- IN4 → GPIO 26 (RR backward)
- ENA → GPIO 18 (RL PWM)
- ENB → GPIO 19 (RR PWM)

**Power:**
- Connect motor power supply (6xAA) to motor driver 12V input
- Connect GND between Pi and motor drivers (IMPORTANT!)
- DO NOT connect motor 12V to Pi

#### 2. Connect Camera

1. Locate camera connector (between HDMI and USB ports)
2. Pull up on black plastic clip
3. Insert ribbon cable (blue side toward USB ports)
4. Push clip down to secure

#### 3. Verify Camera

```bash
libcamera-hello --timeout 5000
```

You should see a 5-second preview.

### Part 5: Hardware Testing

#### 1. Test Camera Capture

```bash
cd ~/robotcar
python3 -m pi.car_hardware --test-camera --simulate
```

Should show 10 successful frame captures.

#### 2. Test Motors (BE CAREFUL!)

⚠️ **Warning:** Motors will actually move! Ensure car is elevated or has room to move.

```bash
python3 -m pi.car_hardware --test-motors
```

You should see/hear each motor group activate briefly.

### Part 6: Full System Test

#### 1. Start Server

On your server:

```bash
cd /path/to/robotcar
source venv/bin/activate
python -m server.server_control --manual
```

#### 2. Start Pi Client

On the Raspberry Pi:

```bash
cd ~/robotcar
python3 -m pi.car_hardware
```

You should see:
- Pi: "Connecting to server..."
- Pi: "Connected to server successfully"
- Server: "New connection from..."
- Pi: "Capturing frames..." / "Sent frame..."

#### 3. Test Manual Control

In the server terminal, send commands:

```
> forward 150
> stop
> left 100
> stop
```

The car should respond to each command!

### Part 7: AI Control

#### 1. Stop Manual Mode

Stop the server (Ctrl+C) and the Pi client (Ctrl+C).

#### 2. Start Server in AI Mode

```bash
python -m server.server_control --goal "Explore forward and avoid obstacles"
```

The first run will:
- Load the vision model (takes 1-2 minutes)
- Wait for Pi connection

#### 3. Start Pi Client

On the Pi:

```bash
python3 -m pi.car_hardware
```

The car should now be under AI control! Watch the server logs to see:
- AI's reasoning for each decision
- Generated motor commands
- Vision processing output

## Troubleshooting

### Server Issues

**"CUDA out of memory"**
- Close other GPU applications
- Reduce `max_context_length` in server/config.py
- Use a smaller model

**"Port already in use"**
```bash
sudo lsof -i :5555
kill <PID>
```

### Pi Issues

**"No camera detected"**
- Check ribbon cable connection
- Verify camera is enabled in raspi-config
- Try: `vcgencmd get_camera`

**"No permission for GPIO"**
```bash
sudo usermod -a -G gpio $USER
# Log out and back in
```

**"Connection refused"**
- Verify server IP in pi/config.py
- Check firewall: `sudo ufw status`
- Test connectivity: `ping <server-ip>`

### Performance Issues

**High latency (>500ms)**
- Check WiFi signal strength
- Reduce camera resolution in configs
- Lower frame rate (try 5 FPS)

**Car not responding**
- Check motor watchdog timeout in pi/config.py
- Verify motor power supply
- Check GPIO connections

## Next Steps

Once everything is working:

1. **Tune Parameters**
   - Adjust speeds in command_generator.py
   - Modify prompts for better AI behavior
   - Tweak camera quality/FPS for latency vs quality

2. **Improve Prompts**
   - Edit prompts in server/command_generator.py
   - Add more examples for better AI understanding
   - Include environmental context

3. **Add Features**
   - Obstacle detection logic
   - Goal memory across sessions
   - Multi-step planning

4. **Optimize Performance**
   - Profile inference time
   - Reduce network overhead
   - Add predictive control

## Safety Reminders

- Always have emergency stop ready (Ctrl+C)
- Test at low speeds first
- Clear area of obstacles
- Monitor battery levels
- Motors stop on connection loss (1s timeout)

## Getting Help

If you encounter issues:

1. Check logs for error messages
2. Verify all connections (camera, motors, network)
3. Test components individually
4. Review configuration files
5. Check hardware compatibility

Good luck! 🤖🚗
