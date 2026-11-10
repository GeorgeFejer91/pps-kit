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
	"strings"
	"testing"
)

func TestInstallFromManifestDownloadsVerifiesAndExtracts(t *testing.T) {
	temp := t.TempDir()
	t.Setenv("LOCALAPPDATA", filepath.Join(temp, "LocalAppData"))

	payloadPath := filepath.Join(temp, "payload.zip")
	writeTestZip(t, payloadPath, "apps/PPSDesigner/PPSDesigner.exe", []byte("test executable"))
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
				"component": map[string]any{
					"id":                     "full",
					"version":                "0.1.0",
					"manifest_sha256":        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
					"shared_version":         "0.1.0",
					"shared_manifest_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
				},
				"payloads": []map[string]any{{
					"kind":                   "full_windows_x64",
					"label":                  "Full PPS Toolkit package",
					"filename":               "payload.zip",
					"url":                    serverURL + "/payload.zip",
					"size_bytes":             len(payloadData),
					"sha256":                 payloadHash,
					"platform":               currentPlatform(),
					"windows_runtime_bundle": request.URL.Query().Get("runtime-bundle") == "1",
					"contains":               []string{"full", "shared"},
				}},
				"entrypoints": []map[string]any{{
					"kind":     "designer",
					"label":    "PPS Experiment Designer",
					"path":     "apps/PPSDesigner/PPSDesigner.exe",
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
	if !pathExists(filepath.Join(installDir, "apps", "PPSDesigner", "PPSDesigner.exe")) {
		t.Fatal("expected Designer executable to be extracted")
	}
	if !pathExists(filepath.Join(installDir, "pps_install_manifest.json")) {
		t.Fatal("expected install marker to be written")
	}
	t.Run("missing bundled runtimes prevent readiness", func(t *testing.T) {
		if currentPlatform() != "windows-amd64" {
			t.Skip("Windows x64 payload")
		}
		installDir := filepath.Join(temp, "incomplete")
		_, err := InstallFromManifest(context.Background(), InstallOptions{
			ManifestSource:    server.URL + "/manifest.json?runtime-bundle=1",
			ExpectedComponent: "full",
			InstallDir:        installDir,
		}, func(event ProgressEvent) {
			if event.Stage == "ready" {
				t.Error("an incomplete runtime bundle was reported ready")
			}
		})
		if err == nil || !strings.Contains(err.Error(), "verify bundled Microsoft Visual C++ 2013 Runtime") {
			t.Fatalf("expected a bundled runtime verification error, got %v", err)
		}
		if pathExists(installDir) || pathExists(installDir+".partial") {
			t.Fatal("incomplete install was left on disk")
		}
	})
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
