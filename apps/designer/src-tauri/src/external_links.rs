// This handoff opens an ordinary web URL in the system browser. It never
// navigates the privileged WebView or accepts a file path/application name.
pub(crate) fn web_url(input: &str) -> Result<String, String> {
    if input.len() > 4096 || input.chars().any(char::is_control) {
        return Err("external_link_invalid".into());
    }
    let url = tauri::Url::parse(input).map_err(|_| "external_link_invalid")?;
    if !matches!(url.scheme(), "https" | "http")
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err("external_link_not_allowed".into());
    }
    let url = url.to_string();
    if url.len() > 4096 {
        return Err("external_link_invalid".into());
    }
    Ok(url)
}

#[cfg(test)]
mod tests {
    use super::web_url;

    #[test]
    fn external_web_urls_are_bounded_and_cannot_select_local_handlers() {
        for url in [
            "https://doi.org/10.1038/example",
            "https://github.com/GeorgeFejer91/pps-kit/releases",
            "http://publisher.example/paper?q=auditory%20tactile#methods",
        ] {
            assert_eq!(web_url(url).unwrap(), url);
        }
        for url in [
            "",
            "/local/path",
            "C:\\private\\file.txt",
            "file:///C:/private/file.txt",
            "javascript:alert(1)",
            "data:text/html,example",
            "mailto:a@example.org",
            "pps-resource://localhost/asset.wav",
            "https://",
            "https://user:password@example.org/paper",
            "https://example.org/\nnext",
            "https://example.org/\0next",
        ] {
            assert!(web_url(url).is_err(), "disallowed URL accepted");
        }
        assert!(web_url(&format!("https://example.org/{}", "a".repeat(4096))).is_err());
    }
}
