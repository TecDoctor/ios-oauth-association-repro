# iOS sandbox authentication diagnostics

This repository contains an independently written UIKit association probe and
UI-only tests for a privately fetched SDK sample. No private SDK source, built
applications, endpoint configuration, or credentials are committed here.

## Configuration

Actions requires `PROBE_CONFIG_JSON` with `ISSUER_URL`, `CLIENT_ID`,
`CALLBACK_HOST`, `CALLBACK_PATH`, `APP_BUNDLE_ID`, and `APP_TEAM_ID`.
The identity must already be authorized by the callback domain's AASA document.

Full SDK verification additionally requires:

- `SANDBOX_CREDENTIALS_JSON` with `E2E_USERNAME` and `E2E_PASSWORD`.
- `HEALTH_PORTAL_SDK_REPO_ACCESS_APP_PRIVATE_KEY` as an Actions secret.
- `HEALTH_PORTAL_SDK_REPO_ACCESS_APP_CLIENT_ID` as an Actions secret or variable.
- The GitHub App must have read access to the private SDK repository.

Organization secrets/variables must include this repository in their access
selection. The checkout token has contents-read permission and is not persisted.
SDK source is pinned to the diagnostic revision recorded in the workflow.

## Execution

Maintainer pull requests and main pushes run the full SDK verification. Manual
dispatch can select `sdk` or `probe`. Fork pull requests do not receive a job.
The workflow uses standard public `macos-26`, Xcode 26.6, and exactly one fresh
CI-owned iPhone SE (third generation) with iOS 26.2. It runs neither Android nor
Docker. Each build uses two compiler workers. It does not touch local simulators.

The SDK test verifies authenticated state, logout, and logout persistence after
relaunch. It centers controls away from header overlays and allows 1000 seconds
for asynchronous UI phases. Before credentials are entered, a failed SDK login
can be retried in the same app, with screenshots and private native diagnostics.
A browser alone is not considered successful authentication.

## Association probe

The standalone app uses ASWebAuthenticationSession with an HTTPS callback and
an active scene presentation window. It generates a fresh PKCE challenge but
does not retain a verifier, exchange tokens, or verify login/logout.

The cold simulator rejected the first five native sessions in run 39021198545;
the sixth opened the authentication browser about 62 seconds after the first
attempt. Screenshots confirm browser presentation, with the page still loading.
This supports delayed association readiness. It does not prove full login.

The probe retries only explicit domain-association errors within the same app
process, for at most 1000 seconds. Other terminal errors fail immediately.
Waiting for association logs before XCTest was insufficient in an earlier run:
XCTest installation changed the app registration and prompted another refresh.

## Private evidence

Raw build/test logs, screenshots, native errors, and system logs can contain
private values. They are encrypted with `diagnostics/recipient.pem` before
artifact upload. The matching private key is held outside this repository.
Artifacts expire after three days. No public Actions cache is used for SDK code
or builds. Generated configuration, SDK checkout and build files are removed
at the end of the job. Never upload plaintext logs or app bundles.

Local generic simulator compilation is supported for validation, but both run
scripts refuse to operate outside GitHub Actions. Do not install the probe over
an existing local app with the same identity. Repository review requirements
remain in place; successful diagnostics do not bypass approval.
