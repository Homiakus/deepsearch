use crate::error::AcquisitionError;
use crate::security::url_policy::UrlPolicy;
use url::Url;

#[derive(Debug, Clone)]
pub struct RedirectTracker {
    pub max_redirects: usize,
    pub history: Vec<String>,
}

impl RedirectTracker {
    pub fn new(max_redirects: usize) -> Self {
        Self {
            max_redirects,
            history: Vec::new(),
        }
    }

    pub fn record_redirect(&mut self, next_url_str: &str) -> Result<Url, AcquisitionError> {
        if self.history.len() >= self.max_redirects {
            return Err(AcquisitionError::SecurityViolation(format!(
                "Max redirect limit of {} reached",
                self.max_redirects
            )));
        }

        let parsed = UrlPolicy::validate_url(next_url_str)?;
        self.history.push(next_url_str.to_string());
        Ok(parsed)
    }
}
