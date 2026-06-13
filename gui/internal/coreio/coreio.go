// Package coreio contains the JSON protocol shared by the headless Go core
// and the Qt front-end.
package coreio

import "dst-deployer/internal/config"

// Envelope is one JSON line emitted by dst-deployer-core.
type Envelope struct {
	Type    string          `json:"type"`
	Line    string          `json:"line,omitempty"`
	Message string          `json:"message,omitempty"`
	Config  *ConfigResponse `json:"config,omitempty"`
	Result  any             `json:"result,omitempty"`
}

// ConfigResponse is returned by the config command.
type ConfigResponse struct {
	Path          string         `json:"path"`
	LogDir        string         `json:"log_dir"`
	DefaultMirror string         `json:"default_mirror"`
	Config        *config.Config `json:"config"`
}

// RunRequest describes one deployment operation.
type RunRequest struct {
	Operation   string         `json:"operation"`
	Profile     config.Profile `json:"profile"`
	Mirror      string         `json:"mirror"`
	UseSudo     bool           `json:"use_sudo"`
	AptUpgrade  bool           `json:"apt_upgrade"`
	Port        int            `json:"port"`
	TCP         bool           `json:"tcp"`
	UDP         bool           `json:"udp"`
	ScriptBytes []byte         `json:"-"`
}

// SaveProfileRequest updates persisted preferences and optionally a profile.
type SaveProfileRequest struct {
	Profile    config.Profile `json:"profile"`
	Selected   string         `json:"selected"`
	Mirror     string         `json:"mirror"`
	UseSudo    bool           `json:"use_sudo"`
	AptUpgrade bool           `json:"apt_upgrade"`
}

// DeleteProfileRequest deletes one persisted profile.
type DeleteProfileRequest struct {
	Name string `json:"name"`
}
