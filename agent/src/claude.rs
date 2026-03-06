use std::process::Stdio;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::mpsc;
use tracing::{error, info};

/// A chunk of streaming output from Claude Code.
#[derive(Debug, Clone)]
pub enum StreamEvent {
    /// A text chunk of output.
    Chunk(String),
    /// Claude has finished; contains the full accumulated output.
    Done(String),
    /// An error occurred.
    Error(String),
}

/// Run a Claude Code session with streaming output.
///
/// Uses `claude --output-format stream-json -p` for streaming JSON output.
/// Each line of stdout is parsed for text content and sent to the channel.
/// Returns the full accumulated output.
pub async fn run_claude_code_streaming(
    instruction: &str,
    working_directory: Option<&str>,
    tx: mpsc::UnboundedSender<StreamEvent>,
) -> anyhow::Result<String> {
    let claude_path = find_claude_binary()?;
    info!("Using Claude binary at: {}", claude_path);

    let mut cmd = Command::new(&claude_path);
    cmd.arg("--output-format")
        .arg("stream-json")
        .arg("--verbose")
        .arg("-p")
        .arg(instruction)
        .env_remove("CLAUDECODE")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(dir) = working_directory {
        cmd.current_dir(dir);
    }

    let mut child = cmd.spawn()?;
    let stdout = child.stdout.take().ok_or_else(|| anyhow::anyhow!("Failed to capture stdout"))?;

    let mut reader = BufReader::new(stdout).lines();
    let mut full_output = String::new();

    while let Some(line) = reader.next_line().await? {
        if line.is_empty() {
            continue;
        }

        // Parse stream-json output to extract text content
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&line) {
            // Claude stream-json format: look for assistant text deltas
            let msg_type = json.get("type").and_then(|t| t.as_str()).unwrap_or("");

            match msg_type {
                "content_block_delta" => {
                    if let Some(delta) = json.get("delta") {
                        if let Some(text) = delta.get("text").and_then(|t| t.as_str()) {
                            full_output.push_str(text);
                            let _ = tx.send(StreamEvent::Chunk(text.to_string()));
                        }
                    }
                }
                "assistant" => {
                    // Final assistant message — extract full text from content blocks
                    if let Some(content) = json.get("content").and_then(|c| c.as_array()) {
                        for block in content {
                            if let Some(text) = block.get("text").and_then(|t| t.as_str()) {
                                if full_output.is_empty() {
                                    full_output.push_str(text);
                                    let _ = tx.send(StreamEvent::Chunk(text.to_string()));
                                }
                            }
                        }
                    }
                }
                "result" => {
                    // Final result message — may contain the complete text
                    if let Some(result_text) = json
                        .get("result")
                        .and_then(|r| r.as_str())
                    {
                        if full_output.is_empty() {
                            full_output.push_str(result_text);
                        }
                    }
                }
                _ => {
                    // Other message types (system, metadata) — ignore
                }
            }
        } else {
            // Non-JSON line — treat as raw text output
            full_output.push_str(&line);
            full_output.push('\n');
            let _ = tx.send(StreamEvent::Chunk(format!("{line}\n")));
        }
    }

    let status = child.wait().await?;
    if !status.success() {
        // Capture stderr for better error diagnostics
        let stderr_output = if let Some(mut stderr) = child.stderr.take() {
            let mut buf = String::new();
            use tokio::io::AsyncReadExt;
            let _ = stderr.read_to_string(&mut buf).await;
            buf
        } else {
            String::new()
        };
        let err_msg = if stderr_output.is_empty() {
            format!("Claude Code exited with status {status}")
        } else {
            format!("Claude Code exited with status {status}: {stderr_output}")
        };
        error!("Claude Code stderr: {stderr_output}");
        let _ = tx.send(StreamEvent::Error(err_msg.clone()));
        anyhow::bail!(err_msg);
    }

    let _ = tx.send(StreamEvent::Done(full_output.clone()));
    Ok(full_output)
}

/// Run a Claude Code session without streaming (batch mode).
///
/// Uses `claude --print` for non-interactive execution that outputs
/// the final result to stdout.
pub async fn run_claude_code(instruction: &str, working_directory: Option<&str>) -> anyhow::Result<String> {
    let claude_path = find_claude_binary()?;
    info!("Using Claude binary at: {}", claude_path);

    let mut cmd = Command::new(&claude_path);
    cmd.arg("--print")
        .arg(instruction)
        .env_remove("CLAUDECODE")
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
