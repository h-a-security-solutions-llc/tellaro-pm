use std::collections::HashSet;
use std::sync::Mutex;
use tokio::sync::mpsc;
use tracing::{error, info};

use crate::claude::{self, StreamEvent};

static ACTIVE_ITEMS: Mutex<Option<HashSet<String>>> = Mutex::new(None);

fn get_active_items() -> std::sync::MutexGuard<'static, Option<HashSet<String>>> {
    let mut guard = ACTIVE_ITEMS.lock().unwrap();
    if guard.is_none() {
        *guard = Some(HashSet::new());
    }
    guard
}

pub fn active_work_item_ids() -> Vec<String> {
    get_active_items()
        .as_ref()
        .map(|s| s.iter().cloned().collect())
        .unwrap_or_default()
}

/// Execute a work item with streaming output.
///
/// Returns a channel receiver that yields StreamEvent chunks as the agent
/// processes the instruction. The caller should forward these to the backend
/// WebSocket.
pub async fn execute_work_item_streaming(
    work_item_id: &str,
    instruction: &str,
    working_directory: Option<&str>,
    _persona_id: Option<&str>,
) -> (mpsc::UnboundedReceiver<StreamEvent>, tokio::task::JoinHandle<anyhow::Result<String>>) {
    // Track active work item
    {
        let mut items = get_active_items();
        items.as_mut().unwrap().insert(work_item_id.to_string());
    }

    info!(
        work_item_id = %work_item_id,
        "Executing work item via Claude Code (streaming)"
    );

    let (tx, rx) = mpsc::unbounded_channel();
    let wid = work_item_id.to_string();
    let inst = instruction.to_string();
    let wd = working_directory.map(|s| s.to_string());

    let handle = tokio::spawn(async move {
        let result = claude::run_claude_code_streaming(
            &inst,
            wd.as_deref(),
            tx,
        )
        .await;

        // Remove from active set
        {
            let mut items = get_active_items();
            items.as_mut().unwrap().remove(&wid);
        }

        match &result {
            Ok(output) => {
                info!(
                    work_item_id = %wid,
                    output_len = output.len(),
                    "Work item completed successfully"
                );
            }
            Err(e) => {
                error!(
                    work_item_id = %wid,
                    "Work item failed: {e}"
                );
            }
        }

        result
    });

    (rx, handle)
}

pub async fn execute_work_item(
    work_item_id: &str,
    instruction: &str,
    working_directory: Option<&str>,
    _persona_id: Option<&str>,
) -> anyhow::Result<String> {
    // Track active work item
    {
        let mut items = get_active_items();
        items.as_mut().unwrap().insert(work_item_id.to_string());
    }

    info!(
        work_item_id = %work_item_id,
        "Executing work item via Claude Code"
    );

    let result = claude::run_claude_code(instruction, working_directory).await;

    // Remove from active set
    {
        let mut items = get_active_items();
        items.as_mut().unwrap().remove(work_item_id);
    }

    match &result {
        Ok(output) => {
            info!(
                work_item_id = %work_item_id,
                output_len = output.len(),
                "Work item completed successfully"
            );
        }
        Err(e) => {
            error!(
                work_item_id = %work_item_id,
                "Work item failed: {e}"
            );
        }
    }

    result
}
