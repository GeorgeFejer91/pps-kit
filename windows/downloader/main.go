package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"strings"
)

var defaultManifestURL = "https://github.com/GeorgeFejer91/pps-kit/releases/latest/download/pps_download_manifest.v1.json"
var buildVersion = "dev"

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	flags := flag.NewFlagSet("PPS Toolkit Downloader", flag.ContinueOnError)
	manifest := flags.String("manifest", defaultManifestURL, "Download manifest URL or local pps_download_manifest.v1.json path.")
	installDir := flags.String("install-dir", "", "Install directory. Defaults to %LOCALAPPDATA%\\PPS Toolkit\\versions\\v<version>.")
	payloadKind := flags.String("payload-kind", defaultPayloadKind, "Manifest payload kind to install.")
	noShortcuts := flags.Bool("no-shortcuts", false, "Do not create Desktop or Start Menu shortcuts.")
	launch := flags.Bool("launch", false, "Launch the dashboard after installation.")
	force := flags.Bool("force", false, "Replace an existing unverified install directory.")
	quiet := flags.Bool("quiet", false, "Use console output only; do not open the Windows progress UI.")
	versionFlag := flags.Bool("version", false, "Print downloader version.")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if *versionFlag {
		fmt.Println(buildVersion)
		return 0
	}

	options := InstallOptions{
		ManifestSource:  *manifest,
		PayloadKind:     *payloadKind,
		InstallDir:      *installDir,
		CreateShortcuts: !*noShortcuts,
		Launch:          *launch,
		Force:           *force,
	}
	if !*quiet && shouldUseInteractiveUI() {
		return runInteractive(context.Background(), options)
	}
	result, err := InstallFromManifest(context.Background(), options, consoleProgress)
	if err != nil {
		fmt.Fprintf(os.Stderr, "PPS Toolkit install failed: %v\n", err)
		return 1
	}
	fmt.Printf("Installed PPS Toolkit %s at %s\n", result.Manifest.Version, result.InstallDir)
	return 0
}

func consoleProgress(event ProgressEvent) {
	if event.Total > 0 && event.Downloaded > 0 {
		percent := float64(event.Downloaded) * 100 / float64(event.Total)
		fmt.Printf("[%s] %s %.1f%%\n", event.Stage, event.Message, percent)
		return
	}
	if strings.TrimSpace(event.Message) != "" {
		fmt.Printf("[%s] %s\n", event.Stage, event.Message)
	}
}
