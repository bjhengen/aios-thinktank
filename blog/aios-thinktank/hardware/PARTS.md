# AIOS:ThinkTank Parts List

## On-Vehicle Components

### Compute

| Component | Description | Notes |
|-----------|-------------|-------|
| **Raspberry Pi 4 Model B (2GB)** | Quad Core 64-bit, WiFi, Bluetooth | The "peripheral nervous system" - handles camera streaming and motor control |
| **Raspberry Pi Camera Module 3** | Official Pi camera | The AI's eyes - every frame goes to the server for processing |
| **SanDisk 32GB Ultra microSDHC** | 120MB/s A1 Class 10 UHS-I | Boot media for minimal Linux image |

### Chassis & Mobility

| Component | Description | Notes |
|-----------|-------------|-------|
| **Professional 60mm Mecanum Wheel Car Chassis MC100** | Metal smart car chassis kit with 4x DC TT motors and 60mm mecanum wheels | Omnidirectional movement - forward, backward, strafe, rotate. Compatible with Arduino/Raspberry Pi. The angled rollers on mecanum wheels allow movement in any direction with simple motor speed control. |

### Motor Control

| Component | Description | Notes |
|-----------|-------------|-------|
| **JTAREA L298N H Bridge Motor Driver Module** | Dual H-Bridge stepper/DC motor driver (4 pack) | Controls 2 motors per board. We'll use 2 boards for 4-wheel independent control. Each motor needs 2 GPIO pins (direction + PWM). |

### Sensors

| Component | Description | Notes |
|-----------|-------------|-------|
| **Smraza Ultrasonic Module** | HC-SR04 ultrasonic distance sensor (5 pack) | Optional safety backup - could provide distance data to AI or trigger emergency stop. Not required for core experiment but good to have. |

### Power

| Component | Description | Notes |
|-----------|-------------|-------|
| **Corpco 6x AA Battery Holder** | Standard snap connector, 9V output | Initial motor power supply (with PWM limiting - see notes below) |
| **SDTC Tech 4x AA Battery Holder** | Thickened wires, snap connector, 6V output | *On order* — cleaner solution matching motor voltage |
| **yeewanke Rechargeable AA Batteries** | 1.5V 3600mWh Li-ion (8 pack with charger) | 2000+ cycle rechargeable |
| **Anker PowerCore Slim 10000** | 10000mAh USB power bank | Powers the Raspberry Pi via USB-C. Keeps Pi power isolated from motor power to reduce noise. |

#### Motor Voltage Notes

**The DC TT motors in the MC100 chassis are rated 3V-6V.**

With the 6xAA holder (9V nominal), the L298N drops ~1.5-2V, delivering ~7-7.5V to motors — still above spec. 

**Solution: PWM limiting.** Cap duty cycle at ~80% max, which effectively limits voltage to ~6V. This is implemented in software and noted in the daemon code. As batteries discharge (9V → 7V over time), this provides headroom to maintain consistent speed.

**Cleaner solution:** The 4xAA holder delivers 6V nominal, matching motor specs exactly. No PWM limiting required (though still useful for speed control). Ordered for future use.

### Wiring

| Component | Description | Notes |
|-----------|-------------|-------|
| **ELEGOO Dupont Wire Kit** | 120pcs - 40pin M-F, 40pin M-M, 40pin F-F | Primary wiring for GPIO to motor driver connections |
| **BOJACK Breadboard Kit** | 4x 830 tie points, 400 tie points boards, 126 jumper wires | For prototyping connections before finalizing |
| **Cable Ties (4" black)** | 1000 pack | Cable management, securing components to chassis |

---

## Development & Setup Components

*These are used for Pi setup and development, not mounted on the vehicle.*

| Component | Description | Notes |
|-----------|-------------|-------|
| **Miuzei Raspberry Pi 4 Case** | Case with fan cooling, 5V 3A power supply, 4x aluminum heatsinks | For bench development. The Pi will likely run naked or with minimal case on the vehicle. |
| **Amazon Basics Micro HDMI to HDMI Cable** | 18Gbps, 4K@60Hz, 6 foot | Initial Pi setup and debugging |
| **Amazon Basics USB Wired Mouse** | 3-button with scroll | Initial Pi setup |
| **UNI Card Reader** | USB 3.0 / USB-C | Flashing the microSD card |

---

## GPIO Pin Planning

The Raspberry Pi 4 has 40 GPIO pins. Here's our preliminary allocation:

### Motor Control (L298N x2)

Each L298N controls 2 motors and needs:
- 2x IN pins per motor (direction control)
- 1x EN pin per motor (PWM speed control)

| Function | GPIO Pin | L298N Pin | Notes |
|----------|----------|-----------|-------|
| Motor FL IN1 | TBD | Board 1 IN1 | Front Left direction |
| Motor FL IN2 | TBD | Board 1 IN2 | Front Left direction |
| Motor FL EN | TBD | Board 1 ENA | Front Left speed (PWM) |
| Motor FR IN1 | TBD | Board 1 IN3 | Front Right direction |
| Motor FR IN2 | TBD | Board 1 IN4 | Front Right direction |
| Motor FR EN | TBD | Board 1 ENB | Front Right speed (PWM) |
| Motor RL IN1 | TBD | Board 2 IN1 | Rear Left direction |
| Motor RL IN2 | TBD | Board 2 IN2 | Rear Left direction |
| Motor RL EN | TBD | Board 2 ENA | Rear Left speed (PWM) |
| Motor RR IN1 | TBD | Board 2 IN3 | Rear Right direction |
| Motor RR IN2 | TBD | Board 2 IN4 | Rear Right direction |
| Motor RR EN | TBD | Board 2 ENB | Rear Right speed (PWM) |

**Total motor control: 12 GPIO pins**

### Camera

The Pi Camera Module 3 connects via the CSI ribbon cable, not GPIO.

### Ultrasonic Sensors (Optional)

| Function | GPIO Pin | Notes |
|----------|----------|-------|
| Ultrasonic TRIG | TBD | Trigger pin |
| Ultrasonic ECHO | TBD | Echo pin |

---

## Power Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    POWER DISTRIBUTION                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────┐      ┌─────────────────────────┐   │
│  │ Anker PowerCore │─USB─▶│    Raspberry Pi 4       │   │
│  │   10000mAh      │  C   │    (5V via USB-C)       │   │
│  └─────────────────┘      └─────────────────────────┘   │
│                                                         │
│  ┌─────────────────┐      ┌─────────────────────────┐   │
│  │ 6x AA Batteries │─9V──▶│   L298N Motor Driver    │   │
│  │   (9V nominal)  │      │   (powers 4 motors)     │   │
│  └─────────────────┘      └─────────────────────────┘   │
│                                                         │
│  NOTE: Separate power supplies for logic (Pi) and       │
│  motors reduces electrical noise and prevents           │
│  brownouts when motors draw high current.               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Server Components (Not Purchased - Existing)

| Component | Description | Notes |
|-----------|-------------|-------|
| **RTX 5090 Server** | Brian's existing home server | Runs Llama 3.2 Vision for AI inference |
| **Llama 3.2 Vision (11B)** | Multimodal vision-language model | The "operating intelligence" - processes camera frames, outputs motor commands |

---

## Shopping Links

*For readers who want to build their own:*

| Component | Link |
|-----------|------|
| Raspberry Pi 4 Model B (2GB) | [Amazon](https://www.amazon.com/dp/B07TC2BK1X) |
| Raspberry Pi Camera Module 3 | [Amazon](https://www.amazon.com/dp/B0BN1V5RQY) |
| MC100 Mecanum Chassis Kit | [Amazon](https://www.amazon.com/dp/B0XXXXXXXX) |
| L298N Motor Driver (4 pack) | [Amazon](https://www.amazon.com/dp/B0XXXXXXXX) |
| 4x AA Battery Holder | [Amazon](https://www.amazon.com/dp/B0858Y4JPL) |
| *Add actual links when publishing* | |

---

*Last updated: January 2025*
