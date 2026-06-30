# Verbal Project Context Agent Instructions

**Purpose:** Guide AI assistants in using the Verbal project context for debugging and feature development

---

## 🎯 When to Use This Context

Use this project context system when the user asks about:

### Debugging Scenarios
- "Why is my recording not working?"
- "Transcription is failing"
- "Sync isn't working between devices"
- "The app crashes on startup"
- "Hotkey not detected"
- "Text doesn't paste after transcription"
- "Build is failing"
- Any error or bug in Verbal

### Feature Development
- "Add translation support"
- "Create a new screen for analytics"
- "How do I add a new API integration?"
- "I want to extend the sync functionality"
- "Add custom sound effects"
- Any request to add or modify features

### Code Understanding
- "How does the transcription work?"
- "Explain the sync architecture"
- "What files handle audio recording?"
- "Where is the configuration stored?"
- "Show me the data flow"

---

## 📚 Available Documentation

The project context is located in `.project-context/` with these files:

| File | Purpose | Use When |
|------|---------|----------|
| **INDEX.md** | Complete project navigation | Finding files, architecture overview |
| **SKILL.md** | Structured workflows | Following debugging/development process |
| **API_REFERENCE.md** | API documentation | Looking up function signatures |
| **DEBUGGING_GUIDE.md** | Debugging approaches | Troubleshooting specific issues |
| **FEATURE_DEVELOPMENT.md** | Implementation patterns | Adding new features |
| **QUICK_REFERENCE.md** | Cheat sheet | Quick lookups |
| **README.md** | System overview | Understanding how to use the context |

---

## 🔍 How to Use the Context

### Step 1: Identify the Domain

Based on the user's request, determine which domain they're asking about:

| Request Type | Domain | Primary File |
|--------------|--------|--------------|
| Recording issues | Audio | `app/recorder.py`, `app/hotkey.py` |
| Transcription errors | AI/ML | `app/transcriber.py`, `app/ai_cleanup.py` |
| Sync problems | Backend | `app/sync.py`, Supabase |
| UI/UX bugs | Frontend | `app/dashboard.py`, `screens/` |
| Build failures | DevOps | `*.spec`, `build.sh` |
| Mobile issues | Mobile | `verbal-mobile/`, `App.tsx` |
| Configuration | Config | `app/config.py` |

---

### Step 2: Retrieve Relevant Context

Use the appropriate file based on the task:

#### For Debugging:
1. Open `SKILL.md` → "Debugging Workflow" section
2. Follow the structured approach
3. Reference `DEBUGGING_GUIDE.md` for specific issues
4. Use `INDEX.md` to locate relevant files

#### For Feature Development:
1. Open `SKILL.md` → "Feature Development" section
2. Choose the appropriate template from `FEATURE_DEVELOPMENT.md`
3. Follow the implementation steps
4. Reference `API_REFERENCE.md` for existing patterns

#### For Code Understanding:
1. Open `INDEX.md` → "Architecture Overview"
2. Navigate to "Component Map" or "Key Files Reference"
3. Use `API_REFERENCE.md` for detailed API docs

---

### Step 3: Apply the Knowledge

#### Example 1: Debugging Recording Issue

**User:** "My recording stops after 2 seconds on the second attempt"

**Steps:**
1. **Identify domain:** Recording/Audio → `app/recorder.py`, `app/hotkey.py`
2. **Check INDEX.md:** "Common Debugging Scenarios" → "1. Recording Cuts Short"
3. **Use DEBUGGING_GUIDE.md:** Follow Section 1 debugging steps
4. **Apply solution:**
   - Add timestamp logging to hotkey handler
   - Add minimum duration check
   - Consider switching to hold mode

**Response:**
```markdown
This is a known issue with toggle mode (documented in INDEX.md).

**Root Cause:** NSEvent fires multiple events, causing premature stop.

**Solution:**
1. Add logging to `app/hotkey.py`:
   ```python
   logger.info(f"[{time.time():.6f}] Key event: keycode={keycode}")
   ```

2. Add minimum duration in `app/main.py`:
   ```python
   if duration < 2.0:
       logger.warning("Recording stopped too early")
       return
   ```

3. Or switch to hold mode in settings.

See DEBUGGING_GUIDE.md Section 1 for complete details.
```

---

#### Example 2: Adding Translation Feature

**User:** "I want to add DeepL translation support"

**Steps:**
1. **Identify domain:** Feature Development → API Integration
2. **Check FEATURE_DEVELOPMENT.md:** Template 1 - New API Integration
3. **Follow template:**
   - Create `app/deepl_translator.py`
   - Update `app/config.py`
   - Integrate into `app/main.py`
   - Add UI in `app/dashboard.py`

**Response:**
```markdown
I'll help you add DeepL translation following the pattern in FEATURE_DEVELOPMENT.md.

**Step 1: Create the translator module**
```python
# app/deepl_translator.py
class DeepLTranslator:
    def __init__(self, api_key):
        self.api_key = api_key
    
    def translate(self, text, target_lang):
        # Implementation from Template 1
        pass
```

**Step 2: Add configuration**
```python
# app/config.py DEFAULT_CONFIG
"deepl_api_key": "",
"translation_target_lang": "EN-US",
```

**Step 3: Integrate...**
```

---

#### Example 3: Understanding Sync

**User:** "How does cross-device sync work?"

**Steps:**
1. **Identify domain:** Architecture/Understanding
2. **Check INDEX.md:** "APIs & Integrations" → "Supabase"
3. **Reference API_REFERENCE.md:** `SyncClient` class
4. **Explain data flow:**

**Response:**
```markdown
Verbal uses Supabase Realtime for cross-device sync:

**Architecture:**
```
Device A → Supabase → Device B
         (Realtime)
```

**Data Flow:**
1. Transcription completes on Device A
2. `SyncClient.push()` sends to Supabase
3. Supabase Realtime broadcasts to Device B
4. Device B receives and pastes to clipboard

**Key Files:**
- `app/sync.py` - SyncClient implementation
- Database: `transcriptions` table
- WebSocket: Realtime subscription

See INDEX.md "APIs & Integrations" and API_REFERENCE.md "SyncClient" for details.
```

---

## 🛠️ Tool Usage

When working with the context, use these tools:

### read_file
- Read specific sections of context files
- Get detailed information about components

### grep_search
- Search for specific patterns across context files
- Find relevant sections quickly

### semantic_search
- Search for concepts across the entire context
- Find related information

---

## 📋 Response Guidelines

### When Debugging
1. **Identify the issue** - What component is failing?
2. **Reference the docs** - Point to specific sections
3. **Provide steps** - Follow DEBUGGING_GUIDE.md
4. **Include code** - Show exact logging/fixes needed
5. **Test** - Verify the fix works

### When Developing
1. **Choose template** - From FEATURE_DEVELOPMENT.md
2. **Show implementation** - Step-by-step code
3. **Integration points** - Where to modify existing code
4. **Testing** - How to verify it works
5. **References** - Point to relevant docs

### When Explaining
1. **Start high-level** - Architecture overview
2. **Trace data flow** - Component to component
3. **Show code** - Actual implementation
4. **Reference docs** - Where to learn more

---

## 🎯 Best Practices

### Do's
- ✅ Always reference the specific documentation file
- ✅ Follow the structured workflows in SKILL.md
- ✅ Provide code examples from templates
- ✅ Point to INDEX.md for navigation
- ✅ Use QUICK_REFERENCE.md for quick answers
- ✅ Keep responses focused and actionable

### Don'ts
- ❌ Don't guess - use the documentation
- ❌ Don't skip steps in workflows
- ❌ Don't provide outdated information
- ❌ Don't ignore cross-platform considerations
- ❌ Don't forget to mention testing

---

## 🔄 Keeping Current

### When to Update Context
- New features added to codebase
- Architecture changes
- New debugging patterns discovered
- API integrations modified
- Configuration options changed

### How to Update
1. Edit the relevant markdown file
2. Add new sections as needed
3. Update cross-references
4. Keep examples current
5. Document lessons learned

---

## 📞 Quick Reference

### Common File Locations
- Desktop code: `whisperflow/app/`
- Mobile code: `verbal-mobile/`
- Config: `~/.verbal/config.json`
- Logs: `~/.verbal/logs/app.log`

### Common Commands
- Run desktop: `python3 -m app.main`
- Run mobile: `npx expo start`
- View logs: `tail -f ~/.verbal/logs/app.log`
- Build macOS: `./build.sh`
- Build Windows: `./build-win.sh`

### Common APIs
- Groq: `whisper-large-v3-turbo` (transcription)
- Gemini: `gemini-2.0-flash` (formatting)
- Supabase: Realtime sync backend

---

## ✅ Checklist for AI Assistants

Before responding to a Verbal-related request:

- [ ] Identify the domain (debugging, feature dev, understanding)
- [ ] Select the appropriate context file
- [ ] Follow the structured workflow
- [ ] Reference specific sections in response
- [ ] Provide actionable code/examples
- [ ] Point to documentation for more details
- [ ] Consider cross-platform impact
- [ ] Mention testing requirements

---

**End of Agent Instructions**
