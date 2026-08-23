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
	    "kind": "full_windows_x64",
	    "label": "Full PPS Toolkit package",
	    "filename": "PPS-Toolkit-v0.1.0-windows-x64.zip",
	    "url": "https://zenodo.example/files/PPS.zip",
	    "size_bytes": 12,
	    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	    "platform": "windows-amd64",
	    "contains": ["full", "shared"]
	  }],
	  "entrypoints": [{"kind": "designer", "label": "PPS Experiment Designer", "path": "apps/PPSDesigner/PPSDesigner.exe", "shortcut": true}]
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
	entrypoint, ok := manifest.Entrypoint("designer")
	if !ok || entrypoint.Path == "" {
		t.Fatalf("designer entrypoint missing: %#v", entrypoint)
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

func TestParseDownloadManifestRejectsExternalAutoDownloadWithoutPermission(t *testing.T) {
	_, err := ParseDownloadManifest([]byte(`{
	  "schema": "pps-download-manifest.v1",
	  "version": "0.1.0",
	  "payloads": [{
	    "kind": "offline_lab_windows_x64",
	    "filename": "x.zip",
	    "url": "https://example.test/x.zip",
	    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	  }],
	  "external_dependencies": [{
	    "kind": "native_driver",
	    "label": "Native driver",
	    "provider_page_url": "https://provider.example/drivers",
	    "download_url": "https://mirror.example/native-driver.exe",
	    "filename": "native-driver.exe",
	    "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
	    "redistribution_permitted": false,
	    "auto_download": true
	  }]
	}`))
	if err == nil {
		t.Fatal("ParseDownloadManifest accepted auto_download without redistribution permission")
	}
}

func TestParseDownloadManifestAcceptsPinnedComponentHashes(t *testing.T) {
	manifest, err := ParseDownloadManifest([]byte(`{
	  "schema": "pps-download-manifest.v1",
	  "version": "0.1.0",
	  "component": {
	    "id": "designer",
	    "version": "0.1.0",
	    "manifest_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	    "shared_version": "0.1.0",
	    "shared_manifest_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	  },
	  "payloads": [{
	    "kind": "designer_windows_x64",
	    "filename": "designer.zip",
	    "url": "https://example.test/designer.zip",
	    "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
	  }]
	}`))
	if err != nil {
		t.Fatalf("ParseDownloadManifest returned error: %v", err)
	}
	if manifest.Component.ID != "designer" {
		t.Fatalf("component = %q, want designer", manifest.Component.ID)
	}
}
