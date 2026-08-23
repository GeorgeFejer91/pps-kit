//go:build windows

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

func createShortcuts(installDir string, manifest DownloadManifest) error {
	desktop := filepath.Join(os.Getenv("USERPROFILE"), "Desktop")
	startMenu := filepath.Join(os.Getenv("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs", "PPS Toolkit")
	if err := os.MkdirAll(startMenu, 0o755); err != nil {
		return err
	}
	for _, entrypoint := range manifest.Entrypoints {
		if !entrypoint.Shortcut || strings.TrimSpace(entrypoint.Path) == "" {
			continue
		}
		target := filepath.Join(installDir, filepath.FromSlash(strings.ReplaceAll(entrypoint.Path, "\\", "/")))
		name := sanitizeShortcutName(entrypoint.Label)
		if name == "" {
			name = "PPS Toolkit"
		}
		icon := shortcutIcon(installDir, target)
		if err := makeShortcut(filepath.Join(startMenu, name+".lnk"), target, installDir, icon); err != nil {
			return err
		}
		if entrypoint.Kind == "designer" || entrypoint.Kind == "dashboard" || entrypoint.Kind == "experiment_runner" {
			if err := makeShortcut(filepath.Join(desktop, name+".lnk"), target, installDir, icon); err != nil {
				return err
			}
		}
	}
	return nil
}

func makeShortcut(linkPath string, target string, workingDir string, icon string) error {
	script := fmt.Sprintf(
		`$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut(%s); $s.TargetPath = %s; $s.WorkingDirectory = %s; $s.IconLocation = %s; $s.Save()`,
		psQuote(linkPath),
		psQuote(target),
		psQuote(workingDir),
		psQuote(icon),
	)
	cmd := exec.Command("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script)
	return cmd.Run()
}

func shortcutIcon(installDir string, target string) string {
	candidates := []string{
		filepath.Join(installDir, "src", "peripersonal_space_toolkit", "assets", "pps_toolkit_icon.ico"),
		filepath.Join(installDir, "dist", "PPSExperimentRunner", "PPSExperimentRunner.exe"),
		target,
	}
	for _, candidate := range candidates {
		if pathExists(candidate) {
			return candidate
		}
	}
	return target
}

func sanitizeShortcutName(value string) string {
	replacer := strings.NewReplacer("\\", "-", "/", "-", ":", "-", "*", "-", "?", "", "\"", "'", "<", "", ">", "", "|", "-")
	return strings.TrimSpace(replacer.Replace(value))
}

func psQuote(value string) string {
	return "'" + strings.ReplaceAll(value, "'", "''") + "'"
}
