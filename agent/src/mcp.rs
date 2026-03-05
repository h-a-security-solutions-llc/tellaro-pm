use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use tracing::{info, warn};

#[derive(Debug, Serialize, Deserialize)]
pub struct McpServerConfig {
    pub command: String,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default)]
    pub env: HashMap<String, String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct ClaudeConfig {
    #[serde(default, rename = "mcpServers")]
    mcp_servers: HashMap<String, McpServerConfig>,
}

fn claude_config_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".claude")
        .join("claude_desktop_config.json")
}

fn load_config() -> anyhow::Result<ClaudeConfig> {
    let path = claude_config_path();
    if !path.exists() {
        return Ok(ClaudeConfig {
            mcp_servers: HashMap::new(),
        });
    }
    let data = std::fs::read_to_string(&path)?;
    Ok(serde_json::from_str(&data)?)
}

fn save_config(config: &ClaudeConfig) -> anyhow::Result<()> {
    let path = claude_config_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let json = serde_json::to_string_pretty(config)?;
    std::fs::write(&path, json)?;
    Ok(())
}

/// List all installed MCP servers.
pub async fn list_servers() -> anyhow::Result<()> {
    let config = load_config()?;

    if config.mcp_servers.is_empty() {
        println!("No MCP servers installed.");
        return Ok(());
    }

    println!("Installed MCP servers:");
    println!("{:<20} {:<30} ARGS", "NAME", "COMMAND");
    println!("{}", "-".repeat(70));

    for (name, server) in &config.mcp_servers {
        println!(
            "{:<20} {:<30} {}",
            name,
            server.command,
            server.args.join(" ")
        );
    }

    Ok(())
}

/// Well-known MCP servers and their default configurations.
fn known_servers() -> HashMap<&'static str, McpServerConfig> {
    let mut servers = HashMap::new();

    servers.insert(
        "filesystem",
        McpServerConfig {
            command: "npx".to_string(),
            args: vec![
                "-y".to_string(),
                "@modelcontextprotocol/server-filesystem".to_string(),
            ],
            env: HashMap::new(),
        },
    );

    servers.insert(
        "github",
        McpServerConfig {
            command: "npx".to_string(),
            args: vec![
                "-y".to_string(),
                "@modelcontextprotocol/server-github".to_string(),
            ],
            env: HashMap::new(),
        },
    );

    servers.insert(
        "postgres",
        McpServerConfig {
            command: "npx".to_string(),
            args: vec![
                "-y".to_string(),
                "@modelcontextprotocol/server-postgres".to_string(),
            ],
            env: HashMap::new(),
        },
    );

    servers.insert(
        "slack",
        McpServerConfig {
            command: "npx".to_string(),
            args: vec![
                "-y".to_string(),
                "@modelcontextprotocol/server-slack".to_string(),
            ],
            env: HashMap::new(),
        },
    );

    servers.insert(
        "memory",
        McpServerConfig {
            command: "npx".to_string(),
            args: vec![
                "-y".to_string(),
                "@modelcontextprotocol/server-memory".to_string(),
            ],
            env: HashMap::new(),
        },
    );

    servers
}

/// Install an MCP server by name.
pub async fn install_server(name: &str) -> anyhow::Result<()> {
    let mut config = load_config()?;

    if config.mcp_servers.contains_key(name) {
        warn!("MCP server '{name}' is already installed");
        return Ok(());
    }

    let known = known_servers();
    let server_config = match known.get(name) {
        Some(cfg) => McpServerConfig {
            command: cfg.command.clone(),
            args: cfg.args.clone(),
            env: cfg.env.clone(),
        },
        None => {
            // Try as an npx package name
            info!("Unknown server '{name}', installing as npx package...");
            McpServerConfig {
                command: "npx".to_string(),
                args: vec!["-y".to_string(), name.to_string()],
                env: HashMap::new(),
            }
        }
    };

    config
        .mcp_servers
        .insert(name.to_string(), server_config);
    save_config(&config)?;

    println!("Installed MCP server: {name}");
    Ok(())
}

/// Uninstall an MCP server by name.
pub async fn uninstall_server(name: &str) -> anyhow::Result<()> {
    let mut config = load_config()?;

    if config.mcp_servers.remove(name).is_none() {
        anyhow::bail!("MCP server '{name}' is not installed");
    }

    save_config(&config)?;
    println!("Uninstalled MCP server: {name}");
    Ok(())
}
