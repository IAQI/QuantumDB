/// Default page size when the client does not specify `limit`.
pub const DEFAULT_LIMIT: i64 = 100;

/// Hard upper bound on `limit`. Larger values are clamped down to this.
/// Prevents `?limit=999999999` from forcing a full-table fetch + serialise.
pub const MAX_LIMIT: i64 = 1000;

/// Clamp client-supplied pagination parameters to safe ranges.
///
/// - `limit` is clamped to `1..=MAX_LIMIT`, defaulting to `DEFAULT_LIMIT` when absent.
/// - `offset` is clamped to `>= 0`, defaulting to `0` when absent.
pub fn clamp_pagination(limit: Option<i64>, offset: Option<i64>) -> (i64, i64) {
    let limit = limit.unwrap_or(DEFAULT_LIMIT).clamp(1, MAX_LIMIT);
    let offset = offset.unwrap_or(0).max(0);
    (limit, offset)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_when_none() {
        assert_eq!(clamp_pagination(None, None), (DEFAULT_LIMIT, 0));
    }

    #[test]
    fn clamps_huge_limit() {
        assert_eq!(clamp_pagination(Some(i64::MAX), None), (MAX_LIMIT, 0));
        assert_eq!(clamp_pagination(Some(999_999_999), None), (MAX_LIMIT, 0));
    }

    #[test]
    fn clamps_negative_limit_to_one() {
        assert_eq!(clamp_pagination(Some(-5), None), (1, 0));
        assert_eq!(clamp_pagination(Some(0), None), (1, 0));
    }

    #[test]
    fn clamps_negative_offset_to_zero() {
        assert_eq!(clamp_pagination(None, Some(-100)), (DEFAULT_LIMIT, 0));
    }

    #[test]
    fn passes_valid_values() {
        assert_eq!(clamp_pagination(Some(50), Some(200)), (50, 200));
        assert_eq!(clamp_pagination(Some(MAX_LIMIT), Some(0)), (MAX_LIMIT, 0));
    }
}
