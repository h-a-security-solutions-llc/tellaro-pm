mod claude;
mod config;
mod connection;
mod doctor;
mod install;
mod log_stream;
mod mcp;
mod provision;
mod worker;

use clap::{Parser, Subcommand};
use tracing::{info, warn};

#[derive(Parser)]
#[command(name = "tellaro-pm-agent", version, about = "Tellaro PM Agent Daemon")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Provision, install, and start the agent daemon
    Start {
        /// Provisioning token from the Tellaro PM UI
        #[arg(short, long, env = "TELLARO_PROVISION_TOKEN")]
        token: String,

        /// Backend server URL
        #[arg(short, long, env = "TELLARO_SERVER_URL", default_value = "https://pm.tellaro.io")]
        server: String,

        /// Agent display name
        #[arg(short, long, env = "TELLARO_AGENT_NAME")]
        name: Option<String>,

        /// Skip self-installation and auto-start registration
        #[arg(long)]
        no_install: bool,
    },

    /// Reconnect using saved config (used by the auto-start entry)
    Run,

    /// Uninstall the agent: stop the service, remove auto-start, delete binary and config
    Uninstall,

    /// Manage MCP servers
    Mcp {
        #[command(subcommand)]
        action: McpAction,
    },

    /// Run claude doctor and report results
    Doctor {
        /// Attempt automatic self-healing
        #[arg(long)]
        heal: bool,
    },

    /// Show where the agent is installed and its current status
    Status,
}

#[derive(Subcommand)]
enum McpAction {
    /// List installed MCP servers
    List,
    /// Install an MCP server
    Install {
        /// MCP server name (e.g., "filesystem", "github")
        name: String,
    },
    /// Uninstall an MCP server
    Uninstall {
        /// MCP server name
        name: String,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    use tracing_subscriber::layer::SubscriberExt;
    use tracing_subscriber::util::SubscriberInitExt;

    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .with(tracing_subscriber::fmt::layer())
        .with(log_stream::LogStreamLayer)
        .init();

    let cli = Cli::parse();

    match cli.command {
        Commands::Start {
            token,
            server,
            name,
            no_install,
        } => {
            let agent_name = name.unwrap_or_else(|| {
                let hostname = hostname::get()
                    .map(|h| h.to_string_lossy().to_string())
                    .unwrap_or_else(|_| "unknown".to_string());
                format!("agent-{hostname}")
            });

            info!("Starting Tellaro agent '{agent_name}'...");

            // 1. Exchange provisioning token for JWT
            let provision_result =
                provision::exchange_token(&server, &token, &agent_name).await?;
            info!(
                agent_id = %provision_result.agent_id,
                "Provisioned successfully"
            );

            // 2. Install binary and register auto-start
            if !no_install {
                match install::install_and_autostart() {
                    Ok(()) => info!("Agent installed for auto-start on login"),
                    Err(e) => warn!("Auto-install failed (continuing anyway): {e}"),
                }
            }

            // 3. Connect WebSocket and run main loop
            connection::run(&server, &provision_result).await?;
        }

        Commands::Run => {
            let config = config::AgentConfig::load().map_err(|e| {
                anyhow::anyhow!(
                    "No saved config found at {:?}. Run 'tellaro-pm-agent start' first. ({e})",
                    config::AgentConfig::config_path()
                )
            })?;

            info!(
                agent_id = %config.agent_id,
                server = %config.server_url,
                "Reconnecting agent '{}'...",
                config.agent_name,
            );

            let provision_result = provision::ExchangeResponse {
                access_token: config.access_token,
                agent_id: config.agent_id,
                expires_in: 0,
            };

            connection::run(&config.server_url, &provision_result).await?;
        }

        Commands::Uninstall => {
            info!("Uninstalling Tellaro agent...");
            install::uninstall()?;
            println!("Tellaro PM agent has been uninstalled.");
        }

        Commands::Mcp { action } => match action {
            McpAction::List => mcp::list_servers().await?,
            McpAction::Install { name } => mcp::install_server(&name).await?,
            McpAction::Uninstall { name } => mcp::uninstall_server(&name).await?,
        },

        Commands::Doctor { heal } => {
            doctor::run_doctor(heal).await?;
        }

        Commands::Status => {
            print_status();
        }
    }

    Ok(())
}

fn print_status() {
    println!("Tellaro PM Agent Status");
    println!("{}", "-".repeat(40));

    // Installation
    let bin = install::install_dir().join(if cfg!(target_os = "windows") {
        "tellaro-pm-agent.exe"
    } else {
        "tellaro-pm-agent"
    });
    if bin.exists() {
        println!("Installed:  {}", bin.display());
    } else {
        println!("Installed:  not installed");
    }

    // Config
    let config_path = config::AgentConfig::config_path();
    match config::AgentConfig::load() {
        Ok(cfg) => {
            println!("Config:     {}", config_path.display());
            println!("Server:     {}", cfg.server_url);
            println!("Agent ID:   {}", cfg.agent_id);
            println!("Agent Name: {}", cfg.agent_name);
        }
        Err(_) => {
            println!("Config:     not found");
        }
    }

    // Platform auto-start
    println!("Platform:   {}/{}", std::env::consts::OS, std::env::consts::ARCH);
    println!(
        "Auto-start: {}",
        if install::is_installed() {
            "registered"
        } else {
            "not registered"
        }
    );
}
