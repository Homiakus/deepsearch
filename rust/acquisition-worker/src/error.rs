use thiserror::Error;

#[derive(Error, Debug, Clone)]
pub enum AcquisitionError {
    #[error("Security policy violation: {0}")]
    SecurityViolation(String),

    #[error("Invalid URL: {0}")]
    InvalidUrl(String),

    #[error("HTTP transport error: {0}")]
    HttpError(String),

    #[error("Navigation timeout: {0}")]
    Timeout(String),

    #[error("Browser runtime crash or failure: {0}")]
    BrowserCrash(String),

    #[error("Unsupported capability required: {0}")]
    UnsupportedCapability(String),

    #[error("Quality check failed: {0}")]
    QualityFailure(String),

    #[error("CAS artifact write error: {0}")]
    ArtifactWriteError(String),

    #[error("Axiom ADGO protocol error: {0}")]
    AdgoError(String),

    #[error("Execution error: {0}")]
    Other(String),
}

impl AcquisitionError {
    pub fn failure_class(&self) -> &'static str {
        match self {
            AcquisitionError::SecurityViolation(_) => "security",
            AcquisitionError::InvalidUrl(_) => "invalid_input",
            AcquisitionError::HttpError(msg) => {
                if msg.contains("429") {
                    "rate_limit"
                } else {
                    "transient"
                }
            }
            AcquisitionError::Timeout(_) => "transient",
            AcquisitionError::BrowserCrash(_) => "transient",
            AcquisitionError::UnsupportedCapability(_) => "quality",
            AcquisitionError::QualityFailure(_) => "quality",
            AcquisitionError::ArtifactWriteError(_) => "ambiguous_side_effect",
            AcquisitionError::AdgoError(_) => "transient",
            AcquisitionError::Other(_) => "permanent",
        }
    }

    pub fn is_retryable(&self) -> bool {
        matches!(
            self.failure_class(),
            "transient" | "rate_limit" | "ambiguous_side_effect"
        )
    }
}
