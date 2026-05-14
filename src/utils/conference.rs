/// Conference slug utilities
///
/// Canonical slug format: `{lower-venue}-{year}` (e.g. `qip-2024`, `qcrypt-2018`,
/// `tqc-2022`). Permanent and human-readable.
///
/// `parse_conference_slug` is permissive — it also accepts the legacy compact
/// uppercase form (e.g. `QIP2024`) and mixed-case variants, so REST clients
/// using either style continue to work. `make_conference_slug` always emits the
/// canonical lowercase-hyphen form.

/// Valid venue prefixes (uppercase canonical form). Longest first so the parser
/// matches `QCRYPT` before `QIP` when no separator is present.
const VENUES: &[&str] = &["QCRYPT", "QIP", "TQC"];

/// Parse a conference slug into `(venue, year)` components.
///
/// Accepted forms (case-insensitive):
/// - `qip-2024`, `qip_2024`, `qip 2024` — separator between venue and year
/// - `QIP2024` — legacy compact form, no separator
///
/// # Examples
/// ```
/// use quantumdb::utils::parse_conference_slug;
///
/// assert_eq!(parse_conference_slug("qip-2024"), Some(("QIP".to_string(), 2024)));
/// assert_eq!(parse_conference_slug("QCRYPT-2018"), Some(("QCRYPT".to_string(), 2018)));
/// assert_eq!(parse_conference_slug("tqc-2022"), Some(("TQC".to_string(), 2022)));
/// assert_eq!(parse_conference_slug("QIP2024"), Some(("QIP".to_string(), 2024))); // legacy
/// assert_eq!(parse_conference_slug("invalid-2024"), None);
/// assert_eq!(parse_conference_slug("qip"), None); // missing year
/// ```
pub fn parse_conference_slug(slug: &str) -> Option<(String, i32)> {
    let slug_upper = slug.to_uppercase();

    for venue in VENUES {
        if let Some(rest) = slug_upper.strip_prefix(venue) {
            // Allow optional separator between venue and year.
            let year_str = rest.trim_start_matches(|c: char| !c.is_ascii_digit());
            if let Ok(year) = year_str.parse::<i32>() {
                if (1990..=2100).contains(&year) {
                    return Some((venue.to_string(), year));
                }
            }
        }
    }

    None
}

/// Generate the canonical slug from venue and year.
///
/// # Examples
/// ```
/// use quantumdb::utils::make_conference_slug;
///
/// assert_eq!(make_conference_slug("QIP", 2024), "qip-2024");
/// assert_eq!(make_conference_slug("qcrypt", 2018), "qcrypt-2018");
/// ```
pub fn make_conference_slug(venue: &str, year: i32) -> String {
    format!("{}-{}", venue.to_lowercase(), year)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_canonical() {
        assert_eq!(parse_conference_slug("qip-2024"), Some(("QIP".to_string(), 2024)));
        assert_eq!(parse_conference_slug("qcrypt-2018"), Some(("QCRYPT".to_string(), 2018)));
        assert_eq!(parse_conference_slug("tqc-2022"), Some(("TQC".to_string(), 2022)));
        assert_eq!(parse_conference_slug("qip-1998"), Some(("QIP".to_string(), 1998)));
    }

    #[test]
    fn test_parse_legacy_compact() {
        assert_eq!(parse_conference_slug("QIP2024"), Some(("QIP".to_string(), 2024)));
        assert_eq!(parse_conference_slug("QCRYPT2011"), Some(("QCRYPT".to_string(), 2011)));
        assert_eq!(parse_conference_slug("TQC2006"), Some(("TQC".to_string(), 2006)));
    }

    #[test]
    fn test_case_insensitive() {
        assert_eq!(parse_conference_slug("QIP-2024"), Some(("QIP".to_string(), 2024)));
        assert_eq!(parse_conference_slug("Qcrypt-2018"), Some(("QCRYPT".to_string(), 2018)));
        assert_eq!(parse_conference_slug("qip2024"), Some(("QIP".to_string(), 2024)));
    }

    #[test]
    fn test_invalid_venue() {
        assert_eq!(parse_conference_slug("invalid-2024"), None);
        assert_eq!(parse_conference_slug("ABC2024"), None);
    }

    #[test]
    fn test_missing_year() {
        assert_eq!(parse_conference_slug("qip"), None);
        assert_eq!(parse_conference_slug("qcrypt-"), None);
    }

    #[test]
    fn test_invalid_year() {
        assert_eq!(parse_conference_slug("qip-abcd"), None);
        assert_eq!(parse_conference_slug("qip-1800"), None); // too old
        assert_eq!(parse_conference_slug("qip-2200"), None); // too far future
    }

    #[test]
    fn test_make_slug() {
        assert_eq!(make_conference_slug("QIP", 2024), "qip-2024");
        assert_eq!(make_conference_slug("qcrypt", 2018), "qcrypt-2018");
        assert_eq!(make_conference_slug("TQC", 2022), "tqc-2022");
    }
}
