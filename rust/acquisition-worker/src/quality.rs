use crate::models::QualityReport;
use regex::Regex;
use std::collections::HashMap;

pub struct QualityEvaluator {
    block_patterns: Vec<Regex>,
    spa_patterns: Vec<Regex>,
}

impl Default for QualityEvaluator {
    fn default() -> Self {
        Self::new()
    }
}

impl QualityEvaluator {
    pub fn new() -> Self {
        let block_patterns = vec![
            Regex::new(r"(?i)cloudflare").unwrap(),
            Regex::new(r"(?i)attention required").unwrap(),
            Regex::new(r"(?i)access denied").unwrap(),
            Regex::new(r"(?i)captcha").unwrap(),
            Regex::new(r"(?i)datadome").unwrap(),
            Regex::new(r"(?i)perimeterx").unwrap(),
            Regex::new(r"(?i)security check").unwrap(),
            Regex::new(r"(?i)please verify you are a human").unwrap(),
            Regex::new(r"(?i)bot detection").unwrap(),
            Regex::new(r"(?i)checking your browser before accessing").unwrap(),
        ];

        let spa_patterns = vec![
            Regex::new(r#"(?i)<div\s+id=["']root["']\s*>\s*</div>"#).unwrap(),
            Regex::new(r#"(?i)<div\s+id=["']app["']\s*>\s*</div>"#).unwrap(),
            Regex::new(r#"(?i)<div\s+id=["']__next["']\s*>\s*</div>"#).unwrap(),
            Regex::new(r"(?i)you need to enable javascript to run this app").unwrap(),
            Regex::new(r"(?i)please enable javascript").unwrap(),
        ];

        Self {
            block_patterns,
            spa_patterns,
        }
    }

    pub fn evaluate(
        &self,
        _url: &str,
        status_code: u16,
        _headers: &HashMap<String, String>,
        html_or_text: &str,
        expected_min_text_chars: usize,
    ) -> QualityReport {
        let mut reasons = Vec::new();
        let mut score: f64 = 1.0;
        let mut completeness: f64 = 1.0;
        let mut blocked = false;
        let mut likely_unrendered = false;
        let mut suggested_escalation = None;

        // 1. HTTP Status code
        if status_code >= 400 {
            score -= 0.6;
            completeness = 0.0;
            reasons.push(format!("HTTP error status: {}", status_code));
            if status_code == 403 || status_code == 429 {
                blocked = true;
                reasons.push("Rate limit or access forbidden".to_string());
                suggested_escalation = Some("chromium".to_string());
            }
        }

        // 2. Block patterns
        let sample_len = html_or_text.len().min(10000);
        let sample = &html_or_text[..sample_len];

        for pattern in &self.block_patterns {
            if pattern.is_match(sample) {
                blocked = true;
                score -= 0.5;
                reasons.push(format!("Block pattern detected: {}", pattern.as_str()));
                suggested_escalation = Some("chromium".to_string());
                break;
            }
        }

        // 3. Unrendered SPA shell detection
        for pattern in &self.spa_patterns {
            if pattern.is_match(sample) {
                likely_unrendered = true;
                score -= 0.4;
                completeness = completeness.min(0.3);
                reasons.push("Empty SPA root or disabled JS message detected".to_string());
                if suggested_escalation.is_none() {
                    suggested_escalation = Some("servo".to_string());
                }
                break;
            }
        }

        // 4. Useful text characters estimation
        let tag_regex = Regex::new(r"<[^>]+>").unwrap();
        let stripped = tag_regex.replace_all(html_or_text, " ");
        let text_chars = stripped.split_whitespace().map(|w| w.len()).sum::<usize>();

        if text_chars < expected_min_text_chars {
            score -= 0.3;
            let ratio = (text_chars as f64) / (expected_min_text_chars.max(1) as f64);
            completeness = completeness.min(ratio.max(0.1));
            reasons.push(format!(
                "Low useful text characters: {} < {}",
                text_chars, expected_min_text_chars
            ));
            if suggested_escalation.is_none() && !blocked {
                suggested_escalation = Some("servo".to_string());
            }
        }

        QualityReport {
            score: (score.clamp(0.0, 1.0) * 1000.0).round() / 1000.0,
            completeness: (completeness.clamp(0.0, 1.0) * 1000.0).round() / 1000.0,
            blocked,
            likely_unrendered,
            reasons,
            suggested_escalation,
        }
    }
}
