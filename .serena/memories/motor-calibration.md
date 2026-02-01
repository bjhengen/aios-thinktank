# Robot Car Motor Calibration

## Turn Calibration (90% power / PWM 230, on tile floor)

| Direction | 90° Duration | Notes |
|-----------|--------------|-------|
| RIGHT | ~2.0-2.5s | Left wheels FWD, Right wheels BWD |
| LEFT | ~1.25s | Left wheels BWD, Right wheels FWD |

**CRITICAL: Left turns are ~2x MORE EFFICIENT than right turns!**

## Small Adjustments (90% power)
- Left 10°: ~0.4s
- Left 15-20°: ~0.6s

## Power Requirements
- **Turns**: 90% (PWM ~230) required to reliably rotate from stop
- **Forward/Backward on tile**: 75% (PWM ~190)
- **Forward/Backward on carpet**: 85% (PWM ~215)

## Motor GPIO Mapping
```python
MOTORS = {
    'FL': {'fwd': 17, 'bwd': 27, 'pwm': 12},
    'FR': {'fwd': 6,  'bwd': 5,  'pwm': 18},
    'RL': {'fwd': 22, 'bwd': 23, 'pwm': 13},
    'RR': {'fwd': 26, 'bwd': 16, 'pwm': 19},
}
```

## Turn Commands
- **RIGHT turn**: FL/RL forward (fwd=1, bwd=0), FR/RR backward (fwd=0, bwd=1)
- **LEFT turn**: FL/RL backward (fwd=0, bwd=1), FR/RR forward (fwd=1, bwd=0)

## SSH Access
- Pi hostname: `thinktank` (192.168.1.140)
- Camera capture: `rpicam-jpeg -o /tmp/frame.jpg --width 640 --height 480 --quality 80 -t 1`

## Root Cause of Asymmetry
Likely weight distribution (battery pack) or motor power differences between left and right sides.

---
*Last updated: January 2026 after calibration session*
