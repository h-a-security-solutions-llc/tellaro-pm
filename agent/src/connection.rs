use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::sync::mpsc;
use tokio::time;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

use crate::claude::StreamEvent;
use crate::doctor;
use crate::log_stream;
use crate::provision::ExchangeResponse;
use crate::worker;

const HEARTBEAT_INTERVAL: Duration = Duration::from_secs(30);
const LOG_FLUSH_INTERVAL: Duration = Duration::from_secs(10);
const DOCTOR_INTERVAL: Duration = Duration::from_secs(3600); // 1 hour
const RECONNECT_DELAY: Duration = Duration::from_secs(5);
const MAX_RECONNECT_DELAY: Duration = Duration::from_secs(300);

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type")]
enum WsMessage {
    #[serde(rename = "heartbeat")]
    Heartbeat { agent_id: String, status: String },
    #[serde(rename = "work_item_dispatch")]
    WorkItemDispatch {
        work_item: serde_json::Value,
    },
    #[serde(rename = "work_dispatch")]
    WorkDispatch {
        work_item_id: String,
        instruction: String,
        working_directory: Option<String>,
        persona_id: Option<String>,
    },
    #[serde(rename = "work_result")]
    WorkResult {
        work_item_id: String,
        status: String,
        output: Option<String>,
    },
    #[serde(rename = "persona_sync")]
    PersonaSync {
        #[allow(dead_code)]
        personas: Vec<serde_json::Value>,
    },
    #[serde(rename = "heartbeat_ack")]
    HeartbeatAck,
    #[serde(rename = "work_item_ack")]
    WorkItemAck {
        #[allow(dead_code)]
        work_item_id: String,
        #[allow(dead_code)]
        status: Option<String>,
    },
    #[serde(rename = "capability_ack")]
    CapabilityAck,
    #[serde(rename = "error")]
    Error { message: String },
}

pub async fn run(server: &str, provision: &ExchangeResponse) -> anyhow::Result<()> {
    let mut reconnect_delay = RECONNECT_DELAY;

    loop {
        match connect_and_run(server, provision).await {
            Ok(()) => {
                // Server closed the connection gracefully — reconnect after a short delay.
                // The agent should never voluntarily exit; only SIGTERM/SIGINT stops it.
                info!("Server closed connection; reconnecting in {}s...", RECONNECT_DELAY.as_secs());
                reconnect_delay = RECONNECT_DELAY; // reset backoff on clean close
                time::sleep(reconnect_delay).await;
            }
            Err(e) => {
                error!("Connection error: {e}");
                warn!("Reconnecting in {}s...", reconnect_delay.as_secs());
                time::sleep(reconnect_delay).await;
                // Exponential backoff capped at MAX_RECONNECT_DELAY
                reconnect_delay = (reconnect_delay * 2).min(MAX_RECONNECT_DELAY);
            }
        }
    }
}

async fn connect_and_run(server: &str, provision: &ExchangeResponse) -> anyhow::Result<()> {
    // Convert http(s) to ws(s)
    let ws_url = server
        .replace("https://", "wss://")
        .replace("http://", "ws://");
    let url = format!(
        "{ws_url}/ws/agent?token={}&agent_id={}",
        urlencoding::encode(&provision.access_token),
        urlencoding::encode(&provision.agent_id),
    );

    info!("Connecting to WebSocket...");
    let (ws_stream, _) = connect_async(&url).await?;
    info!("WebSocket connected");

    let (mut write, mut read) = ws_stream.split();

    let agent_id = provision.agent_id.clone();
    let mut heartbeat_interval = time::interval(HEARTBEAT_INTERVAL);
    let mut log_flush_interval = time::interval(LOG_FLUSH_INTERVAL);
    let mut doctor_interval = time::interval(DOCTOR_INTERVAL);
    // Skip immediate first ticks
    log_flush_interval.tick().await;
    doctor_interval.tick().await;

    // Channel for worker tasks to send stream events back to the WS writer
    let (stream_tx, mut stream_rx) = mpsc::unbounded_channel::<StreamMessage>();

    // Send initial heartbeat
    let hb = WsMessage::Heartbeat {
        agent_id: agent_id.clone(),
        status: "online".to_string(),
    };
    write
        .send(Message::Text(serde_json::to_string(&hb)?))
        .await?;

    loop {
        tokio::select! {
            // Incoming messages from server
            msg = read.next() => {
                match msg {
                    Some(Ok(Message::Text(text))) => {
                        handle_message(&text, &agent_id, &stream_tx).await;
                    }
                    Some(Ok(Message::Ping(data))) => {
                        write.send(Message::Pong(data)).await?;
                    }
                    Some(Ok(Message::Close(_))) | None => {
                        info!("Server closed connection");
                        return Ok(());
                    }
                    Some(Err(e)) => {
                        return Err(e.into());
                    }
                    _ => {}
                }
            }

            // Stream events from worker tasks → WebSocket
            Some(stream_msg) = stream_rx.recv() => {
                let json = serde_json::to_string(&stream_msg.payload);
                if let Ok(json_str) = json {
                    if let Err(e) = write.send(Message::Text(json_str)).await {
                        error!("Failed to send stream message: {e}");
                    }
                }
            }

            // Periodic heartbeat
            _ = heartbeat_interval.tick() => {
                let active_items = worker::active_work_item_ids();
                let status = if active_items.is_empty() { "online" } else { "busy" };
                let hb = WsMessage::Heartbeat {
                    agent_id: agent_id.clone(),
                    status: status.to_string(),
                };
                if let Err(e) = write.send(Message::Text(serde_json::to_string(&hb)?)).await {
                    error!("Failed to send heartbeat: {e}");
                    return Err(e.into());
                }
            }

            // Flush buffered logs to the backend
            _ = log_flush_interval.tick() => {
                let entries = log_stream::drain_logs();
                if !entries.is_empty() {
                    let msg = serde_json::json!({
                        "type": "log_batch",
                        "entries": entries,
                    });
                    if let Err(e) = write.send(Message::Text(msg.to_string())).await {
                        error!("Failed to send log batch: {e}");
                    }
                }
            }

            // Periodic claude doctor (spawned so it never blocks the WS loop)
            _ = doctor_interval.tick() => {
                tokio::spawn(async {
                    info!("Running periodic claude doctor check...");
                    if let Err(e) = doctor::run_doctor(true).await {
                        warn!("Doctor check failed: {e}");
                    }
                });
            }
        }
    }
}

/// A message from a worker task that should be sent over the WebSocket.
struct StreamMessage {
    payload: serde_json::Value,
}

/// Extract work item fields from a work_item_dispatch message.
fn extract_work_dispatch(work_item: &serde_json::Value) -> Option<(String, String, Option<String>, Option<String>, Option<String>)> {
    let id = work_item.get("id")?.as_str()?.to_string();
    let instruction = work_item.get("instruction")?.as_str()?.to_string();
    let working_directory = work_item.get("working_directory").and_then(|v| v.as_str()).map(|s| s.to_string());
    let persona_id = work_item.get("persona_id").and_then(|v| v.as_str()).map(|s| s.to_string());
    let chat_session_id = work_item.get("chat_session_id").and_then(|v| v.as_str()).map(|s| s.to_string());
    Some((id, instruction, working_directory, persona_id, chat_session_id))
}

async fn handle_message(
    text: &str,
    _agent_id: &str,
    stream_tx: &mpsc::UnboundedSender<StreamMessage>,
) {
    match serde_json::from_str::<WsMessage>(text) {
        Ok(WsMessage::WorkItemDispatch { work_item }) => {
            // New-style dispatch from manager with full work_item object
            if let Some((work_item_id, instruction, working_directory, persona_id, chat_session_id)) =
                extract_work_dispatch(&work_item)
            {
                info!(work_item_id = %work_item_id, "Received work_item_dispatch");
                spawn_streaming_worker(
                    work_item_id,
                    instruction,
                    working_directory,
                    persona_id,
                    chat_session_id,
                    stream_tx.clone(),
                );
            } else {
                warn!("work_item_dispatch missing required fields: {work_item}");
            }
        }
        Ok(WsMessage::WorkDispatch {
            work_item_id,
            instruction,
            working_directory,
            persona_id,
        }) => {
            // Legacy dispatch format
            info!(work_item_id = %work_item_id, "Received work dispatch (legacy)");
            spawn_streaming_worker(
                work_item_id,
                instruction,
                working_directory,
                persona_id,
                None,
                stream_tx.clone(),
            );
        }
        Ok(WsMessage::PersonaSync { personas }) => {
            info!("Received persona sync ({} personas)", personas.len());
        }
        Ok(WsMessage::HeartbeatAck) => {}
        Ok(WsMessage::WorkItemAck { .. }) => {}
        Ok(WsMessage::CapabilityAck) => {}
        Ok(WsMessage::Error { message }) => {
            error!("Server error: {message}");
        }
        Ok(_) => {}
        Err(e) => {
            warn!("Failed to parse message: {e}, raw: {text}");
        }
    }
}

fn spawn_streaming_worker(
    work_item_id: String,
    instruction: String,
    working_directory: Option<String>,
    persona_id: Option<String>,
    chat_session_id: Option<String>,
    stream_tx: mpsc::UnboundedSender<StreamMessage>,
) {
    let has_chat = chat_session_id.is_some();

    tokio::spawn(async move {
        if has_chat {
            // Use streaming mode for chat-bound work items
            let _ = stream_tx.send(StreamMessage {
                payload: serde_json::json!({
                    "type": "stream_start",
                    "work_item_id": &work_item_id,
                    "chat_session_id": &chat_session_id,
                }),
            });

            // Update status to running
            let _ = stream_tx.send(StreamMessage {
                payload: serde_json::json!({
                    "type": "work_item_update",
                    "work_item_id": &work_item_id,
                    "status": "running",
                }),
            });

            let (mut rx, handle) = worker::execute_work_item_streaming(
                &work_item_id,
                &instruction,
                working_directory.as_deref(),
                persona_id.as_deref(),
            )
            .await;

            // Forward stream events to WebSocket
            let mut full_output = String::new();
            while let Some(event) = rx.recv().await {
                match event {
                    StreamEvent::Chunk(text) => {
                        let _ = stream_tx.send(StreamMessage {
                            payload: serde_json::json!({
                                "type": "stream_chunk",
                                "work_item_id": &work_item_id,
                                "chat_session_id": &chat_session_id,
                                "content": &text,
                            }),
                        });
                    }
                    StreamEvent::Done(output) => {
                        full_output = output;
                    }
                    StreamEvent::Error(err) => {
                        error!(work_item_id = %work_item_id, "Stream error: {err}");
                    }
                }
            }

            // Wait for the task to complete
            let result = handle.await;

            let (status, output) = match result {
                Ok(Ok(output)) => ("completed", output),
                Ok(Err(e)) => ("failed", format!("Error: {e}")),
                Err(e) => ("failed", format!("Task panicked: {e}")),
            };

            if status == "completed" && full_output.is_empty() {
                full_output = output.clone();
            }

            // Send stream_end with final content
            let _ = stream_tx.send(StreamMessage {
                payload: serde_json::json!({
                    "type": "stream_end",
                    "work_item_id": &work_item_id,
                    "chat_session_id": &chat_session_id,
                    "content": &full_output,
                }),
            });

            // Send final work item update
            let _ = stream_tx.send(StreamMessage {
                payload: serde_json::json!({
                    "type": "work_item_update",
                    "work_item_id": &work_item_id,
                    "status": status,
                    "output": if status == "completed" { &full_output } else { &output },
                }),
            });
        } else {
            // Non-chat work items: use batch mode
            let result = worker::execute_work_item(
                &work_item_id,
                &instruction,
                working_directory.as_deref(),
                persona_id.as_deref(),
            )
            .await;

            let (status, output) = match result {
                Ok(output) => ("completed", output),
                Err(e) => ("failed", format!("Error: {e}")),
            };

            let _ = stream_tx.send(StreamMessage {
                payload: serde_json::json!({
                    "type": "work_item_update",
                    "work_item_id": &work_item_id,
                    "status": status,
                    "output": output,
                }),
            });
        }
    });
}
