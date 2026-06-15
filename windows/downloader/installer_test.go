package main

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"testing"
)

func TestVerifyFileSHA256(t *testing.T) {
	path := filepath.Join(t.TempDir(), "payload.zip")
	if err := os.WriteFile(path, []byte("payload"), 0o644); err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256([]byte("payload"))
	if err := verifyFileSHA256(path, hex.EncodeToString(hash[:])); err != nil {
		t.Fatalf("verifyFileSHA256 returned error: %v", err)
	}
	if err := verifyFileSHA256(path, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"); err == nil {
		t.Fatal("verifyFileSHA256 accepted wrong hash")
	}
}

func TestExtractZipRejectsZipSlip(t *testing.T) {
	dir := t.TempDir()
	zipPath := filepath.Join(dir, "bad.zip")
	file, err := os.Create(zipPath)
	if err != nil {
		t.Fatal(err)
	}
	writer := zip.NewWriter(file)
	entry, err := writer.Create("../escape.txt")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := entry.Write([]byte("nope")); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	if err := extractZip(zipPath, filepath.Join(dir, "out")); err == nil {
		t.Fatal("extractZip accepted a zip-slip entry")
	}
}

func TestHandleExternalDependenciesOpensProviderPageWhenRedistributionBlocked(t *testing.T) {
	var opened []string
	previous := openExternalURL
	openExternalURL = func(rawURL string) error {
		opened = append(opened, rawURL)
		return nil
	}
	t.Cleanup(func() {
		openExternalURL = previous
	})

	statuses, err := handleExternalDependencies(
		context.Background(),
		[]ExternalDependency{{
			Kind:                    "native_instruments_komplete_audio_asio",
			Label:                   "Native Instruments Komplete Audio ASIO Driver",
			ProviderPageURL:         "https://provider.example/drivers",
			RedistributionPermitted: false,
			AutoDownload:            false,
		}},
		t.TempDir(),
		func(ProgressEvent) {},
	)
	if err != nil {
		t.Fatalf("handleExternalDependencies returned error: %v", err)
	}
	if len(statuses) != 1 || statuses[0].Status != "provider_action_required" {
		t.Fatalf("unexpected statuses: %#v", statuses)
	}
	if len(opened) != 1 || opened[0] != "https://provider.example/drivers" {
		t.Fatalf("provider URL was not opened: %#v", opened)
	}
}
