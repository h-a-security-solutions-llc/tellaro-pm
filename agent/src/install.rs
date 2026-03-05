//! Self-installation: copies the binary into the user's local directory and
//! registers it to start automatically on login.
//!
//! Platform behaviour:
//!   - **Windows**: Copies to `%LOCALAPPDATA%\TellaroPM\tellaro-pm-agent.exe`,
//!     adds an `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` registry
//!     entry so it launches after login.
//!   - **macOS**: Copies to `~/Library/Application Support/TellaroPM/tellaro-pm-agent`,
//!     writes a LaunchAgent plist at `~/Library/LaunchAgents/io.tellaro.pm-agent.plist`
//!     and loads it via `launchctl`.
//!   - **Linux (native)**: Copies to `~/.local/bin/tellaro-pm-agent`, writes a systemd
//!     user service at `~/.config/systemd/user/tellaro-pm-agent.service` and enables it.
//!   - **Linux (WSL)**: Copies to `~/.local/bin/tellaro-pm-agent`, registers a Windows
//!     startup entry via `cmd.exe /C reg add` that runs
//!     `wsl.exe -d <distro> -- ~/.local/bin/tellaro-pm-agent run`.
//!     WSL has no login session of its own — it starts when Windows opens it, so
//!     auto-start must be driven from the Windows side.
//!
//! The installed binary is invoked with `run` (not `start`) so it reconnects
//! using the saved config rather than requiring a provisioning token each boot.

use std::path::{Path, PathBuf};
use tracing::{info, warn};

use crate::config::AgentConfig;

const BINARY_NAME_WINDOWS: &str = "tellaro-pm-agent.exe";
const BINARY_NAME_UNIX: &str = "tellaro-pm-agent";
const REGISTRY_VALUE_NAME: &str = "TellaroPMAgent";

/// Where the binary gets installed per-platform.
pub fn install_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        dirs::data_local_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("TellaroPM")
    }

    #[cfg(target_os = "macos")]
    {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("Library")
            .join("Application Support")
            .join("TellaroPM")
    }

    #[cfg(target_os = "linux")]
    {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".local")
            .join("bin")
    }
}

fn installed_binary_path() -> PathBuf {
    let name = if cfg!(target_os = "windows") {
        BINARY_NAME_WINDOWS
    } else {
        BINARY_NAME_UNIX
    };
    install_dir().join(name)
}

// -----------------------------------------------------------------------
// Public API
// -----------------------------------------------------------------------

/// Copy the running binary into the user's local directory and register
/// it as a startup item so it runs automatically after login.
pub fn install_and_autostart() -> anyhow::Result<()> {
    let dest = copy_self()?;
    register_autostart(&dest)?;
    info!("Agent installed and registered for auto-start");
    Ok(())
}

/// Remove the installed binary and deregister the startup item.
pub fn uninstall() -> anyhow::Result<()> {
    deregister_autostart()?;
    remove_binary()?;
    info!("Agent uninstalled and auto-start removed");
    Ok(())
}

/// Check whether the agent is already installed at the expected location.
pub fn is_installed() -> bool {
    installed_binary_path().exists()
}

// -----------------------------------------------------------------------
// Binary copy
// -----------------------------------------------------------------------

fn copy_self() -> anyhow::Result<PathBuf> {
    let current_exe = std::env::current_exe()?;
    let dest = installed_binary_path();

    // Don't copy over ourselves
    if current_exe == dest {
        info!("Already running from install location");
        return Ok(dest);
    }

    let parent = dest.parent().unwrap();
    std::fs::create_dir_all(parent)?;

    std::fs::copy(&current_exe, &dest)?;
    info!("Copied binary to {}", dest.display());

    // On Unix, ensure the binary is executable
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = std::fs::metadata(&dest)?.permissions();
        perms.set_mode(0o755);
        std::fs::set_permissions(&dest, perms)?;
    }

    Ok(dest)
}

fn remove_binary() -> anyhow::Result<()> {
    let path = installed_binary_path();
    if path.exists() {
        std::fs::remove_file(&path)?;
        info!("Removed binary at {}", path.display());
    }

    // Also remove the config
    let config_path = AgentConfig::config_path();
    if config_path.exists() {
        std::fs::remove_file(&config_path)?;
        info!("Removed config at {}", config_path.display());
    }

    // Try to remove empty parent dirs (best-effort)
    if let Some(parent) = path.parent() {
        let _ = std::fs::remove_dir(parent);
    }

    Ok(())
}

// -----------------------------------------------------------------------
// Windows: HKCU\Software\Microsoft\Windows\CurrentVersion\Run
// -----------------------------------------------------------------------

#[cfg(target_os = "windows")]
fn register_autostart(binary_path: &Path) -> anyhow::Result<()> {
    use std::process::Command;

    let exe = binary_path.to_string_lossy();
    let value = format!("\"{}\" run", exe);

    let status = Command::new("reg")
        .args([
            "add",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
            "/v",
            REGISTRY_VALUE_NAME,
            "/t",
            "REG_SZ",
            "/d",
            &value,
            "/f",
        ])
        .status()?;

    if !status.success() {
        anyhow::bail!("Failed to add registry startup entry");
    }

    info!("Registered Windows startup entry: {value}");
    Ok(())
}

#[cfg(target_os = "windows")]
fn deregister_autostart() -> anyhow::Result<()> {
    use std::process::Command;

    let status = Command::new("reg")
        .args([
            "delete",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
            "/v",
            REGISTRY_VALUE_NAME,
            "/f",
        ])
        .status()?;

    if !status.success() {
        warn!("Registry entry may not have existed (non-zero exit)");
    }

    info!("Removed Windows startup entry");
    Ok(())
}

// -----------------------------------------------------------------------
// macOS: LaunchAgent plist
// -----------------------------------------------------------------------

#[cfg(target_os = "macos")]
fn launchagent_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Library")
        .join("LaunchAgents")
        .join("io.tellaro.pm-agent.plist")
}

#[cfg(target_os = "macos")]
fn register_autostart(binary_path: &Path) -> anyhow::Result<()> {
    use std::process::Command;

    let plist_path = launchagent_path();
    let exe = binary_path.to_string_lossy();
    let log_dir = dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Library")
        .join("Logs")
        .join("TellaroPM");

    std::fs::create_dir_all(&log_dir)?;
    std::fs::create_dir_all(plist_path.parent().unwrap())?;

    let plist = format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.tellaro.pm-agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe}</string>
        <string>run</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>{stdout}</string>
    <key>StandardErrorPath</key>
    <string>{stderr}</string>
</dict>
</plist>"#,
        exe = exe,
        stdout = log_dir.join("agent.stdout.log").display(),
        stderr = log_dir.join("agent.stderr.log").display(),
    );

    std::fs::write(&plist_path, plist)?;
    info!("Wrote LaunchAgent plist to {}", plist_path.display());

    let status = Command::new("launchctl")
        .args(["load", "-w"])
        .arg(&plist_path)
        .status()?;

    if !status.success() {
        warn!("launchctl load returned non-zero — agent may already be loaded");
    }

    info!("LaunchAgent loaded");
    Ok(())
}

#[cfg(target_os = "macos")]
fn deregister_autostart() -> anyhow::Result<()> {
    use std::process::Command;

    let plist_path = launchagent_path();

    if plist_path.exists() {
        let _ = Command::new("launchctl")
            .args(["unload", "-w"])
            .arg(&plist_path)
            .status();

        std::fs::remove_file(&plist_path)?;
        info!("Removed LaunchAgent plist");
    }

    Ok(())
}

// -----------------------------------------------------------------------
// Linux: WSL detection
// -----------------------------------------------------------------------

#[cfg(target_os = "linux")]
fn is_wsl() -> bool {
    // Primary: WSL always sets this env var
    if std::env::var("WSL_DISTRO_NAME").is_ok() {
        return true;
    }
    // Fallback: /proc/version contains "microsoft" (WSL2) or "Microsoft" (WSL1)
    if let Ok(version) = std::fs::read_to_string("/proc/version") {
        if version.to_lowercase().contains("microsoft") {
            return true;
        }
    }
    false
}

#[cfg(target_os = "linux")]
fn wsl_distro_name() -> String {
    std::env::var("WSL_DISTRO_NAME").unwrap_or_else(|_| "Ubuntu".to_string())
}

// -----------------------------------------------------------------------
// Linux: dispatch to WSL or native systemd
// -----------------------------------------------------------------------

#[cfg(target_os = "linux")]
fn register_autostart(binary_path: &Path) -> anyhow::Result<()> {
    if is_wsl() {
        register_autostart_wsl(binary_path)
    } else {
        register_autostart_systemd(binary_path)
    }
}

#[cfg(target_os = "linux")]
fn deregister_autostart() -> anyhow::Result<()> {
    if is_wsl() {
        deregister_autostart_wsl()
    } else {
        deregister_autostart_systemd()
    }
}

// -----------------------------------------------------------------------
// Linux (WSL): register via Windows registry through cmd.exe
//
// WSL has no login session — it starts when Windows opens a terminal or
// launches `wsl.exe`. The only reliable way to auto-start a WSL process
// on Windows login is to create a Windows startup entry that calls
// `wsl.exe -d <distro> -- <path> run`.
// -----------------------------------------------------------------------

#[cfg(target_os = "linux")]
fn register_autostart_wsl(binary_path: &Path) -> anyhow::Result<()> {
    use std::process::Command;

    let distro = wsl_distro_name();
    let linux_path = binary_path.to_string_lossy();

    // wsl.exe runs the binary as the default WSL user (the one who
    // provisioned the agent), inheriting their env and filesystem.
    let reg_value = format!("wsl.exe -d {distro} -- {linux_path} run");

    info!("WSL detected (distro: {distro}), registering Windows startup entry");

    let status = Command::new("cmd.exe")
        .args([
            "/C",
            "reg",
            "add",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
            "/v",
            REGISTRY_VALUE_NAME,
            "/t",
            "REG_SZ",
            "/d",
            &reg_value,
            "/f",
        ])
        .status()?;

    if !status.success() {
        anyhow::bail!("Failed to add Windows registry startup entry from WSL");
    }

    info!("Registered Windows startup entry (via WSL): {reg_value}");
    Ok(())
}

#[cfg(target_os = "linux")]
fn deregister_autostart_wsl() -> anyhow::Result<()> {
    use std::process::Command;

    let status = Command::new("cmd.exe")
        .args([
            "/C",
            "reg",
            "delete",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
            "/v",
            REGISTRY_VALUE_NAME,
            "/f",
        ])
        .status()?;

    if !status.success() {
        warn!("Registry entry may not have existed (non-zero exit)");
    }

    info!("Removed Windows startup entry (via WSL)");
    Ok(())
}

// -----------------------------------------------------------------------
// Linux (native): systemd user service
// -----------------------------------------------------------------------

#[cfg(target_os = "linux")]
fn service_path() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| {
            dirs::home_dir()
                .unwrap_or_else(|| PathBuf::from("."))
                .join(".config")
        })
        .join("systemd")
        .join("user")
        .join("tellaro-pm-agent.service")
}

#[cfg(target_os = "linux")]
fn register_autostart_systemd(binary_path: &Path) -> anyhow::Result<()> {
    use std::process::Command;

    let svc_path = service_path();
    let exe = binary_path.to_string_lossy();

    std::fs::create_dir_all(svc_path.parent().unwrap())?;

    let unit = format!(
        r#"[Unit]
Description=Tellaro PM Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={exe} run
Restart=on-failure
RestartSec=10
Environment=RUST_LOG=info

[Install]
WantedBy=default.target
"#,
        exe = exe,
    );

    std::fs::write(&svc_path, unit)?;
    info!("Wrote systemd user service to {}", svc_path.display());

    let _ = Command::new("systemctl")
        .args(["--user", "daemon-reload"])
        .status();

    let status = Command::new("systemctl")
        .args(["--user", "enable", "--now", "tellaro-pm-agent.service"])
        .status()?;

    if !status.success() {
        warn!("systemctl enable returned non-zero");
    }

    // Ensure lingering is enabled so user services run without an active session
    let _ = Command::new("loginctl")
        .args(["enable-linger"])
        .status();

    info!("systemd user service enabled and started");
    Ok(())
}

#[cfg(target_os = "linux")]
fn deregister_autostart_systemd() -> anyhow::Result<()> {
    use std::process::Command;

    let svc_path = service_path();

    if svc_path.exists() {
        let _ = Command::new("systemctl")
            .args(["--user", "stop", "tellaro-pm-agent.service"])
            .status();

        let _ = Command::new("systemctl")
            .args(["--user", "disable", "tellaro-pm-agent.service"])
            .status();

        std::fs::remove_file(&svc_path)?;

        let _ = Command::new("systemctl")
            .args(["--user", "daemon-reload"])
            .status();

        info!("Removed systemd user service");
    }

    Ok(())
}
