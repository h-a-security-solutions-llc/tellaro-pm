use serde::{Deserialize, Serialize};
use tracing::info;

use crate::config::AgentConfig;

#[derive(Debug, Serialize)]
struct ExchangeRequest {
    token: String,
    name: String,
    machine_info: MachineInfo,
    capabilities: Vec<String>,
}

#[derive(Debug, Serialize)]
struct MachineInfo {
    os: String,
    arch: String,
    hostname: String,
}

#[derive(Debug, Deserialize)]
pub struct ExchangeResponse {
    pub access_token: String,
    pub agent_id: String,
    #[allow(dead_code)]
    pub expires_in: u64,
}

pub async fn exchange_token(
    server: &str,
    token: &str,
    name: &str,
) -> anyhow::Result<ExchangeResponse> {
    let hostname = hostname::get()
        .map(|h| h.to_string_lossy().to_string())
        .unwrap_or_else(|_| "unknown".to_string());

    let body = ExchangeRequest {
        token: token.to_string(),
        name: name.to_string(),
        machine_info: MachineInfo {
            os: std::env::consts::OS.to_string(),
            arch: std::env::consts::ARCH.to_string(),
            hostname: hostname.clone(),
        },
        capabilities: detect_capabilities(),
    };

    let url = format!("{server}/api/v1/agents/provisioning/exchange");
    info!("Exchanging provisioning token at {url}...");

    let client = reqwest::Client::new();
    let resp = client.post(&url).json(&body).send().await?;

    if !resp.status().is_success() {
        let status = resp.status();
        let text = resp.text().await.unwrap_or_default();
        anyhow::bail!("Provisioning failed ({status}): {text}");
    }

    let result: ExchangeResponse = resp.json().await?;

    // Save config locally for reconnection
    let config = AgentConfig {
        server_url: server.to_string(),
        agent_id: result.agent_id.clone(),
        access_token: result.access_token.clone(),
        agent_name: name.to_string(),
    };
    config.save()?;
    info!("Agent config saved to {:?}", AgentConfig::config_path());

    Ok(result)
}

fn detect_capabilities() -> Vec<String> {
    let mut caps = vec!["claude-code".to_string()];

    if which::which("git").is_ok() {
        caps.push("git".to_string());
    }
    if which::which("node").is_ok() || which::which("nodejs").is_ok() {
        caps.push("node".to_string());
    }
    if which::which("python3").is_ok() || which::which("python").is_ok() {
        caps.push("python".to_string());
    }
    if which::which("docker").is_ok() {
        caps.push("docker".to_string());
    }
    if which::which("cargo").is_ok() {
        caps.push("rust".to_string());
    }

    caps
}
