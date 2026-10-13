# Provider cryptography policy

The optional engine accepts only its 35 catalog templates and instantiates only
the selected provider. The [dated audit graph](evidence/provider-crypto-2026-10-13.json)
links each template to its factory, provider packages, authentication and transport.
It covers pinned evcc source plus this project's mandatory patch; it is not a
claim about every evcc integration or a live account certification.

## Secure defaults

All cloud HTTP clients in the selected provider graph use the patched request
transport or the process default transport. The engine requires TLS 1.2 or newer;
TLS 1.2 suites are restricted to ECDHE with AES-GCM or ChaCha20-Poly1305, and TLS
1.3 uses Go's defaults. Normal certificate-chain and hostname validation remains
enabled. A further check rejects verified chains with RSA keys shorter than 2048
bits, elliptic curves below 224 bits, malformed Ed25519 keys or unknown key types.
BMW CarData MQTT uses the same TLS policy; Fiat's Cognito client receives the
provider's HTTP client. The policy applies even when legacy compatibility is on. The cloud transports
also reject HTTP requests, including HTTPS redirects to plaintext. Python HTTPS
redirects receive the same downgrade protection before private data is sent.

Provider OAuth state and nonce generation uses `crypto/rand`, with no predictable
fallback if the operating system cannot supply randomness. Bluelink CCI refuses
RSA password-encryption keys shorter than 2048 bits. Manufacturer public client
identifiers and application stamps are not treated as independent secret keys.

The direct Python Mercedes client uses SHA-256 PKCE and Python `secrets`, with
an owned TLS 1.2+ context using the same ECDHE/AEAD policy. Both aiohttp's memory-BIO SSLObject and requests' SSLSocket check every certificate in the verified chain with cryptography before sending application data (RSA >=2048 bits, EC >=224 bits, DSA >=2048/224 bits, or Ed25519/Ed448). The check fails closed if the supported CPython 3.12 runtime cannot expose its verified chain. Local
Home Assistant HTTP and MQTT remain operator-configured trust boundaries; see
[the security case](security-assurance.md). This policy does not encrypt local
configuration/token files or make plaintext local MQTT/HTTP safe on hostile networks.

## Explicit compatibility for legacy protocols

These manufacturer-specific mechanisms cannot be upgraded by changing a client
algorithm without breaking the remote protocol. They are disabled by default:

- `aiways`: MD5 password transformation.
- `carwings`: fixed-key, fixed-IV AES-CBC password transformation.
- `mg`: SHA-1 password transformation, MD5 request derivation and fixed AES parameters.
- `niu-e-scooter`: MD5 password transformation.
- `smart-hello`: MD5 request-body hashing and HMAC-SHA1 with a public application key.
- `toyota`, `lexus`, `subaru`: a constant `plain` PKCE verifier/challenge, which does
  not provide the protection of a random verifier with an S256 challenge.

If compatibility with one of these services is necessary, knowingly opt in by
adding the JSON boolean `"allowLegacyCrypto": true` to that provider's private
configuration. The string `"true"`, numbers and other types are rejected. Omission
or `false` rejects the provider before authentication. The option is consumed by
the engine and is not forwarded to the upstream factory. Remove it or set it to
`false` to completely disable these mechanisms again. This flag does not turn off
TLS validation, lower TLS requirements or permit an unsupported template.

HTTPS still protects these exchanges in transit, but does not repair weak
application cryptography or ineffective PKCE. Use a unique account password where
supported and avoid exposing credentials, request bodies or token stores. If a
provider fails the TLS checks, stop using it and investigate the server chain;
do not bypass certificate verification. Report protocol changes through the
project's confidential security channel when credentials might be affected.

## Verification and limits

The tests exercise all catalog entries with absent/false/true/invalid compatibility
settings, the actual configuration-loader boundary, certificate key policy, and
real local TLS handshakes. Untrusted certificates, wrong hostnames and rejected
protocols fail before a private HTTP request reaches the server. The Go race
detector and vet are run on the patched engine. Tests use synthetic credentials,
not vehicle accounts. Changes can uncover a manufacturer with outdated TLS or
unusual certificate keys; that provider will fail closed until investigated.

Re-run this audit whenever the catalog, upstream revision, transport construction,
authentication flow or patch changes. Keep the import graphs and pinned-input
hashes alongside the review evidence. The engine is rebuilt explicitly; an old
binary already installed on a device does not acquire these safeguards from a
Python-only update.
