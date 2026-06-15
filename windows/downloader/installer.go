package main

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

type InstallOptions struct {
	ManifestSource  string
	PayloadKind     string
	InstallDir      string
	CreateShortcuts bool
	Launch          bool
	Force           bool
}

type InstallResult struct {
	Manifest                 DownloadManifest
	Payload                  Payload
	InstallDir               string
	PayloadPath              string
	LaunchPath               string
	Reused                   bool
	ExternalDependencyStatus []ExternalDependencyStatus
}

type ProgressEvent struct {
	Stage      string
	Message    string
	Downloaded int64
	Total      int64
}

type ProgressFunc func(ProgressEvent)

var openExternalURL = openURL

type ExternalDependencyStatus struct {
	Kind       string
	Label      string
	Status     string
	Path       string
	Message    string
	ProviderURL string
}

func InstallFromManifest(ctx context.Context, options InstallOptions, progress ProgressFunc) (InstallResult, error) {
	if progress == nil {
		progress = func(ProgressEvent) {}
	}
	progress(ProgressEvent{Stage: "manifest", Message: "Reading download manifest"})
	manifestBytes, err := readSource(ctx, options.ManifestSource)
	if err != nil {
		return InstallResult{}, err
	}
	manifest, err := ParseDownloadManifest(manifestBytes)
	if err != nil {
		return InstallResult{}, err
	}
	payload, err := manifest.SelectPayload(options.PayloadKind)
	if err != nil {
		return InstallResult{}, err
	}

	installDir := strings.TrimSpace(options.InstallDir)
	if installDir == "" {
		installDir = defaultInstallDir(manifest.Version)
	}
	installDir, err = filepath.Abs(installDir)
	if err != nil {
		return InstallResult{}, fmt.Errorf("resolve install dir: %w", err)
	}
	downloadDir, err := defaultDownloadDir()
	if err != nil {
		return InstallResult{}, err
	}
	payloadPath := filepath.Join(downloadDir, payload.Filename)

	if !options.Force && existingInstallLooksValid(installDir, payload) {
		dependencyStatuses, err := handleExternalDependencies(ctx, manifest.ExternalDependencies, downloadDir, progress)
		if err != nil {
			return InstallResult{}, err
		}
		result := InstallResult{Manifest: manifest, Payload: payload, InstallDir: installDir, PayloadPath: payloadPath, Reused: true, ExternalDependencyStatus: dependencyStatuses}
		result.LaunchPath = resolveLaunchPath(installDir, manifest)
		if options.Launch {
			_ = launchEntrypoint(result.LaunchPath)
		}
		progress(ProgressEvent{Stage: "ready", Message: "Existing verified install is ready", Total: 1, Downloaded: 1})
		return result, nil
	}

	if err := os.MkdirAll(downloadDir, 0o755); err != nil {
		return InstallResult{}, fmt.Errorf("create download dir: %w", err)
	}
	progress(ProgressEvent{Stage: "download", Message: "Downloading offline lab package", Total: payload.SizeBytes})
	if err := ensurePayload(ctx, payload, payloadPath, "Downloading offline lab package", progress); err != nil {
		return InstallResult{}, err
	}
	progress(ProgressEvent{Stage: "verify", Message: "Verifying SHA256"})
	if err := verifyFileSHA256(payloadPath, payload.SHA256); err != nil {
		return InstallResult{}, err
	}

	if filepath.Clean(installDir) == filepath.Clean(downloadDir) {
		return InstallResult{}, errors.New("install dir cannot be the download dir")
	}
	if pathExists(installDir) && !options.Force {
		return InstallResult{}, fmt.Errorf("install dir already exists but is not verified for this payload: %s", installDir)
	}
	if pathExists(installDir) {
		if !canReplaceInstallDir(installDir) {
			return InstallResult{}, fmt.Errorf("refusing to replace install dir outside the PPS version root: %s", installDir)
		}
		if err := os.RemoveAll(installDir); err != nil {
			return InstallResult{}, fmt.Errorf("remove old install dir: %w", err)
		}
	}
	partialDir := installDir + ".partial"
	_ = os.RemoveAll(partialDir)
	if err := os.MkdirAll(partialDir, 0o755); err != nil {
		return InstallResult{}, fmt.Errorf("create partial install dir: %w", err)
	}
	progress(ProgressEvent{Stage: "extract", Message: "Extracting verified package"})
	if err := extractZip(payloadPath, partialDir); err != nil {
		_ = os.RemoveAll(partialDir)
		return InstallResult{}, err
	}
	if err := writeInstallMarker(partialDir, manifest, payload); err != nil {
		_ = os.RemoveAll(partialDir)
		return InstallResult{}, err
	}
	if err := os.MkdirAll(filepath.Dir(installDir), 0o755); err != nil {
		_ = os.RemoveAll(partialDir)
		return InstallResult{}, fmt.Errorf("create install parent: %w", err)
	}
	if err := os.Rename(partialDir, installDir); err != nil {
		_ = os.RemoveAll(partialDir)
		return InstallResult{}, fmt.Errorf("finalize install dir: %w", err)
	}

	dependencyStatuses, err := handleExternalDependencies(ctx, manifest.ExternalDependencies, downloadDir, progress)
	if err != nil {
		return InstallResult{}, err
	}
	result := InstallResult{Manifest: manifest, Payload: payload, InstallDir: installDir, PayloadPath: payloadPath, ExternalDependencyStatus: dependencyStatuses}
	result.LaunchPath = resolveLaunchPath(installDir, manifest)
	if options.CreateShortcuts {
		progress(ProgressEvent{Stage: "shortcuts", Message: "Creating shortcuts"})
		if err := createShortcuts(installDir, manifest); err != nil {
			return result, err
		}
	}
	if options.Launch {
		progress(ProgressEvent{Stage: "launch", Message: "Launching PPS Toolkit"})
		if err := launchEntrypoint(result.LaunchPath); err != nil {
			return result, err
		}
	}
	progress(ProgressEvent{Stage: "ready", Message: "PPS Toolkit is installed", Total: 1, Downloaded: 1})
	return result, nil
}

func handleExternalDependencies(ctx context.Context, dependencies []ExternalDependency, downloadDir string, progress ProgressFunc) ([]ExternalDependencyStatus, error) {
	statuses := make([]ExternalDependencyStatus, 0, len(dependencies))
	for _, dependency := range dependencies {
		label := strings.TrimSpace(dependency.Label)
		if label == "" {
			label = dependency.Kind
		}
		if !dependency.AutoDownload {
			statuses = append(statuses, ExternalDependencyStatus{
				Kind:        dependency.Kind,
				Label:       label,
				Status:      "provider_action_required",
				ProviderURL: dependency.ProviderPageURL,
				Message:     fmt.Sprintf("%s must be installed from the provider source: %s", label, dependency.ProviderPageURL),
			})
			progress(ProgressEvent{Stage: "external-dependency", Message: fmt.Sprintf("%s requires provider install: %s", label, dependency.ProviderPageURL)})
			_ = openExternalURL(dependency.ProviderPageURL)
			continue
		}
		if !dependency.RedistributionPermitted {
			return statuses, fmt.Errorf("refusing to auto-download %s without redistribution permission", label)
		}
		externalDir := filepath.Join(downloadDir, "external")
		if err := os.MkdirAll(externalDir, 0o755); err != nil {
			return statuses, fmt.Errorf("create external dependency cache: %w", err)
		}
		path := filepath.Join(externalDir, dependency.Filename)
		payload := Payload{
			Kind:      dependency.Kind,
			Label:     label,
			Filename:  dependency.Filename,
			URL:       dependency.DownloadURL,
			SizeBytes: dependency.SizeBytes,
			SHA256:    dependency.SHA256,
		}
		progress(ProgressEvent{Stage: "external-dependency", Message: "Downloading " + label, Total: dependency.SizeBytes})
		if err := ensurePayload(ctx, payload, path, "Downloading "+label, progress); err != nil {
			return statuses, err
		}
		if err := verifyFileSHA256(path, dependency.SHA256); err != nil {
			return statuses, err
		}
		statuses = append(statuses, ExternalDependencyStatus{
			Kind:        dependency.Kind,
			Label:       label,
			Status:      "downloaded_verified",
			Path:        path,
			ProviderURL: dependency.ProviderPageURL,
			Message:     fmt.Sprintf("%s downloaded and SHA256-verified. Run the installer if Windows prompts are required.", label),
		})
	}
	return statuses, nil
}

func readSource(ctx context.Context, source string) ([]byte, error) {
	source = strings.TrimSpace(source)
	if source == "" {
		source = defaultManifestURL
	}
	parsed, err := url.Parse(source)
	if err == nil && (parsed.Scheme == "http" || parsed.Scheme == "https") {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, source, nil)
		if err != nil {
			return nil, err
		}
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			return nil, fmt.Errorf("download manifest: %w", err)
		}
		defer resp.Body.Close()
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			return nil, fmt.Errorf("download manifest returned %s", resp.Status)
		}
		return io.ReadAll(resp.Body)
	}
	return os.ReadFile(source)
}

func ensurePayload(ctx context.Context, payload Payload, outputPath string, message string, progress ProgressFunc) error {
	if pathExists(outputPath) && verifyFileSHA256(outputPath, payload.SHA256) == nil {
		progress(ProgressEvent{Stage: "download", Message: "Reusing previously downloaded verified package", Downloaded: payload.SizeBytes, Total: payload.SizeBytes})
		return nil
	}
	partPath := outputPath + ".part"
	var lastErr error
	for attempt := 1; attempt <= 3; attempt++ {
		lastErr = downloadOnce(ctx, payload, partPath, message, progress)
		if lastErr == nil {
			if err := os.Rename(partPath, outputPath); err != nil {
				return fmt.Errorf("finalize download: %w", err)
			}
			return nil
		}
		time.Sleep(time.Duration(attempt) * time.Second)
	}
	return lastErr
}

func downloadOnce(ctx context.Context, payload Payload, partPath string, message string, progress ProgressFunc) error {
	var start int64
	if stat, err := os.Stat(partPath); err == nil {
		start = stat.Size()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, payload.URL, nil)
	if err != nil {
		return err
	}
	if start > 0 {
		req.Header.Set("Range", fmt.Sprintf("bytes=%d-", start))
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("download package: %w", err)
	}
	defer resp.Body.Close()

	flags := os.O_CREATE | os.O_WRONLY
	if start > 0 && resp.StatusCode == http.StatusPartialContent {
		flags |= os.O_APPEND
	} else {
		start = 0
		flags |= os.O_TRUNC
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("download package returned %s", resp.Status)
	}
	file, err := os.OpenFile(partPath, flags, 0o644)
	if err != nil {
		return err
	}
	defer file.Close()

	total := payload.SizeBytes
	if total == 0 && resp.ContentLength > 0 {
		total = start + resp.ContentLength
	}
	written := start
	buffer := make([]byte, 1024*512)
	for {
		n, readErr := resp.Body.Read(buffer)
		if n > 0 {
			if _, err := file.Write(buffer[:n]); err != nil {
				return err
			}
			written += int64(n)
			progress(ProgressEvent{Stage: "download", Message: message, Downloaded: written, Total: total})
		}
		if readErr == io.EOF {
			break
		}
		if readErr != nil {
			return readErr
		}
	}
	return nil
}

func verifyFileSHA256(path string, expected string) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return err
	}
	actual := hex.EncodeToString(hash.Sum(nil))
	if !strings.EqualFold(actual, expected) {
		return fmt.Errorf("sha256 mismatch for %s: expected %s, got %s", path, expected, actual)
	}
	return nil
}

func extractZip(zipPath string, destination string) error {
	reader, err := zip.OpenReader(zipPath)
	if err != nil {
		return fmt.Errorf("open zip: %w", err)
	}
	defer reader.Close()
	root, err := filepath.Abs(destination)
	if err != nil {
		return err
	}
	rootWithSep := root + string(os.PathSeparator)
	for _, file := range reader.File {
		target := filepath.Join(root, file.Name)
		targetAbs, err := filepath.Abs(target)
		if err != nil {
			return err
		}
		if targetAbs != root && !strings.HasPrefix(strings.ToLower(targetAbs), strings.ToLower(rootWithSep)) {
			return fmt.Errorf("refusing zip entry outside install dir: %s", file.Name)
		}
		if file.FileInfo().IsDir() {
			if err := os.MkdirAll(targetAbs, file.Mode()); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(targetAbs), 0o755); err != nil {
			return err
		}
		source, err := file.Open()
		if err != nil {
			return err
		}
		destinationFile, err := os.OpenFile(targetAbs, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, file.Mode())
		if err != nil {
			source.Close()
			return err
		}
		_, copyErr := io.Copy(destinationFile, source)
		closeErr := destinationFile.Close()
		source.Close()
		if copyErr != nil {
			return copyErr
		}
		if closeErr != nil {
			return closeErr
		}
	}
	return nil
}

func writeInstallMarker(root string, manifest DownloadManifest, payload Payload) error {
	marker := map[string]any{
		"schema":         "pps-local-install.v1",
		"version":        manifest.Version,
		"source_tag":     manifest.SourceTag,
		"payload_kind":   payload.Kind,
		"payload_sha256": payload.SHA256,
		"installed_utc":  time.Now().UTC().Format(time.RFC3339),
	}
	data, err := json.MarshalIndent(marker, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(root, "pps_install_manifest.json"), append(data, '\n'), 0o644)
}

func existingInstallLooksValid(root string, payload Payload) bool {
	data, err := os.ReadFile(filepath.Join(root, "pps_install_manifest.json"))
	if err != nil {
		return false
	}
	var marker map[string]any
	if err := json.Unmarshal(data, &marker); err != nil {
		return false
	}
	return marker["payload_kind"] == payload.Kind && strings.EqualFold(fmt.Sprint(marker["payload_sha256"]), payload.SHA256)
}

func defaultInstallDir(version string) string {
	base := os.Getenv("LOCALAPPDATA")
	if base == "" {
		if home, err := os.UserHomeDir(); err == nil {
			base = filepath.Join(home, "AppData", "Local")
		}
	}
	return filepath.Join(base, "PPS Toolkit", "versions", "v"+strings.TrimPrefix(version, "v"))
}

func defaultDownloadDir() (string, error) {
	base := os.Getenv("LOCALAPPDATA")
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		base = filepath.Join(home, "AppData", "Local")
	}
	return filepath.Join(base, "PPS Toolkit", "downloads"), nil
}

func canReplaceInstallDir(path string) bool {
	base := os.Getenv("LOCALAPPDATA")
	if base == "" {
		return false
	}
	versionRoot, err := filepath.Abs(filepath.Join(base, "PPS Toolkit", "versions"))
	if err != nil {
		return false
	}
	target, err := filepath.Abs(path)
	if err != nil {
		return false
	}
	versionRoot = strings.ToLower(versionRoot) + string(os.PathSeparator)
	target = strings.ToLower(target)
	return strings.HasPrefix(target, versionRoot)
}

func resolveLaunchPath(root string, manifest DownloadManifest) string {
	if entrypoint, ok := manifest.Entrypoint("dashboard"); ok && entrypoint.Path != "" {
		return filepath.Join(root, filepath.FromSlash(strings.ReplaceAll(entrypoint.Path, "\\", "/")))
	}
	return filepath.Join(root, "windows", "Launch_HTML_Dashboard.bat")
}

func launchEntrypoint(path string) error {
	if strings.TrimSpace(path) == "" {
		return nil
	}
	if strings.EqualFold(filepath.Ext(path), ".bat") || strings.EqualFold(filepath.Ext(path), ".cmd") {
		return exec.Command("cmd", "/c", "start", "", path).Start()
	}
	return exec.Command(path).Start()
}

func openURL(rawURL string) error {
	rawURL = strings.TrimSpace(rawURL)
	if rawURL == "" {
		return nil
	}
	parsed, err := url.Parse(rawURL)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") {
		return fmt.Errorf("refusing to open non-http URL: %s", rawURL)
	}
	switch runtime.GOOS {
	case "windows":
		return exec.Command("rundll32", "url.dll,FileProtocolHandler", rawURL).Start()
	case "darwin":
		return exec.Command("open", rawURL).Start()
	default:
		return exec.Command("xdg-open", rawURL).Start()
	}
}

func pathExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
