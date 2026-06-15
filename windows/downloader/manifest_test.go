package main

import "testing"

func TestParseDownloadManifestSelectsWindowsPayload(t *testing.T) {
	manifest, err := ParseDownloadManifest([]byte(`{
	  "schema": "pps-download-manifest.v1",
	  "project": "peripersonal-space-toolkit",
	  "version": "0.1.0",
	  "source_tag": "v0.1.0",
	  "source_commit": "abc123",
	  "zenodo_doi": "10.5281/zenodo.123",
	  "created_utc": "2026-06-13T12:00:00Z",
	  "payloads": [{
	    "kind": "offline_lab_windows_x64",
	    "label": "Offline lab package",
	    "filename": "PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip",
	    "url": "https://zenodo.example/files/PPS.zip",
	    "size_bytes": 12,
	    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	    "platform": "windows-amd64",
	    "contains": ["runner"]
	  }],
	  "entrypoints": [{"kind": "dashboard", "label": "PPS Dashboard", "path": "windows/Launch_HTML_Dashboard.bat", "shortcut": true}]
	}`))
	if err != nil {
		t.Fatalf("ParseDownloadManifest returned error: %v", err)
	}
	payload, err := manifest.SelectPayload("")
	if err != nil {
		t.Fatalf("SelectPayload returned error: %v", err)
	}
	if payload.Kind != defaultPayloadKind {
		t.Fatalf("payload kind = %q, want %q", payload.Kind, defaultPayloadKind)
	}
	entrypoint, ok := manifest.Entrypoint("dashboard")
	if !ok || entrypoint.Path == "" {
		t.Fatalf("dashboard entrypoint missing: %#v", entrypoint)
	}
}

func TestParseDownloadManifestRejectsMissingHash(t *testing.T) {
	_, err := ParseDownloadManifest([]byte(`{
	  "schema": "pps-download-manifest.v1",
	  "version": "0.1.0",
	  "payloads": [{"kind": "offline_lab_windows_x64", "filename": "x.zip", "url": "https://example.test/x.zip", "sha256": "bad"}]
	}`))
	if err == nil {
		t.Fatal("ParseDownloadManifest accepted a payload without a valid SHA256")
	}
}

func TestParseDownloadManifestRejectsIncompletePackageInventory(t *testing.T) {
	_, err := ParseDownloadManifest([]byte(`{
	  "schema": "pps-download-manifest.v1",
	  "version": "0.1.0",
	  "payloads": [{
	    "kind": "offline_lab_windows_x64",
	    "filename": "x.zip",
	    "url": "https://example.test/x.zip",
	    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	    "package_inventory": {
	      "schema": "pps-installer-package-inventory.v1",
	      "filename": "pps_package_inventory.v1.json",
	      "path_in_payload": "pps_package_inventory.v1.json",
	      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
	      "item_count": 10,
	      "required_item_count": 8,
	      "missing_required_count": 1
	    }
	  }]
	}`))
	if err == nil {
		t.Fatal("ParseDownloadManifest accepted an inventory with missing required items")
	}
}
