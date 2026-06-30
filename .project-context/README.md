# Verbal Project Context

**Purpose:** Comprehensive documentation and reference materials for debugging and feature development in the Verbal project.

---

## 📚 Documentation Index

This folder contains structured documentation to help you work efficiently with the Verbal codebase.

### Core Documents

| Document | Purpose | When to Use |
|----------|---------|-------------|
| [INDEX.md](./INDEX.md) | **Start here** - Complete project overview | Understanding architecture, finding files, quick reference |
| [SKILL.md](./SKILL.md) | **Use this skill** - How to use the context effectively | When debugging or developing features, follow this workflow |
| [RULES.md](./RULES.md) | **Mandatory rules** - When to use/update context | AI assistants, developers making changes |
| [UPDATE_GUIDE.md](./UPDATE_GUIDE.md) | **Keep current** - How to update context | After making code changes, feature additions |
| [API_REFERENCE.md](./API_REFERENCE.md) | Complete API documentation | Looking up function signatures, parameters, return values |
| [DEBUGGING_GUIDE.md](./DEBUGGING_GUIDE.md) | Systematic debugging approaches | Troubleshooting bugs, errors, or unexpected behavior |
| [FEATURE_DEVELOPMENT.md](./FEATURE_DEVELOPMENT.md) | Feature implementation patterns | Adding new features, following best practices |

---

## 🎯 How to Use This Context

### For Debugging

1. **Start with [INDEX.md](./INDEX.md)**
   - Locate the component related to your issue
   - Check "Common Debugging Scenarios" section

2. **Use [DEBUGGING_GUIDE.md](./DEBUGGING_GUIDE.md)**
   - Follow the systematic approach for your issue type
   - Use the debugging checklist
   - Add targeted logging as suggested

3. **Reference [API_REFERENCE.md](./API_REFERENCE.md)**
   - Look up function signatures
   - Understand data flow between components

### For Feature Development

1. **Start with [INDEX.md](./INDEX.md)**
   - Identify affected components
   - Review existing patterns

2. **Use [FEATURE_DEVELOPMENT.md](./FEATURE_DEVELOPMENT.md)**
   - Follow the appropriate template
   - Implement using established patterns
   - Test according to guidelines

3. **Reference [SKILL.md](./SKILL.md)**
   - Ensure you're using the context effectively
   - Follow the debugging/development workflow

---

## 🗂️ File Structure

```
.project-context/
├── README.md                    # This file - overview and usage guide
├── INDEX.md                     # Project index and navigation
├── SKILL.md                     # How to use this context effectively
├── API_REFERENCE.md             # Complete API documentation
├── DEBUGGING_GUIDE.md           # Systematic debugging approaches
├── FEATURE_DEVELOPMENT.md       # Feature implementation patterns
└── (future additions)           # Architecture diagrams, decision logs, etc.
```

---

## 🔍 Quick Reference

### Component Locations

| Component | Desktop File | Mobile File |
|-----------|-------------|-------------|
| Recording | `app/recorder.py` | `lib/audio.ts` |
| Transcription | `app/transcriber.py` | `lib/groq.ts` |
| AI Processing | `app/ai_cleanup.py` | N/A |
| Sync | `app/sync.py` | `lib/supabase.ts` |
| UI (Desktop) | `app/dashboard.py` | N/A |
| UI (Mobile) | N/A | `screens/*.tsx` |
| Configuration | `app/config.py` | `app.json` |

### Log Locations

- **Desktop:** `~/.verbal/logs/app.log`
- **Mobile:** Check via `npx expo start --clear`
- **Supabase:** Dashboard → Logs → Realtime

### Configuration

- **Desktop:** `~/.verbal/config.json`
- **Environment:** `.env` in project root
- **Mobile:** `verbal-mobile/app.json`

### Build Commands

```bash
# Desktop (macOS)
cd whisperflow && ./build.sh

# Desktop (Windows)
cd whisperflow && ./build-win.sh

# Mobile
cd verbal-mobile && npx expo start
```

---

## 🛠️ Using the Skill

The [SKILL.md](./SKILL.md) file provides structured guidance for:

### Debugging Scenarios
- Recording/audio issues
- Transcription errors
- Sync problems
- UI/UX bugs
- Build failures
- Mobile-specific issues

### Feature Development
- Adding API integrations
- Creating mobile screens
- Extending configuration
- Implementing sync features

### Code Understanding
- Architecture overview
- Data flow tracing
- Cross-platform differences
- Pattern recognition

---

## 📖 Example Workflows

### Workflow 1: Fix Transcription Bug

**Problem:** "Transcription fails on second attempt"

**Steps:**
1. Open [INDEX.md](./INDEX.md) → "Common Debugging Scenarios" → "Transcription Fails"
2. Follow steps in [DEBUGGING_GUIDE.md](./DEBUGGING_GUIDE.md) → Section 2
3. Add logging to `app/transcriber.py` as suggested
4. Check logs: `tail -f ~/.verbal/logs/app.log`
5. Identify root cause (e.g., API rate limit, audio issue)
6. Implement fix following patterns in [FEATURE_DEVELOPMENT.md](./FEATURE_DEVELOPMENT.md)

### Workflow 2: Add New Feature

**Problem:** "Add translation support to Verbal"

**Steps:**
1. Open [INDEX.md](./INDEX.md) → "Feature Development Guide"
2. Review [FEATURE_DEVELOPMENT.md](./FEATURE_DEVELOPMENT.md) → Template 1: API Integration
3. Create new module: `app/deepl_translator.py`
4. Update config in `app/config.py`
5. Integrate into `app/main.py`
6. Add UI in `app/dashboard.py`
7. Test following guidelines in [FEATURE_DEVELOPMENT.md](./FEATURE_DEVELOPMENT.md)

### Workflow 3: Understand Sync Architecture

**Problem:** "How does cross-device sync work?"

**Steps:**
1. Open [INDEX.md](./INDEX.md) → "APIs & Integrations" → "Supabase"
2. Review database schema and API endpoints
3. Check [API_REFERENCE.md](./API_REFERENCE.md) → `SyncClient` class
4. Trace data flow: `app/sync.py` → Supabase → Mobile
5. Review [CROSSPLATFORM_SYNC_PLAN.md](../whisperflow/CROSSPLATFORM_SYNC_PLAN.md) for design decisions

---

## 🎓 Best Practices

### When Debugging
- Always start with logs
- Use the debugging checklist
- Add targeted logging, not random prints
- Test hypotheses systematically
- Document findings for future reference

### When Developing
- Follow existing code patterns
- Add comprehensive logging
- Write tests before deploying
- Update documentation
- Consider cross-platform impact

### When Learning
- Start with the INDEX.md overview
- Trace data flow through components
- Read the actual code (not just docs)
- Experiment in a safe environment
- Ask questions when stuck

---

## 🔄 Keeping Context Updated

This context should evolve with the project:

### When to Update
- New features added
- Architecture changes
- New debugging patterns discovered
- API integrations changed
- Configuration options modified

### How to Update
1. Edit the relevant markdown file
2. Add new sections as needed
3. Update cross-references
4. Keep examples current
5. Document lessons learned

---

## 📞 Quick Help

### I need to...

**...find a file:** → [INDEX.md](./INDEX.md) → "Component Map" or "Key Files Reference"

**...understand how something works:** → [INDEX.md](./INDEX.md) → "Architecture Overview" or [API_REFERENCE.md](./API_REFERENCE.md)

**...fix a bug:** → [DEBUGGING_GUIDE.md](./DEBUGGING_GUIDE.md) → Find your issue type

**...add a feature:** → [FEATURE_DEVELOPMENT.md](./FEATURE_DEVELOPMENT.md) → Choose a template

**...understand the skill:** → [SKILL.md](./SKILL.md) → Follow the workflow

---

## 📝 Contributing

When adding new documentation:

1. **Follow the existing format** - Markdown with clear headings
2. **Include examples** - Code snippets, commands, logs
3. **Cross-reference** - Link to related documents
4. **Keep it current** - Update when code changes
5. **Be specific** - Concrete examples over abstract advice

---

## 🔗 Related Documentation

Outside this folder:

- [README.md](../README.md) - Product overview
- [PICO_TECHNICAL_DOCS.md](../whisperflow/PICO_TECHNICAL_DOCS.md) - macOS technical details
- [CROSSPLATFORM_SYNC_PLAN.md](../whisperflow/CROSSPLATFORM_SYNC_PLAN.md) - Sync architecture
- [TRANSCRIPTION_FORMATTING_RULES.md](../whisperflow/TRANSCRIPTION_FORMATTING_RULES.md) - AI formatting rules
- [RELEASE_NOTES_v*.md](../whisperflow/) - Version history

---

**Last Updated:** 2026-06-30  
**Maintained By:** Development Team  
**Contact:** See project README for contact information
