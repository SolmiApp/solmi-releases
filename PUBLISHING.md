# Solmi release publisher — prepared locally

This package is intended for `SolmiApp/solmi-releases`. It contains publication tooling, not application source or signing keys. It has not been installed on GitHub or exercised against a real release.

The workflow runs manually from `main`. The default is validation only. A candidate must be a full commit SHA in this public distribution repository whose entire tree contains exactly `app-release.apk` and `update-manifest.json`. Create this artifact commit in the distribution repository; never push a branch with private application history. The gate inspects the complete tree, including entries hidden by sparse checkout. The GitHub-generated source archive for the artifact tag therefore contains only these distribution files.

Before activating this package, transfer and verify the public distribution repository under SolmiApp, preserve its old releases and redirects, and install these files on its main branch. Upload only an approved current signed APK plus its matching flat manifest to a distribution-only candidate branch. Run the workflow with `publish=false` and review its result. Use the same immutable candidate SHA with `publish=true` for publication. `allow_first_release` is false by default and is needed only when the organization channel genuinely has no previous stable release.

Publication uses the repository's real `GITHUB_TOKEN`. It creates a draft, checks that GitHub reports `github-actions[bot]` as its author, downloads and verifies the uploaded APK and manifest again, checks that the previous stable release has not changed, and only then publishes the draft as latest. Failures leave an unpublished draft for review; they do not overwrite existing releases. The publisher refuses to run locally or from another repository/branch. Signing keys are never required by this publisher.

The validator covers both existing manifest formats, but the provided workflow publishes only the main Solmi application. Solmi Sensor still needs its own verified source/build workflow and `solmi-update` raw-branch publication; this package does not implement that transition.

Local verification: 22 standard-library unit/contract tests; actionlint 1.7.12 (ShellCheck unavailable on this machine); actual Android tooling inspected the existing main-app APK and matched the expected signature. Mocked publication tests are not evidence of a real GitHub release. The inspected APK is not claimed to include the current local source. No APK was built, installed or published during these checks.
