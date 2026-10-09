# مقياس — تطبيق أندرويد / Miqyas for Android

Built by GitHub on every change under `mobile/` (workflow *Android APK*):

- **miqyas-apk** — installs directly on a phone.
- **miqyas-aab-for-google-play** — the file Google Play takes.

Every feature built on the server reaches the app the same day, with no new
release. A release is needed only for a new name, icon or domain.

## Before publishing

1. Set the real domain in `twa.properties` (`domain=`) and push; GitHub
   rebuilds both files.
2. Package name: `ae.miqyas.app` (in `app/build.gradle`).

## Publishing on Google Play (any developer account)

1. Create the app in Play Console, upload the `.aab`.
2. Play re-signs the app with its own key. Copy **App integrity → App signing
   key certificate → SHA-256** and add it in Miqyas, so the app opens
   full-screen for Play users too:
   Settings → Technical → System Parameters → `mizan.android_sha256` =
   `<Play SHA-256>,18:9E:13:95:1B:33:07:C3:4C:B1:88:83:22:CE:ED:62:C8:45:0B:33:B7:AD:2C:D0:44:2A:A0:B2:EC:31:B5:81`
3. A personal account created after Nov 2023 must run a closed test with 12
   testers for 14 days before going public; an organisation account need not.

The upload key stays with ProAccount (`secrets/android-release.jks`, and the
GitHub secrets); the publisher never needs it — they upload the `.aab`.
