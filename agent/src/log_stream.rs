//! Buffered log layer that captures tracing events for streaming to the backend.

use std::sync::Mutex;

use chrono::Utc;
use serde::Serialize;
use tracing::field::{Field, Visit};
use tracing::{Event, Level, Subscriber};
use tracing_subscriber::layer::Context;
use tracing_subscriber::Layer;

/// A single log entry to be sent to the backend.
#[derive(Debug, Clone, Serialize)]
pub struct LogEntry {
    pub level: String,
    pub message: String,
    pub target: String,
    pub timestamp: String,
}

/// Shared buffer of pending log entries.
static LOG_BUFFER: Mutex<Vec<LogEntry>> = Mutex::new(Vec::new());

/// Drain all buffered log entries.
pub fn drain_logs() -> Vec<LogEntry> {
    let mut buf = LOG_BUFFER.lock().unwrap_or_else(|e| e.into_inner());
    std::mem::take(&mut *buf)
}

/// A tracing layer that captures events into `LOG_BUFFER`.
pub struct LogStreamLayer;

impl<S: Subscriber> Layer<S> for LogStreamLayer {
    fn on_event(&self, event: &Event<'_>, _ctx: Context<'_, S>) {
        let metadata = event.metadata();
        let level = match *metadata.level() {
            Level::ERROR => "ERROR",
            Level::WARN => "WARN",
            Level::INFO => "INFO",
            Level::DEBUG => "DEBUG",
            Level::TRACE => "TRACE",
        };

        let mut visitor = MessageVisitor::default();
        event.record(&mut visitor);

        let entry = LogEntry {
            level: level.to_string(),
            message: visitor.message,
            target: metadata.target().to_string(),
            timestamp: Utc::now().to_rfc3339(),
        };

        if let Ok(mut buf) = LOG_BUFFER.lock() {
            // Cap buffer to prevent unbounded memory growth
            if buf.len() < 10_000 {
                buf.push(entry);
            }
        }
    }
}

#[derive(Default)]
struct MessageVisitor {
    message: String,
}

impl Visit for MessageVisitor {
    fn record_debug(&mut self, field: &Field, value: &dyn std::fmt::Debug) {
        if field.name() == "message" {
            self.message = format!("{value:?}");
        } else if self.message.is_empty() {
            self.message = format!("{}: {value:?}", field.name());
        } else {
            self.message
                .push_str(&format!(" {}={value:?}", field.name()));
        }
    }

    fn record_str(&mut self, field: &Field, value: &str) {
        if field.name() == "message" {
            self.message = value.to_string();
        } else if self.message.is_empty() {
            self.message = format!("{}: {value}", field.name());
        } else {
            self.message.push_str(&format!(" {}={value}", field.name()));
        }
    }
}
