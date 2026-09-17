import { createClient } from '@supabase/supabase-js'
import type { Database } from './types'

const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

// Fail loudly and specifically. A missing env var on Cloudflare Pages otherwise
// surfaces as an opaque "Failed to fetch" at login, which is a miserable thing
// to debug on a phone. See DEPLOY.md - they must be set for BOTH the Production
// and Preview environments, and the project re-deployed afterwards.
if (!url || !anonKey) {
  throw new Error(
    'Missing Supabase configuration. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY ' +
      '(in .env.local for local dev, or in the Cloudflare Pages environment variables ' +
      'for both Production and Preview), then rebuild.',
  )
}

export const supabase = createClient<Database>(url, anonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
})
