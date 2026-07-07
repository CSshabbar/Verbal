# Google Sign-In setup (Verbal)

The fastest path: **Supabase holds the Google credentials; the apps just use Supabase Auth.**
You configure Google once. ~10 minutes.

---

## 1. Create a Google OAuth client (Google Cloud Console)

1. Go to <https://console.cloud.google.com/> → create/select a project (e.g. "Verbal").
2. **APIs & Services → OAuth consent screen**
   - User type: **External** → Create.
   - App name: `Verbal`, your support email, developer email. Save.
   - **Test users → Add users → add your own Google email.**
     (While the app is in "Testing" you don't need Google verification — this is the fast path for personal use. Only your added test users can sign in.)
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Web application**.
   - Authorized redirect URI — add exactly:
     ```
     https://ovpcthjingugwvpxlsna.supabase.co/auth/v1/callback
     ```
   - Create → copy the **Client ID** and **Client secret**.

## 2. Enable Google in Supabase

1. Supabase dashboard → your project (`ovpcthjingugwvpxlsna`).
2. **Authentication → Providers → Google → Enable.**
   - Paste the **Client ID** and **Client secret** from step 1. Save.
3. **Authentication → URL Configuration → Redirect URLs → add:**
   ```
   http://localhost:8765/callback     ← desktop app (required now)
   verbal://auth-callback             ← mobile app (add when mobile is wired)
   ```
   Save.

That's everything for the **desktop app**. Launch it → menu bar → **Sign in with Google**.
The browser opens, you pick your Google account, and it returns to the app signed in.
If your account is already used on another device, you'll get the **"New device detected — Sync?"** prompt.

---

## 3. Database (already covered, but verify)

Your synced tables are keyed by `user_id`. After sign-in, `user_id` becomes your **Supabase
user id** automatically — no manual entry. The tables you already have work as-is:
`transcriptions`, `notes`, `canvas`, `devices`, `pairings`, plus the `recordings` bucket.

No new migration is strictly required for basic sign-in. (If you previously created data
under a manual/guest `user_id`, that old data stays under the old id — new signed-in data
lives under your Google user id.)

### Optional hardening (later, recommended before real launch)
Right now the apps talk to Supabase with the **anon key** and separate data by `user_id`.
That means data is scoped per user but not cryptographically enforced. To enforce it, switch
the apps to send each user's **JWT** and add RLS policies like:
```sql
alter table public.transcriptions enable row level security;
create policy "own rows" on public.transcriptions
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
-- repeat for notes, canvas, devices, recordings objects
```
This is a follow-up task (it requires the apps to use the authenticated token for all
requests + token refresh). Ask me to do it when you're ready.

---

## 4. Mobile — BUILT ✅ (needs one Supabase redirect URL + a dev build)

Mobile Google sign-in is wired: `useAuth.signInWithGoogle()` runs Supabase OAuth in an
in-app browser and returns via the `verbal://auth-callback` deep link (scheme `verbal` is in
app.json). On sign-in it adopts your Supabase user id, registers the device, and shows the
same "New device detected — Sync?" prompt. `expo-web-browser` + `expo-auth-session` are
installed. Welcome screen is Google-only.

To make it work:
1. **Supabase → Authentication → URL Configuration → Redirect URLs → add:**
   ```
   verbal://auth-callback
   ```
   (Keep `http://localhost:8765/callback` for desktop too.)
2. **Build a dev client** (expo-web-browser/auth-session are native):
   ```
   cd verbal-mobile
   eas build --profile development --platform ios   # or android
   # then: npx expo start --dev-client
   ```
   Sign in from the Welcome screen → Google → back into the app.

No separate Google Cloud client is needed for mobile — it reuses the same Supabase Google
provider from step 2 (the OAuth happens through Supabase's callback).
