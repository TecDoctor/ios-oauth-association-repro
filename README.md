# iOS HTTPS authentication association reproduction

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
