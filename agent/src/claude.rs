use std::process::Stdio;
use tokio::process::Command;
use tracing::{error, info};

/// Run a Claude Code session with the given instruction.
///
/// Uses `claude --print` for non-interactive execution that outputs
/// the final result to stdout.
pub async fn run_claude_code(instruction: &str, working_directory: Option<&str>) -> anyhow::Result<String> {
    let claude_path = find_claude_binary()?;
    info!("Using Claude binary at: {}", claude_path);

    let mut cmd = Command::new(&claude_path);
    cmd.arg("--print")
        .arg(instruction)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(dir) = working_directory {
        cmd.current_dir(dir);
    }

    let output = cmd.spawn()?.wait_with_output().await?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        error!("Claude Code failed: {stderr}");
        anyhow::bail!("Claude Code exited with status {}: {stderr}", output.status)
    }
}

/// Run `claude doctor` and return the output.
pub async fn run_claude_doctor() -> anyhow::Result<String> {
    let claude_path = find_claude_binary()?;

    let output = Command::new(&claude_path)
        .arg("doctor")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?
        .wait_with_output()
        .await?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    Ok(format!("{stdout}\n{stderr}"))
}

/// Find the claude binary in PATH or common locations.
fn find_claude_binary() -> anyhow::Result<String> {
    // Try PATH first
    if let Ok(path) = which::which("claude") {
        return Ok(path.to_string_lossy().to_string());
    }

    // Common install locations
    let candidates = [
        // npm global
        dirs::home_dir()
            .map(|h| h.join(".npm-global/bin/claude")),
        // Homebrew
        Some(std::path::PathBuf::from("/usr/local/bin/claude")),
        Some(std::path::PathBuf::from("/opt/homebrew/bin/claude")),
        // Windows npm global
        dirs::home_dir()
            .map(|h| h.join("AppData/Roaming/npm/claude.cmd")),
    ];

    for candidate in candidates.into_iter().flatten() {
        if candidate.exists() {
            return Ok(candidate.to_string_lossy().to_string());
        }
    }

    anyhow::bail!(
        "Claude Code CLI not found. Install it with: npm install -g @anthropic-ai/claude-code\n\
         See https://docs.anthropic.com/en/docs/claude-code for details."
    )
}
