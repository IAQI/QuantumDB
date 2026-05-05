use axum::http::StatusCode;

/// Maximum allowed length for any URL field (RFC-recommended hard cap is ~2 KB).
pub const MAX_URL_LEN: usize = 2048;

/// Maximum length for short identifier-style strings (names, codes, slugs).
pub const MAX_NAME_LEN: usize = 255;

/// Maximum length for medium free-text fields (titles, session names, awards).
pub const MAX_TITLE_LEN: usize = 1000;

/// Maximum length for long free-text fields (abstracts).
pub const MAX_ABSTRACT_LEN: usize = 50_000;

/// Maximum serialised size for a JSONB `metadata` payload.
pub const MAX_METADATA_BYTES: usize = 4096;

/// Validate that a string field does not exceed `max_len` bytes.
pub fn validate_text_len(value: &str, max_len: usize) -> Result<(), StatusCode> {
    if value.len() > max_len {
        tracing::warn!(
            value_len = value.len(),
            max = max_len,
            "Text field exceeds maximum length"
        );
        return Err(StatusCode::BAD_REQUEST);
    }
    Ok(())
}

/// Validate an optional string field. `None` and `Some("")` are accepted.
pub fn validate_optional_text_len(
    value: Option<&str>,
    max_len: usize,
) -> Result<(), StatusCode> {
    match value {
        Some(s) => validate_text_len(s, max_len),
        None => Ok(()),
    }
}

/// Validate a JSONB metadata payload: must be a JSON object (not an array or scalar)
/// and its serialised form must not exceed `MAX_METADATA_BYTES`.
///
/// `None` is accepted (no metadata supplied).
pub fn validate_metadata(value: Option<&serde_json::Value>) -> Result<(), StatusCode> {
    let Some(v) = value else {
        return Ok(());
    };
    if !v.is_object() {
        tracing::warn!("metadata must be a JSON object");
        return Err(StatusCode::BAD_REQUEST);
    }
    // serde_json::to_string is infallible for already-parsed Values.
    let serialised = v.to_string();
    if serialised.len() > MAX_METADATA_BYTES {
        tracing::warn!(
            metadata_bytes = serialised.len(),
            max = MAX_METADATA_BYTES,
            "metadata payload exceeds maximum size"
        );
        return Err(StatusCode::BAD_REQUEST);
    }
    Ok(())
}

/// Validate a single URL string.
///
/// Accepts only `http://...` and `https://...` URLs (case-insensitive scheme check).
/// Rejects `javascript:`, `data:`, `vbscript:`, `file:`, etc. — schemes that can be
/// rendered into an `<a href="...">` attribute and pivot to script execution or
/// local-file access.
///
/// Also enforces a hard length cap (`MAX_URL_LEN`) to prevent oversized values.
///
/// Returns `StatusCode::BAD_REQUEST` on rejection so handlers can `?`-propagate.
pub fn validate_url(value: &str) -> Result<(), StatusCode> {
    if value.len() > MAX_URL_LEN {
        tracing::warn!(
            url_len = value.len(),
            max = MAX_URL_LEN,
            "URL exceeds maximum length"
        );
        return Err(StatusCode::BAD_REQUEST);
    }

    let lower = value.trim_start().to_ascii_lowercase();
    let after_scheme = if let Some(rest) = lower.strip_prefix("https://") {
        rest
    } else if let Some(rest) = lower.strip_prefix("http://") {
        rest
    } else {
        tracing::warn!(scheme = %value.chars().take(20).collect::<String>(), "URL has disallowed scheme");
        return Err(StatusCode::BAD_REQUEST);
    };

    // Require at least one host character after the scheme.
    if after_scheme.trim().is_empty() {
        return Err(StatusCode::BAD_REQUEST);
    }

    Ok(())
}

/// Validate an optional URL field. `None` and `Some("")` are accepted (no URL).
pub fn validate_optional_url(value: Option<&str>) -> Result<(), StatusCode> {
    match value {
        Some(s) if !s.is_empty() => validate_url(s),
        _ => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_http_and_https() {
        assert!(validate_url("http://example.com").is_ok());
        assert!(validate_url("https://example.com/path?q=1").is_ok());
        assert!(validate_url("HTTPS://EXAMPLE.COM").is_ok());
    }

    #[test]
    fn rejects_javascript_uri() {
        assert!(validate_url("javascript:alert(1)").is_err());
        assert!(validate_url("JaVaScRiPt:alert(1)").is_err());
        assert!(validate_url("  javascript:alert(1)").is_err());
    }

    #[test]
    fn rejects_data_uri() {
        assert!(validate_url("data:text/html,<script>alert(1)</script>").is_err());
    }

    #[test]
    fn rejects_vbscript_and_file() {
        assert!(validate_url("vbscript:msgbox(1)").is_err());
        assert!(validate_url("file:///etc/passwd").is_err());
    }

    #[test]
    fn rejects_empty_after_scheme() {
        assert!(validate_url("https://").is_err());
        assert!(validate_url("http://   ").is_err());
    }

    #[test]
    fn rejects_oversized_url() {
        let huge = format!("https://example.com/{}", "a".repeat(MAX_URL_LEN));
        assert!(validate_url(&huge).is_err());
    }

    #[test]
    fn optional_url_accepts_none_and_empty() {
        assert!(validate_optional_url(None).is_ok());
        assert!(validate_optional_url(Some("")).is_ok());
        assert!(validate_optional_url(Some("https://x.test")).is_ok());
        assert!(validate_optional_url(Some("javascript:alert(1)")).is_err());
    }

    #[test]
    fn text_len_accepts_within_bound() {
        assert!(validate_text_len("hello", 10).is_ok());
        assert!(validate_text_len(&"a".repeat(100), 100).is_ok());
    }

    #[test]
    fn text_len_rejects_oversized() {
        assert!(validate_text_len(&"a".repeat(101), 100).is_err());
    }

    #[test]
    fn optional_text_len_handles_none() {
        assert!(validate_optional_text_len(None, 10).is_ok());
        assert!(validate_optional_text_len(Some("hi"), 10).is_ok());
        assert!(validate_optional_text_len(Some("oversized!!!"), 5).is_err());
    }

    #[test]
    fn metadata_accepts_object() {
        let v = serde_json::json!({"source_type": "manual"});
        assert!(validate_metadata(Some(&v)).is_ok());
        assert!(validate_metadata(None).is_ok());
    }

    #[test]
    fn metadata_rejects_array_or_scalar() {
        let arr = serde_json::json!([1, 2, 3]);
        assert!(validate_metadata(Some(&arr)).is_err());
        let scalar = serde_json::json!("hello");
        assert!(validate_metadata(Some(&scalar)).is_err());
    }

    #[test]
    fn metadata_rejects_oversized_payload() {
        let huge = serde_json::json!({ "blob": "x".repeat(MAX_METADATA_BYTES) });
        assert!(validate_metadata(Some(&huge)).is_err());
    }
}
