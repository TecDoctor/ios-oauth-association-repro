# iOS HTTPS authentication association reproduction

## Current diagnostic branch

On `fruwe/HEP-3370-wireguard-proof`, the manually dispatched `probe.yml`
attempts one complete SDK sample login, logout and logout-persistence check on
`xcode-27`, using one bundled iPhone 17 / iOS 27 simulator. Temporary private
checkouts use previously authorized read-only access; source stays on the
disposable runner. Credentials come from encrypted Actions secrets and all raw
evidence is encrypted before upload. Sandbox uses no GCP resources; the optional
Docker target connects to an already prepared remote cluster.

The earlier original `InteractionProbe` remains available as source. Its public
screenshots contain only synthetic UI and `example.com`. Its separate tap and
long-press experiments each made one press, without authentication retries.

Evidence so far:

- [Simple button fixture](https://github.com/TecDoctor/ios-oauth-association-repro/actions/runs/39533908402): both gestures activated the handler once.
- [Inline navigation, tab bar, picker and full-width button](https://github.com/TecDoctor/ios-oauth-association-repro/actions/runs/39535476085): both gestures activated the handler once.
- [Native browser handoff](https://github.com/TecDoctor/ios-oauth-association-repro/actions/runs/39536550060): both gestures activated the handler once and reached Apple’s Continue prompt. A generic pass does not establish private SDK behavior, domain association, credentials, or complete login/logout.

The following sections describe the earlier HTTPS-association probe, which is
retained as a separate diagnostic source and is not invoked by this branch's
current workflow.

A standalone UIKit app that starts Apple's ASWebAuthenticationSession with an
HTTPS callback. Written independently for this reproduction; no private SDK,
package dependency, or account credentials are required.

This probe isolates domain association and session presentation. It does NOT
perform a full login/logout or exchange authorization codes for tokens. An
accepted start or a pending session is NOT proof that the browser appeared.

## Configuration

Create one Actions repository secret, `PROBE_CONFIG_JSON`, containing a JSON
object with `ISSUER_URL`, `CLIENT_ID`, `CALLBACK_HOST`, `CALLBACK_PATH`,
`APP_BUNDLE_ID`, and `APP_TEAM_ID`. Use an app identity already authorized by
the callback domain's apple-app-site-association document. A different identity
needs its own AASA registration; otherwise rejection is expected.

The configuration script performs OIDC discovery and creates a fresh request
with state, nonce, and PKCE challenge. It does not retain a PKCE verifier or
redeem a returned authorization code. No login password or private SDK access
credential is needed.

Secret injection is not enough to keep these values private: the generated app,
configuration, screenshots, and raw platform logs can contain the endpoint.
Do not publish those files as unencrypted artifacts. The workflow prints only fixed event
names and build/entitlement presence flags. It runs on maintainer pushes to main or manual dispatch, takes
no untrusted inputs, and needs no private-repository checkout token.

## Local preparation

Install XcodeGen if needed. Export `PROBE_CONFIG_JSON` into the environment,
then run `python3 scripts/configure.py` and
`xcodegen generate --spec .generated-project.json`.
Build the AssociationProbe scheme for the iOS Simulator.

Do not install over an existing app with the same bundle ID on a developer's
running simulator. Use the disposable hosted simulator for this reproduction.
The preparation/typecheck of this source does not start or modify a simulator.

## Interpretation

`association_failure` is the failure of interest. `other_session_failure` needs
further private diagnostics; cancellation also reaches that category.
`callback_received` is only evidence that Apple returned a callback, not that
login or token exchange succeeded. A session that stays pending needs separate
visual confirmation before claiming success.

Next diagnostics should compare the finished executable's embedded associated
domains with the generated configuration and inspect iOS association-service
state. Public reports must redact hostnames and app identity. No full SDK test
or existing private workflow should be moved here without a separate review.

## Hosted execution

The workflow uses the standard public `macos-26` runner,
Xcode 26.6, and one fresh iPhone SE / iOS 26.2 simulator. It does not run Android,
Docker, or a private repository's CI. It refuses to substitute another runtime.
The session observation allowance is 1000 seconds. Explicit terminal errors
finish early. Each build has two compiler workers.

The initial run diagnoses executable and debug-library entitlement placement.
It does not silently change signing or disable the debug library to obtain a
passing result. The final screenshot and association-service logs are encrypted using the
committed public certificate before upload. The private decryption key is held
outside this repository. The encrypted artifact expires after three days.
Unencrypted builds, logs, and screenshots are never uploaded.

`SANDBOX_CREDENTIALS_JSON` may be provisioned separately for later login/logout
verification. This initial workflow does not reference or read it. SDK repository
access secrets are also unused.

## Generic transport diagnostic (HEP-3370)

The `fruwe/HEP-3370-wireguard-proof` experiment branch contains only generic
networking probes. `scripts/transport_server.sh` initializes a disposable Linux
host with WireGuard, pinned SSH, and a public Caddy image serving synthetic files.
It contains no application checkout, cloud credentials, or login account data.
The probe workflow uses an encrypted `REMOTE_PROBE_JSON` secret for the temporary
endpoint and public server identities. Runner private keys remain runner-local;
only public peer registrations and bounded results are uploaded. Register the
public keys through the host's `probe-peer-2`, `probe-peer-3`, and `probe-peer-4`
metadata entries. Delete the VM, boot disk and temporary secret after testing.

Evidence from three concurrent clients (two Ubuntu, one macOS):

- Automatic client MTU: [run 39457742146](https://github.com/TecDoctor/ios-oauth-association-repro/actions/runs/39457742146)
  reproduced stalled TLS connections despite successful small SSH commands.
  The large-file SSH fixture separately failed file permissions and is not
  usable as baseline evidence for throughput.
- Explicit client MTU 1280: [run 39458335439](https://github.com/TecDoctor/ios-oauth-association-repro/actions/runs/39458335439)
  passed every SSH and HTTPS check, including 1 MiB transfers, on all clients.
  The SSH fixture was corrected to read synthetic bytes from `/dev/zero`.
  Server interfaces reported physical MTU 1460 and WireGuard MTU 1420.

These results support the client MTU correction for this networking path. They
are not application login/logout acceptance or proof of overall CI stability.

### Owner-task follow-up

The prepared `probe.yml` now additionally invokes the existing Keycloak Make
owners for forwarding setup/removal, HTTPS forwarding, and macOS/iOS simulator
CA trust. This requires the organization variable
`HEALTH_PORTAL_KEYCLOAK_REPO_ACCESS_APP_CLIENT_ID` and secret
`HEALTH_PORTAL_KEYCLOAK_REPO_ACCESS_APP_PRIVATE_KEY` to be available to this repo.
A read-only App token checks out only the private Makefile and scripts on the
disposable runner with credential persistence disabled. That checkout and its
outputs are never uploaded or committed here. Artifacts are explicitly limited
to generic result JSON, interface metadata and the synthetic Safari screenshot.

The owner-task experiment was executed after its access configuration was enabled.
The macOS job uses the bundled iPhone 17 / iOS 27 simulator without downloading
runtimes or building an application. Safari evidence must be visually inspected:
a successful `openurl` command is not itself proof of certificate acceptance.


Owner-task evidence:

- [Run 39466725526](https://github.com/TecDoctor/ios-oauth-association-repro/actions/runs/39466725526)
  passed the actual owner forwarding setup/removal and port-443 HTTPS on both
  Ubuntu runners and macOS. Its first Safari screenshot still showed a loading
  Start Page, so command success alone was not accepted as iOS page-load proof.
- [Run 39468298923](https://github.com/TecDoctor/ios-oauth-association-repro/actions/runs/39468298923)
  added a native iOS URLSession assertion: HTTP 200, exact `healthy` response and
  no error, using normal certificate validation. Safari was then launched before
  one navigation; its screenshot was visually inspected and rendered `healthy`
  without a certificate warning. This is HTTPS infrastructure evidence, not
  application login/logout acceptance. No private sample app was built.

## Temporary SDK handoff observation

The manually dispatched `probe.yml` on the diagnostic branch can temporarily
check out the private SDK with the previously authorized read-only GitHub App.
An empty SDK ref uses its latest default branch; an explicit diagnostic branch
can expose bounded handler/discovery events. Source and build output remain on
the disposable runner. Only an encrypted diagnostic archive is uploaded; raw
screenshots, logs, SDK sources and configuration are never public artifacts.
The current probe attempts one sandbox login, logout and logout-persistence check
on iPhone 17 / iOS 27, using the authorized encrypted `SANDBOX_CREDENTIALS_JSON`
secret. Credentials are bound through Maestro's documented `MAESTRO_` variables
and checked before typing. The default SDK is tested unchanged. If an event-enabled diagnostic branch is
selected, its additional one-handler/one-success assertions must also pass.
Without that instrumentation, acceptance requires the complete single-execution
UI flow, including logout persistence; missing instrumentation is reported explicitly.

Before authentication, the probe observes iOS's association records for up to
1000 seconds and requires the exact application identity and every configured
`webcredentials` domain to be approved. It never edits that database, grants an
approval, retries authentication, or treats pending registration as success.
Native terminal failures stop the observation and preserve encrypted evidence.
A successful handoff alone is not full authentication acceptance.
Sandbox trials use no GCP resources or paid private-repository CI.

The optional Docker target connects only to an already prepared remote cluster;
it never provisions a host or builds containers on macOS. An external controller
must first verify cluster readiness and supply the authorized temporary encrypted
`REMOTE_PROBE_JSON` secret with its endpoint, WireGuard public key, SSH host public
key, optional public CA (`ca_pem`), domain list, HTTPS health URL, and disposable `account`
(`E2E_USERNAME`/`E2E_PASSWORD`). Only generated public client keys are uploaded for
registration in peer slot 6 during app compilation. No cloud credentials are
available to the public workflow. If the CA is omitted, the client retrieves the
owner-downloaded public certificate through the pinned SSH host identity.

A temporary read-only Keycloak checkout supplies the existing forwarding setup,
forwarding, and macOS/iOS certificate-trust Make tasks. Their private source is
never uploaded. The runner removes its owned forwarding and tunnel on completion
or failure; the external controller owns cluster expiry and secret removal.
Offline transport checks: `python3 -m unittest discover -s scripts -p test_remote_sdk_client.py`.

The Docker client wiring has offline checks; its complete hosted login/logout acceptance is still pending.

## Latest complete sandbox evidence

[Run 39626901541](https://github.com/TecDoctor/ios-oauth-association-repro/actions/runs/39626901541)
passed the complete sandbox flow with the unchanged default SDK and standard
signing settings in 12 minutes 12 seconds, including the app build. Authenticated
and post-relaunch unauthenticated screenshots were inspected privately. OS
association readiness took 22.156 seconds. Animation waits after the form submit
and logout callback took 1.599 and 2.915 seconds respectively.

Earlier trials failed during XCTest queries while the authentication browser was
closing. The successful trial waits for animation completion before querying the
next screen; all functional assertions remain required. This single pass does
not establish stability or prove the underlying XCTest failure eliminated.
Docker acceptance remains pending.

## Opt-in public driver investigation

`safari-foreground-probe=true` rebuilds only Maestro's public XCTest runner from
`cli-2.10.0` commit `14a408335e17a090df1e26bdbeaf80d8122a8fd8`.
The experiment logs Safari's application state and skips its WebView query when
Safari is not foreground. It replaces only the three bundled runner resources;
the private SDK and the full login/logout assertions remain unchanged.
This is an experimental tool build, not a released Maestro fix or an accepted
main-E2E dependency. Its purpose is to test the observed background-Safari query
failure without driver restarts, authentication retries, or shorter assertions.
Upstream source: [ViewHierarchyHandler.swift](https://github.com/mobile-dev-inc/Maestro/blob/14a408335e17a090df1e26bdbeaf80d8122a8fd8/maestro-ios-xctest-runner/maestro-driver-iosUITests/Routes/Handlers/ViewHierarchyHandler.swift).
