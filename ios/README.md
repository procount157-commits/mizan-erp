# مقياس — تطبيق الآيفون / Miqyas for iPhone

The app shows the Miqyas system itself, so every feature built on the server
reaches the iPhone the same day, **without a new App Store release**. A new
release is needed only to change the app's name, icon, or permissions.

## For the developer publishing it

1. Download the latest **miqyas-ios-project** artifact from the
   *iOS app* workflow on GitHub (or run `xcodegen generate` in this folder).
2. Edit **`Config.xcconfig`** — the only file to change:
   - `MIQYAS_BUNDLE_ID` — the App ID you register (default `ae.miqyas.app`)
   - `MIQYAS_TEAM_ID` — your Team ID
   - `MIQYAS_DOMAIN` — the client domain, e.g. `miqyas.ae`
   - `MIQYAS_VERSION` / `MIQYAS_BUILD` — raise the build number per upload
3. In the developer account, enable **Push Notifications** on the App ID.
4. Open `Miqyas.xcodeproj` → Product → **Archive** → Distribute → App Store
   Connect. Automatic signing handles the certificates.
5. **Push key for the server**: Keys → “+” → Apple Push Notifications service
   → download the `.p8` (once only). In Miqyas: Settings → **Phone Apps** →
   Team ID, Key ID, Bundle ID, and paste the `.p8` contents.
   Use *Development build* only for apps run straight from Xcode.

## App Review notes (paste into App Store Connect)

- Business app for contracting companies; accounts are created by each
  company's administrator — there is no public sign-up, so no in-app account
  deletion applies.
- Provide the review login (a demo company) in “Sign-in required”.
- Native features: company selection, camera capture of bills, push
  notifications that open the related record, file download and sharing.
- Consider **Unlisted** distribution: only people with the link can find it.

## What the app asks permission for

Camera (bills and receipts), Photos (attach / save), Microphone (voice
messages in team chat), Location while in use (site report, attendance),
Notifications (asked after sign-in).
