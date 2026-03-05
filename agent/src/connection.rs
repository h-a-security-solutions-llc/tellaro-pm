use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::time;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

use crate::doctor;
use crate::provision::ExchangeResponse;
use crate::worker;

const HEARTBEAT_INTERVAL: Duration = Duration::from_secs(30);
const DOCTOR_INTERVAL: Duration = Duration::from_secs(3600); // 1 hour
const RECONNECT_DELAY: Duration = Duration::from_secs(5);
const MAX_RECONNECT_DELAY: Duration = Duration::from_secs(300);

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type")]
enum WsMessage {
    #[serde(rename = "heartbeat")]
    Heartbeat { agent_id: String, status: String },
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
    #[serde(rename = "error")]
    Error { message: String },
}

pub async fn run(server: &str, provision: &ExchangeResponse) -> anyhow::Result<()> {
    let mut reconnect_delay = RECONNECT_DELAY;

    loop {
        match connect_and_run(server, provision).await {
            Ok(()) => {
                info!("Connection closed gracefully");
                break;
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

    Ok(())
}

async fn connect_and_run(server: &str, provision: &ExchangeResponse) -> anyhow::Result<()> {
    // Convert http(s) to ws(s)
    let ws_url = server
        .replace("https://", "wss://")
        .replace("http://", "ws://");
    let url = format!(
        "{ws_url}/ws/agent?token={}",
        urlencoding::encode(&provision.access_token)
    );

    info!("Connecting to WebSocket...");
    let (ws_stream, _) = connect_async(&url).await?;
    info!("WebSocket connected");

    let (mut write, mut read) = ws_stream.split();

    let agent_id = provision.agent_id.clone();
    let mut heartbeat_interval = time::interval(HEARTBEAT_INTERVAL);
    let mut doctor_interval = time::interval(DOCTOR_INTERVAL);

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
                        handle_message(&text, &agent_id, &mut write).await;
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

            // Periodic claude doctor
            _ = doctor_interval.tick() => {
                info!("Running periodic claude doctor check...");
                if let Err(e) = doctor::run_doctor(true).await {
                    warn!("Doctor check failed: {e}");
                }
            }
        }
    }
}

async fn handle_message(
    text: &str,
    _agent_id: &str,
    _write: &mut futures_util::stream::SplitSink<
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
        Message,
    >,
) {
    match serde_json::from_str::<WsMessage>(text) {
        Ok(WsMessage::WorkDispatch {
            work_item_id,
            instruction,
            working_directory,
            persona_id,
        }) => {
            info!(work_item_id = %work_item_id, "Received work dispatch");

            // Spawn a worker task
            let item_id = work_item_id.clone();
            tokio::spawn(async move {
                let result =
                    worker::execute_work_item(&item_id, &instruction, working_directory.as_deref(), persona_id.as_deref())
                        .await;

                match result {
                    Ok(output) => {
                        info!(work_item_id = %item_id, "Work item completed");
                        // Result will be sent back via the worker's own reporting
                        let _ = output;
                    }
                    Err(e) => {
                        error!(work_item_id = %item_id, "Work item failed: {e}");
                    }
                }
            });
        }
        Ok(WsMessage::Error { message }) => {
            error!("Server error: {message}");
        }
        Ok(_) => {}
        Err(e) => {
            warn!("Failed to parse message: {e}, raw: {text}");
        }
    }
}
