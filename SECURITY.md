# Security policy

## Reporting a vulnerability

Please use GitHub private vulnerability reporting for the repository rather than opening a public issue. Include affected versions, reproduction steps, impact, and any suggested mitigation.

Do not include private photos, credentials, or other sensitive user data in a report. Replace them with a synthetic reproduction whenever possible.

## Scope

The bundled renderer reads local images and JSON, writes an output image, and makes no network requests.
The separate local Ark wrapper sends EXIF-stripped image previews and prompts to the configured
model API when invoked, reads each role's credential from its own environment variable or
explicit private local file (including existing shared raw-key files), does not follow
redirects, and makes no automatic retries. Model providers have separate privacy and billing policies.
Local key files are plaintext with owner-only permissions; exclude them from Git, packages
and shared artifacts. Credential readiness checks never display key values or make network calls.
