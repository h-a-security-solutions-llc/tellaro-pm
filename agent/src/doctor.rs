use tracing::{info, warn};

use crate::claude;

/// Run `claude doctor` and optionally attempt self-healing.
pub async fn run_doctor(heal: bool) -> anyhow::Result<()> {
    info!("Running claude doctor...");

    let output = claude::run_claude_doctor().await?;
    println!("{output}");

    if !heal {
        return Ok(());
    }

    // Parse output for known issues and attempt fixes
    let issues = parse_doctor_output(&output);

    if issues.is_empty() {
        info!("No issues found.");
        return Ok(());
    }

    info!("Found {} issue(s), attempting self-healing...", issues.len());

    for issue in &issues {
        match attempt_fix(issue).await {
            Ok(()) => info!("Fixed: {}", issue.description),
            Err(e) => warn!("Could not fix '{}': {e}", issue.description),
        }
    }

    Ok(())
}

#[derive(Debug)]
struct DoctorIssue {
    description: String,
    category: IssueCategory,
}

#[derive(Debug)]
enum IssueCategory {
    MissingDependency(String),
    ConfigError,
    NetworkIssue,
    Unknown,
}

fn parse_doctor_output(output: &str) -> Vec<DoctorIssue> {
    let mut issues = Vec::new();
    let lower = output.to_lowercase();

    // Check for common patterns in claude doctor output
    if lower.contains("not found") || lower.contains("missing") {
        // Try to extract what's missing
        for line in output.lines() {
            let line_lower = line.to_lowercase();
            if line_lower.contains("not found") || line_lower.contains("missing") {
                let category = if line_lower.contains("node") || line_lower.contains("npm") {
                    IssueCategory::MissingDependency("node".to_string())
                } else if line_lower.contains("git") {
                    IssueCategory::MissingDependency("git".to_string())
                } else {
                    IssueCategory::Unknown
                };

                issues.push(DoctorIssue {
                    description: line.trim().to_string(),
                    category,
                });
            }
        }
    }

    if lower.contains("config") && (lower.contains("error") || lower.contains("invalid")) {
        issues.push(DoctorIssue {
            description: "Configuration error detected".to_string(),
            category: IssueCategory::ConfigError,
        });
    }

    if lower.contains("network") || lower.contains("timeout") || lower.contains("connection refused")
    {
        issues.push(DoctorIssue {
            description: "Network connectivity issue".to_string(),
            category: IssueCategory::NetworkIssue,
        });
    }

    issues
}

async fn attempt_fix(issue: &DoctorIssue) -> anyhow::Result<()> {
    match &issue.category {
        IssueCategory::MissingDependency(dep) => {
            warn!(
                "Missing dependency: {dep}. Please install it manually."
            );
            // We don't auto-install system dependencies for safety
            anyhow::bail!("Manual intervention required: install {dep}")
        }
        IssueCategory::ConfigError => {
            info!("Attempting to reset Claude configuration...");
            // Could attempt to regenerate config here
            warn!("Config reset not yet implemented — manual fix needed");
            anyhow::bail!("Config fix not automated yet")
        }
        IssueCategory::NetworkIssue => {
            info!("Network issue detected — will retry on next cycle");
            Ok(())
        }
        IssueCategory::Unknown => {
            warn!("Unknown issue: {}", issue.description);
            anyhow::bail!("Cannot auto-fix unknown issue")
        }
    }
}
