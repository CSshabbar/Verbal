# Flume — Competitive Analysis & Differentiation Strategy

*Prepared July 2026. Companion document to `Flume_PRD_v2.md`.*

---

## 1. Executive Summary

Flume today is a **well-scoped voice-first productivity app** — press-to-talk dictation with AI cleanup, a personal dictionary that learns, notes, a cross-device shared clipboard ("Canvas"), and a lightweight Auto-Learn correction loop on Mac. Its DNA — quiet, non-interrupting, cross-device — is genuinely differentiated from the "loud" competitors who are optimizing for viral demos.

But the category around Flume has moved fast. In the 12 months to July 2026:

- **Wispr Flow** closed a ~$260M Series B at a ~$2B valuation ([Bloomberg](https://www.bloomberg.com/news/articles/2026-05-12/ai-dictation-startup-wispr-in-funding-talks-at-2-billion-value)), is inside 270+ Fortune 500 companies, and is being positioned as a "voice operating system" ([TechCrunch](https://techcrunch.com/2025/11/20/as-its-voice-dectation-app-takes-off-wispr-secures-25m-from-notable-capital/)).
- **Granola** hit a $1.5B valuation on $125M Series C in March 2026 ([TechCrunch](https://techcrunch.com/2026/03/25/granola-raises-125m-hits-1-5b-valuation-as-it-expands-from-meeting-notetaker-to-enterprise-ai-app/)), validating the bot-free meeting-capture pattern Flume's PRD is already leaning into.
- **Willow Voice** raised $4.2M+ from BoxGroup/YC/Ohanian/Shah and grew 50% MoM after launching an iOS voice keyboard with inline edit ([TechCrunch](https://techcrunch.com/2025/11/12/willows-voice-keyboard-lets-you-type-across-all-your-ios-apps-and-actually-edit-what-you-said/)).
- **Aqua Voice** carved out the developer/"vibe coding" niche with a proprietary "Avalon" model and 97.3% accuracy claims ([withaqua.com](https://withaqua.com)).
- **Superwhisper** owns the local/BYOK power-user segment but is stumbling on reliability and community trust ([r/superwhisper](https://www.reddit.com/r/superwhisper/comments/1oxjocz/good_bye_whisper/)).
- The frontier has shifted from "transcription accuracy" to **agentic voice** — voice that *does things* across apps (Wispr Command Mode, VoiceOS, Lemon/heylemon).

The category is bifurcating along four axes: **local-first vs. cloud-first**, **verbatim vs. LLM-rewriting**, **passive dictation vs. agentic**, and **individual vs. team-graph**. Every major player has picked 2–3 of those axes. **None has picked all four coherently.** That is Flume's opening.

Flume's proposed roadmap is directionally right (meeting transcription, snippets, context-aware formatting, voice search, agentic commands, teams), but as-drafted it is **defensively feature-matching Wispr Flow / Willow / Aqua** rather than opening a defensible position. This document proposes a differentiated positioning and 27 concrete feature additions/enhancements, then translates them into a build-ready PRD.

---

## 2. Where Flume Actually Sits Today

### 2.1 Strengths (keep, defend)

| Strength | Why it matters |
|---|---|
| **"Quiet by design" character** — never interrupts, minimal chrome, unobtrusive recording indicator | Real, felt differentiator versus Wispr's aggressive on-screen UI and Otter's visible bot. The competitive research shows "AI over-editing/hallucination" and "screenshot for context without consent" ([efficient.app](https://efficient.app/apps/wispr-flow)) as top complaints — Flume's default posture is already the remedy. |
| **Offline Mac dictation** | ~40% of voice-dictation review complaints are "no offline mode" ([Weesper](https://weesperneonflow.ai/en/blog/2026-02-09-wispr-flow-review-cloud-dictation-2026/)). Wispr, Otter, Willow are all cloud-only. This is already a moat if marketed. |
| **Auto-Learn from corrections (Mac)** | Genuinely novel — most competitors require manual dictionary entry. Superwhisper users complain that overfilling the dictionary triggers hallucinations ([r/superwhisper](https://www.reddit.com/r/superwhisper/comments/1max1yr/insane_they_block_you_if_you_mention_a_competitor/)). Flume's learning loop is superior in principle. |
| **Cross-device toolkit** (Canvas, Notes, Dictionary sync) | Wispr, Willow, Superwhisper are all dictation-first with weak or no shared state. Flume already has the "connected surface" story. |
| **Smart file references in code editors** | A concrete developer win that Wispr and Willow don't quite match; Aqua Voice is the closest competitor here. |

### 2.2 Gaps / risks (as of today's PRD)

| Gap | Evidence |
|---|---|
| **No published transcription engine story** | Users increasingly ask "what model?" — Superwhisper wins by exposing model choice; Aqua wins by branding "Avalon"; MacWhisper wins by transparency (Whisper + Parakeet + WhisperKit). Flume has no answer. |
| **No context-aware formatting today** | Wispr's #1 marketed feature; Aqua's core positioning; Willow's tone presets. Flume treats this as "future scope." |
| **No snippets / voice-triggered text expansion** | Flume's own PRD flags this as "the highest-priority gap." It's table stakes now (Wispr, Willow, VoicePen, TextExpander+AI). |
| **No verbatim mode toggle** | The single most common complaint across all AI-native tools: cleanup adds words the user never said. Users want a switch. |
| **No team layer** | Wispr, Aqua, Willow, Granola all have team tiers with shared dictionaries, snippet libraries, admin controls. Flume has "one person" architecture. |
| **No security/compliance posture disclosed** | SOC 2 Type II, HIPAA BAA, ISO 27001, GDPR are becoming table stakes ([Anvevoice](https://anvevoice.app/faq/voice-ai-soc2-compliance-2026)). Wispr got there under pressure; Willow markets it. Flume must catch up. |
| **No agentic voice mode** | The category-defining 2026 frontier. Command Mode (Wispr Pro), Lemon, VoiceOS all execute real actions. Flume's PRD correctly flags this needs safeguards — but has no design for them. |
| **Windows lag** | Windows is "partial" today. Wispr, Willow, Aqua all ship near-parity Windows. This costs Flume half the addressable market. |
| **Android missing** | Wispr's Android launch had a **375,000-person waitlist** ([market trends report](/home/user/workspace/research/voice_ai_market_trends.md)) — pent-up demand is enormous and Flume is not there. |
| **Distribution / community** | Wispr's endorsements (Reid Hoffman), Willow's (Alexis Ohanian), Superwhisper's (Karpathy, Levels) — Flume has none surfaced. Habit-formation is the primary growth engine in this category and Flume needs a visible community loop. |

---

## 3. The Competitive Landscape (Condensed)

### 3.1 Direct competitors — dictation-first

| Product | Anchor price | Engine | Positioning | Biggest weakness |
|---|---|---|---|---|
| **[Wispr Flow](https://wisprflow.ai/pricing)** | $12/mo (annual) | Undisclosed cloud | Category leader, "voice OS" ambition | Trust deficit (2025 privacy incident), no true offline, reliability outages |
| **[Willow Voice](https://willowvoice.com/pricing)** | $12/mo (annual) | Cloud + limited offline | iOS voice keyboard with inline edit; real-time self-correction | Weak custom dictionary, 8-min continuous cap |
| **[Aqua Voice](https://withaqua.com)** | $8/mo (annual) | Proprietary "Avalon" cloud | Developer/"vibe coding" screen-context | Cloud-only, no HIPAA BAA |
| **[Superwhisper](https://superwhisper.com)** | $8.49/mo | Whisper Large + user-selectable LLMs | Local + model marketplace | Reliability regressions, community trust issues |
| **[MacWhisper](https://goodsnooze.gumroad.com/l/macwhisper)** | ~$60 one-time | Whisper + Parakeet + WhisperKit | Best file-transcription + local dictation | Not real-time-first; Mac-only |
| **[BetterDictation](https://betterdictation.com/)** | $39 lifetime + $2/mo AI | Whisper v3-turbo on Apple Neural Engine | Cheapest, most private baseline | Mac-only, minimal features |
| **[Talon](https://talonvoice.com)** | Free (Patreon) | Multiple backends | RSI/hands-free power users | Extreme learning curve |
| **[Whispering/Epicenter](https://github.com/epicenter-md/epicenter)** | Free OSS | BYOK | Local-first, plain-text data ownership | Minimal features, tiny community |
| **[Dragon Professional](https://www.nuance.com/dragon.html)** | $699 one-time | Nuance proprietary | Legacy verticals (legal/medical) | Stagnant since Microsoft acquisition; Windows-only |

### 3.2 Meeting-transcription adjacencies (Flume's proposed expansion territory)

| Product | Anchor price | Bot? | Diarization | Biggest edge / miss |
|---|---|---|---|---|
| **[Granola](https://www.granola.ai/pricing)** | $14/mo | No (local capture) | Weak on desktop | Human-in-loop notes / $1.5B valuation / no Android |
| **[Otter.ai](https://otter.ai/pricing)** | $16.99/mo | Yes | 79–95% variable | Mature ecosystem / shrinking free tier |
| **[Fireflies.ai](https://fireflies.ai/pricing)** | $10/mo | Yes | Up to 50 speakers | CRM depth / annoying AI-credit meter |
| **[Fathom](https://www.fathom.ai/pricing)** | $20/mo | Yes | Not corroborated | Best free tier / CRM-sync only at top tier |
| **[Meetily](https://meetily.ai/)** | Free OSS / ~$10 Pro | No | Local | 100% self-hosted / needs setup |
| **[Krisp](https://krisp.ai/pricing/)** | $16/mo (trial only) | No (audio-layer plugin) | N/A | Voice AI SDK (accent conversion, isolation) / lost permanent free tier |
| **[Sembly AI](https://www.sembly.ai/pricing/)** | ~$10–17/mo | Yes | Included | Longitudinal risk/commitment tracking |
| **[Read.ai](https://www.read.ai/benchmarks)** | Unpublished | Yes (video required) | Video-based | Sentiment/engagement scoring / high consent friction |
| **[Circleback](https://circleback.ai)** | Not corroborated | Yes | Not corroborated | Commitment extraction focus |
| **[tl;dv](https://tldv.io/)** | Free / $29 | Yes | Not corroborated | Generous free video recording |
| **[Notta](https://notta.ai)** | $13.99/mo | Yes + handheld device | Included | Japanese-language strength / **trains on customer data** |

### 3.3 Adjacent categories worth watching

- **ChatGPT Advanced Voice / Apple Intelligence / Google Recorder / Windows Copilot Voice** — OS-native voice is improving but is *general-purpose assistant*, not a dictation productivity primitive. The gap Flume fills (system-wide, focused, quiet) survives.
- **Text expansion** ([TextExpander](https://textexpander.com/pricing) $3.33–10/mo, [Espanso](https://espanso.org) free, [Raycast](https://www.raycast.com/pricing) free) — none currently marries snippets to voice as a first-class feature. TextExpander added "+AI" in 2025 but not voice-triggered. This is Flume's opportunity.
- **Voice-generation / STT infra** — [ElevenLabs Scribe v2](https://elevenlabs.io/pricing/api) (~150ms latency, 90+ languages, 32-speaker diarization), [Deepgram Nova-3](https://deepgram.com), [AssemblyAI Universal-3.5](https://www.assemblyai.com/benchmarks), [Groq Whisper](https://groq.com) (~$0.04/hr — 9x cheaper than OpenAI) mean best-in-class STT is now a *purchasable commodity*. Flume can be model-agnostic without penalty.
- **Ambient wearables** — Limitless was acquired by Meta and effectively shuttered ([Rewind status](https://rewind.ai/what-happened-to-rewind/)). Flume should *not* chase hardware.

### 3.4 Feature availability at a glance

Legend: ✅ = ships today · 🟡 = partial · 🚧 = roadmap/beta · ❌ = missing

| Capability | Flume today | Wispr | Willow | Aqua | Superwhisper | Granola |
|---|---|---|---|---|---|---|
| System-wide dictation | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Mac / Windows / iOS / Android | ✅/🟡/✅/❌ | ✅/✅/✅/✅ | ✅/✅/✅/✅ | ✅/✅/✅/❌ | ✅/✅/✅/❌ | ✅/🟡/✅/❌ |
| True offline mode | ✅ (Mac) | ❌ | 🟡 | ❌ | ✅ | 🟡 |
| Model transparency / choice | ❌ | ❌ | ❌ | 🟡 | ✅ | ❌ |
| AI cleanup | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Verbatim mode toggle | ❌ | 🟡 | ❌ | ❌ | ✅ | N/A |
| Context-aware formatting | ❌ | ✅ | ✅ | ✅ | 🟡 | N/A |
| Mid-dictation self-correction | ❌ | 🟡 | ✅ | 🟡 | ❌ | N/A |
| Personal dictionary (auto-learn) | ✅ | ✅ | ✅ | 🟡 | 🟡 | N/A |
| Voice-triggered snippets | ❌ | ✅ | ✅ | ❌ | ❌ | N/A |
| Meeting transcription | ❌ (planned) | ❌ | ❌ | ❌ | 🟡 (file) | ✅ |
| Voice search over history | ❌ (planned) | 🟡 | ❌ | ❌ | ❌ | ✅ |
| Agentic voice commands | ❌ (planned) | ✅ (Pro) | 🟡 | ❌ | ❌ | ❌ |
| Team tier + shared dict/snippets | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ |
| SOC 2 Type II / HIPAA BAA | ❌ | ✅ | ✅ | 🟡 | 🟡 | ✅ |
| MCP integration | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (Business) |
| Whisper / silent mode | ❌ | ✅ | ❌ | ❌ | ❌ | N/A |
| Real-time translation | ❌ (planned) | ✅ | ❌ | ❌ | ✅ | ❌ |

---

## 4. The Differentiation Whitespace

Combining Flume's existing DNA with what the category has *not* nailed, I see **five compounding differentiators** worth building the product around. None of these is a single feature — each is a design stance that ripples through many features.

### D1. "Ghost Mode" — the quietest dictation on the market

Every complaint about Wispr's 2025 privacy incident, Superwhisper's cached duplicates, Willow's overzealous rewrites, and Otter's visible bot points at the same underlying frustration: **voice tools are loud, invasive, and untrustworthy**. Flume's stated character is the opposite. Make that a *product line* rather than a vibe:

- Default local-first pipeline, with a visible "cloud used" pill when it isn't.
- No auto-paste for potentially sensitive contexts (password fields, incognito, banking sites) — the exact scenario that produced [Business Insider's Wispr embarrassment story](https://www.businessinsider.com/voice-to-text-wispr-flow-transcription-nearly-ruined-life-review-2026-5).
- Bot-free meeting capture like Granola — but with a **verifiable consent-mode reliability guarantee** unlike Limitless's failed attempt.
- Auditable "what did Flume touch?" activity log — a differentiator no competitor currently ships.

### D2. "Personal Voice Graph" — memory that compounds

Flume already has a personal dictionary, notes, Canvas, and recordings — but they're four silos. Unify them into one **queryable voice graph** (transcripts + notes + snippets + corrections + meeting summaries), with:

- Voice search across the whole graph ("what did I say about the Q3 numbers?") — planned already.
- **Longitudinal commitment tracking** across meetings + Notes, à la [Sembly](https://www.sembly.ai/pricing/) and [Circleback](https://circleback.ai) — but the primary user is *the individual*, not the sales team.
- **A local MCP server** exposing the graph so the user's own coding agents (per the user's compliance/AIOps stack) can query it. This is a niche but *strategically decisive* differentiator against Granola (Business-tier only) and Wispr (no MCP).
- **BYO memory pruning** — user controls retention windows per data type; Flume never fights the user for their data.

### D3. Verbatim / Polished / Rewrite — a real "tone dial"

Every AI-native tool has *one* cleanup style baked in. Users constantly ask for a switch ([market trends report](/home/user/workspace/research/voice_ai_market_trends.md#5-user-complaints-trending-in-reviews)). Ship it as a first-class control:

- **Verbatim** — literal transcription, no cleanup (borrow BetterDictation's stammer-correction as an optional accessibility layer).
- **Polished** — today's Flume behavior.
- **Rewrite** — full context-aware formatting (Wispr parity).
- **Custom prompt** — Superwhisper's power move.

The *dial* is what's missing in the market — everyone forces a choice at install time.

### D4. Voice + Snippets + Macros as one system

Flume's PRD already flags snippets as the "highest priority gap." Go bigger: unify snippets (short trigger → static text), voice macros (short trigger → templated content with variables), and voice commands (short trigger → app action) into **one trigger table** with escalating power. This is functionally what [TextExpander+AI](https://textexpander.com/pricing) is trying to build from the text side and what Wispr's Snippet Library, Voice Macros, and Command Mode are three-separate-things from the voice side. Flume can be the first to ship them as **one primitive** — with the same trigger phrase capable of expanding text, filling a template, or firing an action.

### D5. Confirm-Before-Act agentic model

Flume's own PRD correctly notes that agentic voice needs "safeguards Flume doesn't have yet, like confirmation and undo." **That safeguard *is* the differentiation.** Wispr's Command Mode rewrites in place with no explicit confirmation loop — users get burned. Lemon and VoiceOS execute cross-app actions optimistically. Instead:

- Every agentic voice action produces a **draft preview** (visual card) with **confirm / cancel / edit** — the same UX pattern email clients use for send-with-attachments.
- **Universal Undo** — any action Flume takes creates a reversible history entry with 30-second toast + full activity log.
- **Consent scope per action** — first time Flume "sends an email," it asks explicitly. Users grant scoped, revocable, per-domain consent. Same design language OS permission systems already use.
- This turns Flume from "another agentic tool" into **"the agentic voice tool that won't ruin your life"** — a real, marketable brand promise for the exact enterprise/compliance-heavy buyer the researched competitors keep failing.

---

## 5. Recommended Feature Additions (27 items, prioritized)

**Priority tiers:**
- **P0 — Ship next 60 days** (competitive parity or brand-defining fixes)
- **P1 — Ship 60–180 days** (differentiators)
- **P2 — Ship 180–365 days** (moat / TAM expansion)

### P0 — Competitive parity + brand safety (11 items)

1. **Model transparency page** — publish which STT + LLM Flume uses per platform; add a settings toggle "Show me what's happening" for power users (ties to Superwhisper's moat but goes further with plain-English explanations).
2. **Verbatim / Polished / Rewrite / Custom mode dial** — a first-class output-mode switch, per D3 above. Persist per-app (Slack = Polished; Xcode = Verbatim; Gmail = Rewrite).
3. **Voice-triggered snippets** — mid-sentence trigger phrases expand into text with variables (`{date}`, `{clipboard}`, `{cursor}`). Sync across devices. Already Flume's own #1 flagged gap.
4. **Context-aware formatting v1** — read the active app/URL locally, adjust tone. Ship as an on-by-default enhancement with an explicit off switch.
5. **Mid-dictation self-correction** — LLM layer detects "actually, make that Wednesday" and silently rewrites (Willow's biggest win).
6. **Windows parity sprint** — bring recordings, Notes, Canvas, Auto-Learn, menu-bar mini-dashboard to full parity. Wispr and Willow have crossed this bar.
7. **Android app** — kill the biggest platform gap. Wispr's Android waitlist proved the demand.
8. **First-word capture fix** — the near-universal category bug ([r/windowsapps](https://www.reddit.com/r/windowsapps/comments/1q7k1s8/i_tried_out_15_voice_dictation_apps_so_you_dont/)). Fixing this is a marketing story.
9. **Sensitive-context auto-suppression** — password fields, incognito windows, banking domains, /admin URLs → Flume asks before pasting. Direct remediation of Wispr's Business Insider incident.
10. **Explicit privacy dashboard** — one screen showing (a) what data is stored, (b) where (device vs. cloud), (c) retention, (d) one-click delete + export. GDPR-by-default posture.
11. **SOC 2 Type II attestation + HIPAA BAA option + ISO 27001 roadmap** — start the audit now; it's a 6–9 month process. Publicly commit dates.

### P1 — Differentiators (10 items)

12. **Meeting Transcription (bot-free, local-first)** — capture system audio + mic locally. Multi-speaker diarization via WhisperKit / Parakeet on-device where possible. Structured post-meeting output (topics/decisions/action items) — never a wall of transcript. Consent-mode reliability enforced as a hard test (unlike Limitless).
13. **Voice Macros (unified with snippets)** — templates with variables + optional AI generation step, still triggered mid-sentence. Example: "my meeting followup" → expands into structured template pre-filled from last meeting.
14. **Command Palette (confirm-first agentic)** — press hotkey → say command → see draft card → confirm/edit/cancel. First actions to support: create note, insert clipboard, translate selection, rewrite selection, summarize selection, search my history.
15. **Whisper Mode / silent dictation** — matched-pair feature with Wispr's most-loved late-2025 addition. Direct answer to "voice tools feel awkward around colleagues."
16. **Voice search over the personal voice graph** — the graph itself (D2) plus a semantic index (local Chroma/SQLite-vec) plus a voice interface. Read-only surface, so shippable ahead of full agentic scope.
17. **Personal usage analytics** — words dictated, time saved vs. typing, most-used apps, streaks, dictionary growth. Ship as a friendly weekly digest, not a Salesforce dashboard.
18. **Real-time translation dictation** — leverage ElevenLabs Scribe v2's language coverage or Whisper-large-v3 multilingual. Speak in English, land in Spanish/Hindi/Japanese/etc. Cheap to build on top of existing transcription pipeline.
19. **Personal MCP server** — expose the voice graph to the user's own MCP-aware agents (Claude Code, Cursor, Perplexity Computer, custom agents). This is unique among direct competitors and aligns with the user's own AIOps/agent-orchestration technical stack.
20. **CSV import/export of dictionary + snippets** — matches CarelessWhisper's competitive move; enables migration off Wispr/Dragon (retention play against the incumbents).
21. **Stammer-Correction / Accessibility mode** — BetterDictation's differentiator; costs almost nothing but signals a values-driven product to accessibility-critical users (RSI, dyslexia, stutters). Aqua's founder is dyslexic — this is a live market.

### P2 — Moat & TAM expansion (6 items)

22. **Team tier v1** — shared dictionary + shared snippet library + admin console + SSO/SAML + audit logs + admin-enforced Privacy Mode. Table stakes for enterprise contracts.
23. **Team voice graph (opt-in per user)** — team members can share designated notes, meeting summaries, and commitments across a project workspace. Not "everyone sees everything"; explicit sharing model like Notion pages.
24. **Longitudinal commitment tracking** — parse action items from meetings/notes and surface them in a personal-agent surface ("Sarah asked you for X by Friday"). Sembly / Circleback do this for sales teams; Flume should do it for *individuals*.
25. **Developer SDK / Voice-in-any-app** — following [SpeechOS](https://speechos.ai)'s pattern, expose a small SDK so third-party Mac/Windows apps can offer Flume-powered dictation without duplicating infra. Not a revenue center — a distribution moat.
26. **Voicemail & Call Transcription (mobile)** — the existing Flume PRD item; ship after meeting capture is stable so the pipeline is reused.
27. **Voice-driven text editing on selection** — highlight text, hold hotkey, say instruction, preview the diff, confirm. The safer version of Wispr Command Mode.

---

## 6. What NOT to Build (Anti-Roadmap)

- **Ambient/always-on capture wearables.** Limitless was acquired and shuttered; Rewind was sunset; consent-mode reliability failed publicly. Trust and battery-life cliffs are steeper than software. Stay software-only.
- **Video meeting sentiment scoring (Read.ai-style).** Requires camera access from all participants; violates EU AI Act Article 5(1)(f) on emotion recognition in workplaces ([EU AI Act guide](https://weesperneonflow.ai/en/blog/2026-05-16-eu-ai-act-voice-dictation-compliance-guide-europe-2026/)); high consent friction; not on-brand for a "quiet" product.
- **Visible bot join for meeting capture.** Granola proved bot-free is the more elegant answer. Bots create consent theatre without improving quality.
- **Credit-metered AI features** (Fireflies pattern) layered on top of subscriptions. Universally hated in reviews. Price the tier, not the individual AI action.
- **Training AI models on customer data** as a default. Notta's stance is a live complaint driving churn to Granola ([tl;dv Notta review](https://tldv.io/blog/notta-ai-review/)). Contractual no-training guarantee, on by default.
- **Feature-heavy Command Mode without confirmation UX.** The reason Wispr's Business Insider incident happened. Ship confirm-first, always.

---

## 7. Pricing Recommendation

Based on category benchmarks ([pricing benchmarks](/home/user/workspace/research/voice_ai_market_trends.md#2-pricing-benchmarks)) and Flume's differentiation:

| Tier | Price | Included |
|---|---|---|
| **Free** | $0 | 3,000 words/week on Mac/Win, 1,500/week iOS/Android. Verbatim mode + Polished mode. Local Mac dictation unlimited (**stronger free tier than Wispr's 2,000/week** — Flume's local Mac inference cost is near-zero, so this is a defensible moat). Personal dictionary (50 entries). Snippets (10). Canvas + Notes with 30-day history. |
| **Pro (individual)** | $10/mo billed annually · $13/mo monthly | Unlimited words, all modes including Rewrite + Custom, unlimited dictionary/snippets, meeting transcription (up to 20 hours/month), voice search over graph, translation, agentic Command Palette, cross-device unlimited history. **Undercuts Wispr ($12) and Willow ($12) on annual, matches Aqua ($8) on value.** |
| **Teams** | $15/user/mo (min 3 seats) | Everything in Pro + shared dictionary/snippets, admin console, SSO/SAML, audit log, admin-enforced Privacy Mode, per-workspace voice graph. |
| **Enterprise** | Custom | SOC 2 Type II, HIPAA BAA, ISO 27001, SCIM, on-device model deployment option, dedicated success. |
| **Student / Nonprofit / Accessibility** | 50% off Pro | Match competitor discounts; the accessibility discount specifically is an on-brand differentiator. |

**Rationale for pricing:**
- $10/mo Pro (annual) is $2/mo below Wispr and Willow, matching Aqua — the "quiet, private, doesn't burn you" positioning justifies matching, not premium, pricing.
- Larger free tier is defensible because ~70% of Flume's inference cost can be on-device (Mac + Windows-on-ARM), unlike Wispr which pays cloud STT per word.
- No credit-metered AI features. Universal category complaint.

---

## 8. Compliance & Trust Posture (Concrete Commitments)

The PRD should commit to these publicly on day one of the v2 launch:

- **No training on customer data, ever.** Contractual, not just marketing. Same posture Granola made table stakes.
- **Zero data retention mode**, on by default for Free tier, enforceable at admin level for Teams+.
- **Sub-processor list** published and updated within 30 days of any change.
- **SOC 2 Type II audit begun** with target completion within 9 months of PRD v2 launch. Milestones published quarterly.
- **HIPAA BAA available** on Enterprise tier at v2 GA + 90 days.
- **ISO 27001 target** at v2 GA + 12 months.
- **GDPR "by default":** local-first inference where available; explicit data-subject rights portal (export, delete, correct) exposed in-app.
- **EU AI Act Article 50 compliance:** any synthetic content produced by Flume marked as such in metadata; users see when AI has cleaned/rewritten their text.
- **No emotion recognition, ever.** Article 5(1)(f) compliance by design.
- **Auditable activity log** exposed in-app: every action Flume has taken on the user's behalf, forever undoable.

---

## 9. Distribution & Growth (Not in PRD, but noted for context)

Even the best PRD won't matter if Flume can't get out from under Wispr's shadow. The category's distribution playbook is remarkably consistent ([market trends report §9](/home/user/workspace/research/voice_ai_market_trends.md#9-distribution-channels-that-work)):

- **Habit-formation is the growth engine.** Every P0 feature above (verbatim toggle, snippets, first-word fix) increases daily use, which is what drives referrals.
- **A single high-profile endorsement** is worth more than paid marketing. Wispr = Hoffman, Willow = Ohanian, Superwhisper = Karpathy. Flume needs one credible name.
- **Product Hunt + LinkedIn launch** for v2 GA, with a coordinated founder-story angle around "the quiet voice tool built by ex-[X]."
- **Aggressive regional pricing** (India, LATAM, SEA) — Wispr's India move proved this doubles addressable users. Bake this in from day one.
- **Accessibility positioning** as an owned narrative — no direct competitor (except Talon, which is not consumer) owns it. RSI/dyslexia/stutter users are underserved and vocal.
- **Migration tools** — CSV import from Wispr, TextExpander, Dragon dictionaries. Reduce switching cost.

---

## 10. Summary of Recommendations

1. **Positioning:** "The quiet voice tool" — bot-free, local-first, verifiable, undoable, values-driven. Own the trust axis explicitly.
2. **P0 (60 days):** Verbatim/Polished/Rewrite dial, snippets, context-aware formatting, mid-dictation correction, Windows/Android parity, model transparency, sensitive-context suppression, first-word fix, privacy dashboard, SOC 2 audit start.
3. **P1 (60–180 days):** Bot-free meeting transcription, voice macros, confirm-first Command Palette, Whisper Mode, voice search, personal analytics, translation, personal MCP server, CSV import, accessibility mode.
4. **P2 (180–365 days):** Teams tier, team voice graph, longitudinal commitments, developer SDK, voicemail transcription, voice text editing.
5. **Pricing:** $10/mo Pro annual, $15/user Teams. Beefier free tier than Wispr.
6. **Compliance:** No training on user data (contractual), SOC 2 Type II + HIPAA BAA + ISO 27001 within 12 months.
7. **Anti-roadmap:** No wearables, no visible bots, no video sentiment, no credit-meters, no data training, no confirmation-less agentic actions.

The updated PRD document (`Flume_PRD_v2.md`) translates this analysis into a coding-agent-ready build spec.
