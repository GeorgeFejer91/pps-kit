package main

import (
	"archive/zip"
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
