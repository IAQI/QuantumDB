/// Conference slug utilities
///
/// Slugs are human-friendly identifiers in the format: {VENUE}{YEAR}
/// Examples: QIP2024, QCRYPT2018, TQC2022

/// Valid venue prefixes
const VENUES: &[&str] = &["QCRYPT", "QIP", "TQC"];

/// Parse a conference slug into (venue, year) components
///
/// # Examples
/// ```
/// use quantumdb::utils::parse_conference_slug;
///
/// assert_eq!(parse_conference_slug("QIP2024"), Some(("QIP".to_string(), 2024)));
/// assert_eq!(parse_conference_slug("QCRYPT2018"), Some(("QCRYPT".to_string(), 2018)));
/// assert_eq!(parse_conference_slug("TQC2022"), Some(("TQC".to_string(), 2022)));
/// assert_eq!(parse_conference_slug("qip2024"), Some(("QIP".to_string(), 2024))); // case insensitive
/// assert_eq!(parse_conference_slug("INVALID2024"), None);
/// assert_eq!(parse_conference_slug("QIP"), None); // missing year
/// ```
pub fn parse_conference_slug(slug: &str) -> Option<(String, i32)> {
    let slug_upper = slug.to_uppercase();

    // Try each venue prefix (longest first to match QCRYPT before QIP)
    for venue in VENUES {
        if slug_upper.starts_with(venue) {
            let year_str = &slug_upper[venue.len()..];
            if let Ok(year) = year_str.parse::<i32>() {
                // Sanity check: year should be reasonable (1990-2100)
                if (1990..=2100).contains(&year) {
                    return Some((venue.to_string(), year));
                }
            }
        }
    }

    None
}

/// Generate a slug from venue and year
///
/// # Examples
/// ```
/// use quantumdb::utils::make_conference_slug;
///
/// assert_eq!(make_conference_slug("QIP", 2024), "QIP2024");
/// assert_eq!(make_conference_slug("QCRYPT", 2018), "QCRYPT2018");
/// ```
pub fn make_conference_slug(venue: &str, year: i32) -> String {
    format!("{}{}", venue.to_uppercase(), year)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_qip() {
        assert_eq!(parse_conference_slug("QIP2024"), Some(("QIP".to_string(), 2024)));
        assert_eq!(parse_conference_slug("QIP1998"), Some(("QIP".to_string(), 1998)));
    }

    #[test]
    fn test_parse_qcrypt() {
        assert_eq!(parse_conference_slug("QCRYPT2024"), Some(("QCRYPT".to_string(), 2024)));
        assert_eq!(parse_conference_slug("QCRYPT2011"), Some(("QCRYPT".to_string(), 2011)));
    }

    #[test]
    fn test_parse_tqc() {
        assert_eq!(parse_conference_slug("TQC2022"), Some(("TQC".to_string(), 2022)));
        assert_eq!(parse_conference_slug("TQC2006"), Some(("TQC".to_string(), 2006)));
    }

    #[test]
    fn test_case_insensitive() {
        assert_eq!(parse_conference_slug("qip2024"), Some(("QIP".to_string(), 2024)));
        assert_eq!(parse_conference_slug("Qcrypt2018"), Some(("QCRYPT".to_string(), 2018)));
        assert_eq!(parse_conference_slug("tqc2022"), Some(("TQC".to_string(), 2022)));
    }

    #[test]
    fn test_invalid_venue() {
        assert_eq!(parse_conference_slug("INVALID2024"), None);
        assert_eq!(parse_conference_slug("ABC2024"), None);
    }

    #[test]
    fn test_missing_year() {
        assert_eq!(parse_conference_slug("QIP"), None);
        assert_eq!(parse_conference_slug("QCRYPT"), None);
    }

    #[test]
    fn test_invalid_year() {
        assert_eq!(parse_conference_slug("QIPabcd"), None);
        assert_eq!(parse_conference_slug("QIP1800"), None); // too old
        assert_eq!(parse_conference_slug("QIP2200"), None); // too far future
    }

    #[test]
    fn test_make_slug() {
        assert_eq!(make_conference_slug("QIP", 2024), "QIP2024");
        assert_eq!(make_conference_slug("qcrypt", 2018), "QCRYPT2018");
        assert_eq!(make_conference_slug("TQC", 2022), "TQC2022");
    }
}
