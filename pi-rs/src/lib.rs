//! robotcar-pi library — shared by the main binary and the `test_*` binaries.

pub mod config;
pub mod motors;
pub mod protocol;
pub mod sensors;

use std::io::Write;

use chrono::Local;
use log::LevelFilter;

/// Python-logger-compatible format: "YYYY-MM-DD HH:MM:SS - module - LEVEL - message".
/// Matched byte-for-byte with `shared/utils.py::setup_logging` so logs grep
/// identically across the Python and Rust versions during migration.
pub fn init_logging() {
    env_logger::Builder::new()
        .format(|buf, record| {
            writeln!(
                buf,
                "{} - {} - {} - {}",
                Local::now().format("%Y-%m-%d %H:%M:%S"),
                record.target(),
                record.level(),
                record.args()
            )
        })
        .filter_level(LevelFilter::Info)
        .parse_env("ROBOTCAR_LOG")
        .init();
}

pub fn hostname() -> Option<String> {
    std::fs::read_to_string("/etc/hostname")
        .ok()
        .map(|s| s.trim().to_string())
}
