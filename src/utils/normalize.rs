//! Name normalization utilities for author matching.
//!
//! This module provides functions to normalize names for deduplication and matching.
//! Key transformations:
//! - Convert to lowercase
//! - Remove accents/diacritics (é → e, ü → u, etc.)
//! - Normalize whitespace
//! - Handle special characters
//! - Support various name formats (Western, Asian, etc.)

use unicode_normalization::UnicodeNormalization;

/// Normalize a name for matching purposes.
///
/// Transformations applied:
/// 1. Replace special characters that don't decompose (ł, ø, æ, etc.)
/// 2. Unicode NFD normalization (decompose characters)
/// 3. Remove combining diacritical marks (accents)
/// 4. Convert to lowercase
/// 5. Normalize whitespace (collapse multiple spaces, trim)
///
/// # Examples
///
/// ```
/// use quantumdb::utils::normalize_name;
///
/// assert_eq!(normalize_name("José García"), "jose garcia");
/// assert_eq!(normalize_name("Müller"), "muller");
/// assert_eq!(normalize_name("Schrödinger"), "schrodinger");
/// assert_eq!(normalize_name("  Alice   Bob  "), "alice bob");
/// ```
pub fn normalize_name(name: &str) -> String {
    // First, replace special characters that don't decompose via NFD
    let replaced = replace_special_chars(name);

    replaced
        // NFD decomposition: splits characters into base + combining marks
        // e.g., "é" becomes "e" + combining acute accent
        .nfd()
        // Filter out combining diacritical marks (Unicode category Mn)
        .filter(|c| !is_combining_mark(*c))
        // Collect to string for further processing
        .collect::<String>()
        // Convert to lowercase
        .to_lowercase()
        // Normalize whitespace
        .split_whitespace()
        .collect::<Vec<&str>>()
        .join(" ")
}

/// Replace special characters that don't decompose via Unicode NFD.
///
/// Some characters like Ł, Ø, Æ are distinct letters, not accented versions,
/// so they need explicit replacement for normalization.
fn replace_special_chars(s: &str) -> String {
    s.chars()
        .map(|c| match c {
            // Polish
            'Ł' => 'L',
            'ł' => 'l',
            // Nordic
            'Ø' => 'O',
            'ø' => 'o',
            'Æ' => 'A',
            'æ' => 'a',
            'Å' => 'A',
            'å' => 'a',
            // German
            'ß' => 's', // Eszett to single s (could also be "ss")
            // Icelandic
            'Ð' => 'D',
            'ð' => 'd',
            'Þ' => 'T',
            'þ' => 't',
            // Croatian/Serbian
            'Đ' => 'D',
            'đ' => 'd',
            // Turkish
            'İ' => 'I',
            'ı' => 'i',
            'Ğ' => 'G',
            'ğ' => 'g',
            'Ş' => 'S',
            'ş' => 's',
            // Others pass through for NFD handling
            _ => c,
        })
        .collect()
}

/// Normalize a name and also remove punctuation for looser matching.
///
/// In addition to standard normalization:
/// - Removes hyphens, apostrophes, periods
/// - Useful for matching "O'Brien" with "OBrien" or "Jean-Pierre" with "Jean Pierre"
///
/// # Examples
///
/// ```
/// use quantumdb::utils::normalize_name_loose;
///
/// assert_eq!(normalize_name_loose("O'Brien"), "obrien");
/// assert_eq!(normalize_name_loose("Jean-Pierre"), "jeanpierre");
/// assert_eq!(normalize_name_loose("Dr. Smith Jr."), "dr smith jr");
/// ```
pub fn normalize_name_loose(name: &str) -> String {
    let normalized = normalize_name(name);

    normalized
        .chars()
        .filter(|c| c.is_alphanumeric() || c.is_whitespace())
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<&str>>()
        .join(" ")
}

/// Extract initials from a name.
///
/// Returns uppercase initials from each word in the name.
///
/// # Examples
///
/// ```
/// use quantumdb::utils::extract_initials;
///
/// assert_eq!(extract_initials("Alice Bob Quantum"), "ABQ");
/// assert_eq!(extract_initials("John von Neumann"), "JVN");
/// ```
pub fn extract_initials(name: &str) -> String {
    name.split_whitespace()
        .filter_map(|word| word.chars().next())
        .map(|c| c.to_uppercase().to_string())
        .collect()
}

/// Check if a character is a combining diacritical mark.
///
/// Combining marks are Unicode characters that modify the preceding character,
/// such as accents (́), umlauts (̈), cedillas (̧), etc.
fn is_combining_mark(c: char) -> bool {
    // Unicode combining diacritical marks range
    // See: https://unicode.org/charts/PDF/U0300.pdf
    matches!(c,
        '\u{0300}'..='\u{036F}' |  // Combining Diacritical Marks
        '\u{1AB0}'..='\u{1AFF}' |  // Combining Diacritical Marks Extended
        '\u{1DC0}'..='\u{1DFF}' |  // Combining Diacritical Marks Supplement
        '\u{20D0}'..='\u{20FF}' |  // Combining Diacritical Marks for Symbols
        '\u{FE20}'..='\u{FE2F}'    // Combining Half Marks
    )
}

/// Compare two names for potential match, returning a similarity score.
///
/// Returns a value between 0.0 (no match) and 1.0 (exact match).
/// Uses normalized forms for comparison.
///
/// # Examples
///
/// ```
/// use quantumdb::utils::name_similarity;
///
/// // Exact match after accent normalization
/// assert!(name_similarity("José García", "Jose Garcia") > 0.99);
/// // Partial word overlap
/// assert!(name_similarity("Alice Smith", "Bob Smith") > 0.3);
/// // No common words
/// assert!(name_similarity("John Doe", "Alice Smith") < 0.1);
/// ```
pub fn name_similarity(name1: &str, name2: &str) -> f64 {
    let norm1 = normalize_name(name1);
    let norm2 = normalize_name(name2);

    if norm1 == norm2 {
        return 1.0;
    }

    // Check loose match
    let loose1 = normalize_name_loose(name1);
    let loose2 = normalize_name_loose(name2);

    if loose1 == loose2 {
        return 0.95;
    }

    // Calculate Jaccard similarity on words
    let words1: std::collections::HashSet<&str> = norm1.split_whitespace().collect();
    let words2: std::collections::HashSet<&str> = norm2.split_whitespace().collect();

    let intersection = words1.intersection(&words2).count();
    let union = words1.union(&words2).count();

    if union == 0 {
        return 0.0;
    }

    intersection as f64 / union as f64
}

/// Split a full name into (given_name, family_name) components.
///
/// Uses common heuristics:
/// - For Western names: last word is family name, rest is given name
/// - Handles common prefixes like "van", "von", "de", "la"
///
/// # Examples
///
/// ```
/// use quantumdb::utils::split_name;
///
/// assert_eq!(split_name("John Smith"), (Some("John".into()), Some("Smith".into())));
/// assert_eq!(split_name("Ludwig van Beethoven"), (Some("Ludwig".into()), Some("van Beethoven".into())));
/// ```
pub fn split_name(full_name: &str) -> (Option<String>, Option<String>) {
    let parts: Vec<&str> = full_name.split_whitespace().collect();

    if parts.is_empty() {
        return (None, None);
    }

    if parts.len() == 1 {
        return (None, Some(parts[0].to_string()));
    }

    // Common family name prefixes
    let prefixes = ["van", "von", "de", "del", "della", "di", "da", "la", "le", "du", "des", "ten", "ter", "vander"];

    // Find where the family name starts
    let mut family_start = parts.len() - 1;

    // Check if there's a prefix before the last name
    for i in (0..parts.len() - 1).rev() {
        if prefixes.contains(&parts[i].to_lowercase().as_str()) {
            family_start = i;
        } else {
            break;
        }
    }

    let given = if family_start > 0 {
        Some(parts[..family_start].join(" "))
    } else {
        None
    };

    let family = Some(parts[family_start..].join(" "));

    (given, family)
}

/// Generate potential name variants for fuzzy matching.
///
/// Returns a list of normalized variants that might match this name:
/// - Standard normalization
/// - Loose normalization (no punctuation)
/// - Initials + family name
/// - Family name only
pub fn generate_name_variants(full_name: &str) -> Vec<String> {
    let mut variants = Vec::new();

    // Standard normalized form
    let normalized = normalize_name(full_name);
    variants.push(normalized.clone());

    // Loose normalized form
    let loose = normalize_name_loose(full_name);
    if loose != normalized {
        variants.push(loose);
    }

    // Split into given/family
    let (given, family) = split_name(full_name);

    // Family name only
    if let Some(ref fam) = family {
        let norm_family = normalize_name(fam);
        if !variants.contains(&norm_family) {
            variants.push(norm_family);
        }
    }

    // Initials + family name (e.g., "A. Einstein")
    if let (Some(ref giv), Some(ref fam)) = (&given, &family) {
        let initials = extract_initials(giv);
        let variant = format!("{} {}", initials.to_lowercase(), normalize_name(fam));
        if !variants.contains(&variant) {
            variants.push(variant);
        }
    }

    variants
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_basic() {
        assert_eq!(normalize_name("Alice"), "alice");
        assert_eq!(normalize_name("ALICE"), "alice");
        assert_eq!(normalize_name("  alice  "), "alice");
    }

    #[test]
    fn test_normalize_accents() {
        assert_eq!(normalize_name("José"), "jose");
        assert_eq!(normalize_name("García"), "garcia");
        assert_eq!(normalize_name("Müller"), "muller");
        assert_eq!(normalize_name("Schrödinger"), "schrodinger");
        assert_eq!(normalize_name("Cañón"), "canon");
        assert_eq!(normalize_name("naïve"), "naive");
        assert_eq!(normalize_name("Zürich"), "zurich");
        assert_eq!(normalize_name("Čech"), "cech");
        assert_eq!(normalize_name("Łukasz"), "lukasz");
    }

    #[test]
    fn test_normalize_whitespace() {
        assert_eq!(normalize_name("  Alice   Bob  "), "alice bob");
        assert_eq!(normalize_name("Alice\t\nBob"), "alice bob");
        assert_eq!(normalize_name("Alice  Bob  Carol"), "alice bob carol");
    }

    #[test]
    fn test_normalize_loose() {
        assert_eq!(normalize_name_loose("O'Brien"), "obrien");
        assert_eq!(normalize_name_loose("Jean-Pierre"), "jeanpierre");
        assert_eq!(normalize_name_loose("Dr. Smith"), "dr smith");
        assert_eq!(normalize_name_loose("Smith, Jr."), "smith jr");
    }

    #[test]
    fn test_extract_initials() {
        assert_eq!(extract_initials("Alice Bob"), "AB");
        assert_eq!(extract_initials("John von Neumann"), "JVN");
        assert_eq!(extract_initials("Alice"), "A");
    }

    #[test]
    fn test_split_name() {
        assert_eq!(
            split_name("John Smith"),
            (Some("John".into()), Some("Smith".into()))
        );
        assert_eq!(
            split_name("Ludwig van Beethoven"),
            (Some("Ludwig".into()), Some("van Beethoven".into()))
        );
        assert_eq!(
            split_name("Leonardo da Vinci"),
            (Some("Leonardo".into()), Some("da Vinci".into()))
        );
        assert_eq!(
            split_name("Galileo"),
            (None, Some("Galileo".into()))
        );
    }

    #[test]
    fn test_name_similarity() {
        // Exact match after normalization
        assert!(name_similarity("José García", "Jose Garcia") > 0.99);

        // Same name, different accents
        assert!(name_similarity("Müller", "Muller") > 0.99);

        // Partial match
        let sim = name_similarity("Alice Smith", "Bob Smith");
        assert!(sim > 0.3 && sim < 0.7);

        // No match
        assert!(name_similarity("Alice", "Bob") < 0.1);
    }

    #[test]
    fn test_generate_variants() {
        let variants = generate_name_variants("Albert Einstein");
        assert!(variants.contains(&"albert einstein".to_string()));
        assert!(variants.contains(&"einstein".to_string()));
        assert!(variants.contains(&"a einstein".to_string()));
    }

    #[test]
    fn test_nordic_characters() {
        assert_eq!(normalize_name("Åsa"), "asa");
        assert_eq!(normalize_name("Øresund"), "oresund");
        assert_eq!(normalize_name("Björk"), "bjork");
    }

    #[test]
    fn test_complex_names() {
        // Common academic name patterns
        assert_eq!(normalize_name("Jean-François"), "jean-francois");
        assert_eq!(normalize_name_loose("Jean-François"), "jeanfrancois");

        // Multiple accents
        assert_eq!(normalize_name("Éléonore"), "eleonore");

        // Vietnamese
        assert_eq!(normalize_name("Nguyễn"), "nguyen");
    }
}
