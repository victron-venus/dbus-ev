package main

import (
	_ "embed" // Required by go:embed to include the provider catalog in the binary.
	"encoding/json"
)

//go:embed catalog.json
var catalogJSON []byte

func supported(name string) bool {
	var catalog struct{ Templates []struct{ Template string } }
	if json.Unmarshal(catalogJSON, &catalog) != nil {
		return false
	}
	for _, t := range catalog.Templates {
		if t.Template == name {
			return true
		}
	}
	return false
}
