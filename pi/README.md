# Pi Daemon

The minimal software layer running on the Raspberry Pi 4.

## Responsibilities

- Capture frames from the Pi Camera
- Stream frames to the RTX 5090 server over WiFi
- Receive motor commands from the server
- Apply PWM signals to the motor driver
- Safety watchdog: stop motors if no command received within 200ms

## Philosophy

This code should be as minimal as possible. No decision-making, no intelligence—just I/O. The AI on the server is the operating intelligence; this daemon is just the peripheral nervous system.

## Status

🚧 *Not yet implemented*
