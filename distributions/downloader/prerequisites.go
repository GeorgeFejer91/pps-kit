package main

import (
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"path/filepath"
)

//go:embed windows_prerequisites.json
var windowsPrerequisiteLock []byte

type windowsPrerequisite struct {
	ID       string `json:"id"`
	Label    string `json:"label"`
	Filename string `json:"filename"`
	SHA256   string `json:"sha256"`
}

func installWindowsPrerequisites(ctx context.Context, root string, progress ProgressFunc) error {
	var prerequisites []windowsPrerequisite
	if err := json.Unmarshal(windowsPrerequisiteLock, &prerequisites); err != nil {
		return fmt.Errorf("read embedded Windows runtime lock: %w", err)
	}
	return provisionPrerequisites(ctx, filepath.Join(root, "support", "windows-prerequisites"), prerequisites,
		windowsPrerequisitePresent, runWindowsPrerequisite, progress)
}

func provisionPrerequisites(ctx context.Context, dir string, prerequisites []windowsPrerequisite,
	present func(context.Context, string) bool,
	install func(context.Context, string, string) error, progress ProgressFunc) error {
	// Verify every bundled installer before any of them can request elevation.
	for _, prerequisite := range prerequisites {
		path := filepath.Join(dir, prerequisite.Filename)
		if err := verifyFileSHA256(path, prerequisite.SHA256); err != nil {
			return fmt.Errorf("verify bundled %s: %w", prerequisite.Label, err)
		}
	}
	for _, prerequisite := range prerequisites {
		if present(ctx, prerequisite.ID) {
			progress(ProgressEvent{Stage: "prerequisites", Message: prerequisite.Label + " is already installed"})
			continue
		}
		progress(ProgressEvent{Stage: "prerequisites", Message: "Installing " + prerequisite.Label})
		if err := install(ctx, prerequisite.ID, filepath.Join(dir, prerequisite.Filename)); err != nil {
			return fmt.Errorf("install %s: %w", prerequisite.Label, err)
		}
		if !present(ctx, prerequisite.ID) {
			return fmt.Errorf("%s is unavailable after its installer finished", prerequisite.Label)
		}
	}
	return nil
}
