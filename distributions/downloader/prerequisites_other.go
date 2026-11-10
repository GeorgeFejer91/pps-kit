//go:build !windows

package main

import (
	"context"
	"errors"
)

func windowsPrerequisitePresent(context.Context, string) bool { return false }

func runWindowsPrerequisite(context.Context, string, string) error {
	return errors.New("Windows runtimes require Windows")
}
