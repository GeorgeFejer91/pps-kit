package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"runtime"
	"strings"
)

const manifestSchema = "pps-download-manifest.v1"
const defaultPayloadKind = "offline_lab_windows_x64"

type DownloadManifest struct {
	Schema       string       `json:"schema"`
	Project      string       `json:"project"`
	Version      string       `json:"version"`
	SourceTag    string       `json:"source_tag"`
	SourceCommit string       `json:"source_commit"`
	ZenodoDOI    string       `json:"zenodo_doi"`
	CreatedUTC   string       `json:"created_utc"`
	Payloads     []Payload    `json:"payloads"`
	Entrypoints  []Entrypoint `json:"entrypoints"`
}

type Payload struct {
	Kind      string   `json:"kind"`
	Label     string   `json:"label"`
	Filename  string   `json:"filename"`
	URL       string   `json:"url"`
	SizeBytes int64    `json:"size_bytes"`
	SHA256    string   `json:"sha256"`
	Platform  string   `json:"platform"`
	Contains  []string `json:"contains"`
}

type Entrypoint struct {
	Kind     string `json:"kind"`
	Label    string `json:"label"`
	Path     string `json:"path"`
	Shortcut bool   `json:"shortcut"`
}

func ParseDownloadManifest(data []byte) (DownloadManifest, error) {
	var manifest DownloadManifest
	if err := json.Unmarshal(data, &manifest); err != nil {
		return manifest, fmt.Errorf("parse download manifest: %w", err)
	}
	if err := manifest.Validate(); err != nil {
		return manifest, err
	}
	return manifest, nil
}

func (m DownloadManifest) Validate() error {
	if m.Schema != manifestSchema {
		return fmt.Errorf("unsupported manifest schema %q", m.Schema)
	}
	if strings.TrimSpace(m.Version) == "" {
		return errors.New("manifest version is required")
	}
	if len(m.Payloads) == 0 {
		return errors.New("manifest must contain at least one payload")
	}
	for _, payload := range m.Payloads {
		if strings.TrimSpace(payload.Kind) == "" {
			return errors.New("payload kind is required")
		}
		if strings.TrimSpace(payload.URL) == "" {
			return fmt.Errorf("payload %q is missing url", payload.Kind)
		}
		if strings.TrimSpace(payload.Filename) == "" {
			return fmt.Errorf("payload %q is missing filename", payload.Kind)
		}
		if len(payload.SHA256) != 64 {
			return fmt.Errorf("payload %q must include a 64-character SHA256", payload.Kind)
		}
		if payload.SizeBytes < 0 {
			return fmt.Errorf("payload %q has a negative size", payload.Kind)
		}
	}
	return nil
}

func (m DownloadManifest) SelectPayload(kind string) (Payload, error) {
	if strings.TrimSpace(kind) == "" {
		kind = defaultPayloadKind
	}
	platform := currentPlatform()
	var fallback *Payload
	for index := range m.Payloads {
		payload := m.Payloads[index]
		if payload.Kind != kind {
			continue
		}
		if fallback == nil {
			fallback = &payload
		}
		if payload.Platform == "" || strings.EqualFold(payload.Platform, platform) {
			return payload, nil
		}
	}
	if fallback != nil {
		return *fallback, nil
	}
	return Payload{}, fmt.Errorf("manifest has no payload with kind %q", kind)
}

func (m DownloadManifest) Entrypoint(kind string) (Entrypoint, bool) {
	for _, entrypoint := range m.Entrypoints {
		if entrypoint.Kind == kind {
			return entrypoint, true
		}
	}
	return Entrypoint{}, false
}

func currentPlatform() string {
	return runtime.GOOS + "-" + runtime.GOARCH
}
