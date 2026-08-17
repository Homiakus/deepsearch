use crate::error::AcquisitionError;
use ipnet::{Ipv4Net, Ipv6Net};
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use url::Url;

pub struct UrlPolicy;

impl UrlPolicy {
    /// Validates URL scheme, hostname, and private IP ranges for SSRF prevention (DS-RB15).
    pub fn validate_url(raw_url: &str) -> Result<Url, AcquisitionError> {
        let parsed = Url::parse(raw_url)
            .map_err(|e| AcquisitionError::InvalidUrl(format!("{}: {}", raw_url, e)))?;

        // 1. Allowed Schemes
        let scheme = parsed.scheme().to_lowercase();
        if scheme != "http" && scheme != "https" {
            return Err(AcquisitionError::SecurityViolation(format!(
                "Disallowed URL scheme '{}'. Only HTTP and HTTPS are permitted.",
                scheme
            )));
        }

        // 2. Host presence
        let host = parsed
            .host_str()
            .ok_or_else(|| AcquisitionError::InvalidUrl("Missing host in URL".to_string()))?;

        // 3. Localhost names
        let host_lower = host.to_lowercase();
        if host_lower == "localhost"
            || host_lower.ends_with(".localhost")
            || host_lower == "local"
            || host_lower.ends_with(".local")
            || host_lower.ends_with(".internal")
        {
            return Err(AcquisitionError::SecurityViolation(format!(
                "Access to local host '{}' is blocked by security policy.",
                host
            )));
        }

        // 4. If host is direct IP, check private ranges
        if let Ok(ip) = host.parse::<IpAddr>() {
            Self::validate_ip(ip)?;
        }

        Ok(parsed)
    }

    /// Verifies that an IP address does not belong to private/reserved ranges.
    pub fn validate_ip(ip: IpAddr) -> Result<(), AcquisitionError> {
        match ip {
            IpAddr::V4(ipv4) => {
                if Self::is_private_ipv4(ipv4) {
                    return Err(AcquisitionError::SecurityViolation(format!(
                        "Access to private IPv4 '{}' is blocked by SSRF policy.",
                        ipv4
                    )));
                }
            }
            IpAddr::V6(ipv6) => {
                if Self::is_private_ipv6(ipv6) {
                    return Err(AcquisitionError::SecurityViolation(format!(
                        "Access to private IPv6 '{}' is blocked by SSRF policy.",
                        ipv6
                    )));
                }
            }
        }
        Ok(())
    }

    pub fn is_private_ipv4(ip: Ipv4Addr) -> bool {
        // RFC1918, Loopback, Link-Local, Broadcast, Carrier-grade NAT
        let private_nets: &[Ipv4Net] = &[
            "0.0.0.0/8".parse().unwrap(),
            "10.0.0.0/8".parse().unwrap(),
            "127.0.0.0/8".parse().unwrap(),
            "169.254.0.0/16".parse().unwrap(),
            "172.16.0.0/12".parse().unwrap(),
            "192.168.0.0/16".parse().unwrap(),
            "100.64.0.0/10".parse().unwrap(),
            "198.18.0.0/15".parse().unwrap(),
            "224.0.0.0/4".parse().unwrap(),
            "240.0.0.0/4".parse().unwrap(),
            "255.255.255.255/32".parse().unwrap(),
        ];

        for net in private_nets {
            if net.contains(&ip) {
                return true;
            }
        }
        false
    }

    pub fn is_private_ipv6(ip: Ipv6Addr) -> bool {
        // Loopback ::1, Unique Local fc00::/7, Link Local fe80::/10, Multicast ff00::/8
        if ip == Ipv6Addr::LOCALHOST || ip == Ipv6Addr::UNSPECIFIED {
            return true;
        }

        let private_nets: &[Ipv6Net] = &[
            "::1/128".parse().unwrap(),
            "::/128".parse().unwrap(),
            "fc00::/7".parse().unwrap(),
            "fe80::/10".parse().unwrap(),
            "ff00::/8".parse().unwrap(),
        ];

        for net in private_nets {
            if net.contains(&ip) {
                return true;
            }
        }
        false
    }
}
