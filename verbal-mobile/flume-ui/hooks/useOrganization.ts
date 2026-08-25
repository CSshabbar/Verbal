/**
 * useOrganization — the team/organization layer (IDI-216).
 *
 * Backed by lib/organizations (AsyncStorage `flume_org` cache + the Supabase
 * `organization*` tables and RPCs). Consumed by TeamScreen.
 *
 * Contract (kept in step with useOrganization.mock.ts — the mock IS the design
 * contract, conventions §.mock.ts):
 *   { org, invites, usage, board, loading, error, hasTeam, isAdmin,
 *     reload, createTeam, joinTeam, invite, revoke, setRole, remove, leave,
 *     saveSettings, saveConsent, saveTeamDictionary, setUsageDays, setBoardDays }
 *
 * Fail-closed: every path resolves to the no-team state rather than throwing.
 * Team UI must never be able to wedge the app, and must never block dictation.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import {
  NO_ORG,
  getCachedOrg,
  fetchOrg,
  createOrg,
  claimInvite,
  inviteMember,
  listInvites,
  revokeInvite,
  setMemberRole,
  removeMember,
  leaveOrg,
  setConsent,
  setOrgSettings,
  saveTeamDictionary as saveTeamDictionaryLib,
  usageSummary,
  leaderboard,
  appBreakdown,
  type Org,
  type OrgInvite,
  type UsageRow,
  type BoardRow,
  type AppRow,
} from '../../lib/organizations';
import type { Dictionary } from '../../lib/dictionary';

export type { Org, OrgMember, OrgInvite, UsageRow, BoardRow, AppRow, OrgRole } from '../../lib/organizations';

export function useOrganization() {
  const [org, setOrg] = useState<Org>(NO_ORG);
  const [invites, setInvites] = useState<OrgInvite[]>([]);
  const [usage, setUsage] = useState<{ rows: UsageRow[]; members: number; consented: number }>({
    rows: [],
    members: 0,
    consented: 0,
  });
  const [board, setBoard] = useState<{ enabled: boolean; rows: BoardRow[] }>({ enabled: false, rows: [] });
  // Per-member app mix, keyed by user_id. Empty until members dictate on a
  // build that records it — see appBreakdown().
  const [apps, setApps] = useState<Record<string, AppRow[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [usageDays, setUsageDaysState] = useState(30);
  const [boardDays, setBoardDaysState] = useState(7);

  // A screen that unmounts mid-fetch must not setState — the team screens are
  // reachable from a modal stack that dismisses on Back.
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const loadExtras = useCallback(
    async (current: Org, days = usageDays, bDays = boardDays) => {
      if (!current.org_id) {
        if (alive.current) {
          setInvites([]);
          setUsage({ rows: [], members: 0, consented: 0 });
          setBoard({ enabled: false, rows: [] });
          setApps({});
        }
        return;
      }
      const admin = current.role === 'owner' || current.role === 'admin';
      // Each payload paints on its own — a failing leaderboard must never blank
      // the roster that already loaded.
      // Usage and app-mix are fetched for EVERYONE; the RPCs decide what comes
      // back (all consenting members for an admin, your own row otherwise).
      // Invites have no member-scoped version, so they stay admin-only.
      const [inv, use, brd, app] = await Promise.all([
        admin ? listInvites() : Promise.resolve([] as OrgInvite[]),
        usageSummary(days),
        leaderboard(bDays),
        appBreakdown(days),
      ]);
      if (!alive.current) return;
      setInvites(inv);
      setUsage(use);
      setBoard(brd);
      setApps(app);
    },
    [usageDays, boardDays],
  );

  const load = useCallback(
    async (refresh = true) => {
      if (alive.current) setLoading(true);
      try {
        // Paint the cache first so the screen isn't empty while the network runs.
        const cached = await getCachedOrg();
        if (alive.current && cached.org_id) setOrg(cached);
        const fresh = refresh ? await fetchOrg() : cached;
        if (alive.current) {
          setOrg(fresh);
          setError('');
        }
        await loadExtras(fresh);
      } catch {
        if (alive.current) setError("Couldn't reach your team");
      } finally {
        if (alive.current) setLoading(false);
      }
    },
    [loadExtras],
  );

  useEffect(() => {
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Every mutation re-renders from what the backend returned, never from an
  // optimistic local edit — roles and membership are other people's data too.
  const apply = useCallback(
    async (res: { ok: boolean; error?: string; org?: Org }) => {
      if (res.ok) {
        const next = res.org ?? (await fetchOrg());
        if (alive.current) {
          setOrg(next);
          setError('');
        }
        await loadExtras(next);
        return { ok: true };
      }
      if (alive.current) setError(res.error ?? 'Something went wrong');
      return { ok: false, error: res.error };
    },
    [loadExtras],
  );

  const createTeam = useCallback(
    async (name: string, company = '') => apply(await createOrg(name, company)),
    [apply],
  );
  const joinTeam = useCallback(async (linkOrToken: string) => apply(await claimInvite(linkOrToken)), [apply]);

  const invite = useCallback(
    async (email: string, role: 'member' | 'admin' = 'member') => {
      const res = await inviteMember(email, role);
      if (res.ok) {
        const inv = await listInvites();
        if (alive.current) {
          setInvites(inv);
          setError('');
        }
      } else if (alive.current) {
        setError(res.error ?? "Couldn't send the invite");
      }
      return res;
    },
    [],
  );

  const revoke = useCallback(async (inviteId: string) => {
    const res = await revokeInvite(inviteId);
    if (res.ok) {
      const inv = await listInvites();
      if (alive.current) setInvites(inv);
    } else if (alive.current) {
      setError(res.error ?? "Couldn't revoke that invite");
    }
    return res;
  }, []);

  const setRole = useCallback(
    async (userId: string, role: 'admin' | 'member') => apply(await setMemberRole(userId, role)),
    [apply],
  );
  const remove = useCallback(async (userId: string) => apply(await removeMember(userId)), [apply]);
  const leave = useCallback(async () => apply(await leaveOrg()), [apply]);
  const saveSettings = useCallback(
    async (fields: { name?: string; company_name?: string; leaderboard_enabled?: boolean; stats_visible_to_members?: boolean }) =>
      apply(await setOrgSettings(fields)),
    [apply],
  );
  const saveConsent = useCallback(
    async (usageConsent: boolean, boardOptIn: boolean) => apply(await setConsent(usageConsent, boardOptIn)),
    [apply],
  );

  const saveTeamDictionary = useCallback(
    async (d: Dictionary) => {
      const res = await saveTeamDictionaryLib(d);
      if (res.ok) {
        const fresh = await fetchOrg();
        if (alive.current) {
          setOrg(fresh);
          setError('');
        }
      } else if (alive.current) {
        setError(res.error ?? "Couldn't save the team dictionary");
      }
      return res;
    },
    [],
  );

  const setUsageDays = useCallback(
    async (days: number) => {
      setUsageDaysState(days);
      const [use, app] = await Promise.all([usageSummary(days), appBreakdown(days)]);
      if (alive.current) { setUsage(use); setApps(app); }
    },
    [],
  );
  const setBoardDays = useCallback(
    async (days: number) => {
      setBoardDaysState(days);
      const brd = await leaderboard(days);
      if (alive.current) setBoard(brd);
    },
    [],
  );

  return {
    org,
    invites,
    usage,
    board,
    apps,
    loading,
    error,
    usageDays,
    boardDays,
    hasTeam: !!org.org_id,
    isAdmin: org.role === 'owner' || org.role === 'admin',
    isOwner: org.role === 'owner',
    reload: load,
    createTeam,
    joinTeam,
    invite,
    revoke,
    setRole,
    remove,
    leave,
    saveSettings,
    saveConsent,
    saveTeamDictionary,
    setUsageDays,
    setBoardDays,
  };
}
