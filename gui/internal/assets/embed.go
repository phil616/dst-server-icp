// Package assets embeds files needed by headless and GUI entry points.
package assets

import _ "embed"

// InstallScript is the bundled install-dst.sh.
//
//go:embed install-dst.sh
var InstallScript []byte
