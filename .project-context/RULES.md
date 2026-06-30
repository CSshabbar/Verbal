# Verbal Project Context Rules

**Purpose:** Define when and how to use the project context system, and ensure it stays current with codebase changes

**Version:** 1.0  
**Last Updated:** 2026-06-30

---

## 🎯 Rule 1: Always Use Context for Specific Scenarios

### Mandatory Context Usage

**You MUST use the project context system when:**

#### Debugging Tasks
- User reports a bug or error in Verbal
- Logs show issues in transcription, recording, or sync
- Build fails with PyInstaller or Expo errors
- Hotkey detection not working
- Text injection fails
- Sync between devices broken
- API calls failing (Groq, Gemini, Supabase)

#### Feature Development Tasks
- User wants to add new features to desktop or mobile apps
- Need to understand existing patterns for implementation
- Adding new API integrations
- Extending sync functionality
- Creating new UI components
- Modifying configuration options

#### Code Understanding Tasks
- User asks how a specific component works
- Need to trace data flow through the system
- Understanding cross-platform differences
- Learning the architecture before making changes

#### Code Modification Tasks
- Editing existing files in `whisperflow/app/`
- Editing existing files in `verbal-mobile/`
- Changing configuration schema
- Modifying build scripts or `.spec` files

---

## 📚 Rule 2: Use the Right Document for the Task

### Document Selection Matrix

| Task Type | Primary Document | Secondary Document | Reference |
|-----------|-----------------|-------------------|-----------|
| **Debugging - Recording** | DEBUGGING_GUIDE.md §1 | INDEX.md → Recorder | API_REFERENCE.md → Recorder |
| **Debugging - Transcription** | DEBUGGING_GUIDE.md §2 | INDEX.md → Transcriber | API_REFERENCE.md → transcriber.py |
| **Debugging - Sync** | DEBUGGING_GUIDE.md §4 | INDEX.md → Supabase | API_REFERENCE.md → SyncClient |
| **Debugging - Build** | DEBUGGING_GUIDE.md §5 | INDEX.md → Build | *.spec files |
| **Feature - API Integration** | FEATURE_DEVELOPMENT.md → Template 1 | INDEX.md → APIs | API_REFERENCE.md → External APIs |
| **Feature - Mobile Screen** | FEATURE_DEVELOPMENT.md → Template 2 | INDEX.md → Mobile | App.tsx |
| **Feature - Config Option** | FEATURE_DEVELOPMENT.md → Template 3 | INDEX.md → Config | app/config.py |
| **Feature - Sync Extension** | FEATURE_DEVELOPMENT.md → Template 4 | INDEX.md → Supabase | app/sync.py |
| **Understanding - Architecture** | INDEX.md → Architecture Overview | README.md | PICO_TECHNICAL_DOCS.md |
| **Understanding - Component** | INDEX.md → Component Map | API_REFERENCE.md | Source file |
| **Quick Lookup** | QUICK_REFERENCE.md | INDEX.md | Source file |

---

## 🔄 Rule 3: Context Update Triggers

### When to Update the Context

You MUST update the project context when ANY of these changes occur:

#### Code Changes
- ✅ New file created in `whisperflow/app/` or `verbal-mobile/`
- ✅ New function or class added to existing module
- ✅ Configuration options added/modified in `app/config.py`
- ✅ API integration added or changed
- ✅ Database schema modified
- ✅ Build process changed (`.spec` files, build scripts)

#### Feature Additions
- ✅ New feature implemented
- ✅ New screen added to mobile app
- ✅ New menu item or UI component in desktop
- ✅ New setting or preference added

#### Bug Fixes
- ✅ New debugging pattern discovered
- ✅ Solution found for previously undocumented issue
- ✅ Workaround implemented for known bug

#### Architecture Changes
- ✅ New external service integrated
- ✅ Data flow changed
- ✅ Component refactored or moved
- ✅ New dependency added

#### Documentation Gaps
- ✅ User asks question not answered in context
- ✅ AI assistant cannot find needed information
- ✅ Code pattern not documented

---

## 📝 Rule 4: How to Update the Context

### Update Workflow

When a change is made, follow this workflow:

#### Step 1: Identify What Changed
```
Change Type: [New Feature | Bug Fix | Refactoring | Configuration | API | Other]
Affected Files: [List all modified files]
Impact: [Desktop | Mobile | Both | Build | Config]
```

#### Step 2: Determine Which Documents to Update

| Change Type | Update These Documents |
|-------------|----------------------|
| New file created | INDEX.md (Component Map), API_REFERENCE.md |
| New function/class | API_REFERENCE.md, INDEX.md (Key Files) |
| New config option | INDEX.md (Configuration), API_REFERENCE.md (config.py) |
| New API integration | INDEX.md (APIs), API_REFERENCE.md (External APIs), FEATURE_DEVELOPMENT.md (add example) |
| Database schema change | INDEX.md (Database Schema), API_REFERENCE.md (Database) |
| Build process change | INDEX.md (Build & Deployment), DEBUGGING_GUIDE.md (Build section) |
| New debugging pattern | DEBUGGING_GUIDE.md (add new section or update existing) |
| Bug fix solution | DEBUGGING_GUIDE.md (update relevant section) |
| New feature | INDEX.md (all relevant sections), FEATURE_DEVELOPMENT.md (add template if pattern is reusable) |

#### Step 3: Make the Updates

**For INDEX.md:**
- Add to appropriate section (Component Map, Key Files, Configuration, etc.)
- Update cross-references
- Keep formatting consistent

**For API_REFERENCE.md:**
- Add function signature with parameters and return type
- Include docstring content
- Add usage example
- Note any exceptions or error conditions

**For DEBUGGING_GUIDE.md:**
- Document the symptom
- Explain root cause
- Provide step-by-step debug steps
- Include code examples for logging
- List common causes and solutions

**For FEATURE_DEVELOPMENT.md:**
- Create new template if pattern is reusable
- Include complete code examples
- Show integration points
- Add testing guidelines

**For QUICK_REFERENCE.md:**
- Add to relevant quick lookup table
- Keep it concise (one-liner if possible)
- Update commands or file locations if changed

#### Step 4: Verify Updates
- [ ] Information is accurate
- [ ] Cross-references are correct
- [ ] Code examples are valid
- [ ] Formatting is consistent
- [ ] No sensitive data included (API keys, etc.)

---

## 🛠️ Rule 5: Context Usage Workflow

### Before Starting Any Task

1. **Check if context exists**
   ```
   Is this a debugging task? → Use DEBUGGING_GUIDE.md
   Is this a feature task? → Use FEATURE_DEVELOPMENT.md
   Is this a lookup task? → Use INDEX.md or QUICK_REFERENCE.md
   ```

2. **Read the relevant section**
   - Follow the workflow in SKILL.md
   - Use the document selection matrix (Rule 2)

3. **Apply the knowledge**
   - Use code examples from context
   - Follow documented patterns
   - Reference specific sections in responses

### During Implementation

4. **Monitor for changes**
   - Are you creating new files? → Update INDEX.md
   - Are you adding new functions? → Update API_REFERENCE.md
   - Are you discovering new patterns? → Update appropriate doc

5. **Document as you go**
   - Don't wait until the end
   - Update context immediately after making changes
   - Add comments in code pointing to context docs

### After Completion

6. **Review and update**
   - Did you solve a new type of problem? → Add to DEBUGGING_GUIDE.md
   - Did you create a reusable pattern? → Add to FEATURE_DEVELOPMENT.md
   - Did you learn something new? → Add to appropriate section

7. **Verify completeness**
   - Can someone else solve this problem using the context?
   - Are all affected files documented?
   - Are cross-references up to date?

---

## 📋 Rule 6: Context Quality Standards

### Content Requirements

All context updates MUST:

- ✅ **Be accurate** - Match the actual code implementation
- ✅ **Be specific** - Include exact file paths, function names, line numbers if relevant
- ✅ **Be complete** - Cover all parameters, return values, error conditions
- ✅ **Be current** - Reflect the latest codebase state
- ✅ **Be clear** - Use consistent formatting and terminology
- ✅ **Be actionable** - Provide steps that can be followed immediately
- ✅ **Include examples** - Code snippets, commands, log outputs
- ✅ **Cross-reference** - Link to related sections in other documents

### Formatting Standards

- Use Markdown consistently
- Follow existing heading hierarchy
- Use code blocks with language specification
- Include tables for structured data
- Add cross-references with relative links

### Prohibited Content

- ❌ API keys or secrets (even in examples)
- ❌ User-specific data (usernames, emails, etc.)
- ❌ Outdated information (mark as deprecated if keeping for reference)
- ❌ Unverified assumptions (label as "TODO: Verify")

---

## 🎓 Rule 7: AI Assistant Guidelines

### When AI Should Use Context

AI assistants MUST use the project context when:

1. **User mentions Verbal-specific components**
   - "How does the transcriber work?" → Use API_REFERENCE.md
   - "Where is the sync logic?" → Use INDEX.md → Sync section

2. **User asks for debugging help**
   - "Recording isn't working" → Use DEBUGGING_GUIDE.md → Section 1
   - "Sync is broken" → Use DEBUGGING_GUIDE.md → Section 4

3. **User wants to add features**
   - "Add translation" → Use FEATURE_DEVELOPMENT.md → Template 1
   - "New mobile screen" → Use FEATURE_DEVELOPMENT.md → Template 2

4. **User asks architectural questions**
   - "How does data flow?" → Use INDEX.md → Architecture
   - "What files handle X?" → Use INDEX.md → Component Map

### How AI Should Reference Context

When providing answers, AI MUST:

1. **Cite the source**
   ```markdown
   According to INDEX.md → Component Map, the recorder is in `app/recorder.py`.
   ```

2. **Quote relevant sections**
   ```markdown
   As documented in DEBUGGING_GUIDE.md Section 2:
   > "Check API key validity first, then verify network connectivity"
   ```

3. **Follow documented workflows**
   ```markdown
   Following the workflow in SKILL.md → Debugging:
   Step 1: Check logs with `tail -f ~/.verbal/logs/app.log`
   Step 2: Isolate the component...
   ```

4. **Point to documentation for more details**
   ```markdown
   For complete implementation details, see FEATURE_DEVELOPMENT.md → Template 1.
   ```

---

## 🔄 Rule 8: Context Maintenance Schedule

### Regular Reviews

#### Weekly Checks
- [ ] Review recent code changes
- [ ] Update context for any new files/functions
- [ ] Add new debugging patterns discovered during the week
- [ ] Verify cross-references are still valid

#### Monthly Reviews
- [ ] Complete review of all context documents
- [ ] Remove outdated information
- [ ] Add missing sections or examples
- [ ] Test that documented workflows still work
- [ ] Update version numbers and dates

#### After Major Releases
- [ ] Comprehensive context audit
- [ ] Document all new features
- [ ] Update architecture diagrams
- [ ] Review and update all templates
- [ ] Verify all quick reference information

---

## 📊 Rule 9: Context Metrics

### Track These Metrics

- **Coverage:** % of codebase documented
  - Target: 100% of public APIs
  - Target: 100% of configuration options
  - Target: 100% of debugging scenarios encountered

- **Accuracy:** % of documentation matching code
  - Target: 100% (no outdated info)

- **Usage:** How often context is referenced
  - Track: AI assistant context usage
  - Track: Developer context usage

- **Freshness:** Time between code change and doc update
  - Target: < 24 hours for critical changes
  - Target: < 1 week for minor changes

### Quality Checks

Before considering context "complete":

- [ ] Can a new developer debug common issues using only the docs?
- [ ] Can a developer add a new feature using only the templates?
- [ ] Are all files in `whisperflow/app/` documented?
- [ ] Are all files in `verbal-mobile/` documented?
- [ ] Are all configuration options documented?
- [ ] Are all external APIs documented?
- [ ] Are all debugging scenarios documented?

---

## 🚨 Rule 10: Enforcement

### Automatic Checks

When making changes, verify:

1. **File creation** → Did you update INDEX.md?
2. **Function addition** → Did you update API_REFERENCE.md?
3. **Config change** → Did you update INDEX.md and API_REFERENCE.md?
4. **Bug fix** → Did you update DEBUGGING_GUIDE.md?
5. **New pattern** → Did you update FEATURE_DEVELOPMENT.md?

### Review Checklist

Before committing code changes:

- [ ] Context updated for all new files
- [ ] Context updated for all new functions
- [ ] Context updated for all config changes
- [ ] Debugging patterns documented
- [ ] Feature templates updated (if applicable)
- [ ] Cross-references verified
- [ ] No sensitive data in docs
- [ ] Version/date updated in relevant docs

---

## 📝 Rule 11: Context Update Templates

### Template: New File Documentation

```markdown
### `app/new_module.py` - Module Purpose

#### Class: `NewClass`

##### `__init__(param1: type, param2: type)`
Initialize the new class.

**Parameters:**
- `param1` - Description
- `param2` - Description

**Example:**
```python
obj = NewClass(param1="value", param2=42)
```

##### `method_name(arg: type) -> return_type`
Method description.

**Parameters:**
- `arg` - Description

**Returns:**
- `return_type` - Description
```

### Template: New Debugging Scenario

```markdown
### N. Issue Name

**Symptoms:**
- What users see/experience
- Error messages (if any)

**Root Cause:**
- Technical explanation of why this happens

**Debug Steps:**
1. First step with command/code
2. Second step with command/code
3. Continue...

**Solution:**
- How to fix permanently
- Workarounds if applicable

**Related:**
- Link to other relevant sections
```

### Template: New Feature Template

```markdown
### Template N: Feature Type

**Example:** Adding X to Verbal

#### Step 1: Create Module
```python
# app/new_feature.py
class NewFeature:
    # Implementation
    pass
```

#### Step 2: Update Config
```python
# app/config.py
DEFAULT_CONFIG = {
    # ...
    "new_feature_option": default_value,
}
```

#### Step 3: Integrate
```python
# app/main.py
from app.new_feature import NewFeature
# Integration code
```

#### Step 4: Add UI
```python
# app/dashboard.py
# UI code
```
```

---

## ✅ Rule 12: Quick Decision Tree

### "Should I use the context?"

```
Is it Verbal-related?
├─ Yes → Is it debugging?
│         ├─ Yes → Use DEBUGGING_GUIDE.md
│         └─ No → Is it feature development?
│                  ├─ Yes → Use FEATURE_DEVELOPMENT.md
│                  └─ No → Is it code understanding?
│                           ├─ Yes → Use INDEX.md + API_REFERENCE.md
│                           └─ No → Use QUICK_REFERENCE.md
└─ No → Context not needed
```

### "Should I update the context?"

```
Did you make changes to the codebase?
├─ Yes → Did you create new files?
│         ├─ Yes → Update INDEX.md (Component Map)
│         └─ No → Did you add new functions/classes?
│                  ├─ Yes → Update API_REFERENCE.md
│                  └─ No → Did you fix a bug?
│                           ├─ Yes → Update DEBUGGING_GUIDE.md
│                           └─ No → Did you add a feature?
│                                    ├─ Yes → Update INDEX.md + FEATURE_DEVELOPMENT.md
│                                    └─ No → Any config changes?
│                                             ├─ Yes → Update INDEX.md + API_REFERENCE.md
│                                             └─ No → No update needed
└─ No → No update needed
```

---

## 📚 Summary

### The 12 Rules

1. **Always Use Context** for debugging, feature dev, and code understanding
2. **Use Right Document** based on task type
3. **Update Triggers** - Know when context needs updating
4. **Update Workflow** - Follow the 4-step process
5. **Usage Workflow** - Before, during, and after tasks
6. **Quality Standards** - Accuracy, completeness, clarity
7. **AI Guidelines** - How AI should use and reference context
8. **Maintenance Schedule** - Weekly, monthly, post-release reviews
9. **Metrics** - Track coverage, accuracy, usage, freshness
10. **Enforcement** - Automatic checks and review checklist
11. **Templates** - Standard formats for updates
12. **Decision Tree** - Quick reference for when to use/update

---

**End of Rules Document**
