//go:build !windows

package main

func createShortcuts(_ string, _ DownloadManifest) error {
	return nil
}
