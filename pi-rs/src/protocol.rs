// Public API of this module is wire-contract surface; some items are consumed
// only by later phases (network, camera threads). Silence dead-code warnings
// until those call sites land.
#![allow(dead_code)]

//! Wire-format protocol for car ↔ server communication.
//!
//! This is a port of `shared/protocol.py`. It must stay byte-for-byte compatible
//! with the Python server — tests assert round-trip against fixtures generated
//! by the Python implementation.
//!
//! Three things on the wire:
//!
//! 1. **MotorCommand** — 6 bytes, server → car.
//!    Format: `[l_speed][r_speed][l_dir][r_dir][duration_ms_hi][duration_ms_lo]`
//!
//! 2. **SensorData** — 20 bytes, car → server (prefixed onto frames).
//!    Format: `[magic_0x53][magic_0x01][fc_hi][fc_lo]...[rr_hi][rr_lo][8 reserved]`
//!
//! 3. **Frame** — car → server. `[4-byte big-endian size][payload]`.
//!    Payload is either plain JPEG, or a sensor-prefixed JPEG detected via magic bytes.

use thiserror::Error;

// ═══════════════════════════════════════════════════════════════════════════
// Constants — match shared/protocol.py byte-for-byte
// ═══════════════════════════════════════════════════════════════════════════

pub const SENSOR_MAGIC: [u8; 2] = [0x53, 0x01];
pub const SENSOR_HEADER_SIZE: usize = 20;
pub const FRAME_HEADER_SIZE: usize = 4;
pub const COMMAND_SIZE: usize = 6;
pub const MAX_FRAME_SIZE: usize = 10 * 1024 * 1024;
pub const DEFAULT_PORT: u16 = 5555;
pub const KEEPALIVE_INTERVAL_SECS: u64 = 5;
pub const CONNECTION_TIMEOUT_SECS: u64 = 30;

// ═══════════════════════════════════════════════════════════════════════════
// Errors
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ProtocolError {
    #[error("invalid buffer length: expected {expected}, got {got}")]
    InvalidLength { expected: usize, got: usize },

    #[error("invalid direction byte: {0} (must be 0, 1, or 2)")]
    InvalidDirection(u8),

    #[error("invalid sensor magic: {0:02x?} (expected {1:02x?})")]
    InvalidSensorMagic([u8; 2], [u8; 2]),

    #[error("frame too large: {size} bytes (max {max})")]
    FrameTooLarge { size: usize, max: usize },
}

pub type Result<T> = std::result::Result<T, ProtocolError>;

// ═══════════════════════════════════════════════════════════════════════════
// Direction
// ═══════════════════════════════════════════════════════════════════════════

#[repr(u8)]
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Direction {
    Backward = 0,
    Forward = 1,
    Stop = 2,
}

impl Direction {
    pub fn from_u8(b: u8) -> Result<Self> {
        match b {
            0 => Ok(Direction::Backward),
            1 => Ok(Direction::Forward),
            2 => Ok(Direction::Stop),
            _ => Err(ProtocolError::InvalidDirection(b)),
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MotorCommand
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct MotorCommand {
    pub left_speed: u8,
    pub right_speed: u8,
    pub left_dir: Direction,
    pub right_dir: Direction,
    pub duration_ms: u16,
}

impl MotorCommand {
    pub const SIZE: usize = COMMAND_SIZE;

    pub fn stop() -> Self {
        Self {
            left_speed: 0,
            right_speed: 0,
            left_dir: Direction::Stop,
            right_dir: Direction::Stop,
            duration_ms: 0,
        }
    }

    pub fn forward(speed: u8, duration_ms: u16) -> Self {
        Self {
            left_speed: speed,
            right_speed: speed,
            left_dir: Direction::Forward,
            right_dir: Direction::Forward,
            duration_ms,
        }
    }

    pub fn backward(speed: u8, duration_ms: u16) -> Self {
        Self {
            left_speed: speed,
            right_speed: speed,
            left_dir: Direction::Backward,
            right_dir: Direction::Backward,
            duration_ms,
        }
    }

    pub fn rotate_left(speed: u8, duration_ms: u16) -> Self {
        Self {
            left_speed: speed,
            right_speed: speed,
            left_dir: Direction::Backward,
            right_dir: Direction::Forward,
            duration_ms,
        }
    }

    pub fn rotate_right(speed: u8, duration_ms: u16) -> Self {
        Self {
            left_speed: speed,
            right_speed: speed,
            left_dir: Direction::Forward,
            right_dir: Direction::Backward,
            duration_ms,
        }
    }

    pub fn to_bytes(&self) -> [u8; COMMAND_SIZE] {
        let dur = self.duration_ms.to_be_bytes();
        [
            self.left_speed,
            self.right_speed,
            self.left_dir as u8,
            self.right_dir as u8,
            dur[0],
            dur[1],
        ]
    }

    pub fn from_bytes(buf: &[u8]) -> Result<Self> {
        if buf.len() != COMMAND_SIZE {
            return Err(ProtocolError::InvalidLength {
                expected: COMMAND_SIZE,
                got: buf.len(),
            });
        }
        Ok(Self {
            left_speed: buf[0],
            right_speed: buf[1],
            left_dir: Direction::from_u8(buf[2])?,
            right_dir: Direction::from_u8(buf[3])?,
            duration_ms: u16::from_be_bytes([buf[4], buf[5]]),
        })
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// SensorData
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Copy, Clone, Debug, Default, PartialEq, Eq)]
pub struct SensorData {
    /// Front-center distance in mm. 0 = invalid / no reading.
    pub fc: u16,
    pub fl: u16,
    pub fr: u16,
    pub rl: u16,
    pub rr: u16,
}

impl SensorData {
    pub const SIZE: usize = SENSOR_HEADER_SIZE;

    pub fn empty() -> Self {
        Self::default()
    }

    pub fn to_bytes(&self) -> [u8; SENSOR_HEADER_SIZE] {
        let mut buf = [0u8; SENSOR_HEADER_SIZE];
        buf[0..2].copy_from_slice(&SENSOR_MAGIC);
        buf[2..4].copy_from_slice(&self.fc.to_be_bytes());
        buf[4..6].copy_from_slice(&self.fl.to_be_bytes());
        buf[6..8].copy_from_slice(&self.fr.to_be_bytes());
        buf[8..10].copy_from_slice(&self.rl.to_be_bytes());
        buf[10..12].copy_from_slice(&self.rr.to_be_bytes());
        // bytes 12..20 stay zero (reserved)
        buf
    }

    pub fn from_bytes(buf: &[u8]) -> Result<Self> {
        if buf.len() < SENSOR_HEADER_SIZE {
            return Err(ProtocolError::InvalidLength {
                expected: SENSOR_HEADER_SIZE,
                got: buf.len(),
            });
        }
        let magic = [buf[0], buf[1]];
        if magic != SENSOR_MAGIC {
            return Err(ProtocolError::InvalidSensorMagic(magic, SENSOR_MAGIC));
        }
        Ok(Self {
            fc: u16::from_be_bytes([buf[2], buf[3]]),
            fl: u16::from_be_bytes([buf[4], buf[5]]),
            fr: u16::from_be_bytes([buf[6], buf[7]]),
            rl: u16::from_be_bytes([buf[8], buf[9]]),
            rr: u16::from_be_bytes([buf[10], buf[11]]),
        })
    }

    /// Convert mm-with-0-as-invalid into cm-with-None-as-invalid.
    /// Mirrors Python's `SensorData.to_dict()` semantics.
    pub fn to_cm(&self) -> SensorDistancesCm {
        let conv = |mm: u16| if mm == 0 { None } else { Some(mm as f32 / 10.0) };
        SensorDistancesCm {
            fc: conv(self.fc),
            fl: conv(self.fl),
            fr: conv(self.fr),
            rl: conv(self.rl),
            rr: conv(self.rr),
        }
    }
}

#[derive(Copy, Clone, Debug, Default, PartialEq)]
pub struct SensorDistancesCm {
    pub fc: Option<f32>,
    pub fl: Option<f32>,
    pub fr: Option<f32>,
    pub rl: Option<f32>,
    pub rr: Option<f32>,
}

// ═══════════════════════════════════════════════════════════════════════════
// Frame encoding
// ═══════════════════════════════════════════════════════════════════════════

pub fn encode_frame(jpeg: &[u8]) -> Result<Vec<u8>> {
    if jpeg.len() > MAX_FRAME_SIZE {
        return Err(ProtocolError::FrameTooLarge {
            size: jpeg.len(),
            max: MAX_FRAME_SIZE,
        });
    }
    let mut out = Vec::with_capacity(FRAME_HEADER_SIZE + jpeg.len());
    out.extend_from_slice(&(jpeg.len() as u32).to_be_bytes());
    out.extend_from_slice(jpeg);
    Ok(out)
}

/// Encode JPEG payload prefixed with sensor header.
/// Wire format: `[4-byte total_size][20-byte sensors][JPEG]`
pub fn encode_frame_with_sensors(jpeg: &[u8], sensors: &SensorData) -> Result<Vec<u8>> {
    let payload_size = SENSOR_HEADER_SIZE + jpeg.len();
    if payload_size > MAX_FRAME_SIZE {
        return Err(ProtocolError::FrameTooLarge {
            size: payload_size,
            max: MAX_FRAME_SIZE,
        });
    }
    let mut out = Vec::with_capacity(FRAME_HEADER_SIZE + payload_size);
    out.extend_from_slice(&(payload_size as u32).to_be_bytes());
    out.extend_from_slice(&sensors.to_bytes());
    out.extend_from_slice(jpeg);
    Ok(out)
}

pub fn decode_frame_size(header: &[u8]) -> Result<u32> {
    if header.len() != FRAME_HEADER_SIZE {
        return Err(ProtocolError::InvalidLength {
            expected: FRAME_HEADER_SIZE,
            got: header.len(),
        });
    }
    Ok(u32::from_be_bytes([header[0], header[1], header[2], header[3]]))
}

/// Given a payload (after the 4-byte size header has been consumed), pull the
/// sensor header if its magic is present, otherwise treat the whole payload as JPEG.
/// Returns `(sensors, jpeg_slice)`. Backward-compatible with plain-JPEG payloads.
pub fn decode_frame_payload(data: &[u8]) -> (SensorData, &[u8]) {
    if data.len() >= SENSOR_HEADER_SIZE && data[..2] == SENSOR_MAGIC {
        match SensorData::from_bytes(&data[..SENSOR_HEADER_SIZE]) {
            Ok(sensors) => (sensors, &data[SENSOR_HEADER_SIZE..]),
            Err(_) => (SensorData::empty(), data),
        }
    } else {
        (SensorData::empty(), data)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests — fixtures generated by Python (see tools/protocol_fixtures.py)
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    // ----- Direction -----

    #[test]
    fn direction_round_trip_all_valid() {
        for (byte, dir) in [
            (0u8, Direction::Backward),
            (1u8, Direction::Forward),
            (2u8, Direction::Stop),
        ] {
            assert_eq!(Direction::from_u8(byte).unwrap(), dir);
            assert_eq!(dir as u8, byte);
        }
    }

    #[test]
    fn direction_rejects_invalid() {
        for bad in [3u8, 4, 127, 255] {
            assert_eq!(
                Direction::from_u8(bad),
                Err(ProtocolError::InvalidDirection(bad))
            );
        }
    }

    // ----- MotorCommand against Python-generated fixtures -----

    #[test]
    fn motor_command_fwd_190_2000_matches_python() {
        // Python: MotorCommand(190, 190, FORWARD, FORWARD, 2000) → [190, 190, 1, 1, 7, 208]
        let cmd = MotorCommand::forward(190, 2000);
        assert_eq!(cmd.to_bytes(), [190, 190, 1, 1, 7, 208]);
    }

    #[test]
    fn motor_command_rotate_right_matches_python() {
        // Python: MotorCommand(220, 220, FORWARD, BACKWARD, 1800) → [220, 220, 1, 0, 7, 8]
        let cmd = MotorCommand::rotate_right(220, 1800);
        assert_eq!(cmd.to_bytes(), [220, 220, 1, 0, 7, 8]);
    }

    #[test]
    fn motor_command_rotate_left_matches_python() {
        // Python: MotorCommand(220, 220, BACKWARD, FORWARD, 1050) → [220, 220, 0, 1, 4, 26]
        let cmd = MotorCommand::rotate_left(220, 1050);
        assert_eq!(cmd.to_bytes(), [220, 220, 0, 1, 4, 26]);
    }

    #[test]
    fn motor_command_stop_matches_python() {
        // Python: MotorCommand.stop() → [0, 0, 2, 2, 0, 0]
        assert_eq!(MotorCommand::stop().to_bytes(), [0, 0, 2, 2, 0, 0]);
    }

    #[test]
    fn motor_command_max_duration_matches_python() {
        // Python: MotorCommand(150, 150, BACKWARD, BACKWARD, 65535) → [150, 150, 0, 0, 255, 255]
        let cmd = MotorCommand::backward(150, 65535);
        assert_eq!(cmd.to_bytes(), [150, 150, 0, 0, 255, 255]);
    }

    #[test]
    fn motor_command_asymmetric_curve_matches_python() {
        // Python: MotorCommand(200, 150, FORWARD, FORWARD, 1500) → [200, 150, 1, 1, 5, 220]
        let cmd = MotorCommand {
            left_speed: 200,
            right_speed: 150,
            left_dir: Direction::Forward,
            right_dir: Direction::Forward,
            duration_ms: 1500,
        };
        assert_eq!(cmd.to_bytes(), [200, 150, 1, 1, 5, 220]);
    }

    #[test]
    fn motor_command_round_trip() {
        let samples = [
            MotorCommand::forward(190, 2000),
            MotorCommand::rotate_right(220, 1800),
            MotorCommand::rotate_left(220, 1050),
            MotorCommand::stop(),
            MotorCommand::backward(150, 65535),
        ];
        for cmd in samples {
            let bytes = cmd.to_bytes();
            let decoded = MotorCommand::from_bytes(&bytes).unwrap();
            assert_eq!(cmd, decoded);
        }
    }

    #[test]
    fn motor_command_rejects_short_buffer() {
        assert!(matches!(
            MotorCommand::from_bytes(&[0, 0, 0]),
            Err(ProtocolError::InvalidLength { expected: 6, got: 3 })
        ));
    }

    #[test]
    fn motor_command_rejects_invalid_direction_byte() {
        let bytes = [100u8, 100, 1, 9, 0, 0]; // right_dir=9 is invalid
        assert!(matches!(
            MotorCommand::from_bytes(&bytes),
            Err(ProtocolError::InvalidDirection(9))
        ));
    }

    // ----- SensorData against Python-generated fixtures -----

    #[test]
    fn sensor_typical_matches_python() {
        // Python: SensorData(fc=0, fl=627, fr=537, rl=0, rr=90)
        //   → [83, 1, 0, 0, 2, 115, 2, 25, 0, 0, 0, 90, 0, 0, 0, 0, 0, 0, 0, 0]
        let s = SensorData { fc: 0, fl: 627, fr: 537, rl: 0, rr: 90 };
        assert_eq!(
            s.to_bytes(),
            [83, 1, 0, 0, 2, 115, 2, 25, 0, 0, 0, 90, 0, 0, 0, 0, 0, 0, 0, 0]
        );
    }

    #[test]
    fn sensor_empty_matches_python() {
        // Python: SensorData.empty() — all zeros except magic
        let b = SensorData::empty().to_bytes();
        assert_eq!(b[0..2], SENSOR_MAGIC);
        assert!(b[2..].iter().all(|&x| x == 0));
    }

    #[test]
    fn sensor_max_u16_matches_python() {
        let s = SensorData { fc: 65535, fl: 65535, fr: 65535, rl: 65535, rr: 65535 };
        let expected = [
            83, 1, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 0, 0, 0, 0, 0, 0, 0, 0,
        ];
        assert_eq!(s.to_bytes(), expected);
    }

    #[test]
    fn sensor_mixed_matches_python() {
        // Python: SensorData(fc=1234, fl=0, fr=9999, rl=500, rr=0)
        let s = SensorData { fc: 1234, fl: 0, fr: 9999, rl: 500, rr: 0 };
        let expected = [
            83, 1, 4, 210, 0, 0, 39, 15, 1, 244, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        ];
        assert_eq!(s.to_bytes(), expected);
    }

    #[test]
    fn sensor_round_trip() {
        let samples = [
            SensorData { fc: 0, fl: 627, fr: 537, rl: 0, rr: 90 },
            SensorData::empty(),
            SensorData { fc: 1234, fl: 0, fr: 9999, rl: 500, rr: 0 },
        ];
        for s in samples {
            let bytes = s.to_bytes();
            let decoded = SensorData::from_bytes(&bytes).unwrap();
            assert_eq!(s, decoded);
        }
    }

    #[test]
    fn sensor_rejects_bad_magic() {
        let mut bytes = [0u8; 20];
        bytes[0] = 0xAA;
        bytes[1] = 0xBB;
        assert!(matches!(
            SensorData::from_bytes(&bytes),
            Err(ProtocolError::InvalidSensorMagic(..))
        ));
    }

    #[test]
    fn sensor_to_cm_converts_and_drops_zeros() {
        let s = SensorData { fc: 0, fl: 627, fr: 537, rl: 0, rr: 90 };
        let cm = s.to_cm();
        assert_eq!(cm.fc, None);
        assert_eq!(cm.fl, Some(62.7));
        assert_eq!(cm.fr, Some(53.7));
        assert_eq!(cm.rl, None);
        assert_eq!(cm.rr, Some(9.0));
    }

    // ----- Frame encoding against Python-generated fixtures -----

    const JPEG_FIXTURE: &[u8] = &[255, 216, 255, 224, 0, 16, 74, 70, 73, 70, 0, 1];

    #[test]
    fn encode_frame_size_header_matches_python() {
        // Python: encode_frame(JPEG_FIXTURE) — first 8 bytes = [0, 0, 0, 12, 255, 216, 255, 224]
        let out = encode_frame(JPEG_FIXTURE).unwrap();
        assert_eq!(&out[..8], &[0, 0, 0, 12, 255, 216, 255, 224]);
        assert_eq!(out.len(), 16);
    }

    #[test]
    fn encode_frame_with_sensors_matches_python() {
        // Python fixture result — first 24 bytes:
        //   [0, 0, 0, 32, 83, 1, 0, 100, 0, 200, 1, 44, 0, 0, 1, 144, 0, 0, 0, 0, 0, 0, 0, 0]
        let s = SensorData { fc: 100, fl: 200, fr: 300, rl: 0, rr: 400 };
        let out = encode_frame_with_sensors(JPEG_FIXTURE, &s).unwrap();
        let expected_prefix = [
            0, 0, 0, 32, 83, 1, 0, 100, 0, 200, 1, 44, 0, 0, 1, 144, 0, 0, 0, 0, 0, 0, 0, 0,
        ];
        assert_eq!(&out[..24], &expected_prefix);
        assert_eq!(out.len(), 36);
    }

    #[test]
    fn decode_frame_size_reads_big_endian() {
        assert_eq!(decode_frame_size(&[0, 0, 0, 12]).unwrap(), 12);
        assert_eq!(decode_frame_size(&[0, 0, 1, 0]).unwrap(), 256);
        assert_eq!(decode_frame_size(&[0xFF, 0xFF, 0xFF, 0xFF]).unwrap(), u32::MAX);
    }

    #[test]
    fn decode_frame_payload_with_sensor_header() {
        let s = SensorData { fc: 100, fl: 200, fr: 300, rl: 0, rr: 400 };
        let out = encode_frame_with_sensors(JPEG_FIXTURE, &s).unwrap();
        // Skip the 4-byte size header to get just the payload
        let (sensors, jpeg) = decode_frame_payload(&out[FRAME_HEADER_SIZE..]);
        assert_eq!(sensors, s);
        assert_eq!(jpeg, JPEG_FIXTURE);
    }

    #[test]
    fn decode_frame_payload_backward_compat_plain_jpeg() {
        // Old-style: payload has no sensor header, it's just the JPEG.
        let (sensors, jpeg) = decode_frame_payload(JPEG_FIXTURE);
        assert_eq!(sensors, SensorData::empty());
        assert_eq!(jpeg, JPEG_FIXTURE);
    }

    #[test]
    fn encode_frame_rejects_oversize() {
        let giant = vec![0u8; MAX_FRAME_SIZE + 1];
        assert!(matches!(
            encode_frame(&giant),
            Err(ProtocolError::FrameTooLarge { .. })
        ));
    }
}
