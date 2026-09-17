# Deploying Progress

Everything here is done from a browser. You need a Supabase account and a
Cloudflare account, both free. Budget about 15 minutes the first time; after
that, deploys happen automatically on every push.

There is a troubleshooting section at the bottom covering the things that
actually go wrong on a first deploy. If something breaks, look there first.

---

## 1. Create the Supabase project

1. Go to <https://supabase.com/dashboard> and click **New project**.
2. Name it `progress`, pick a region physically near you, and set a database
   password (save it in your password manager — you will not be shown it again).
3. Wait for provisioning to finish, roughly two minutes.

## 2. Create the database schema

In the dashboard, open **SQL Editor** and run these four files **in order**.
Open each one from this repo, copy its entire contents, paste, and hit **Run**.

| Order | File | What it does |
|---|---|---|
| 1 | `supabase/migrations/0001_schema.sql` | Tables, constraints, signup trigger |
| 2 | `supabase/migrations/0002_rls.sql` | Row Level Security — **do not skip this** |
| 3 | `supabase/migrations/0003_views.sql` | e1RM function and the session-bests view |
| 4 | `supabase/seed/exercises.sql` | 123 built-in exercises |

Order matters: each file depends on the one before it.

To confirm it worked, run this in the SQL editor:

```sql
select count(*) from public.exercises;   -- expect 123
```

> **Prefer the CLI?** With the [Supabase CLI](https://supabase.com/docs/guides/local-development)
> installed you can run `supabase link --project-ref <your-ref>` then
> `supabase db push`, and apply the seed with
> `supabase db execute --file supabase/seed/exercises.sql`.

## 3. Decide how signup works

By default Supabase emails a confirmation link before a new account can sign in.
For a personal app that is friction with no benefit, and the built-in mailer is
rate limited to a couple of messages an hour.

Go to **Authentication → Sign In / Providers → Email** and turn
**Confirm email** *off*. Signup then logs you straight in.

Leave it on if you intend to share this with other people.

## 4. Get your API credentials

Go to **Project Settings → Data API** for the URL, and **Project Settings →
API Keys** for the key. You want two values:

- **Project URL** — `https://<ref>.supabase.co`
- **anon / publishable key** — the long one labelled `anon`

> Use the **anon** key, never the **service_role** key. The service_role key
> bypasses Row Level Security entirely, and anything in this app's environment
> ends up inside the JavaScript bundle that any visitor can read. The anon key
> is safe there precisely because RLS constrains it.

## 5. Run it locally (optional but recommended)

```bash
cp .env.example .env.local     # then paste your two values into .env.local
npm install
npm run dev
```

Open <http://localhost:5173>, create an account, and confirm the Today screen
reports "123 exercises ready to use". If that number appears, your database,
auth and RLS are all working.

## 6. Deploy to Cloudflare Pages

1. Push this repo to GitHub if you have not already.
2. Go to <https://dash.cloudflare.com> → **Workers & Pages** → **Create** →
   **Pages** → **Connect to Git**, and authorise your `Progress` repository.
3. Set the build configuration:

   | Setting | Value |
   |---|---|
   | Framework preset | None (or Vite) |
   | Build command | `npm run build` |
   | Build output directory | `dist` |
   | Root directory | *(leave blank)* |

4. Under **Environment variables**, add all three — and add them to
   **Production and Preview both**, not just Production:

   ```
   VITE_SUPABASE_URL       https://<ref>.supabase.co
   VITE_SUPABASE_ANON_KEY  <your anon key>
   NODE_VERSION            22
   ```

5. **Save and Deploy.** Note the URL you get, e.g.
   `https://progress-abc.pages.dev`.

## 7. Tell Supabase about that URL

Back in Supabase, go to **Authentication → URL Configuration**:

- **Site URL** — your `https://…pages.dev` address
- **Redirect URLs** — add both `https://…pages.dev/**` and
  `http://localhost:5173/**`

Skipping this makes login appear to succeed and then dump you back on the login
screen, with nothing useful in the console.

## 8. Install it on your phone

Open the Pages URL on your phone.

- **iPhone / Safari** — Share → *Add to Home Screen*
- **Android / Chrome** — ⋮ menu → *Add to Home screen*

It then launches fullscreen with no browser chrome.

---

## Verifying the deploy

Work through these. All six should pass.

1. The Pages URL loads and shows the sign-in screen.
2. You can create an account and land on the Today screen.
3. Today reports **123 exercises ready to use** — this one line proves env vars,
   auth, RLS and the seed are all correct.
4. Settings loads, and changing **Units** to `lb` persists across a page reload.
   That proves writes pass RLS, not just reads.
5. Navigate to `/settings`, then **hard-refresh the page**. It must load, not
   404. This is the `public/_redirects` check.
6. Sign out and back in; your settings are still there.

### Verifying RLS properly

This is the security-critical one, since the anon key is public. In the Supabase
SQL editor:

```sql
-- Confirm RLS is actually enabled on all six tables. Every row must say true.
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
order by tablename;

-- Every user should see all 123 built-in exercises.
select count(*) from public.exercises where owner_id is null;
```

Then create a *second* account in the app and confirm it cannot see the first
account's data. Every table filters on `user_id = auth.uid()`, so B's queries
return B's rows only — and because built-in exercises have no update or delete
policy, neither account can alter the shared library.

---

## Troubleshooting

**Blank white page, console says "Missing Supabase configuration"**
The environment variables are not reaching the build. They must be set on the
Pages project *before* a build runs, and they are read at build time, not run
time — so after adding them you must trigger a fresh deploy
(**Deployments → … → Retry deployment**) for them to take effect.

**Login succeeds then bounces straight back to the login screen**
Step 7. The Pages URL is not in Supabase's Site URL / Redirect URLs.

**Any route other than `/` 404s when refreshed**
`public/_redirects` is missing from the build output. Confirm the file exists
and that the build output directory is `dist`.

**"Invalid login credentials" on an account you just created**
Email confirmation is still on (step 3) and you have not clicked the link in
your inbox. Either confirm the address or turn the setting off.

**Build fails on Cloudflare but works locally**
Almost always the Node version. Set `NODE_VERSION` to `22` in the Pages
environment variables. The `.nvmrc` in this repo pins local development to the
same version.

**The app worked and now every request fails**
Supabase pauses free-tier projects after 7 days of no activity. Open the
dashboard and click **Restore project**; nothing is lost.
