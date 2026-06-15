//go:build !windows

package main

import (
	"context"
)

func shouldUseInteractiveUI() bool {
	return false
}

func runInteractive(ctx context.Context, options InstallOptions) int {
	result, err := InstallFromManifest(ctx, options, consoleProgress)
	if err != nil {
		return 1
	}
	_ = result
	return 0
}
