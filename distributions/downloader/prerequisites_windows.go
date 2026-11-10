package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
)

func windowsPrerequisitePresent(ctx context.Context, id string) bool {
	systemDir := filepath.Join(os.Getenv("SystemRoot"), "System32")
	switch id {
	case "vc2013":
		return pathExists(filepath.Join(systemDir, "msvcr120.dll"))
	case "vc14":
		return pathExists(filepath.Join(systemDir, "msvcp140.dll")) &&
			pathExists(filepath.Join(systemDir, "vcruntime140.dll")) &&
			pathExists(filepath.Join(systemDir, "vcruntime140_1.dll"))
	case "webview2":
		const key = `Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}`
		for _, prefix := range []string{`HKLM\SOFTWARE\WOW6432Node\`, `HKCU\Software\`} {
			cmd := exec.CommandContext(ctx, filepath.Join(systemDir, "reg.exe"), "query", prefix+key, "/v", "pv", "/reg:64")
			cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
			if output, err := cmd.Output(); err == nil && hasWebViewVersion(string(output)) {
				return true
			}
		}
	}
	return false
}

func hasWebViewVersion(output string) bool {
	for _, line := range strings.Split(output, "\n") {
		fields := strings.Fields(line)
		if len(fields) != 3 || fields[0] != "pv" || fields[1] != "REG_SZ" {
			continue
		}
		version := strings.Split(fields[2], ".")
		if len(version) == 4 {
			major, err := strconv.Atoi(version[0])
			return err == nil && major > 0
		}
	}
	return false
}

func runWindowsPrerequisite(ctx context.Context, id string, path string) error {
	var arguments string
	switch id {
	case "vc2013", "vc14":
		arguments = "/install /quiet /norestart"
	case "webview2":
		arguments = "/silent /install"
	default:
		return fmt.Errorf("unknown Windows prerequisite %q", id)
	}
	// Run only the already verified redistributable with elevation. Keep the
	// main application install and the shortcuts in the invoking user's profile.
	script := `$ErrorActionPreference = 'Stop'; $p = Start-Process -FilePath ` + psQuote(path) +
		` -ArgumentList ` + psQuote(arguments) + ` -Verb RunAs -Wait -PassThru; exit $p.ExitCode`
	powershell := filepath.Join(os.Getenv("SystemRoot"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
	cmd := exec.CommandContext(ctx, powershell, "-NoProfile", "-NonInteractive", "-Command", script)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("%w %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}
