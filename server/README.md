# Control Server

The AI brain running on the RTX 5090 server.

## Responsibilities

- Receive camera frames from the Pi over WiFi
- Pass frames to Llama 3.2 Vision with the control prompt
- Parse motor commands from the model output
- Send motor commands back to the Pi

## The Prompt is the Program

Instead of coded control logic, we use natural language:

```
You are controlling a mecanum-wheel robot car. You receive camera 
frames showing what the car sees.

Respond ONLY with a JSON object containing motor speeds:
{"fl": 0, "fr": 0, "rl": 0, "rr": 0}

Values range from -100 (full reverse) to 100 (full forward).

Mecanum wheel physics:
- All wheels forward: car moves forward
- All wheels backward: car moves backward  
- Left wheels backward, right wheels forward: rotate left
- FL/RR forward, FR/RL backward: strafe right

Your goal: [TASK GOES HERE]

Move carefully. You have ~200ms latency between seeing and acting.
```

## Stack

- Python (FastAPI or simple WebSocket server)
- Llama 3.2 Vision (11B) via llama.cpp or similar
- RTX 5090 for inference

## Status

🚧 *Not yet implemented*
