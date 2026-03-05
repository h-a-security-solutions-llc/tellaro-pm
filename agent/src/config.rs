use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Persistent agent configuration stored locally after provisioning.
#[derive(Debug, Serialize, Deserialize)]
pub struct AgentConfig {
    pub server_url: String,
    pub agent_id: String,
    pub access_token: String,
    pub agent_name: String,
}

impl AgentConfig {
    pub fn config_dir() -> PathBuf {
        dirs::config_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("tellaro-pm-agent")
    }

    pub fn config_path() -> PathBuf {
        Self::config_dir().join("config.json")
    }

    pub fn save(&self) -> anyhow::Result<()> {
        let dir = Self::config_dir();
        std::fs::create_dir_all(&dir)?;
        let json = serde_json::to_string_pretty(self)?;
        std::fs::write(Self::config_path(), json)?;
        Ok(())
    }

    pub fn load() -> anyhow::Result<Self> {
        let data = std::fs::read_to_string(Self::config_path())?;
        Ok(serde_json::from_str(&data)?)
    }
}
