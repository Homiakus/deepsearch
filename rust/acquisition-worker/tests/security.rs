use acquisition_worker::security::UrlPolicy;

#[test]
fn test_security_valid_urls() {
    assert!(UrlPolicy::validate_url("https://example.com").is_ok());
    assert!(UrlPolicy::validate_url("http://sub.domain.org/path?q=1").is_ok());
    assert!(UrlPolicy::validate_url("https://8.8.8.8/dns-query").is_ok());
    assert!(UrlPolicy::validate_url("https://1.1.1.1/").is_ok());
}

#[test]
fn test_security_blocked_schemes() {
    assert!(UrlPolicy::validate_url("file:///etc/passwd").is_err());
    assert!(UrlPolicy::validate_url("gopher://127.0.0.1:70").is_err());
    assert!(UrlPolicy::validate_url("ftp://ftp.example.com/file").is_err());
    assert!(UrlPolicy::validate_url("javascript:alert(1)").is_err());
}

#[test]
fn test_security_blocked_localhost_names() {
    assert!(UrlPolicy::validate_url("http://localhost:8080").is_err());
    assert!(UrlPolicy::validate_url("http://admin.localhost/").is_err());
    assert!(UrlPolicy::validate_url("http://local/service").is_err());
    assert!(UrlPolicy::validate_url("http://service.internal/").is_err());
}

#[test]
fn test_security_blocked_private_ipv4() {
    // Loopback 127.x
    assert!(UrlPolicy::validate_url("http://127.0.0.1/").is_err());
    assert!(UrlPolicy::validate_url("http://127.0.1.5:8000/").is_err());

    // RFC1918 10.x
    assert!(UrlPolicy::validate_url("http://10.0.0.1/admin").is_err());
    assert!(UrlPolicy::validate_url("http://10.255.255.254/").is_err());

    // RFC1918 172.16-31.x
    assert!(UrlPolicy::validate_url("http://172.16.0.1/").is_err());
    assert!(UrlPolicy::validate_url("http://172.31.255.255/").is_err());

    // RFC1918 192.168.x
    assert!(UrlPolicy::validate_url("http://192.168.1.1/").is_err());
    assert!(UrlPolicy::validate_url("http://192.168.100.50/").is_err());

    // Link-local 169.254.x
    assert!(UrlPolicy::validate_url("http://169.254.169.254/latest/meta-data").is_err());
}

#[test]
fn test_security_blocked_private_ipv6() {
    // Loopback ::1
    assert!(UrlPolicy::validate_url("http://[::1]:80/").is_err());

    // Unique Local fc00::/7
    assert!(UrlPolicy::validate_url("http://[fd00::1]/").is_err());

    // Link-Local fe80::/10
    assert!(UrlPolicy::validate_url("http://[fe80::1]/").is_err());
}
