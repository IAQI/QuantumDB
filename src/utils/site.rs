//! Site-wide constants and helpers for the open-data surface: the public base
//! URL, the data license, CSV encoding and JSON-LD embedding.

use std::sync::OnceLock;

/// Data license (the code is MIT; the data is CC0, see `data/LICENSE`).
pub const DATA_LICENSE: &str = "CC0-1.0";
pub const DATA_LICENSE_URL: &str = "https://creativecommons.org/publicdomain/zero/1.0/";
pub const THIRD_PARTY_NOTICE: &str = "Facts and the database itself are dedicated to the public domain under CC0 1.0. \
Abstracts, slides and recordings linked or reproduced here remain the property of their authors and are provided for reference.";
pub const HOW_TO_CITE: &str = "QuantumDB: a database of the QIP, QCrypt and TQC conferences. \
International Association for Quantum Information (IAQI). https://quantumdb.iaqi.org";
pub const CONTACT_EMAIL: &str = "quantumdb@iaqi.org";
pub const SOURCE_REPO: &str = "https://github.com/IAQI/QuantumDB";

/// Absolute base URL of the public site, without a trailing slash. Read once
/// from `PUBLIC_BASE_URL`; defaults to the live instance.
pub fn public_base_url() -> &'static str {
    static URL: OnceLock<String> = OnceLock::new();
    URL.get_or_init(|| {
        std::env::var("PUBLIC_BASE_URL")
            .ok()
            .map(|s| s.trim().trim_end_matches('/').to_string())
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| "https://quantumdb.iaqi.org".to_string())
    })
}

/// Quote one CSV field per RFC 4180: wrap in quotes when it contains a comma,
/// quote, CR or LF, doubling any embedded quotes.
pub fn csv_field(s: &str) -> String {
    if s.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s.to_string()
    }
}

/// Encode one CSV row (newline-terminated).
pub fn csv_row<S: AsRef<str>>(fields: &[S]) -> String {
    let mut line = fields
        .iter()
        .map(|f| csv_field(f.as_ref()))
        .collect::<Vec<_>>()
        .join(",");
    line.push('\n');
    line
}

/// Serialize a JSON-LD object for embedding in `<script type="application/ld+json">`.
/// `<`, `>` and `&` are escaped as JSON unicode escapes so text such as
/// `</script>` inside a title can't end the script element early.
pub fn json_ld(value: &serde_json::Value) -> String {
    serde_json::to_string(value)
        .unwrap_or_else(|_| "{}".to_string())
        .replace('<', "\\u003c")
        .replace('>', "\\u003e")
        .replace('&', "\\u0026")
}

/// Escape text for XML element content (sitemap URLs).
pub fn xml_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

/// The schema.org `Dataset` description of QuantumDB, shared by the home and
/// about pages (eligible for Google Dataset Search).
pub fn dataset_json_ld() -> serde_json::Value {
    let base = public_base_url();
    serde_json::json!({
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "QuantumDB",
        "alternateName": "IAQI QuantumDB",
        "description": "Curated database of the quantum information conferences QIP (Quantum Information Processing), QCrypt (Conference on Quantum Cryptography) and TQC (Theory of Quantum Computation, Communication and Cryptography): every conference instance, accepted talks and posters with their authors, programme/steering/organizing committees, and figures announced at the business meetings.",
        "url": base,
        "sameAs": SOURCE_REPO,
        "keywords": ["quantum information", "quantum computing", "quantum cryptography", "conferences", "QIP", "QCrypt", "TQC", "bibliography"],
        "license": DATA_LICENSE_URL,
        "isAccessibleForFree": true,
        "creator": {"@type": "Organization", "name": "International Association for Quantum Information (IAQI)", "url": "https://iaqi.org"},
        "publisher": {"@type": "Organization", "name": "International Association for Quantum Information (IAQI)", "url": "https://iaqi.org"},
        "temporalCoverage": "1998/..",
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": format!("{base}/api/v1/export/all.json"), "name": "Index of all conferences"},
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": format!("{base}/api/v1/export/all-full.json"), "name": "Full dataset (all conferences, talks, authors, committees)"},
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": format!("{base}/api/v1/export/authors.json"), "name": "All authors"}
        ],
        "citation": HOW_TO_CITE
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quotes_csv_fields_only_when_needed() {
        assert_eq!(csv_field("plain"), "plain");
        assert_eq!(csv_field("a,b"), "\"a,b\"");
        assert_eq!(csv_field("say \"hi\""), "\"say \"\"hi\"\"\"");
        assert_eq!(csv_field("two\nlines"), "\"two\nlines\"");
        assert_eq!(csv_field(""), "");
    }

    #[test]
    fn encodes_csv_rows() {
        assert_eq!(csv_row(&["QIP", "2015", "x, y"]), "QIP,2015,\"x, y\"\n");
    }

    #[test]
    fn json_ld_cannot_close_script() {
        let v = serde_json::json!({"name": "</script><b>&"});
        let s = json_ld(&v);
        assert!(!s.contains('<') && !s.contains('>') && !s.contains('&'));
        let back: serde_json::Value = serde_json::from_str(&s).unwrap();
        assert_eq!(back["name"], "</script><b>&");
    }

    #[test]
    fn escapes_xml() {
        assert_eq!(xml_escape("a&b<c>"), "a&amp;b&lt;c&gt;");
    }
}
