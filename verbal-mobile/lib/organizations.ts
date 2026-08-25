/**
 * Team / Organization layer — mobile client (IDI-216).
 *
 * The mirror of `whisperflow/app/organizations.py`. Edit one, edit the other:
 * the merge rule, the fail-closed shape and the error copy are all expected to
 * match across the two platforms.
 *
 * THREE THINGS THAT ARE LOAD-BEARING HERE:
 *
 * 1. **Everything fails closed to "no team".** Every exported function resolves
 *    to the no-org shape on any error. No team, an offline device, a 403 and an
 *    unapplied migration are indistinguishable to callers — which is the point:
 *    dictation must be completely unaffected either way (Hard Rule #1).
 *
 * 2. **The four `organization*` tables are `TO authenticated` + `auth.uid()`.**
 *    Unlike every other table in this codebase (Hard Rule #10's `TO public`
 *    compromise), they are properly enforced. A signed-out or paired-only device
 *    reads zero rows and simply has no team — correct, not a bug to work around.
 *    This is why the team layer shipped without waiting on IDI-29.
 *
 * 3. **The AsyncStorage cache is what the dictation path reads.** `teamDictionary()`
 *    is a pure cache read with no network call, so the recording→transcribe→insert
 *    path never waits on the team. `fetchOrg()` refreshes the cache off that path.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { supabase } from './supabase';
import { getCloudUserId } from './storage';
import { getSyncEnabled } from './syncStore';
import { normalize, type Dictionary } from './dictionary';

const KEY = 'flume_org';

export type OrgRole = 'owner' | 'admin' | 'member';

export type OrgMember = {
  user_id: string;
  email: string;
  display_name: string;
  role: OrgRole;
  status: string;
  usage_consent: boolean;
  leaderboard_opt_in: boolean;
  joined_at: string | null;
};

export type Org = {
  org_id: string;
  name: string;
  company_name: string;
  role: OrgRole | '';
  plan: string;
  seats: number;
  leaderboard_enabled: boolean;
  stats_visible_to_members: boolean;
  usage_consent: boolean;
  leaderboard_opt_in: boolean;
  members: OrgMember[];
  dictionary: Dictionary;
  dictionary_updated_at: string;
};

export type OrgInvite = {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  created_at: string;
};

export type UsageRow = {
  user_id: string;
  email: string;
  display_name: string;
  role: string;
  dictations: number;
  words: number;
  speech_ms: number;
  last_active: string | null;
};

export type BoardRow = { user_id: string; display_name: string; words: number; speech_ms: number };

export type OrgResult = { ok: boolean; error?: string; org?: Org };

/** The shape returned whenever there is no team, for any reason. */
export const NO_ORG: Org = {
  org_id: '',
  name: '',
  company_name: '',
  role: '',
  plan: '',
  seats: 0,
  leaderboard_enabled: false,
  stats_visible_to_members: false,
  usage_consent: false,
  leaderboard_opt_in: false,
  members: [],
  dictionary: { vocabulary: [], replacements: [], snippets: [] },
  dictionary_updated_at: '',
};

// In-memory mirror of the cache so the dictation path never awaits AsyncStorage
// either. Seeded by the first getCachedOrg()/fetchOrg() and kept in step on write.
let memo: Org | null = null;

function coerce(raw: any): Org {
  if (!raw || typeof raw !== 'object' || !raw.org_id) return { ...NO_ORG };
  return {
    ...NO_ORG,
    ...raw,
    members: Array.isArray(raw.members) ? raw.members : [],
    dictionary: normalize(raw.dictionary),
  };
}

async function store(org: Org): Promise<Org> {
  memo = org;
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(org));
  } catch {
    // cache-only failure — the in-memory copy still serves this app run
  }
  return org;
}

/** The cached org, or NO_ORG. Never throws, never hits the network. */
export async function getCachedOrg(): Promise<Org> {
  if (memo) return memo;
  try {
    const raw = await AsyncStorage.getItem(KEY);
    memo = coerce(raw ? JSON.parse(raw) : null);
  } catch {
    memo = { ...NO_ORG };
  }
  return memo;
}

/** Synchronous read of the in-memory copy — for the dictation path, which must
 *  not await anything it doesn't have to. Returns NO_ORG until first load. */
export function peekOrg(): Org {
  return memo ?? NO_ORG;
}

/**
 * Drop the cached org. Called from the sign-out / account-switch teardown
 * (Hard Rule #13): another organization's shared vocabulary, snippets and member
 * list must never survive into the next account signed in on this device.
 */
export async function clearOrgCache(): Promise<void> {
  memo = null;
  try {
    await AsyncStorage.removeItem(KEY);
  } catch {
    // best effort
  }
}

/** Pull membership + org + roster + shared dictionary and refresh the cache. */
export async function fetchOrg(): Promise<Org> {
  try {
    const userId = await getCloudUserId();
    if (!userId) return await store({ ...NO_ORG });

    const { data, error } = await supabase
      .from('organization_members')
      .select(
        'org_id,role,usage_consent,leaderboard_opt_in,' +
          // IDI-219 renamed the column to `purchased_seats`; aliased back to `seats`
        // so the Org type and every screen reference stay unchanged.
        'organizations(id,name,company_name,plan,seats:purchased_seats,leaderboard_enabled,stats_visible_to_members)',
      )
      .eq('user_id', userId)
      .eq('status', 'active')
      .maybeSingle();
    if (error || !data) return await store({ ...NO_ORG });

    const row: any = data;
    // PostgREST returns the embedded row as an object for a to-one relation, but
    // an array under some client/type combinations — accept both rather than
    // silently rendering an empty team name.
    const o = Array.isArray(row.organizations) ? row.organizations[0] : row.organizations;
    const orgId = o?.id ?? row.org_id;
    if (!orgId) return await store({ ...NO_ORG });

    const [members, dict] = await Promise.all([fetchMembers(orgId), fetchTeamDictionary(orgId)]);

    return await store({
      ...NO_ORG,
      org_id: orgId,
      name: o?.name ?? '',
      company_name: o?.company_name ?? '',
      role: (row.role as OrgRole) ?? 'member',
      plan: o?.plan ?? 'team',
      seats: Number(o?.seats ?? 0),
      leaderboard_enabled: !!o?.leaderboard_enabled,
      stats_visible_to_members: !!o?.stats_visible_to_members,
      usage_consent: !!row.usage_consent,
      leaderboard_opt_in: !!row.leaderboard_opt_in,
      members,
      dictionary: dict.dict,
      dictionary_updated_at: dict.updatedAt,
    });
  } catch {
    return await getCachedOrg();
  }
}

async function fetchMembers(orgId: string): Promise<OrgMember[]> {
  try {
    const { data, error } = await supabase
      .from('organization_members')
      .select('user_id,email,display_name,role,status,usage_consent,leaderboard_opt_in,joined_at')
      .eq('org_id', orgId)
      .eq('status', 'active')
      .order('joined_at', { ascending: true });
    if (error || !data) return [];
    return data as OrgMember[];
  } catch {
    return [];
  }
}

async function fetchTeamDictionary(orgId: string): Promise<{ dict: Dictionary; updatedAt: string }> {
  try {
    const { data, error } = await supabase
      .from('organization_dictionary')
      .select('vocabulary,replacements,snippets,updated_at')
      .eq('org_id', orgId)
      .maybeSingle();
    if (error || !data) return { dict: normalize({}), updatedAt: '' };
    return { dict: normalize(data), updatedAt: (data as any).updated_at ?? '' };
  } catch {
    return { dict: normalize({}), updatedAt: '' };
  }
}

/**
 * The cached shared dictionary — pure local read, safe on the dictation path.
 *
 * Empty when there is no team, when the user's Sync toggle is off, or on any
 * error. The sync gate applies HERE rather than in the fetch, because the shared
 * vocabulary IS synced user content: a user who turned sync off should dictate
 * with their own dictionary only, exactly as before joining.
 */
export async function teamDictionary(): Promise<Dictionary> {
  try {
    if (!(await getSyncEnabled())) return normalize({});
    const org = await getCachedOrg();
    return normalize(org.dictionary);
  } catch {
    return normalize({});
  }
}

// ── membership ───────────────────────────────────────────────────────────────

export async function createOrg(name: string, company = ''): Promise<OrgResult> {
  const clean = (name ?? '').trim();
  if (!clean) return { ok: false, error: 'Give the team a name' };
  try {
    const { error } = await supabase.rpc('org_create', {
      p_name: clean,
      p_company: (company ?? '').trim(),
    });
    if (error) {
      if (error.message?.includes('already_in_org')) return { ok: false, error: "You're already in a team" };
      return { ok: false, error: "Couldn't create the team" };
    }
    return { ok: true, org: await fetchOrg() };
  } catch {
    return { ok: false, error: "Couldn't create the team" };
  }
}

const CLAIM_ERRORS: Record<string, string> = {
  invalid_token: "That invite link isn't valid",
  expired: 'That invite has expired — ask for a new one',
  already_used: 'That invite has already been used',
  already_in_org: "You're already in a team",
  no_seats: 'That team has no seats left',
  not_authenticated: 'Sign in first',
};

/** Accepts either a bare token or the whole link as pasted out of the email. */
export function tokenFromInviteInput(v: string): string {
  const s = (v ?? '').trim();
  const m = s.match(/[?&]t=([^&\s]+)/);
  return m ? decodeURIComponent(m[1]) : s;
}

export async function claimInvite(tokenOrLink: string): Promise<OrgResult> {
  const token = tokenFromInviteInput(tokenOrLink);
  if (!token) return { ok: false, error: 'Paste your invite link or code' };
  try {
    const { data, error } = await supabase.rpc('org_claim_invite', { p_token: token });
    if (error) return { ok: false, error: "Couldn't reach the team service" };
    const res: any = data ?? {};
    if (res.ok) return { ok: true, org: await fetchOrg() };
    if (res.error === 'email_mismatch') {
      return {
        ok: false,
        error: `This invite was sent to ${res.invited_email ?? 'another address'} — sign in with that account.`,
      };
    }
    return { ok: false, error: CLAIM_ERRORS[res.error] ?? "That invite couldn't be used" };
  } catch {
    return { ok: false, error: "Couldn't reach the team service" };
  }
}

const INVITE_ERRORS: Record<string, string> = {
  bad_email: "That doesn't look like an email address",
  no_seats: 'No seats left on this plan',
  already_member: "They're already on the team",
  forbidden: 'Only owners and admins can invite',
  email_not_configured: "Email isn't configured yet — invites can't be sent",
  email_failed: "The invite email didn't send",
};

/**
 * Invite by email via the `invite-member` Edge Function. Thin on purpose: the
 * function holds the provider key and re-checks the caller's owner/admin role, so
 * an invite can never be constructed client-side.
 */
export async function inviteMember(
  email: string,
  role: 'member' | 'admin' = 'member',
): Promise<{ ok: boolean; error?: string; link?: string }> {
  const org = await getCachedOrg();
  if (!org.org_id) return { ok: false, error: 'No team yet' };
  if (org.role !== 'owner' && org.role !== 'admin') {
    return { ok: false, error: 'Only owners and admins can invite' };
  }
  try {
    const { data, error } = await supabase.functions.invoke('invite-member', {
      body: { org_id: org.org_id, email: (email ?? '').trim(), role },
    });
    // A non-2xx from an Edge Function surfaces as an error with the body attached;
    // dig the code out so the user sees "no seats left", not "something failed".
    if (error) {
      let code = '';
      try {
        code = JSON.parse(await (error as any).context?.text?.())?.error ?? '';
      } catch {
        code = '';
      }
      return { ok: false, error: INVITE_ERRORS[code] ?? "Couldn't send the invite" };
    }
    const res: any = data ?? {};
    if (!res.ok) return { ok: false, error: INVITE_ERRORS[res.error] ?? "Couldn't send the invite" };
    return { ok: true, link: res.link ?? '' };
  } catch {
    return { ok: false, error: "Couldn't send the invite" };
  }
}

export async function listInvites(): Promise<OrgInvite[]> {
  const org = await getCachedOrg();
  if (!org.org_id) return [];
  try {
    const { data, error } = await supabase
      .from('organization_invites')
      .select('id,email,role,status,expires_at,created_at')
      .eq('org_id', org.org_id)
      .eq('status', 'pending')
      .order('created_at', { ascending: false });
    if (error || !data) return [];
    return data as OrgInvite[];
  } catch {
    return [];
  }
}

export async function revokeInvite(inviteId: string): Promise<{ ok: boolean; error?: string }> {
  const org = await getCachedOrg();
  if (org.role !== 'owner' && org.role !== 'admin') {
    return { ok: false, error: 'Only owners and admins can do that' };
  }
  try {
    const { error } = await supabase
      .from('organization_invites')
      .update({ status: 'revoked' })
      .eq('id', inviteId)
      .eq('org_id', org.org_id);
    return error ? { ok: false, error: "Couldn't revoke that invite" } : { ok: true };
  } catch {
    return { ok: false, error: "Couldn't revoke that invite" };
  }
}

const ROLE_ERRORS: Record<string, string> = {
  forbidden: 'Only owners and admins can do that',
  cannot_change_owner: "The owner's role can't be changed",
  not_a_member: "They're not on the team any more",
};

export async function setMemberRole(userId: string, role: 'admin' | 'member'): Promise<OrgResult> {
  const org = await getCachedOrg();
  try {
    const { data, error } = await supabase.rpc('org_set_role', {
      p_org: org.org_id,
      p_user: userId,
      p_role: role,
    });
    const res: any = data ?? {};
    if (error || !res.ok) return { ok: false, error: ROLE_ERRORS[res.error] ?? "Couldn't change that role" };
    return { ok: true, org: await fetchOrg() };
  } catch {
    return { ok: false, error: "Couldn't change that role" };
  }
}

const REMOVE_ERRORS: Record<string, string> = {
  forbidden: 'Only owners and admins can do that',
  cannot_remove_owner: "The owner can't be removed — transfer the team first",
  not_a_member: "They're not on the team any more",
};

/** Remove someone — or, with your own id, leave the team. */
export async function removeMember(userId: string): Promise<OrgResult> {
  const org = await getCachedOrg();
  try {
    const { data, error } = await supabase.rpc('org_remove_member', {
      p_org: org.org_id,
      p_user: userId,
    });
    const res: any = data ?? {};
    if (error || !res.ok) return { ok: false, error: REMOVE_ERRORS[res.error] ?? "Couldn't remove them" };
    // Leaving is the one case where the cache is DROPPED, not refreshed — the
    // shared vocabulary stops applying the moment membership ends.
    const me = await getCloudUserId();
    if (userId === me) {
      await clearOrgCache();
      return { ok: true, org: { ...NO_ORG } };
    }
    return { ok: true, org: await fetchOrg() };
  } catch {
    return { ok: false, error: "Couldn't remove them" };
  }
}

export async function leaveOrg(): Promise<OrgResult> {
  const me = await getCloudUserId();
  if (!me) return { ok: false, error: 'Not signed in' };
  return await removeMember(me);
}

// ── settings & consent ───────────────────────────────────────────────────────

/** The member's OWN consent flags. The RPC keys on auth.uid(), so nobody can set
 *  these for anyone else — not even an owner. */
export async function setConsent(usage: boolean, leaderboard: boolean): Promise<OrgResult> {
  const org = await getCachedOrg();
  if (!org.org_id) return { ok: false, error: 'No team' };
  try {
    const { error } = await supabase.rpc('org_set_consent', {
      p_org: org.org_id,
      p_usage: usage,
      p_leaderboard: leaderboard,
    });
    if (error) return { ok: false, error: "Couldn't save that preference" };
    return { ok: true, org: await fetchOrg() };
  } catch {
    return { ok: false, error: "Couldn't save that preference" };
  }
}

/** Owner/admin edits to the org row. Allowlisted — a client must never be able to
 *  PATCH `plan`, `seats` or `owner_user_id` on its own authority. */
export async function setOrgSettings(fields: {
  name?: string;
  company_name?: string;
  leaderboard_enabled?: boolean;
  stats_visible_to_members?: boolean;
}): Promise<OrgResult> {
  const org = await getCachedOrg();
  if (org.role !== 'owner' && org.role !== 'admin') {
    return { ok: false, error: 'Only owners and admins can do that' };
  }
  if ((fields.leaderboard_enabled !== undefined || fields.stats_visible_to_members !== undefined)
      && org.role !== 'owner') {
    return { ok: false, error: 'Only the owner can change that' };
  }
  const patch: Record<string, unknown> = {};
  if (fields.name !== undefined) patch.name = fields.name;
  if (fields.company_name !== undefined) patch.company_name = fields.company_name;
  if (fields.leaderboard_enabled !== undefined) patch.leaderboard_enabled = fields.leaderboard_enabled;
  if (fields.stats_visible_to_members !== undefined) patch.stats_visible_to_members = fields.stats_visible_to_members;
  if (Object.keys(patch).length === 0) return { ok: false, error: 'Nothing to save' };
  patch.updated_at = new Date().toISOString();
  try {
    const { error } = await supabase.from('organizations').update(patch).eq('id', org.org_id);
    if (error) return { ok: false, error: "Couldn't save the team settings" };
    return { ok: true, org: await fetchOrg() };
  } catch {
    return { ok: false, error: "Couldn't save the team settings" };
  }
}

// ── shared dictionary (Phase 4) ──────────────────────────────────────────────

/**
 * Write the shared dictionary, compare-and-swap on `updated_at` (IDI-174's
 * pattern): the write is filtered on the last-witnessed value; zero rows back
 * means another admin won the race, so refetch, merge and retry ONCE. A double
 * failure is reported rather than silently dropped.
 */
export async function saveTeamDictionary(d: Dictionary): Promise<{ ok: boolean; error?: string; dictionary?: Dictionary }> {
  const org = await getCachedOrg();
  if (!org.org_id) return { ok: false, error: 'No team' };
  if (org.role !== 'owner' && org.role !== 'admin') {
    return { ok: false, error: 'Only owners and admins can edit the team dictionary' };
  }
  const body = normalize(d);
  try {
    if (await casWriteTeamDict(org.org_id, body, org.dictionary_updated_at)) {
      const fresh = await fetchOrg();
      return { ok: true, dictionary: fresh.dictionary };
    }
    const remote = await fetchTeamDictionary(org.org_id);
    const merged = mergeTeamDictionary(remote.dict, body);
    if (await casWriteTeamDict(org.org_id, merged, remote.updatedAt)) {
      const fresh = await fetchOrg();
      return { ok: true, dictionary: fresh.dictionary };
    }
    return { ok: false, error: "Couldn't sync — another admin was editing. Try again." };
  } catch {
    return { ok: false, error: "Couldn't save the team dictionary" };
  }
}

async function casWriteTeamDict(orgId: string, d: Dictionary, witness: string): Promise<boolean> {
  const stamp = new Date().toISOString();
  const userId = (await getCloudUserId()) ?? '';
  // ALL THREE columns on every write — sending a subset is what let a screen that
  // had only loaded vocabulary blank the snippets on the personal row.
  const row = {
    vocabulary: d.vocabulary,
    replacements: d.replacements,
    snippets: d.snippets ?? [],
    updated_by: userId,
    updated_at: stamp,
  };
  try {
    if (!witness) {
      const { error } = await supabase
        .from('organization_dictionary')
        .upsert({ org_id: orgId, ...row }, { onConflict: 'org_id' });
      return !error;
    }
    const { data, error } = await supabase
      .from('organization_dictionary')
      .update(row)
      .eq('org_id', orgId)
      .eq('updated_at', witness)
      .select('updated_at');
    // `.select()` is what makes the miss detectable: a conditional UPDATE that
    // matched nothing is not an error, it just returns zero rows.
    return !error && !!data && data.length > 0;
  } catch {
    return false;
  }
}

/** Union of two versions of the SHARED dictionary after a lost CAS race. Same
 *  semantics as `mergeDictionaries` for the personal row: the local edit wins a
 *  key collision, nothing is dropped. */
function mergeTeamDictionary(remote: Dictionary, local: Dictionary): Dictionary {
  const r = normalize(remote);
  const l = normalize(local);
  const vocabulary: string[] = [];
  const seen = new Set<string>();
  for (const w of [...r.vocabulary, ...l.vocabulary]) {
    const k = w.toLowerCase();
    if (!seen.has(k)) {
      seen.add(k);
      vocabulary.push(w);
    }
  }
  const reps = new Map<string, any>();
  for (const rep of r.replacements) reps.set(rep.from.toLowerCase(), rep);
  for (const rep of l.replacements) reps.set(rep.from.toLowerCase(), rep);
  const snips = new Map<string, any>();
  for (const s of r.snippets ?? []) snips.set(s.trigger.toLowerCase(), s);
  for (const s of l.snippets ?? []) snips.set(s.trigger.toLowerCase(), s);
  return { vocabulary, replacements: [...reps.values()], snippets: [...snips.values()] };
}

// ── usage insights (Phase 5) ─────────────────────────────────────────────────

/**
 * Per-member aggregates for owners/admins. Counts and durations ONLY — the RPC
 * has no column that could carry transcript text, and members who haven't
 * consented are absent from the result rather than shown as zeroes (so their
 * silence isn't itself a signal).
 */
export async function usageSummary(days = 30): Promise<{ rows: UsageRow[]; members: number; consented: number }> {
  const org = await getCachedOrg();
  const empty = { rows: [] as UsageRow[], members: org.members.length, consented: 0 };
  // NOT gated on role. The RPC does the split — an owner/admin gets every
  // consenting member, anyone else gets exactly their own row, same as
  // org_usage_series and org_app_breakdown. Refusing to ask is what made a plain
  // member's Team screen read as zeroes, since every total there comes from here.
  if (!org.org_id) return empty;
  try {
    const { data, error } = await supabase.rpc('org_usage_summary', { p_org: org.org_id, p_days: days });
    if (error || !data) return empty;
    return {
      rows: data as UsageRow[],
      members: org.members.length,
      consented: org.members.filter((m) => m.usage_consent).length,
    };
  } catch {
    return empty;
  }
}

/** The team-visible ranking (Phase 5b). Readable by every active member once the
 *  owner has enabled it org-wide; lists only members who opted in themselves. */
export async function leaderboard(days = 7): Promise<{ enabled: boolean; rows: BoardRow[] }> {
  const org = await getCachedOrg();
  if (!org.org_id || !org.leaderboard_enabled) return { enabled: false, rows: [] };
  try {
    const { data, error } = await supabase.rpc('org_leaderboard', { p_org: org.org_id, p_days: days });
    if (error || !data) return { enabled: true, rows: [] };
    return { enabled: true, rows: data as BoardRow[] };
  } catch {
    return { enabled: true, rows: [] };
  }
}

/** Daily word counts per member — the desktop Team screen's sparkline data
 *  (org_usage_series), keyed by user_id as [day, words] pairs in day order.
 *  Same visibility rules as usageSummary: the RPC decides the rows (admins and
 *  — when the owner opened stats team-wide — members get every consenting
 *  member; anyone else exactly themselves). */
export async function usageSeries(days = 98): Promise<Record<string, Array<[string, number]>>> {
  const org = await getCachedOrg();
  if (!org.org_id) return {};
  try {
    const { data, error } = await supabase.rpc('org_usage_series', { p_org: org.org_id, p_days: days });
    if (error || !Array.isArray(data)) return {};
    const out: Record<string, Array<[string, number]>> = {};
    for (const r of data as Array<{ user_id?: string; day?: string; words?: number }>) {
      const uid = String(r?.user_id ?? '');
      const day = String(r?.day ?? '');
      if (!uid || !day) continue;
      (out[uid] ??= []).push([day, Number(r?.words ?? 0)]);
    }
    return out;
  } catch {
    return {};
  }
}

export type AppRow = { app: string; dictations: number; words: number };

/** Per-member per-app dictation counts — "where does each person actually use
 *  Flume?". Keyed by user_id, biggest first, so a screen can index straight in.
 *
 *  The `app` column shipped 2026-08-21 and older rows are NULL forever, so an
 *  empty map usually means "not enough new dictations yet" rather than "nobody
 *  uses anything" — the UI has to say which. iOS itself never writes this
 *  column: there is no frontmost-app to read on a phone, so these numbers
 *  describe desktop dictation only. */
export async function appBreakdown(days = 30): Promise<Record<string, AppRow[]>> {
  const org = await getCachedOrg();
  if (!org.org_id) return {};
  try {
    const { data, error } = await supabase.rpc('org_app_breakdown', { p_org: org.org_id, p_days: days });
    if (error || !Array.isArray(data)) return {};
    const out: Record<string, AppRow[]> = {};
    for (const r of data as Array<{ user_id?: string; app?: string; dictations?: number; words?: number }>) {
      const uid = String(r?.user_id ?? '');
      const app = String(r?.app ?? '').trim();
      if (!uid || !app) continue;
      (out[uid] ??= []).push({
        app,
        dictations: Number(r?.dictations ?? 0),
        words: Number(r?.words ?? 0),
      });
    }
    return out;
  } catch {
    return {};
  }
}
