use crate::models::HeartbeatProgress;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::RwLock;

pub struct HeartbeatManager {
    progress: Arc<RwLock<HeartbeatProgress>>,
    is_running: Arc<AtomicBool>,
}

impl Default for HeartbeatManager {
    fn default() -> Self {
        Self::new()
    }
}

impl HeartbeatManager {
    pub fn new() -> Self {
        Self {
            progress: Arc::new(RwLock::new(HeartbeatProgress::default())),
            is_running: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn start(&self, interval: Duration) -> tokio::task::JoinHandle<()> {
        self.is_running.store(true, Ordering::SeqCst);
        let running = self.is_running.clone();
        let progress = self.progress.clone();

        tokio::spawn(async move {
            while running.load(Ordering::SeqCst) {
                tokio::time::sleep(interval).await;
                if !running.load(Ordering::SeqCst) {
                    break;
                }
                let p = progress.read().await;
                tracing::debug!(
                    "Axiom ADGO Activity Heartbeat: processed={}, successful={}, failed={}",
                    p.processed,
                    p.successful,
                    p.failed
                );
            }
        })
    }

    pub fn stop(&self) {
        self.is_running.store(false, Ordering::SeqCst);
    }

    pub async fn update_progress(&self, success: bool, bytes: usize, browser_secs: f64) {
        let mut p = self.progress.write().await;
        p.processed += 1;
        if success {
            p.successful += 1;
        } else {
            p.failed += 1;
        }
        p.bytes_downloaded += bytes;
        p.browser_seconds += browser_secs;
    }
}
