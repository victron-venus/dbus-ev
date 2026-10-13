package main

import (
	"fmt"
	"net/http"
)

const legacyPlainPKCE = "constant plain PKCE verifier and challenge"

// These manufacturer protocols cannot be strengthened unilaterally by a client.
// Keep them disabled unless the operator explicitly accepts the documented risk.
var legacyCryptoProviders = map[string]string{
	"aiways":        "MD5 password transform",
	"carwings":      "fixed-key and fixed-IV AES-CBC password transform",
	"lexus":         legacyPlainPKCE,
	"subaru":        legacyPlainPKCE,
	"toyota":        legacyPlainPKCE,
	"mg":            "SHA-1 password, MD5 request derivation and fixed AES parameters",
	"niu-e-scooter": "MD5 password transform",
	"smart-hello":   "MD5 body hash and HMAC-SHA1 request signature",
}

func validateProviderCrypto(conf map[string]any) error {
	allow, present := conf["allowLegacyCrypto"]
	if present {
		if _, ok := allow.(bool); !ok {
			return fmt.Errorf("allowLegacyCrypto must be a boolean")
		}
	}
	name, _ := conf["template"].(string)
	if reason, legacy := legacyCryptoProviders[name]; legacy && allow != true {
		return fmt.Errorf("provider %s requires explicit allowLegacyCrypto: true (%s); see docs/provider-cryptography.md", name, reason)
	}
	return nil
}

// Cloud requests cannot be redirected to plaintext, even when a provider or
// SDK constructs a fresh client. TLS policy alone cannot stop HTTP downgrades.
type httpsOnlyTransport struct{ base http.RoundTripper }

func (t *httpsOnlyTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if req.URL == nil || req.URL.Scheme != "https" {
		return nil, fmt.Errorf("vehicle cloud requests require HTTPS")
	}
	return t.base.RoundTrip(req)
}
