package main

import (
	"context"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestProvisionPrerequisitesInstallsOnlyMissingVerifiedRuntimes(t *testing.T) {
	dir := t.TempDir()
	prerequisites := []windowsPrerequisite{
		{ID: "present", Label: "Present", Filename: "present.exe"},
		{ID: "missing", Label: "Missing", Filename: "missing.exe"},
	}
	for i := range prerequisites {
		path := filepath.Join(dir, prerequisites[i].Filename)
		if err := os.WriteFile(path, []byte(prerequisites[i].ID), 0o600); err != nil {
			t.Fatal(err)
		}
		hash, err := fileSHA256(path)
		if err != nil {
			t.Fatal(err)
		}
		prerequisites[i].SHA256 = hash
	}

	installed := map[string]bool{"present": true}
	var runs []string
	present := func(_ context.Context, id string) bool { return installed[id] }
	install := func(_ context.Context, id string, path string) error {
		runs = append(runs, path)
		installed[id] = true
		return nil
	}
	progress := func(ProgressEvent) {}
	ctx := context.Background()
	if err := provisionPrerequisites(ctx, dir, prerequisites, present, install, progress); err != nil {
		t.Fatal(err)
	}
	if want := []string{filepath.Join(dir, "missing.exe")}; !reflect.DeepEqual(runs, want) {
		t.Fatalf("runtime installers run: %v, want %v", runs, want)
	}

	t.Run("installer exits without providing runtime", func(t *testing.T) {
		delete(installed, "missing")
		install := func(context.Context, string, string) error { return nil }
		err := provisionPrerequisites(ctx, dir, prerequisites, present, install, progress)
		if err == nil || !strings.Contains(err.Error(), "unavailable after its installer finished") {
			t.Fatalf("expected missing runtime error, got %v", err)
		}
	})

	t.Run("rejects tampering before running any installer", func(t *testing.T) {
		delete(installed, "present")
		runs = nil
		if err := os.WriteFile(filepath.Join(dir, "missing.exe"), []byte("changed"), 0o600); err != nil {
			t.Fatal(err)
		}
		err := provisionPrerequisites(ctx, dir, prerequisites, present, install, progress)
		if err == nil || !strings.Contains(err.Error(), "verify bundled Missing") || len(runs) != 0 {
			t.Fatalf("expected verification failure before running any installer, got %v and %v", err, runs)
		}
	})
}
