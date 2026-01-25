# Ultrasonic Sensor Wiring Guide

## Components Required
- 5x HC-SR04 Ultrasonic Sensors
- 1x TXS0108E 8-Channel Level Shifter Module
- Dupont wires (female-to-female)

## Sensor Placement

```
              [FC]                ← Front Center (straight ahead)
         [FL]     [FR]            ← Front Left/Right (angled 45°)
            ┌─────┐
            │ CAR │
            └─────┘
         [RL]     [RR]            ← Rear Left/Right
```

## GPIO Pin Assignments

| Sensor | Position | TRIG Pin | ECHO Pin | Physical Pin (TRIG) | Physical Pin (ECHO) |
|--------|----------|----------|----------|---------------------|---------------------|
| FC | Front Center | GPIO 4 | GPIO 24 | Pin 7 | Pin 18 |
| FL | Front Left | GPIO 7 | GPIO 25 | Pin 26 | Pin 22 |
| FR | Front Right | GPIO 8 | GPIO 20 | Pin 24 | Pin 38 |
| RL | Rear Left | GPIO 9 | GPIO 14 | Pin 21 | Pin 8 |
| RR | Rear Right | GPIO 10 | GPIO 15 | Pin 19 | Pin 10 |

## Wiring Diagram

### Power Rails
```
Pi 5V (Pin 2 or 4) ────┬──────────────────────► TXS0108E HV (High Voltage)
                       │
                       ├──► HC-SR04 #1 VCC
                       ├──► HC-SR04 #2 VCC
                       ├──► HC-SR04 #3 VCC
                       ├──► HC-SR04 #4 VCC
                       └──► HC-SR04 #5 VCC

Pi 3.3V (Pin 1 or 17) ──────────────────────► TXS0108E LV (Low Voltage)

Pi GND (Pin 6, 9, 14, 20, 25, 30, 34, or 39)
                       ┬──────────────────────► TXS0108E GND
                       │
                       ├──► HC-SR04 #1 GND
                       ├──► HC-SR04 #2 GND
                       ├──► HC-SR04 #3 GND
                       ├──► HC-SR04 #4 GND
                       └──► HC-SR04 #5 GND
```

### TRIG Connections (Direct to Pi - no level shifter needed)
```
Pi GPIO 4  (Pin 7)  ────────────────────────► FC Sensor TRIG
Pi GPIO 7  (Pin 26) ────────────────────────► FL Sensor TRIG
Pi GPIO 8  (Pin 24) ────────────────────────► FR Sensor TRIG
Pi GPIO 9  (Pin 21) ────────────────────────► RL Sensor TRIG
Pi GPIO 10 (Pin 19) ────────────────────────► RR Sensor TRIG
```

### ECHO Connections (Through TXS0108E Level Shifter)
```
FC Sensor ECHO ──► TXS0108E HV1 ──┬── TXS0108E LV1 ──► Pi GPIO 24 (Pin 18)
FL Sensor ECHO ──► TXS0108E HV2 ──┤── TXS0108E LV2 ──► Pi GPIO 25 (Pin 22)
FR Sensor ECHO ──► TXS0108E HV3 ──┼── TXS0108E LV3 ──► Pi GPIO 20 (Pin 38)
RL Sensor ECHO ──► TXS0108E HV4 ──┤── TXS0108E LV4 ──► Pi GPIO 14 (Pin 8)
RR Sensor ECHO ──► TXS0108E HV5 ──┴── TXS0108E LV5 ──► Pi GPIO 15 (Pin 10)
```

## TXS0108E Module Pinout

Most TXS0108E modules have this layout:

```
┌─────────────────────────────────────┐
│  LV    A1  A2  A3  A4  A5  A6  A7  A8  │  ← Low Voltage Side (3.3V to Pi)
│  GND   ●   ●   ●   ●   ●   ●   ●   ●   │
│────────────────────────────────────────│
│  GND   ●   ●   ●   ●   ●   ●   ●   ●   │
│  HV    B1  B2  B3  B4  B5  B6  B7  B8  │  ← High Voltage Side (5V to sensors)
└─────────────────────────────────────┘
```

- Connect Pi 3.3V to LV
- Connect Pi 5V to HV
- Connect GND to GND (both sides share common ground)
- A1-A5 connect to Pi GPIO (ECHO pins)
- B1-B5 connect to sensor ECHO outputs

## Testing

Once wired, test with:

```bash
ssh thinktank "cd ~/robotcar && python3 -m pi.ultrasonic_sensors"
```

Expected output:
```
Ultrasonic Sensor Test
==================================================

Reading 1:
Front Center: 45.2 cm | Front Left: 120.3 cm | Front Right: 88.1 cm | Rear Left: 200.5 cm | Rear Right: 185.2 cm
```

## Troubleshooting

### All readings show "--" (invalid)
- Check power connections (5V to sensors, 3.3V and 5V to level shifter)
- Verify GND is connected to all components
- Check that level shifter is oriented correctly

### One sensor always reads "--"
- Check TRIG wire connection
- Check ECHO wire through level shifter
- Swap with known working sensor to isolate hardware vs wiring issue

### Readings are unstable/jumping
- Add small delay between readings (already done in code)
- Check for loose connections
- Ensure sensors aren't pointed at each other (interference)

### Readings max out at 400cm
- Normal if nothing is in range
- Check sensor isn't pointed at the sky/open space

## Notes

- The HC-SR04 has a ~15° cone of detection
- Minimum reliable distance is ~2cm
- Maximum range is ~400cm (4 meters)
- Soft materials (fabric, carpet) may not reflect well
- Best for hard surfaces, walls, furniture
