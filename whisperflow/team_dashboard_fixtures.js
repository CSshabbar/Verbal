// team_dashboard_fixtures.js — headless assertions over the rendered Team and
// Dictionary screens (IDI-216).
//
//     cd whisperflow && node team_dashboard_fixtures.js
//
// There is no browser here: a thin DOM shim records innerHTML per element id and
// the assertions read it back. That is enough to catch the class of bug that kept
// reaching the user through this surface — a card that renders an empty box where
// it should render a sentence, a control that never appears, a privacy string
// that stopped being true.
// Drives the real rendered dashboard JS against fixture team data and asserts on
// the produced HTML. No browser: a thin DOM shim records innerHTML per element.
//
// Two harness gotchas, both learned the hard way:
//  1. `var` declared inside a contextified vm sandbox is NOT reliably visible as
//     `sandbox.X` from the outside, so fixtures are injected and assertions run
//     INSIDE the context (appended to the source) and report through a
//     pre-existing array whose identity is shared across the boundary.
//  2. setTimeout must be a no-op. A stub that fires immediately runs the 400ms
//     bootstrap, which calls load() and overwrites the fixture with nulls.
const { execFileSync } = require('child_process'), vm = require('vm'), path = require('path');

// Render the real dashboard and pull every <script> out of it, so this exercises
// what ships rather than a copy of it (convention #39: verify a rendered surface
// by rendering it).
const ROOT = __dirname;
const html = execFileSync(
  path.join(ROOT, '.venv/bin/python'),
  ['-c', 'from app import flume_dashboard_html as M; import sys; sys.stdout.write(M.flume_html())'],
  { cwd: ROOT, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 },
);
const blocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (!blocks.length) {
  console.log('THREW: no <script> blocks in the rendered dashboard');
  process.exit(1);
}
// All blocks concatenated: SVG, the formatters and the screens live in separate
// <script> tags but share one global scope in the browser.
let src = blocks.join('\n;\n');
// Top-level `let`/`const` are lexical and unreachable from the appended script's
// own scope only if it were a separate compilation — appending keeps one script,
// so this demotion is belt-and-braces for readability of the probe.
src = src.replace(/^(let|const) /gm, 'var ');

const els = new Map();
function el(id){
  if(!els.has(id)) els.set(id, {id, innerHTML:'', textContent:'', style:{},
    classList:{add(){},remove(){},toggle(){},contains:()=>false},
    value:'', appendChild(){}, addEventListener(){}, setAttribute(){}, removeAttribute(){},
    querySelectorAll:()=>[], querySelector:()=>null, focus(){}, closest:()=>null,
    dataset:{}, children:[], remove(){}, scrollTo(){}, getBoundingClientRect:()=>({width:600,height:400})});
  return els.get(id);
}
const RESULTS = [];
const sandbox = {
  console, RESULTS,
  HTML_OF: (id) => el(id).innerHTML,
  ALL_HTML: () => [...els.values()].map(e=>e.innerHTML).join('\n'),
  document: {
    getElementById: (id)=>el(id), querySelector: ()=>null, querySelectorAll: ()=>[],
    createElement: ()=>el('_tmp'), body: el('_body'), documentElement: el('_html'),
    addEventListener(){},
  },
  window: { addEventListener(){}, matchMedia:()=>({matches:false, addEventListener(){}}), location:{href:''} },
  navigator: { clipboard:{writeText(){}}, userAgent:'node', platform:'MacIntel' },
  setTimeout: ()=>0, clearTimeout: ()=>{}, setInterval: ()=>0, clearInterval: ()=>{},
  requestAnimationFrame: ()=>0, fetch: ()=>Promise.reject(new Error('no net')),
  localStorage: { getItem:()=>null, setItem(){}, removeItem(){} },
  Date, Math, JSON, Number, String, Array, Object, Boolean, RegExp, Error, Promise,
  isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent,
};
sandbox.window.document = sandbox.document;

// ── everything below runs INSIDE the context ────────────────────────────────
src += `
;(function(){
  function chk(name, cond, extra){ RESULTS.push({name:name, ok:!!cond, extra:extra}); }
  api = function(){ return Promise.resolve({ok:false}); };

  var ME='u-me', OTHER='u-other', QUIET='u-quiet';
  STATE = { settings:{ sync_user_id: ME } };
  ACTIVE = 'team';
  TEAM = {
    org_id:'org1', name:'Acme', role:'owner', plan:'team', seats:5,
    domain:'acme.com', is_generic_domain:false, auto_join_enabled:false,
    usage_consent:true, leaderboard_opt_in:true, leaderboard_enabled:false,
    members:[
      {user_id:ME,    display_name:'Me Owner',     email:'me@acme.com', role:'owner',  usage_consent:true},
      {user_id:OTHER, display_name:'Other Person', email:'o@acme.com',  role:'member', usage_consent:true},
      {user_id:QUIET, display_name:'Quiet One',    email:'q@acme.com',  role:'member', usage_consent:false},
    ],
    dictionary:{ vocabulary:['Flume','Groq'], replacements:[{from:'flu',to:'Flume'}],
                 snippets:[{trigger:'sig',expansion:'Best, me'}] },
  };
  TEAM_INV=[]; TEAM_SETUP=true; TEAM_DAYS=30; TEAM_SEL='all'; TEAM_SERIES={};
  TEAM_USAGE = { rows:[
    {user_id:OTHER, display_name:'Other Person', words:9000, dictations:120, speech_ms:600000},
    {user_id:ME,    display_name:'Me Owner',     words:4000, dictations:60,  speech_ms:300000},
  ]};
  TEAM_APPS = {};
  TEAM_APPS[OTHER] = [{app:'Slack',dictations:80,words:6000},{app:'Cursor',dictations:30,words:2400},{app:'Linear',dictations:10,words:600}];
  TEAM_APPS[ME]    = [{app:'Chrome',dictations:60,words:4000}];
  TEAM_BOARD = { rows:[{user_id:OTHER, display_name:'Other Person', words:9000}] };
  DICT = { vocabulary:['minepersonalword'], replacements:[], snippets:[] };

  renderTeam();
  var all = ALL_HTML();

  chk('team screen rendered', /Acme/.test(all));
  chk('ranking card present', /Ranking/.test(all));
  chk('two ranked rows', (all.match(/class="tmbrow/g)||[]).length===2, (all.match(/class="tmbrow/g)||[]).length);
  // The roster is deliberately in membership order, so check rank order on the
  // ranking rows themselves rather than on the whole page.
  var brows = all.split('class="tmbrow').slice(1);
  chk('ranked by words, biggest first',
      brows.length===2 && /Other Person/.test(brows[0]) && /Me Owner/.test(brows[1]),
      brows.length+' rows');
  chk('leader highlighted', /tmbrow p1/.test(all));
  chk('my own row marked', /tmbrow[^"]* me"/.test(all));
  chk('rank numbers rendered', /tmbrank">1</.test(all) && /tmbrank">2</.test(all));
  chk('row shows dictations', /120 dictations/.test(all));
  chk('row shows wpm', /900 wpm/.test(all), (all.match(/\\d+ wpm/)||[])[0]);
  chk('row shows top app', /mostly Slack/.test(all));
  chk('clicking a row selects the member', /selectMember\\('u-other'\\)/.test(all));
  chk('non-sharing member accounted for', /1 member is not sharing/.test(all));

  chk('apps card present', /Where the team writes/.test(all));
  chk('one stacked bar per member with data', (all.match(/class="tmappbar"/g)||[]).length===2, (all.match(/class="tmappbar"/g)||[]).length);
  chk('legend carries shares', /Slack<\\/b> 67%/.test(all), (all.match(/Slack<\\/b> \\d+%/)||[])[0]);
  chk('members without app data flagged', /No app data for 1 member/.test(all));

  chk('no shared-word chips left on Team', !/dictchips/.test(all));
  chk('no shared-word editor left on Team', !/tdAddWord/.test(all));
  chk('Team links to the Dictionary instead', /openTeamDictionary\\(\\)/.test(all));
  chk('Team no longer carries the privacy toggles', !/setTeamConsent/.test(all));
  chk('shared dictionary counts summarised', /2 words<\\/b>, 1 rule and 1 snippet/.test(all));

  chk('words tile', /Words spoken/.test(all) && /13,000/.test(all));
  chk('dictations tile', /Dictations/.test(all) && /180/.test(all));
  chk('pace tile', /Team pace/.test(all) && /867/.test(all), (all.match(/tv">(\\d+)<em/)||[])[1]);

  // ── a single member's page ──────────────────────────────────────────────
  TEAM_SEL = OTHER;
  renderTeam();
  var mem = ALL_HTML();
  chk('member page names the person', /Other Person/.test(mem));
  chk('member app panel present', /Where Other writes/.test(mem));
  chk('member app panel lists every app', /Slack/.test(mem) && /Cursor/.test(mem) && /Linear/.test(mem));
  chk('member app shares add up', /67% &middot; 80/.test(mem), (mem.match(/\d+% &middot; \d+/)||[])[0]);
  chk('member privacy copy mentions apps', /the names of the apps they dictate into/.test(mem));

  TEAM_SEL = ME;
  renderTeam();
  var mine = ALL_HTML();
  chk('my own page uses first-person privacy copy', /counts, durations and app names/.test(mine));
  chk('my own single app renders at 100%', /100% &middot; 60/.test(mine));

  // A member who turned sharing off shows nothing at all — not an app panel with
  // an explanation, which would still be a page about them.
  TEAM_SEL = QUIET;
  renderTeam();
  var q = ALL_HTML();
  chk('non-consenting member shows no app panel', !/Where Quiet writes/.test(q));

  // A CONSENTING member with no app rows is the case that must explain itself.
  var keptApps = TEAM_APPS[ME]; delete TEAM_APPS[ME];
  TEAM_SEL = ME;
  renderTeam();
  var noapp = ALL_HTML();
  chk('empty member app panel explains the cutoff', /21 Aug 2026/.test(noapp));
  chk('empty member app panel mentions iOS', /frontmost window to read on iOS/.test(noapp));
  TEAM_APPS[ME] = keptApps;
  TEAM_SEL = 'all';

  // ── Dictionary screen, team scope ────────────────────────────────────────
  DICT_SCOPE='team'; ACTIVE='dictionary';
  renderDictionary();
  var d = HTML_OF('dictionaryMain');
  chk('team dictionary renders', /Shared vocabulary/.test(d));
  chk('shared words listed', /Flume/.test(d) && /Groq/.test(d));
  chk('shared rules listed', /flu/.test(d));
  chk('shared snippets listed', /sig/.test(d));
  chk('admin gets the add boxes', /tdAddWord\\(\\)/.test(d) && /tdAddRep\\(\\)/.test(d) && /tdAddSnip\\(\\)/.test(d));
  chk('scope tabs on the team page', /setDictScope\\('personal'\\)/.test(d) && /setDictScope\\('team'\\)/.test(d));
  chk('tab labelled with the team name', /Acme<\\/button>/.test(d));
  chk('offers to seed from personal', /Copy mine to the team/.test(d));
  chk('personal-wins rule stated', /Your own entries always win/.test(d));

  TEAM.role='member';
  renderDictionary();
  var ro = HTML_OF('dictionaryMain');
  chk('member cannot edit shared entries', !/tdAddWord\\(\\)/.test(ro) && !/tdRmWord\\(/.test(ro));
  chk('member page marked read-only', /tmreadonly/.test(ro));
  chk('member told who maintains it', /admins maintain these/.test(ro));
  TEAM.role='owner';

  DICT_SCOPE='personal';
  renderDictionary();
  chk('personal dictionary still renders', /minepersonalword/.test(HTML_OF('dictionaryMain')));
  chk('personal page also carries the tabs', /setDictScope/.test(HTML_OF('dictionaryMain')));

  var keep=TEAM; TEAM=null;
  renderDictionary();
  chk('no team means no scope tabs', !/setDictScope/.test(HTML_OF('dictionaryMain')));
  chk('team scope falls back when the team vanishes', (function(){
    DICT_SCOPE='team'; renderDictionary();
    return /minepersonalword/.test(HTML_OF('dictionaryMain'));
  })());
  TEAM=keep; DICT_SCOPE='personal';

  // ── a PLAIN MEMBER's overview ───────────────────────────────────────────
  // This is the case that shipped broken: org_usage_summary was admin-only, the
  // client gated the request on teamAdmin() as well, and every total on the page
  // is derived from those rows — so a member saw a team that looked like it had
  // never dictated anything, explained by "usage appears here as people turn
  // sharing on" while everyone WAS sharing.
  TEAM.role = 'member';
  TEAM_SEL = 'all';
  // What the RPCs actually hand a member: exactly their own row, nobody else's.
  TEAM_USAGE = { rows: [{ user_id: ME, display_name: 'Me Owner', words: 4000, dictations: 60, speech_ms: 300000 }] };
  TEAM_APPS = {}; TEAM_APPS[ME] = [{ app: 'Chrome', dictations: 60, words: 4000 }];
  renderTeam();
  var mem2 = ALL_HTML();
  chk('member sees their own numbers, not zero', /4,000/.test(mem2));
  chk('member page is titled about them', /You on Acme/.test(mem2));
  chk("member total is not claimed as the team's", !/Acme spoke/.test(mem2));
  chk('member hero speaks in second person', /You spoke <b>4,000 words<[/]b>/.test(mem2));
  chk('no contribution ring for one contributor', !/tmringsvg|<svg[^>]*class="tmr/i.test(mem2));
  chk('member tile says "Your words"', /Your words/.test(mem2));
  chk('member tile says "Your pace"', /Your pace/.test(mem2));
  chk('no misleading "N of M sharing" for a member', !/of 3 sharing/.test(mem2));
  chk('member told the scope of the page', /Only your own numbers appear on this page/.test(mem2));
  chk('member gets the day-range control', /teamDays\\(90\\)/.test(mem2));
  chk('member sees their own app mix', /Where you write/.test(mem2));
  chk('member app panel says "You"', /tmapphd"><b>You<[/]b>/.test(mem2));
  chk('member app panel has exactly one bar', (mem2.match(/class="tmappbar"/g)||[]).length===1,
      (mem2.match(/class="tmappbar"/g)||[]).length);
  chk('no "no app data for N members" noise for a member', !/No app data for/.test(mem2));
  chk('member cannot see the invite list', !/tmrfoot/.test(mem2) || !/revokeInvite/.test(mem2));

  // A member who genuinely has not dictated must read as "you haven't", not as
  // "nobody is sharing" — that sentence was the false one.
  TEAM_USAGE = { rows: [] }; TEAM_APPS = {};
  renderTeam();
  var memZero = ALL_HTML();
  chk('empty member view blames nothing on consent', !/as people turn sharing on/.test(memZero));
  chk('empty member view is about them', /You haven.{0,8}t dictated in the last 30 days/.test(memZero));

  // An ADMIN with a loaded-but-empty window must also not blame consent.
  TEAM.role = 'owner';
  TEAM_USAGE = { rows: [] };
  renderTeam();
  chk('admin empty window says nobody dictated', /Nobody on the team has dictated in this window/.test(ALL_HTML()));

  // restore
  TEAM.role = 'owner';
  TEAM_USAGE = { rows: [
    {user_id:OTHER, display_name:'Other Person', words:9000, dictations:120, speech_ms:600000},
    {user_id:ME,    display_name:'Me Owner',     words:4000, dictations:60,  speech_ms:300000},
  ]};
  TEAM_APPS = {};
  TEAM_APPS[OTHER] = [{app:'Slack',dictations:80,words:6000},{app:'Cursor',dictations:30,words:2400},{app:'Linear',dictations:10,words:600}];
  TEAM_APPS[ME]    = [{app:'Chrome',dictations:60,words:4000}];

  // ── the privacy pane now lives in Settings ──────────────────────────────
  ACTIVE = 'settings';
  SETTINGS_GROUP = 'privacy';
  STATE.settings = { sync_user_id: ME };
  renderSettings();
  var set = HTML_OF('settingsMain');
  chk('privacy group is in the rail', /setSettingsGroup\\('privacy'\\)/.test(set));
  chk('privacy group is the current one', /sritem on[^>]*onclick="setSettingsGroup\\('privacy'\\)/.test(set)
      || /setSettingsGroup\\('privacy'\\)[^>]*aria-current="page"/.test(set));
  chk('consent toggle rendered', /setTeamConsent\\(false, true\\)/.test(set));
  chk('ranking opt-in toggle rendered', /setTeamConsent\\(true, false\\)/.test(set));
  chk('privacy pane discloses app names', /names of the apps you dictate into/.test(set));
  chk('privacy pane keeps the Insights caveat', /will always read higher/.test(set));
  chk('rail badge reflects the consent state', /sharing<[/]em>/.test(set));
  chk('an owner is told they cannot leave', /owner cannot leave/.test(set));
  chk('no Leave button for an owner', !/leaveTeam\\(\\)/.test(set));

  TEAM.role = 'member';
  renderSettings();
  var setM = HTML_OF('settingsMain');
  chk('a member gets a Leave button', /leaveTeam\\(\\)/.test(setM));
  TEAM.role = 'owner';

  TEAM.usage_consent = false;
  renderSettings();
  chk('rail badge flips to private', /private<[/]em>/.test(HTML_OF('settingsMain')));
  TEAM.usage_consent = true;

  // Leaving the team while sitting on the group must not strand the pane.
  var keepTeam2 = TEAM; TEAM = null;
  renderSettings();
  var noTeam = HTML_OF('settingsMain');
  chk('privacy group hidden without a team', !/setSettingsGroup\\('privacy'\\)/.test(noTeam));
  chk('group falls back to account', SETTINGS_GROUP === 'account');
  TEAM = keepTeam2; SETTINGS_GROUP = 'privacy';

  // ...and Team keeps a pointer, not the card
  ACTIVE = 'team';
  renderTeam();
  var tp = ALL_HTML();
  chk('Team shows a privacy summary, not toggles', !/setTeamConsent/.test(tp));
  chk('Team points at Settings', /showTeamPrivacy\\(\\)/.test(tp));
  chk('Team states the current sharing state', /sharing your dictation counts/.test(tp));
  chk('Leave team is no longer on the Team overview', !/leaveTeam\\(\\)/.test(tp));

  // ── empty states must not read as broken ────────────────────────────────
  ACTIVE='team';
  TEAM = {org_id:'o', name:'Solo', role:'owner', seats:1, plan:'team',
          usage_consent:true, is_generic_domain:true,
          members:[{user_id:ME, display_name:'Me', role:'owner', usage_consent:true}], dictionary:{}};
  TEAM_USAGE={rows:[]}; TEAM_APPS={}; TEAM_BOARD={rows:[]}; TEAM_INV=[];
  renderTeam();
  var e2 = ALL_HTML();
  chk('empty apps panel explains the cutoff', /21 Aug 2026/.test(e2));
  chk('empty ranking is honest', /Nobody has dictated/.test(e2));
  chk('empty shared dictionary pointer', /Nothing shared yet/.test(e2));
  chk('no NaN anywhere in the empty state', !/NaN/.test(e2));
  chk('no undefined leaking into the empty state', !/undefined/.test(e2));

  // ── non-admin, ranking disabled by the owner ─────────────────────────────
  TEAM = {org_id:'o', name:'Acme', role:'member', seats:5, plan:'team',
          usage_consent:true, leaderboard_enabled:false, is_generic_domain:false, domain:'acme.com',
          members:[{user_id:ME, display_name:'Me', role:'member', usage_consent:true}], dictionary:{}};
  TEAM_USAGE=null; TEAM_APPS={};
  renderTeam();
  var m2 = ALL_HTML();
  chk('member told the ranking is off', /hasn.{0,8}t turned the ranking on/.test(m2));
  chk('member sees no per-person app panel', !/Where the team writes/.test(m2));
  chk('member cannot toggle the ranking', !/toggleTeamBoard\\(\\)/.test(m2));
})();
`;

vm.createContext(sandbox);
try { vm.runInContext(src, sandbox, {filename:'dashboard.js'}); }
catch (e) { console.log('THREW: ' + e.message + '\n' + (e.stack||'').split('\n').slice(0,4).join('\n')); process.exit(1); }

let pass=0, fail=0;
for (const r of RESULTS) {
  if (r.ok) pass++;
  else { fail++; console.log('FAIL: ' + r.name + (r.extra!==undefined ? '  [got: '+r.extra+']' : '')); }
}
console.log(`\ntotal=${pass+fail} passed=${pass} failed=${fail} ALL_GREEN=${fail===0}`);
process.exit(fail?1:0);
