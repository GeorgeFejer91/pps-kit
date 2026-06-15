package main

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestInstallFromManifestDownloadsVerifiesAndExtracts(t *testing.T) {
	temp := t.TempDir()
	t.Setenv("LOCALAPPDATA", filepath.Join(temp, "LocalAppData"))

	payloadPath := filepath.Join(temp, "payload.zip")
	writeTestZip(t, payloadPath, "windows/Launch_HTML_Dashboard.bat", []byte("@echo off\r\n"))
	payloadData, err := os.ReadFile(payloadPath)
	if err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256(payloadData)
	payloadHash := hex.EncodeToString(hash[:])

	var serverURL string
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/manifest.json":
			manifest := map[string]any{
				"schema":        "pps-download-manifest.v1",
				"project":       "peripersonal-space-toolkit",
				"version":       "0.1.0",
				"source_tag":    "v0.1.0",
				"source_commit": "abc123",
				"zenodo_doi":    "10.5281/zenodo.123",
				"created_utc":   "2026-06-13T12:00:00Z",
				"payloads": []map[string]any{{
					"kind":       "offline_lab_windows_x64",
					"label":      "Offline lab package",
					"filename":   "payload.zip",
					"url":        serverURL + "/payload.zip",
					"size_bytes": len(payloadData),
					"sha256":     payloadHash,
					"platform":   currentPlatform(),
					"contains":   []string{"runner"},
				}},
				"entrypoints": []map[string]any{{
					"kind":     "dashboard",
					"label":    "PPS Dashboard",
					"path":     "windows/Launch_HTML_Dashboard.bat",
					"shortcut": false,
				}},
			}
			_ = json.NewEncoder(writer).Encode(manifest)
		case "/payload.zip":
			http.ServeFile(writer, request, payloadPath)
		default:
			http.NotFound(writer, request)
		}
	}))
	defer server.Close()
	serverURL = server.URL

	installDir := filepath.Join(temp, "install")
	result, err := InstallFromManifest(
		context.Background(),
		InstallOptions{
			ManifestSource:  server.URL + "/manifest.json",
			InstallDir:      installDir,
			CreateShortcuts: false,
		},
		nil,
	)
	if err != nil {
		t.Fatalf("InstallFromManifest returned error: %v", err)
	}
	if result.InstallDir != installDir {
		t.Fatalf("InstallDir = %q, want %q", result.InstallDir, installDir)
	}
	if !pathExists(filepath.Join(installDir, "windows", "Launch_HTML_Dashboard.bat")) {
		t.Fatal("expected dashboard launcher to be extracted")
	}
	if !pathExists(filepath.Join(installDir, "pps_install_manifest.json")) {
		t.Fatal("expected install marker to be written")
	}
}

func writeTestZip(t *testing.T, path string, name string, data []byte) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	writer := zip.NewWriter(file)
	entry, err := writer.Create(name)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := entry.Write(data); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
}
