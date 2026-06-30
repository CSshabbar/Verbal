# Context Update Guide

**Purpose:** Step-by-step guide for keeping the project context current

**Version:** 1.0  
**Last Updated:** 2026-06-30

---

## 🎯 Quick Start: "I Just Made Changes, What Do I Update?"

Use this decision tree immediately after making code changes:

```
What did you do?
│
├─ Created new file(s)
│  └─→ Update: INDEX.md (Component Map + Key Files)
│      └─→ Also: API_REFERENCE.md (if file has public APIs)
│
├─ Added new functions/classes
│  └─→ Update: API_REFERENCE.md
│      └─→ Also: INDEX.md (if major component)
│
├─ Modified configuration
│  └─→ Update: INDEX.md (Configuration section)
│      └─→ Also: API_REFERENCE.md (config.py section)
│
├─ Fixed a bug
│  └─→ Update: DEBUGGING_GUIDE.md (add/update relevant section)
│      └─→ Also: INDEX.md (if it's a known issue)
│
├─ Added new feature
│  └─→ Update: INDEX.md (all relevant sections)
│      └─→ Also: FEATURE_DEVELOPMENT.md (if pattern is reusable)
│
├─ Changed build process
│  └─→ Update: INDEX.md (Build & Deployment)
│      └─→ Also: DEBUGGING_GUIDE.md (Build section)
│
└─ Integrated new API/service
   └─→ Update: INDEX.md (APIs & Integrations)
       └─→ Also: API_REFERENCE.md (External APIs section)
```

---

## 📝 Update Templates by Document

### Template 1: Update INDEX.md

#### When to Use
- New file created
- New component added
- Architecture changed
- Configuration options modified

#### What to Update

**Section: Component Map**
```markdown
| Component | File | Purpose | Key Functions |
|-----------|------|---------|---------------|
| NewComponent | `app/new_module.py` | What it does | `function1()`, `function2()` |
```

**Section: Key Files Reference**
```markdown
├── app/
│   ├── new_module.py      # New component description
```

**Section: Configuration Files** (if config changed)
```json
{
  "new_option": "default_value",
  "another_option": true
}
```

**Section: APIs & Integrations** (if API added)
```markdown
### New API Name
- **Endpoint:** `https://api.example.com`
- **Purpose:** What it does
- **Config:** `config_key_name`
- **File:** `app/module.py:function_name()`
```

---

### Template 2: Update API_REFERENCE.md

#### When to Use
- New function added
- New class created
- Function signature changed
- New module created

#### What to Update

**For New Module:**
```markdown
### `app/module_name.py` - Module Purpose

#### Class: `ClassName`

##### `__init__(param1: type, param2: type)`
Initialize the class.

**Parameters:**
- `param1` - Description
- `param2` - Description

**Example:**
```python
obj = ClassName(param1="value", param2=42)
```

##### `method_name(arg: type) -> return_type`
Method description.

**Parameters:**
- `arg` - Description

**Returns:**
- `return_type` - Description
```

**For New Function:**
```markdown
#### Function: `function_name(param1: type, param2: type) -> return_type`

Function description.

**Parameters:**
- `param1` - Description
- `param2` - Description

**Returns:**
- `return_type` - Description

**Example:**
```python
result = function_name(param1="value", param2=42)
```
```

---

### Template 3: Update DEBUGGING_GUIDE.md

#### When to Use
- New bug discovered
- New debugging pattern found
- Solution found for existing issue
- Workaround implemented

#### What to Update

**Add New Section:**
```markdown
### N. Issue Name

**Symptoms:**
- What users see
- Error messages
- Log output patterns

**Root Cause:**
- Technical explanation
- Why it happens

**Debug Steps:**
1. First step with command
   ```bash
   command to run
   ```

2. Second step with code
   ```python
   # Add this logging
   logger.info(f"Debug: {value}")
   ```

3. Continue...

**Solution:**
- Permanent fix
- Workarounds

**Related:**
- Link to other sections
```

---

### Template 4: Update FEATURE_DEVELOPMENT.md

#### When to Use
- New feature pattern established
- Reusable implementation pattern
- New integration type

#### What to Update

**Add New Template:**
```markdown
### Template N: Feature Type

**Example:** Adding X to Verbal

#### Step 1: Create Module
```python
# app/new_feature.py
class NewFeature:
    """Implementation"""
    pass
```

#### Step 2: Update Config
```python
# app/config.py
DEFAULT_CONFIG = {
    # ...
    "new_option": default_value,
}
```

#### Step 3: Integrate
```python
# app/main.py
from app.new_feature import NewFeature
```

#### Step 4: Add UI
```python
# app/dashboard.py
```

#### Step 5: Test
```python
# Test code
```
```

---

### Template 5: Update QUICK_REFERENCE.md

#### When to Use
- New command to remember
- New file location
- New API endpoint
- New configuration option

#### What to Update

**Add to Relevant Table:**

Quick Start Commands:
```markdown
# New command
command --flag value
```

File Locations:
```markdown
| What | Location |
|------|----------|
| New Thing | `path/to/file` |
```

APIs & Keys:
```markdown
### New API Name
- **Purpose:** What it does
- **Config:** `config_key`
```

---

## 🔍 Detailed Update Workflows

### Workflow 1: After Creating New File

**Example:** You created `app/analytics.py`

**Steps:**

1. **Update INDEX.md**
   - Find "Component Map" section
   - Add new row:
     ```markdown
     | **Analytics** | `app/analytics.py` | Usage tracking | `track_event()`, `get_stats()` |
     ```
   
   - Find "Key Files Reference" section
   - Add to file tree:
     ```markdown
     ├── app/
     │   ├── analytics.py         # Usage analytics and stats
     ```

2. **Update API_REFERENCE.md**
   - Add new section:
     ```markdown
     ### `app/analytics.py` - Usage Analytics

     #### Function: `track_event(event_name: str, data: dict) -> None`
     Track an analytics event.

     **Parameters:**
     - `event_name` - Event identifier
     - `data` - Event metadata

     **Example:**
     ```python
     track_event("transcription_completed", {"words": 100})
     ```

     #### Function: `get_stats(user_id: str) -> dict`
     Get usage statistics for user.

     **Parameters:**
     - `user_id` - User identifier

     **Returns:**
     - `dict` - Statistics including total_transcriptions, total_words, etc.
     ```

3. **Update QUICK_REFERENCE.md** (if relevant)
   - Add to file locations table

4. **Verify**
   - [ ] All references added
   - [ ] Code examples are valid
   - [ ] Cross-references work

---

### Workflow 2: After Adding Configuration Option

**Example:** You added `analytics_enabled` config option

**Steps:**

1. **Update INDEX.md**
   - Find "Configuration Files" section
   - Update the JSON example:
     ```json
     {
       "analytics_enabled": true,
       // ... existing options ...
     }
     ```

2. **Update API_REFERENCE.md**
   - Find `app/config.py` section
   - Update DEFAULT_CONFIG documentation:
     ```markdown
     ##### `DEFAULT_CONFIG: dict`
     
     Default configuration values:
     - `analytics_enabled` - Enable analytics tracking (default: true)
     - `...` - existing options
     ```

3. **Update QUICK_REFERENCE.md**
   - Add to Configuration Options section

4. **Verify**
   - [ ] Default value documented
   - [ ] Purpose explained
   - [ ] Usage example provided

---

### Workflow 3: After Fixing Bug

**Example:** You fixed the "recording cuts short" bug

**Steps:**

1. **Update DEBUGGING_GUIDE.md**
   - Find the relevant section (Section 1: Recording Cuts Short)
   - Add "Solution" subsection:
     ```markdown
     **Solution:**
     
     Implemented minimum recording duration:
     
     ```python
     # In app/main.py
     MIN_RECORDING_DURATION = 3.0
     
     def _stop_recording(self):
         duration = time.time() - self._recording_start_time
         if duration < MIN_RECORDING_DURATION:
             logger.warning(f"Enforcing minimum duration")
             time.sleep(MIN_RECORDING_DURATION - duration)
     ```
     ```

2. **Update INDEX.md**
   - Find "Common Debugging Scenarios"
   - Update the entry to mark as "Fixed in v1.0.11"

3. **Add to Release Notes** (if applicable)
   - Update version-specific release notes

4. **Verify**
   - [ ] Solution documented
   - [ ] Code example included
   - [ ] Version noted

---

### Workflow 4: After Adding Feature

**Example:** You added DeepL translation support

**Steps:**

1. **Update INDEX.md**
   - Component Map: Add DeepL translator
   - APIs & Integrations: Add DeepL section
   - Configuration Files: Add DeepL config options
   - Quick Reference: Add DeepL commands

2. **Update API_REFERENCE.md**
   - Add `app/deepl_translator.py` section
   - Document all public methods
   - Add usage examples

3. **Update FEATURE_DEVELOPMENT.md**
   - If pattern is reusable, add as new template
   - Reference the DeepL implementation as example

4. **Update QUICK_REFERENCE.md**
   - Add DeepL API info
   - Add config options
   - Add relevant commands

5. **Verify**
   - [ ] All components documented
   - [ ] API reference complete
   - [ ] Configuration documented
   - [ ] Examples provided

---

## ✅ Update Checklist

### Before Committing

After making code changes, ALWAYS verify:

#### File Creation
- [ ] INDEX.md Component Map updated
- [ ] INDEX.md Key Files Reference updated
- [ ] API_REFERENCE.md section created (if has public APIs)
- [ ] QUICK_REFERENCE.md updated (if relevant)

#### New Functions/Classes
- [ ] API_REFERENCE.md updated with signatures
- [ ] Parameters documented
- [ ] Return values documented
- [ ] Usage examples added

#### Configuration Changes
- [ ] INDEX.md Configuration section updated
- [ ] API_REFERENCE.md config.py updated
- [ ] Default values documented
- [ ] Purpose explained

#### Bug Fixes
- [ ] DEBUGGING_GUIDE.md updated with solution
- [ ] Root cause documented
- [ ] Debug steps documented
- [ ] Version noted

#### Feature Additions
- [ ] INDEX.md all relevant sections updated
- [ ] API_REFERENCE.md new modules documented
- [ ] FEATURE_DEVELOPMENT.md pattern added (if reusable)
- [ ] QUICK_REFERENCE.md quick info added

#### Build/Deployment Changes
- [ ] INDEX.md Build & Deployment updated
- [ ] DEBUGGING_GUIDE.md Build section updated
- [ ] Commands documented
- [ ] Output locations noted

### Quality Checks

Before finalizing update:

- [ ] Information is accurate (matches code)
- [ ] Cross-references are correct
- [ ] Code examples are valid (would run)
- [ ] Formatting is consistent
- [ ] No sensitive data included
- [ ] Version/date updated
- [ ] Spelling/grammar checked

---

## 📊 Update Priority Matrix

### Priority 1: Update Immediately (Before Committing)

- New security-sensitive code
- New configuration options
- New public APIs
- Breaking changes
- New file creation

### Priority 2: Update Within 24 Hours

- Bug fixes
- New features
- Performance improvements
- UI changes

### Priority 3: Update Within 1 Week

- Refactoring (no API changes)
- Code cleanup
- Internal improvements
- Documentation fixes

---

## 🎯 Common Scenarios

### Scenario 1: "I Added a New API Integration"

**What to Update:**

1. **INDEX.md**
   - Component Map: Add new module
   - APIs & Integrations: Add new API section
   - Configuration: Add API key config

2. **API_REFERENCE.md**
   - New module documentation
   - External APIs section

3. **FEATURE_DEVELOPMENT.md**
   - Add/update API integration template

4. **QUICK_REFERENCE.md**
   - API info
   - Config options

---

### Scenario 2: "I Fixed a Crash Bug"

**What to Update:**

1. **DEBUGGING_GUIDE.md**
   - Add/update relevant section
   - Document the fix

2. **INDEX.md**
   - Update "Common Debugging Scenarios"
   - Mark as fixed in current version

3. **Release Notes**
   - Document the fix

---

### Scenario 3: "I Created a New Mobile Screen"

**What to Update:**

1. **INDEX.md**
   - Mobile section: Add new screen
   - Component Map: Add screen file
   - Navigation: Update tab info

2. **API_REFERENCE.md**
   - Document screen component
   - Document any new lib utilities

3. **QUICK_REFERENCE.md**
   - Mobile Navigation table

---

### Scenario 4: "I Changed the Database Schema"

**What to Update:**

1. **INDEX.md**
   - Database Schema section
   - Update table definitions
   - Update indexes

2. **API_REFERENCE.md**
   - Database section
   - Update query examples

3. **Sync Code**
   - Update `app/sync.py` documentation

---

## 🔄 Maintenance Reminders

### Set Calendar Reminders

**Weekly (Every Monday):**
- Review code changes from previous week
- Update context for any missed updates
- Verify all new files are documented

**Monthly (First day of month):**
- Complete review of all documents
- Remove outdated information
- Update version numbers
- Test documented workflows

**After Each Release:**
- Comprehensive audit
- Document all new features
- Update architecture diagrams
- Verify all examples still work

---

## 📝 Update Log Template

Keep track of updates in each document:

```markdown
## Changelog

| Date | Version | Section | Change | Author |
|------|---------|---------|--------|--------|
| 2026-06-30 | 1.0 | All | Initial creation | AI |
| YYYY-MM-DD | X.X | Section | Description | Who |
```

---

## 🆘 Troubleshooting

### "I'm Not Sure What to Update"

1. **List all files you changed**
   ```bash
   git diff --name-only
   ```

2. **For each file, ask:**
   - Is this a new file? → Update INDEX.md
   - Does it have new functions? → Update API_REFERENCE.md
   - Did I add config? → Update INDEX.md + API_REFERENCE.md
   - Did I fix a bug? → Update DEBUGGING_GUIDE.md
   - Did I add a feature? → Update multiple docs

3. **Still unsure?**
   - Check RULES.md → Rule 3: Update Triggers
   - Use the decision tree at the top of this guide

### "I Don't Have Time to Update Everything"

**Minimum Required Updates:**

1. **New files** → INDEX.md Component Map (1 line)
2. **New config** → INDEX.md Configuration (1 line)
3. **Bug fix** → DEBUGGING_GUIDE.md (solution paragraph)

**Can Wait (but do within 1 week):**
- FEATURE_DEVELOPMENT.md templates
- QUICK_REFERENCE.md entries
- Detailed examples

---

## ✅ Summary

### The Update Process

1. **Identify** what changed
2. **Determine** which docs to update (use decision tree)
3. **Apply** the appropriate template
4. **Verify** quality and completeness
5. **Commit** with note about docs updated

### Remember

- **Update immediately** for critical changes
- **Use templates** for consistency
- **Follow checklists** for completeness
- **Set reminders** for maintenance
- **Keep it current** - outdated docs are worse than no docs

---

**End of Update Guide**
