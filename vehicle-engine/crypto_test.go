package main

import (
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/evcc-io/evcc/util"
	"github.com/evcc-io/evcc/util/transport"
)

func TestLegacyCryptoRequiresExplicitBooleanConsent(t *testing.T) {
	var catalog struct{ Templates []struct{ Template string } }
	if err := json.Unmarshal(catalogJSON, &catalog); err != nil {
		t.Fatal(err)
	}
	expected := map[string]bool{"aiways": true, "carwings": true, "mg": true, "niu-e-scooter": true, "smart-hello": true, "toyota": true, "lexus": true, "subaru": true}
	for _, provider := range catalog.Templates {
		for _, consent := range []any{nil, false, true, "true", 1} {
			conf := map[string]any{"template": provider.Template}
			if consent != nil {
				conf["allowLegacyCrypto"] = consent
			}
			err := validateProviderCrypto(conf)
			validType := consent == nil || consent == false || consent == true
			wantOK := validType && (!expected[provider.Template] || consent == true)
			if (err == nil) != wantOK {
				t.Errorf("provider=%s consent=%v error=%v", provider.Template, consent, err)
			}
		}
	}
}

func TestLoadConfigConsumesLegacyConsent(t *testing.T) {
	p := filepath.Join(t.TempDir(), "vehicle.json")
	for _, consent := range []bool{false, true} {
		b, _ := json.Marshal(map[string]any{"template": "aiways", "allowLegacyCrypto": consent})
		if err := os.WriteFile(p, b, 0600); err != nil {
			t.Fatal(err)
		}
		conf, err := loadConfig(p)
		if (err == nil) != consent {
			t.Fatalf("loadConfig consent=%v error=%v", consent, err)
		}
		if _, ok := conf["allowLegacyCrypto"]; ok {
			t.Fatal("engine-only setting leaked to provider template")
		}
	}
}

func TestStrongTLSConfigurationAndCertificateKeys(t *testing.T) {
	c := transport.SecureTLSConfig()
	if c.MinVersion != tls.VersionTLS12 || c.InsecureSkipVerify || c.VerifyConnection == nil {
		t.Fatal("TLS policy weakened")
	}
	for _, test := range []struct {
		name string
		key  any
		ok   bool
	}{
		{"rsa1024", &rsa.PublicKey{N: new(big.Int).Lsh(big.NewInt(1), 1023), E: 65537}, false},
		{"rsa2048", &rsa.PublicKey{N: new(big.Int).Lsh(big.NewInt(1), 2047), E: 65537}, true},
		{"p224", &ecdsa.PublicKey{Curve: elliptic.P224()}, true},
		{"ed25519", ed25519.PublicKey(make([]byte, 32)), true},
		{"unknown", struct{}{}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			err := c.VerifyConnection(tls.ConnectionState{VerifiedChains: [][]*x509.Certificate{{{PublicKey: test.key}}}})
			if (err == nil) != test.ok {
				t.Fatalf("key policy error %v", err)
			}
		})
	}
	if c.VerifyConnection(tls.ConnectionState{}) == nil {
		t.Fatal("unverified peer accepted")
	}
	weak := &x509.Certificate{PublicKey: &rsa.PublicKey{N: new(big.Int).Lsh(big.NewInt(1), 1023), E: 65537}}
	strong := &x509.Certificate{PublicKey: &ecdsa.PublicKey{Curve: elliptic.P256()}}
	if c.VerifyConnection(tls.ConnectionState{VerifiedChains: [][]*x509.Certificate{{strong, weak}}}) == nil {
		t.Fatal("weak issuing CA accepted")
	}
}

func TestTLSRejectsUntrustedWrongHostAndOldProtocolBeforeCredentials(t *testing.T) {
	var requests atomic.Int32
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { requests.Add(1); w.WriteHeader(200) }))
	server.TLS = &tls.Config{MinVersion: tls.VersionTLS12, MaxVersion: tls.VersionTLS12}
	server.StartTLS()
	defer server.Close()
	roots := x509.NewCertPool()
	roots.AddCert(server.Certificate())
	for _, tc := range []struct {
		name     string
		trusted  bool
		hostname string
		min      uint16
		wantOK   bool
	}{
		{"trusted", true, "", tls.VersionTLS12, true},
		{"untrusted", false, "", tls.VersionTLS12, false},
		{"wrong-host", true, "wrong.invalid", tls.VersionTLS12, false},
		{"server-protocol-too-old", true, "", tls.VersionTLS13, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			c := transport.SecureTLSConfig()
			c.ServerName = tc.hostname
			c.MinVersion = tc.min
			if tc.trusted {
				c.RootCAs = roots
			}
			tr := transport.Default()
			tr.TLSClientConfig = c
			defer tr.CloseIdleConnections()
			client := http.Client{Transport: tr}
			req, _ := http.NewRequest(http.MethodGet, server.URL, nil)
			req.Header.Set("Authorization", "Bearer synthetic-test-token")
			before := requests.Load()
			resp, err := client.Do(req)
			if resp != nil {
				io.Copy(io.Discard, resp.Body)
				resp.Body.Close()
			}
			if (err == nil) != tc.wantOK {
				t.Fatalf("unexpected handshake result: %v", err)
			}
			if !tc.wantOK && requests.Load() != before {
				t.Fatal("private HTTP request reached rejected TLS peer")
			}
		})
	}
}

func TestProviderNonceUsesRequestedAlphabet(t *testing.T) {
	for _, alphabet := range []string{"0123456789ABCDEF", "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"} {
		value := util.CryptoRandomString(64, []rune(alphabet))
		if len(value) != 64 || strings.Trim(value, alphabet) != "" {
			t.Fatal("invalid provider nonce")
		}
	}
}

func TestCloudRedirectCannotSendCredentialsToHTTP(t *testing.T) {
	var requests atomic.Int32
	plain := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { requests.Add(1); w.WriteHeader(200) }))
	defer plain.Close()
	secure := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, plain.URL, http.StatusTemporaryRedirect)
	}))
	defer secure.Close()
	roots := x509.NewCertPool()
	roots.AddCert(secure.Certificate())
	for _, gated := range []bool{false, true} {
		base := transport.Default()
		base.TLSClientConfig.RootCAs = roots
		defer base.CloseIdleConnections()
		var tr http.RoundTripper = &httpsOnlyTransport{base: base}
		if gated {
			g, _ := newTraffic(filepath.Join(t.TempDir(), "traffic.json"))
			tr = g.wrap(base)
		}
		client := http.Client{Transport: tr}
		req, _ := http.NewRequest(http.MethodPost, secure.URL, strings.NewReader("synthetic-password"))
		req.Header.Set("Authorization", "Bearer synthetic-token")
		response, err := client.Do(req)
		if response != nil {
			response.Body.Close()
		}
		if err == nil {
			t.Fatal("plaintext redirect allowed")
		}
		if requests.Load() != 0 {
			t.Fatal("private request reached plaintext server")
		}
	}
}
