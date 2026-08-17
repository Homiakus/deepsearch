use crate::error::AcquisitionError;
use crate::security::url_policy::UrlPolicy;
use std::net::SocketAddr;

pub struct DnsPolicy;

impl DnsPolicy {
    /// Validates all resolved socket addresses against SSRF private network restrictions.
    pub fn validate_resolved_addresses(addrs: &[SocketAddr]) -> Result<(), AcquisitionError> {
        if addrs.is_empty() {
            return Err(AcquisitionError::HttpError(
                "DNS resolution returned no addresses".to_string(),
            ));
        }

        for addr in addrs {
            UrlPolicy::validate_ip(addr.ip())?;
        }
        Ok(())
    }
}
