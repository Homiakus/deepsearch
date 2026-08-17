# Rust Browser Acquisition Worker

High-performance URL & Browser acquisition worker for DeepSearch and Axiom ADGO coarse-grained durable orchestration.

## Architecture
- **Control Plane**: Axiom ADGO (`AcquireBatch` durable activity)
- **Execution Layer**: Rust Acquisition Worker (`BackendPlanner`, `SecurityPolicy`, `HttpBackend`, `ServoBackend`, `ChromiumBackend`)
- **Artifact Store**: Content Addressable Storage (CAS) with SHA-256 hashes

## Running Local Dev Server
```bash
cargo run --bin acquisition-worker -- --port 8081
```

## Running Tests
```bash
cargo test
```
