/**
 * useOrganization.mock — the design contract for the team layer (IDI-216).
 *
 * Same exported shape as useOrganization.ts, backed by in-memory state. Nothing
 * at runtime imports this; it is the reference the real hook must stay a drop-in
 * replacement for (verified by mutual type-assignability, IDI-179's rule). Keep
 * the two in sync in the same change — a drifted mock is worse than none, since
 * it IS the contract.
 */
import { useState, useCallback } from 'react';
import { NO_ORG, type Org, type OrgInvite, type UsageRow, type BoardRow } from '../../lib/organizations';
import type { Dictionary } from '../../lib/dictionary';

export type { Org, OrgMember, OrgInvite, UsageRow, BoardRow, OrgRole } from '../../lib/organizations';

// The real hook's mutations widen to {ok:boolean, error?:string} — an `as const`
// literal here would narrow to {ok:true} and break drop-in assignability, which
// is the one property this mock exists to guarantee.
type Ack = { ok: boolean; error?: string };

const DEMO_ORG: Org = {
  org_id: 'org_demo',
  name: 'Idiaz',
  company_name: 'Idiaz Ltd',
  role: 'owner',
  plan: 'team',
  seats: 5,
  leaderboard_enabled: true,
  stats_visible_to_members: false,
  usage_consent: true,
  leaderboard_opt_in: true,
  members: [
    {
      user_id: 'u1',
      email: 'sraza@idiaz.io',
      display_name: 'Shabbar Raza',
      role: 'owner',
      status: 'active',
      usage_consent: true,
      leaderboard_opt_in: true,
      joined_at: '2026-08-01T09:00:00Z',
    },
    {
      user_id: 'u2',
      email: 'dev@idiaz.io',
      display_name: 'Dev Two',
      role: 'member',
      status: 'active',
      usage_consent: false,
      leaderboard_opt_in: false,
      joined_at: '2026-08-04T11:20:00Z',
    },
  ],
  dictionary: {
    vocabulary: ['Idiaz', 'Flume', 'Verbal'],
    replacements: [{ from: 'ideas', to: 'Idiaz' }],
    snippets: [
      {
        id: 'sn1',
        trigger: 'legal footer',
        expansion: 'Confidential — do not forward.',
        label: '',
        used: 3,
        createdAt: '2026-08-02T10:00:00Z',
        updatedAt: '2026-08-02T10:00:00Z',
      },
    ],
  },
  dictionary_updated_at: '2026-08-10T12:00:00Z',
};

const DEMO_INVITES: OrgInvite[] = [
  {
    id: 'inv1',
    email: 'new@idiaz.io',
    role: 'member',
    status: 'pending',
    expires_at: '2026-08-26T00:00:00Z',
    created_at: '2026-08-19T08:00:00Z',
  },
];

const DEMO_USAGE: UsageRow[] = [
  {
    user_id: 'u1',
    email: 'sraza@idiaz.io',
    display_name: 'Shabbar Raza',
    role: 'owner',
    dictations: 128,
    words: 8412,
    speech_ms: 3_600_000,
    last_active: '2026-08-19T07:40:00Z',
  },
];

const DEMO_BOARD: BoardRow[] = [
  { user_id: 'u1', display_name: 'Shabbar Raza', words: 8412, speech_ms: 3_600_000 },
];

export function useOrganization() {
  const [org, setOrg] = useState<Org>(DEMO_ORG);
  const [invites, setInvites] = useState<OrgInvite[]>(DEMO_INVITES);
  const [usage, setUsage] = useState({ rows: DEMO_USAGE, members: 2, consented: 1 });
  const [board, setBoard] = useState({ enabled: true, rows: DEMO_BOARD });
  // Two members with app data, one without — the mock has to exercise the
  // "no app data yet" branch too, since that is what a real team sees first.
  const [apps] = useState<Record<string, Array<{ app: string; dictations: number; words: number }>>>({
    'demo-owner': [
      { app: 'Slack', dictations: 96, words: 7200 },
      { app: 'Cursor', dictations: 41, words: 3100 },
      { app: 'Linear', dictations: 12, words: 640 },
    ],
    'demo-member': [{ app: 'Chrome', dictations: 58, words: 3900 }],
  });
  const [error] = useState('');
  const [usageDays, setUsageDaysState] = useState(30);
  const [boardDays, setBoardDaysState] = useState(7);

  const reload = useCallback(async (_refresh = true) => {}, []);

  const createTeam = useCallback(async (name: string, company = '') => {
    setOrg({ ...DEMO_ORG, name, company_name: company, members: [DEMO_ORG.members[0]] });
    return { ok: true } as Ack;
  }, []);

  const joinTeam = useCallback(async (_linkOrToken: string) => {
    setOrg({ ...DEMO_ORG, role: 'member' });
    return { ok: true } as Ack;
  }, []);

  const invite = useCallback(async (email: string, role: 'member' | 'admin' = 'member') => {
    setInvites((prev) => [
      {
        id: 'inv_' + prev.length,
        email,
        role,
        status: 'pending',
        expires_at: '',
        created_at: '',
      },
      ...prev,
    ]);
    return { ok: true, link: 'https://flume.app/join?t=demo' } as Ack & { link?: string };
  }, []);

  const revoke = useCallback(async (inviteId: string) => {
    setInvites((prev) => prev.filter((i) => i.id !== inviteId));
    return { ok: true } as Ack;
  }, []);

  const setRole = useCallback(async (userId: string, role: 'admin' | 'member') => {
    setOrg((o) => ({ ...o, members: o.members.map((m) => (m.user_id === userId ? { ...m, role } : m)) }));
    return { ok: true } as Ack;
  }, []);

  const remove = useCallback(async (userId: string) => {
    setOrg((o) => ({ ...o, members: o.members.filter((m) => m.user_id !== userId) }));
    return { ok: true } as Ack;
  }, []);

  const leave = useCallback(async () => {
    setOrg(NO_ORG);
    setInvites([]);
    return { ok: true } as Ack;
  }, []);

  const saveSettings = useCallback(
    async (fields: { name?: string; company_name?: string; leaderboard_enabled?: boolean }) => {
      setOrg((o) => ({ ...o, ...fields }));
      return { ok: true } as Ack;
    },
    [],
  );

  const saveConsent = useCallback(async (usageConsent: boolean, boardOptIn: boolean) => {
    setOrg((o) => ({
      ...o,
      usage_consent: usageConsent,
      leaderboard_opt_in: usageConsent && boardOptIn,
    }));
    return { ok: true } as Ack;
  }, []);

  const saveTeamDictionary = useCallback(async (d: Dictionary) => {
    setOrg((o) => ({ ...o, dictionary: d }));
    return { ok: true, dictionary: d } as Ack & { dictionary?: Dictionary };
  }, []);

  const setUsageDays = useCallback(async (days: number) => {
    setUsageDaysState(days);
    setUsage((u) => ({ ...u }));
  }, []);

  const setBoardDays = useCallback(async (days: number) => {
    setBoardDaysState(days);
    setBoard((b) => ({ ...b }));
  }, []);

  return {
    org,
    invites,
    usage,
    board,
    apps,
    loading: false,
    error,
    usageDays,
    boardDays,
    hasTeam: !!org.org_id,
    isAdmin: org.role === 'owner' || org.role === 'admin',
    isOwner: org.role === 'owner',
    reload,
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
