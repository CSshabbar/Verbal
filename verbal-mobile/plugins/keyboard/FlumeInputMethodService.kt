package com.verbal.app.keyboard

import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Intent
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.inputmethodservice.InputMethodService
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.DataOutputStream
import java.io.File
import java.io.FileInputStream
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Flume Keyboard v2 (Android IME) — full QWERTY keyboard with the Flume bar.
 *
 * Matches FLUME_KEYBOARD_V2_DESIGN.md: a suggestions strip, the Flume bar
 * (F · ⚡ snippets · ▦ canvas · 🕐 history · 📖 vocabulary · ● mic), and a content
 * area that swaps between the letters/numbers/symbols key layers and the four
 * overlays. Light + dark themes follow the system night mode.
 *
 * STAGE 1 (this file): layers, Flume bar, theming, overlays, basic suggestions,
 * and the existing mic → groq-proxy dictation. DEFERRED (next stages, marked TODO):
 * emoji picker, GIF (Tenor), glide/swipe typing, ML autocorrect/prediction.
 *
 * Fails closed: secure fields disable the mic; any error shows a message, never crashes.
 */
class FlumeInputMethodService : InputMethodService() {

    // ── palette (set per theme) ──────────────────────────────────────────────────
    private val ACCENT = Color.parseColor("#C85A3E")   // terracotta — THE Flume accent
    private var bg = 0; private var keyBg = 0; private var keyText = 0
    private var pressBg = 0   // key color while pressed (Gboard-style feedback)
    private var modBg = 0; private var barBg = 0; private var iconTint = 0
    private var mutedText = 0; private var returnBg = 0; private var returnText = 0
    private var micBg = 0; private var micFg = 0; private var cardBg = 0; private var highlightBg = 0

    // ── views / state ─────────────────────────────────────────────────────────────
    private var root: LinearLayout? = null
    private var suggestionStrip: LinearLayout? = null
    private var barRow: LinearLayout? = null
    private var content: FrameLayout? = null
    private var status: TextView? = null
    private var mic: TextView? = null
    private val barIcons = HashMap<String, TextView>()
    // Recording UI (waveform + cancel/pause replace the overlay icons while recording).
    private var iconGroup: View? = null
    private var micWrap: View? = null
    private var recordControls: View? = null
    private var waveform: WaveformView? = null
    private var pauseBtn: TextView? = null
    private var timerLabel: TextView? = null
    private var paused = false
    private var recStartMs = 0L
    private var pausedTotalMs = 0L
    private var pauseStartMs = 0L
    // ── clipboard (self-contained: written AND read by this service, never via the
    // one-directional flume_kbd_config.json app→keyboard bridge; content never leaves device)
    private var quickPasteChip: TextView? = null
    private var pendingQuickPaste: String? = null
    private var clipboardCache = ArrayList<Pair<String, String>>()   // (text, iso timestamp), most-recent-first
    private var clipboardLoaded = false
    private var lastClipHash = 0
    private val CLIPBOARD_CAP = 15                // mirrors the dictation-history wire cap
    private val CLIPBOARD_ENTRY_CHAR_CAP = 4000   // bound file size / row rendering only
    private var clipboardListener: ClipboardManager.OnPrimaryClipChangedListener? = null
    // ── transform (select text elsewhere → instruction → LLM rewrite → replace) ─────────
    // Mirrors whisperflow/app/transform.py's Mode B exactly (same prompts, same
    // preview-before-replace contract) — see context/03-features.md for why the
    // mechanism differs (no Accessibility-style selection API, no Cmd+Z equivalent).
    private enum class TransformState { IDLE, COMPOSE, BUSY, PREVIEW }
    private var transformState = TransformState.IDLE
    private var transformButton: TextView? = null
    private var transformCancelButton: View? = null
    private var transformOriginalText = ""
    private var transformInstruction = ""
    private var transformRewrite = ""
    private var pendingUndo: Pair<Int, String>? = null   // (length, original)
    private var undoRunnable: Runnable? = null
    private val TRANSFORM_SELECTION_CHAR_CAP = 8000   // smaller than desktop's 12000 — mobile
                                                       // selections are shorter; same shared-key TPM caution
    private val transformPresets = listOf(
        "Improvise" to "",   // "" = IMPROVISE_SYSTEM_PROMPT, no instruction (mirrors desktop's 1-tap)
        "Formal" to "Make this more formal",
        "Casual" to "Make this more casual",
        "Shorten" to "Make this shorter and tighter",
        "Fix grammar" to "Fix grammar and punctuation",
    )
    // Verbatim from whisperflow/app/transform.py:48-69 — keep in sync; this is a
    // SEPARATE prompt from the dictation cleanup prompt and must never be merged with it.
    private val TRANSFORM_SYSTEM_PROMPT =
        "You transform the user's text according to their instruction.\n" +
        "Rules:\n" +
        "- Return ONLY the transformed text. No preamble, no explanation, no quotes, " +
        "no markdown fences.\n" +
        "- Never add facts, names, numbers or claims that are not in the original text.\n" +
        "- Preserve the language of the original text unless the instruction says to translate.\n" +
        "- Keep meaning intact unless the instruction explicitly asks to change it.\n" +
        "- If the instruction is unclear or impossible, return the original text lightly " +
        "cleaned up (punctuation, casing) instead."
    private val IMPROVISE_SYSTEM_PROMPT =
        "You are a precision editor. Rewrite the user's text to be clearer and tighter.\n" +
        "Rules:\n" +
        "- Return ONLY the rewritten text. No preamble, no explanation, no quotes, " +
        "no markdown fences.\n" +
        "- Preserve the meaning, facts, tone register and language. Never add content.\n" +
        "- Fix grammar, punctuation and awkward phrasing; break up run-ons; remove filler.\n" +
        "- Keep the original structure (paragraphs, lists, greetings/sign-offs) intact.\n" +
        "- Do not shorten by more than ~20% unless the text is redundant."
    private val ampPoll = object : Runnable {
        override fun run() {
            if (!recording) return
            if (!paused) {
                val amp = try { recorder?.maxAmplitude ?: 0 } catch (e: Exception) { 0 }
                val lvl = Math.sqrt((amp / 32767.0)).toFloat().coerceIn(0f, 1f)
                waveform?.tick(lvl)
            }
            main.postDelayed(this, 33)
        }
    }
    private val timerTick = object : Runnable {
        override fun run() {
            if (!recording) return
            val ref = if (paused) pauseStartMs else System.currentTimeMillis()
            val s = ((ref - recStartMs - pausedTotalMs) / 1000).toInt().coerceAtLeast(0)
            timerLabel?.text = "${s / 60}:${(s % 60).toString().padStart(2, '0')}"
            main.postDelayed(this, 250)
        }
    }
    // Ionicons (bundled ttf) — same icon set as the app; tint via setTextColor.
    private val icFont: Typeface? by lazy {
        try { Typeface.createFromAsset(assets, "ionicons.ttf") } catch (e: Exception) { null }
    }
    // App typefaces — Geist for UI/keys, JetBrains Mono for numerals + meta labels.
    private val geist: Typeface? by lazy {
        try { Typeface.createFromAsset(assets, "geist_medium.ttf") } catch (e: Exception) { null }
    }
    private val geistReg: Typeface? by lazy {
        try { Typeface.createFromAsset(assets, "geist_regular.ttf") } catch (e: Exception) { null }
    }
    private val mono: Typeface? by lazy {
        try { Typeface.createFromAsset(assets, "jetbrains_mono.ttf") } catch (e: Exception) { null }
    }
    private val IC_FLASH = "\uF31A"   // flash-outline (snippets)
    private val IC_GRID  = "\uF356"   // grid-outline (canvas)
    private val IC_TIME  = "\uF5DE"   // time-outline (history)
    private val IC_BOOK  = "\uF1A6"   // book-outline (vocabulary)
    private val IC_CLIPBOARD = "\uF248"   // clipboard-outline (clipboard)
    private val IC_TRANSFORM = "\uF58D"   // sparkles-outline (transform)
    private val IC_MIC   = ""   // mic
    private val IC_CLOSE = ""   // close (cancel \u2715)
    private val IC_PAUSE = ""   // pause
    private val IC_PLAY  = ""   // play (resume)
    private val IC_STOP  = ""   // stop (filled square)

    private enum class Layer { LETTERS, NUMBERS, SYMBOLS }
    private var layer = Layer.LETTERS
    private var shifted = false
    private var capsLock = false
    private var activeOverlay: String? = null   // null = keyboard showing
    private var emojiCatIdx = 1
    private val emojiRecents = ArrayList<String>()

    // Enlarged-letter preview bubble shown above the pressed letter key (Gboard-style).
    private var keyPreview: android.widget.PopupWindow? = null
    private var keyPreviewText: TextView? = null

    private var recorder: MediaRecorder? = null
    private var audioFile: File? = null
    private var recording = false
    private var secure = false
    private var busy = false
    private val main = Handler(Looper.getMainLooper())

    // ── input-session identity (IDI-163) ────────────────────────────────────────────
    // A dictation is asynchronous: the user can switch field or app (or the host can
    // move focus into a PASSWORD field) while the audio is still being transcribed.
    // Every new input session bumps `inputSession`; a recording captures the value at
    // record-start and the result is only committed when the SAME session is still
    // current, the field is still non-secure (re-checked live, not the mic-tap cache)
    // and the result isn't stale. Anything else is dropped with a visible message —
    // never typed into a field the user didn't dictate into.
    private var inputSession = 0L
    private var recordingSession = -1L
    private var recordingStartedAtMs = 0L
    private val DICTATION_MAX_AGE_MS = 90_000L

    // Fast-typing correctness (see 05-conventions "keyboard hot path"): the letter
    // key views are updated IN PLACE on shift/caps changes instead of rebuilding the
    // whole keyboard, and suggestions run debounced off the commit path — a rebuild
    // or a heavy per-keystroke scan mid-typing was dropping the next rapid tap.
    private val letterKeyViews = mutableListOf<TextView>()   // char keys; base label in view.tag
    private var shiftKeyView: TextView? = null
    private val suggRunnable = Runnable { doUpdateSuggestions() }

    /** The label to SHOW/COMMIT for a base key, given the live shift/caps state. */
    private fun casedChar(base: String): String =
        if (layer == Layer.LETTERS && (shifted || capsLock) && base.length == 1 && base[0].isLetter())
            base.uppercase() else base

    /** Update letter labels + the shift glyph without tearing down the view tree. */
    private fun refreshLetterCaps() {
        for (v in letterKeyViews) {
            val b = v.tag as? String ?: continue
            v.text = casedChar(b)
        }
        shiftKeyView?.text = if (capsLock) "⇪" else "⇧"
    }

    // ── recording sound effects (bundled WAVs in assets/) ───────────────────────────
    // Low-latency SoundPool, safe from any thread; fails closed so a sound error never
    // throws into the recording/transcribe path.
    private val soundPool: android.media.SoundPool by lazy {
        val attrs = android.media.AudioAttributes.Builder()
            .setUsage(android.media.AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
            .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()
        android.media.SoundPool.Builder().setMaxStreams(3).setAudioAttributes(attrs).build()
    }
    private val soundIds = HashMap<String, Int>()
    private fun loadSounds() {
        if (soundIds.isNotEmpty()) return
        for (name in listOf("flume_start", "flume_stop", "flume_done")) {
            try {
                val afd = assets.openFd("$name.wav")
                soundIds[name] = soundPool.load(afd, 1)
                afd.close()
            } catch (e: Exception) { /* asset missing — skip */ }
        }
    }
    private fun playSound(name: String, volume: Float = 0.35f) {
        try {
            loadSounds()
            val id = soundIds[name] ?: return
            soundPool.play(id, volume, volume, 1, 0, 1f)
        } catch (e: Exception) { /* never break the recording path */ }
    }

    // ── typing suggestions: bundled frequency dictionary + on-device learning ───────
    // flume_words.txt is ~25k words, most-frequent first (rank = position), so prefix
    // matches taken in order are the most likely completions. `learned` is the user's
    // own word-frequency map (persisted), boosted above the dictionary.
    private val dictWords: List<String> by lazy {
        try { assets.open("flume_words.txt").bufferedReader().use { it.readLines() } } catch (e: Exception) { emptyList() }
    }
    private val learned = HashMap<String, Int>()
    private var learnedLoaded = false
    private fun loadLearned() {
        if (learnedLoaded) return
        learnedLoaded = true
        try {
            val js = JSONObject(getSharedPreferences("flume_kbd_learn", MODE_PRIVATE).getString("words", "{}") ?: "{}")
            for (k in js.keys()) learned[k] = js.optInt(k)
        } catch (e: Exception) { /* start empty */ }
    }
    private fun learnWord(raw: String) {
        val w = raw.lowercase().filter { it.isLetter() }
        if (w.length < 2) return
        loadLearned()
        learned[w] = (learned[w] ?: 0) + 1
        try {
            if (learned.size > 600) {                    // bound the personal store
                val top = learned.entries.sortedByDescending { it.value }.take(500).associate { it.key to it.value }
                learned.clear(); learned.putAll(top)
            }
            val js = JSONObject(); for ((k, v) in learned) js.put(k, v)
            getSharedPreferences("flume_kbd_learn", MODE_PRIVATE).edit().putString("words", js.toString()).apply()
        } catch (e: Exception) { /* best-effort */ }
    }

    // ── next-word prediction: bundled bigram table + on-device personal bigrams ─────
    // flume_bigrams.txt is `prev<TAB>next1 next2 next3 …` (space-separated, most-likely
    // first). `learnedBg` is the user's own prev→next frequency map (persisted next to
    // `learned`), preferred over the bundled table.
    private val bigrams: HashMap<String, List<String>> by lazy {
        val m = HashMap<String, List<String>>()
        try {
            assets.open("flume_bigrams.txt").bufferedReader().useLines { seq ->
                for (line in seq) {
                    val tab = line.indexOf('\t'); if (tab <= 0) continue
                    val prev = line.substring(0, tab)
                    val nexts = line.substring(tab + 1).trim().split(' ').filter { it.isNotEmpty() }
                    if (nexts.isNotEmpty()) m[prev] = nexts
                }
            }
        } catch (e: Exception) { /* empty */ }
        m
    }
    private val learnedBg = HashMap<String, HashMap<String, Int>>()
    private var learnedBgLoaded = false
    private fun loadLearnedBg() {
        if (learnedBgLoaded) return
        learnedBgLoaded = true
        try {
            val root = JSONObject(getSharedPreferences("flume_kbd_learn", MODE_PRIVATE).getString("bigrams", "{}") ?: "{}")
            for (p in root.keys()) {
                val inner = root.optJSONObject(p) ?: continue
                val m = HashMap<String, Int>(); for (n in inner.keys()) m[n] = inner.optInt(n)
                learnedBg[p] = m
            }
        } catch (e: Exception) {}
    }
    private fun learnBigram(prev: String, next: String) {
        val p = prev.lowercase().filter { it.isLetter() }; val n = next.lowercase().filter { it.isLetter() }
        if (p.length < 2 || n.length < 2) return
        loadLearnedBg()
        val m = learnedBg.getOrPut(p) { HashMap() }
        m[n] = (m[n] ?: 0) + 1
        try {
            if (learnedBg.size > 400) {   // bound: drop an arbitrary entry when too big
                val k = learnedBg.keys.firstOrNull { it != p }; if (k != null) learnedBg.remove(k)
            }
            val root = JSONObject()
            for ((pp, mm) in learnedBg) { val o = JSONObject(); for ((nn, c) in mm) o.put(nn, c); root.put(pp, o) }
            getSharedPreferences("flume_kbd_learn", MODE_PRIVATE).edit().putString("bigrams", root.toString()).apply()
        } catch (e: Exception) {}
    }

    // ── emoji: bundled full library + word→emoji keyword table ──────────────────────
    // flume_emoji.txt is `Group<TAB>emoji emoji …` (9 groups, space-separated) → the full
    // ~1900-emoji picker. flume_emoji_kw.txt is `keyword<TAB>emoji emoji …` for the
    // word→emoji suggestion chip. Both fail closed to empty on any read error.
    private val emojiLib: List<Pair<String, List<String>>> by lazy {
        val out = ArrayList<Pair<String, List<String>>>()
        try {
            assets.open("flume_emoji.txt").bufferedReader().useLines { seq ->
                for (line in seq) {
                    val tab = line.indexOf('\t'); if (tab <= 0) continue
                    val name = line.substring(0, tab)
                    val list = line.substring(tab + 1).trim().split(' ').filter { it.isNotEmpty() }
                    if (list.isNotEmpty()) out.add(name to list)
                }
            }
        } catch (e: Exception) { /* empty */ }
        out
    }
    private val emojiKw: HashMap<String, List<String>> by lazy {
        val m = HashMap<String, List<String>>()
        try {
            assets.open("flume_emoji_kw.txt").bufferedReader().useLines { seq ->
                for (line in seq) {
                    val tab = line.indexOf('\t'); if (tab <= 0) continue
                    val kw = line.substring(0, tab)
                    val list = line.substring(tab + 1).trim().split(' ').filter { it.isNotEmpty() }
                    if (list.isNotEmpty()) m[kw] = list
                }
            }
        } catch (e: Exception) { /* empty */ }
        m
    }
    // Representative tab glyph per bundled group (same order as flume_emoji.txt).
    private val emojiTabGlyphs = listOf("😀","🧑","🐶","🍔","✈️","⚽","💡","❤️","🏳️")

    // Read the last two alphabetic words before the cursor (prev, justFinished).
    private fun lastTwoWords(): Pair<String, String>? {
        val ic = currentInputConnection ?: return null
        val before = ic.getTextBeforeCursor(64, 0)?.toString()?.trimEnd() ?: return null
        val ms = Regex("[\\p{L}']+").findAll(before).map { it.value }.toList()
        if (ms.size < 2) return null
        return Pair(ms[ms.size - 2], ms[ms.size - 1])
    }

    private fun dp(v: Int): Int =
        TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun rounded(color: Int, radius: Int): GradientDrawable =
        GradientDrawable().apply { setColor(color); cornerRadius = dp(radius).toFloat() }

    // Gapless touch grid (Gboard-style): the touchable View fills its whole cell, but a
    // rounded key is drawn INSIDE with a 3dp inset all sides — so the visual gap between
    // keys is drawn inside each key, and no point in the key area is a dead touch zone.
    private fun keyDrawable(color: Int): android.graphics.drawable.Drawable =
        android.graphics.drawable.InsetDrawable(rounded(color, 8), dp(3))

    private fun isDark(): Boolean =
        (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES

    private fun applyTheme() {
        // Flume design tokens (warm near-black + cream, orange accent).
        if (isDark()) {
            // Canonical "Minimalist dark" tokens (colors.ts / CLAUDE_CODE_PROMPT.md).
            // barBg == bg so the Flume bar blends into the app bottom (no floating card).
            bg = Color.parseColor("#0e1012"); keyBg = Color.parseColor("#2a2d31")
            pressBg = Color.parseColor("#3a3e44")
            keyText = Color.parseColor("#f2f2f2"); modBg = Color.parseColor("#1e2124"); barBg = Color.parseColor("#0e1012")
            iconTint = Color.parseColor("#8b8d90"); mutedText = Color.parseColor("#8b8d90")
            returnBg = Color.parseColor("#f2f2f2"); returnText = Color.parseColor("#0e1012")
            micBg = Color.parseColor("#f2f2f2"); micFg = Color.parseColor("#0e1012")
            cardBg = Color.parseColor("#26282b"); highlightBg = Color.parseColor("#26282b")
        } else {
            bg = Color.parseColor("#ECEBEA"); keyBg = Color.WHITE
            pressBg = Color.parseColor("#d4d4d6")
            keyText = Color.parseColor("#14110f"); modBg = Color.parseColor("#CBCBCD"); barBg = Color.parseColor("#ECEBEA")
            iconTint = Color.parseColor("#6b6b6b"); mutedText = Color.parseColor("#8a857f")
            returnBg = Color.parseColor("#14110f"); returnText = Color.WHITE
            micBg = Color.parseColor("#14110f"); micFg = Color.WHITE
            cardBg = Color.WHITE; highlightBg = Color.parseColor("#E1E0DF")
        }
    }

    // Registered once for the service's process lifetime — an Android IME stays
    // resident more readily than an iOS keyboard extension, so this can notice a
    // clipboard change made in another app before the user reopens this keyboard.
    override fun onCreate() {
        super.onCreate()
        val cm = getSystemService(CLIPBOARD_SERVICE) as? ClipboardManager
        val listener = ClipboardManager.OnPrimaryClipChangedListener { checkClipboardForNewContent() }
        cm?.addPrimaryClipChangedListener(listener)
        clipboardListener = listener
    }

    // ── view tree ─────────────────────────────────────────────────────────────────
    override fun onCreateInputView(): View {
        applyTheme()
        val r = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(bg)
            // Full-bleed: minimal side padding so keys reach near the screen edges and
            // the whole surface reads as one continuous keyboard, not a floating card.
            setPadding(dp(2), dp(2), dp(2), dp(6))
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        suggestionStrip = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(40))
        }
        val sugScroll = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            isFillViewport = true   // let the MATCH_PARENT strip stretch to full width (weighted cells)
            addView(suggestionStrip)
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(40))
        }
        r.addView(sugScroll)
        r.addView(buildFlumeBar())
        content = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        r.addView(content)
        root = r
        showKeyboard()
        updateSuggestions()
        loadSounds()
        return r
    }

    // IDI-163: the earliest per-field callback — bump the session id here so a
    // dictation that is still in flight can never land in the newly-focused field.
    // Deliberately unconditional (including `restarting == true`): a missed bump means
    // text typed into the wrong field, which is strictly worse than a dropped result
    // that the user can see and redo.
    override fun onStartInput(info: EditorInfo?, restarting: Boolean) {
        super.onStartInput(info, restarting)
        bumpInputSession()
        secure = isSecureField(info)
    }

    private fun bumpInputSession() {
        inputSession++
        // A soft-Undo captured against the previous field must never fire into this
        // one — it would delete N characters of unrelated text (IDI-164).
        clearPendingUndo()
    }

    private fun clearPendingUndo() {
        undoRunnable?.let { main.removeCallbacks(it) }
        undoRunnable = null
        if (pendingUndo != null) { pendingUndo = null; refreshQuickPasteChip() }
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        bumpInputSession()
        secure = isSecureField(info)
        if (recording) abortRecording(immediate = true)
        // A transform compose/preview left over from the previous field would swallow
        // every keystroke into `transformInstruction` and could replace text in the
        // WRONG field — always start a new input session with transform IDLE (IDI-164).
        resetTransformState()
        layer = Layer.LETTERS; shifted = false; capsLock = false
        showKeyboard()
        updateSuggestions()
        maybeAutoCap()
        // Fallback in case the listener wasn't registered / the service was killed
        // and relaunched since the clipboard last changed.
        checkClipboardForNewContent()
    }

    // The keyboard is going away (app switch, IME hidden, field closed). Without this
    // a MediaRecorder started for a dictation stays alive holding the microphone for
    // the rest of the process's life, and ampPoll/timerTick keep reposting forever.
    override fun onFinishInputView(finishingInput: Boolean) {
        super.onFinishInputView(finishingInput)
        hideKeyPreview()
        if (recording || recorder != null) abortRecording(immediate = true)
        main.removeCallbacks(ampPoll); main.removeCallbacks(timerTick)
    }

    override fun onDestroy() {
        hideKeyPreview()
        // Same leak as onFinishInputView, for the process-teardown path.
        main.removeCallbacks(ampPoll); main.removeCallbacks(timerTick)
        undoRunnable?.let { main.removeCallbacks(it) }
        main.removeCallbacks(suggRunnable)
        stopAndReleaseRecorder()
        try { soundPool.release() } catch (e: Exception) {}
        try {
            val cm = getSystemService(CLIPBOARD_SERVICE) as? ClipboardManager
            clipboardListener?.let { cm?.removePrimaryClipChangedListener(it) }
        } catch (e: Exception) {}
        super.onDestroy()
    }

    // ── Flume bar ───────────────────────────────────────────────────────────────
    private fun buildFlumeBar(): View {
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(barBg)
            setPadding(dp(6), dp(6), dp(6), dp(6))
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52))
        }
        // F wordmark — inverted square (keyText bg) with a terracotta F.
        bar.addView(TextView(this).apply {
            text = "F"; setTextColor(ACCENT); textSize = 15f
            typeface = geist ?: Typeface.DEFAULT_BOLD; gravity = Gravity.CENTER
            background = rounded(keyText, 8)
            layoutParams = LinearLayout.LayoutParams(dp(32), dp(32))
        })
        quickPasteChip = TextView(this).apply {
            typeface = geist ?: Typeface.DEFAULT
            setTextColor(Color.WHITE); textSize = 13f; gravity = Gravity.CENTER
            background = rounded(ACCENT, 14)
            setPadding(dp(12), dp(6), dp(12), dp(6))
            visibility = View.GONE
            setOnClickListener { tapQuickPasteChip() }
        }
        bar.addView(quickPasteChip)
        // Middle: overlay icons (right-aligned, weight 1) — swapped for the recording
        // controls while dictating.
        val icons = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL or Gravity.END
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
            addView(barIcon(IC_FLASH, "snippets"))
            addView(barIcon(IC_GRID, "canvas"))
            addView(barIcon(IC_TIME, "history"))
            addView(barIcon(IC_CLIPBOARD, "clipboard"))
            addView(barIcon(IC_BOOK, "vocabulary"))
        }
        iconGroup = icons
        bar.addView(icons)
        bar.addView(buildRecordControls())
        bar.addView(buildTransformCancelControl())
        bar.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(dp(6), 1) })
        // Transform — a live action on the current selection, same category as mic/dictation,
        // not a browse-a-list overlay, so it sits next to mic rather than in the icon group.
        transformButton = TextView(this).apply {
            text = IC_TRANSFORM; typeface = icFont; setTextColor(keyText); textSize = 18f; gravity = Gravity.CENTER
            background = rounded(highlightBg, 999)
            layoutParams = LinearLayout.LayoutParams(dp(38), dp(38)).apply { rightMargin = dp(8) }
            visibility = if (transformAvailable()) View.VISIBLE else View.GONE
            setOnClickListener { onTransformTap() }
        }
        bar.addView(transformButton)
        // mic
        mic = TextView(this).apply {
            text = IC_MIC; typeface = icFont; setTextColor(micFg); textSize = 20f; gravity = Gravity.CENTER
            background = rounded(micBg, 20)
            layoutParams = FrameLayout.LayoutParams(dp(40), dp(40))
            setOnClickListener { onMicTap() }
        }
        val mw = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(dp(40), dp(40))
            addView(mic)
            addView(View(this@FlumeInputMethodService).apply {   // terracotta dot badge (top-right)
                background = rounded(ACCENT, 999)
                layoutParams = FrameLayout.LayoutParams(dp(8), dp(8), Gravity.TOP or Gravity.END)
            })
        }
        micWrap = mw
        bar.addView(mw)
        barRow = bar
        return bar
    }

    private fun barIcon(glyph: String, overlay: String): TextView {
        val tv = TextView(this).apply {
            text = glyph; typeface = icFont; setTextColor(iconTint); textSize = 20f; gravity = Gravity.CENTER
            background = rounded(if (activeOverlay == overlay) highlightBg else Color.TRANSPARENT, 10)
            layoutParams = LinearLayout.LayoutParams(dp(40), dp(40)).apply { leftMargin = dp(4) }
            setOnClickListener { toggleOverlay(overlay) }
        }
        barIcons[overlay] = tv
        return tv
    }

    private fun refreshBar() {
        for ((ov, tv) in barIcons)
            tv.background = rounded(if (activeOverlay == ov) highlightBg else Color.TRANSPARENT, 10)
    }

    private fun setMicState(rec: Boolean) {
        mic?.apply {
            if (rec) { typeface = Typeface.DEFAULT; text = "■" }   // ■ stop
            else { typeface = icFont; text = IC_MIC }
        }
    }

    // Recording bar (RECORDING_BAR_PROMPT.md, #51/#52): F · ✕ · waveform · 0:04 · terracotta.
    private fun buildRecordControls(): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            visibility = View.GONE
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
        }
        // cancel — neutral circle chip (Ionicons close, matches iOS SF Symbol)
        val cancel = TextView(this).apply {
            text = IC_CLOSE; setTextColor(keyText); textSize = 18f; gravity = Gravity.CENTER
            typeface = icFont
            background = rounded(highlightBg, 999)
            layoutParams = LinearLayout.LayoutParams(dp(38), dp(38)).apply { leftMargin = dp(8); rightMargin = dp(10) }
            setOnClickListener { abortRecording() }
        }
        // live waveform — text-colored bars, fills the middle
        val wave = WaveformView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
        }
        waveform = wave
        // M:SS mono timer
        val timer = TextView(this).apply {
            text = "0:00"; setTextColor(mutedText); textSize = 12f; letterSpacing = 0.04f
            typeface = mono ?: Typeface.MONOSPACE
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { leftMargin = dp(10); rightMargin = dp(10) }
        }
        timerLabel = timer
        // pause — neutral circle (Ionicons pause); tap toggles pause/resume
        val pauseView = TextView(this).apply {
            text = IC_PAUSE; setTextColor(keyText); textSize = 16f; gravity = Gravity.CENTER
            typeface = icFont
            background = rounded(highlightBg, 999)
            layoutParams = LinearLayout.LayoutParams(dp(38), dp(38)).apply { rightMargin = dp(8) }
            setOnClickListener { togglePause() }
        }
        pauseBtn = pauseView
        // stop — terracotta circle (Ionicons stop); tap = stop & send
        val stop = TextView(this).apply {
            text = IC_STOP; setTextColor(Color.WHITE); textSize = 17f; gravity = Gravity.CENTER
            typeface = icFont
            background = rounded(ACCENT, 999)
            layoutParams = LinearLayout.LayoutParams(dp(42), dp(42))
            setOnClickListener { stopAndTranscribe() }
        }
        row.addView(cancel); row.addView(wave); row.addView(timer); row.addView(pauseView); row.addView(stop)
        recordControls = row
        return row
    }

    // Compose-mode bar swap (mirrors buildRecordControls' role): replaces the icon group
    // + transform button with a single ✕ while the user is composing a transform instruction.
    private fun buildTransformCancelControl(): View {
        val cancel = TextView(this).apply {
            text = IC_CLOSE; setTextColor(keyText); textSize = 18f; gravity = Gravity.CENTER
            typeface = icFont
            background = rounded(highlightBg, 999)
            layoutParams = LinearLayout.LayoutParams(dp(38), dp(38))
            visibility = View.GONE
            setOnClickListener { exitCompose() }
        }
        transformCancelButton = cancel
        return cancel
    }

    private fun enterRecordingUI() {
        paused = false; pauseBtn?.text = IC_PAUSE; pauseBtn?.alpha = 1f
        recStartMs = System.currentTimeMillis(); pausedTotalMs = 0L
        timerLabel?.text = "0:00"
        waveform?.reset()
        // Fade + collapse BOTH the overlay icons and the mic; the bar shows only the
        // recording controls (F wordmark stays).
        iconGroup?.animate()?.alpha(0f)?.setDuration(250)?.withEndAction { iconGroup?.visibility = View.GONE }
        micWrap?.animate()?.alpha(0f)?.setDuration(250)?.withEndAction { micWrap?.visibility = View.GONE }
        // Compose mode's own ✕ would otherwise sit alongside recordControls' cancel —
        // hide it for the duration of the recording, restored in exitRecordingUI().
        transformCancelButton?.visibility = View.GONE
        recordControls?.apply {
            alpha = 0f; translationX = dp(8).toFloat(); visibility = View.VISIBLE
            animate().alpha(1f).translationX(0f).setDuration(250).start()
        }
        main.post(ampPoll); main.post(timerTick)
    }

    private fun exitRecordingUI() {
        main.removeCallbacks(ampPoll); main.removeCallbacks(timerTick)
        paused = false
        recordControls?.animate()?.alpha(0f)?.setDuration(200)?.withEndAction { recordControls?.visibility = View.GONE }
        // Mic can be repurposed to "speak a transform instruction" — if a transform flow
        // is still active (compose/busy), restore ITS bar state, not the normal one.
        // The MIC comes back either way: if the dictation produced nothing usable the
        // user must be able to speak the instruction again (it stayed hidden before).
        if (transformState != TransformState.IDLE) {
            transformCancelButton?.apply { visibility = View.VISIBLE; alpha = 1f }
            micWrap?.apply { visibility = View.VISIBLE; animate().alpha(1f).setDuration(250).start() }
        } else {
            iconGroup?.apply { visibility = View.VISIBLE; animate().alpha(1f).setDuration(250).start() }
            micWrap?.apply { visibility = View.VISIBLE; animate().alpha(1f).setDuration(250).start() }
        }
    }

    // Animation-free variant used when the keyboard is being torn down / restarted
    // (onFinishInputView, onStartInputView): a running ViewPropertyAnimator whose
    // withEndAction never fires on a detached view would leave the bar stuck showing
    // the recording controls the next time the keyboard is shown.
    private fun resetRecordingUIImmediate() {
        main.removeCallbacks(ampPoll); main.removeCallbacks(timerTick)
        paused = false
        recordControls?.apply { animate().cancel(); alpha = 1f; translationX = 0f; visibility = View.GONE }
        pauseBtn?.apply { text = IC_PAUSE; alpha = 1f }
        timerLabel?.text = "0:00"
        waveform?.reset()
        micWrap?.apply { animate().cancel(); alpha = 1f; visibility = View.VISIBLE }
        if (transformState != TransformState.IDLE) {
            transformCancelButton?.apply { visibility = View.VISIBLE; alpha = 1f }
        } else {
            iconGroup?.apply { animate().cancel(); alpha = 1f; visibility = View.VISIBLE }
        }
        setMicState(false)
    }

    private fun togglePause() {
        if (Build.VERSION.SDK_INT < 24) return
        try {
            if (!paused) {
                recorder?.pause(); paused = true; pauseStartMs = System.currentTimeMillis()
                pauseBtn?.text = IC_PLAY; pauseBtn?.alpha = 1f   // play = resume (waveform + timer freeze signal paused)
            } else {
                recorder?.resume(); paused = false
                pausedTotalMs += System.currentTimeMillis() - pauseStartMs
                pauseBtn?.text = IC_PAUSE; pauseBtn?.alpha = 1f
            }
        } catch (e: Exception) { /* pause unsupported — ignore */ }
    }

    // Desktop-widget waveform: a continuous travelling wave (18 bars) that mirrors the
    // overlay_html.py keyframes — bars oscillate on a ~0.9s loop, staggered per bar, and
    // grow taller with real-mic loudness.
    inner class WaveformView(ctx: android.content.Context) : View(ctx) {
        private val n = 18
        private var phase = 0.0
        private var level = 0.0f            // 0..1 smoothed real-mic loudness (0 on simulator)
        private val paint = android.graphics.Paint().apply { color = keyText; isAntiAlias = true }
        fun tick(realLevel: Float) {
            phase += 0.22                    // ~30fps → ~0.9s period like the desktop keyframes
            level += (realLevel.coerceIn(0f, 1f) - level) * 0.35f   // smooth toward target
            invalidate()
        }
        fun reset() { phase = 0.0; level = 0f; invalidate() }
        override fun onDraw(c: android.graphics.Canvas) {
            val bw = dp(2).toFloat(); val gap = dp(2).toFloat()
            val minH = dp(3).toFloat(); val maxH = dp(18).toFloat()
            val totalW = n * bw + (n - 1) * gap
            val startX = (width - totalW) / 2f
            val cy = height / 2f; val r = bw / 2f
            for (i in 0 until n) {
                val osc = 0.5 + 0.5 * Math.sin(phase - i * 0.55)       // travelling wave, staggered per bar
                val amp = (0.55f + 0.45f * level)                       // louder voice → taller (still animates at 0)
                val h = (minH + (maxH - minH) * osc.toFloat() * amp).coerceIn(minH, maxH)
                val x = startX + i * (bw + gap)
                c.drawRoundRect(x, cy - h / 2f, x + bw, cy + h / 2f, r, r, paint)
            }
        }
    }

    // ── keyboard layers ───────────────────────────────────────────────────────────
    private val lettersRows = arrayOf(
        arrayOf("q","w","e","r","t","y","u","i","o","p"),
        arrayOf("a","s","d","f","g","h","j","k","l"),
        arrayOf("z","x","c","v","b","n","m"),
    )
    private val numbersRows = arrayOf(
        arrayOf("1","2","3","4","5","6","7","8","9","0"),
        arrayOf("@","#","$","_","&","-","+","(",")","/"),
        arrayOf("*","\"","'",":",";","!","?"),
    )
    private val symbolsRows = arrayOf(
        arrayOf("~","`","|","•","√","π","÷","×","¶","∆"),
        arrayOf("£","¢","€","¥","^","°","=","{","}","\\"),
        arrayOf("%","©","®","™","✓","[","]"),
    )

    private fun showKeyboard() {
        hideKeyPreview()   // dismiss any stale preview bubble across a rebuild
        activeOverlay = null
        refreshBar()
        content?.removeAllViews()
        content?.addView(buildKeyboard())
    }

    private fun buildKeyboard(): View {
        letterKeyViews.clear(); shiftKeyView = null   // rebuilt fresh below
        val kb = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(6), 0, 0)
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        val rows = when (layer) { Layer.LETTERS -> lettersRows; Layer.NUMBERS -> numbersRows; Layer.SYMBOLS -> symbolsRows }
        // Row 1
        kb.addView(keyRow(rows[0]))
        // Row 2 (indented for letters)
        kb.addView(keyRow(rows[1], sideInset = if (layer == Layer.LETTERS) 0.5f else 0f))
        // Row 3: [shift/=\<] keys [backspace]
        val r3 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46))
                .apply { topMargin = 0 }
        }
        val shiftK = functionKey(if (layer == Layer.LETTERS) (if (capsLock) "⇪" else "⇧") else (if (layer == Layer.NUMBERS) "=\\<" else "?123"), 1.5f) {
            if (layer == Layer.LETTERS) onShift()
            else { layer = if (layer == Layer.NUMBERS) Layer.SYMBOLS else Layer.NUMBERS; showKeyboard() }
        }
        if (layer == Layer.LETTERS) shiftKeyView = shiftK as TextView
        r3.addView(shiftK)
        for (k in rows[2]) r3.addView(charKey(k, 1f))
        val backKey = functionKey("⌫", 1.5f) { }   // touch handler below drives it (with repeat)
        attachRepeat(backKey) { onBackspace() }
        r3.addView(backKey)
        kb.addView(r3)
        // Row 4: [?123/ABC] , [space] . [return]
        val r4 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46))
                .apply { topMargin = 0 }
        }
        r4.addView(functionKey(if (layer == Layer.LETTERS) "?123" else "ABC", 1.5f) {
            layer = if (layer == Layer.LETTERS) Layer.NUMBERS else Layer.LETTERS; showKeyboard()
        })
        val commaKey = charKey(",", 1f)
        // Comma: DOWN commits ","; hold 400ms → emoji picker (replaces the old long-click).
        keyTouch(commaKey, keyBg, fire = { onCharKey(",") }, longPress = { openEmoji() })
        r4.addView(commaKey)
        val space = functionKey("English (US)", 4f) { onSpace() } as TextView
        space.textSize = 12f
        space.background = keyDrawable(keyBg)      // key-colored, not a gray modifier
        space.setTextColor(mutedText)
        spaceTouch(space)                         // swipe to move cursor; tap inserts a space
        r4.addView(space)
        r4.addView(charKey(".", 1f))
        val ret = functionKey("↵", 1.5f) { onEnter() }
        (ret as TextView).apply { background = keyDrawable(returnBg); setTextColor(returnText) }
        keyTouch(ret as TextView, returnBg, { onEnter() })   // re-bind so pressed-state restores returnBg
        r4.addView(ret)
        kb.addView(r4)
        return kb
    }

    private fun keyRow(keys: Array<String>, sideInset: Float = 0f): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46))
                .apply { topMargin = 0 }
        }
        if (sideInset > 0) row.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 1, sideInset) })
        for (k in keys) row.addView(charKey(k, 1f))
        if (sideInset > 0) row.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 1, sideInset) })
        return row
    }

    private fun charKey(label: String, weight: Float): TextView {
        val isLetter = label.length == 1 && label[0].isLetter()
        return TextView(this).apply {
            tag = label                      // base label; live case computed on press
            text = casedChar(label); setTextColor(keyText); textSize = 20f; gravity = Gravity.CENTER
            typeface = geist
            background = keyDrawable(keyBg)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, weight)
                .apply { leftMargin = 0; rightMargin = 0 }
            // Fire on DOWN (never dropped by slide-within-slop). Case is read LIVE so a
            // one-shot/auto-cap flip (updated in place) commits the right case without a rebuild.
            keyTouch(this, keyBg, { onCharKey(casedChar(label)) }, preview = isLetter)
            if (isLetter) letterKeyViews.add(this)
        }
    }

    private fun functionKey(label: String, weight: Float, onTap: () -> Unit): View =
        TextView(this).apply {
            text = label; setTextColor(keyText); textSize = 15f; gravity = Gravity.CENTER
            typeface = geist
            background = keyDrawable(modBg)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, weight)
                .apply { leftMargin = 0; rightMargin = 0 }
            keyTouch(this, modBg, { onTap() })
        }

    // ── key handling ───────────────────────────────────────────────────────────────
    private fun onCharKey(ch: String) {
        commit(ch)
        // one-shot shift clears after a letter — update key labels IN PLACE (a full
        // showKeyboard() rebuild here raced the next rapid tap and dropped it).
        if (layer == Layer.LETTERS && shifted && !capsLock) { shifted = false; refreshLetterCaps() }
    }

    private fun commit(s: String) {
        // While composing a transform instruction, the SAME letter keys feed a local
        // buffer instead of the host app — the original selection is never touched
        // until Replace, which is what keeps it alive through the whole flow.
        if (transformState == TransformState.COMPOSE) {
            transformInstruction += s
            refreshTransformComposeUI()
            return
        }
        // Learn the just-finished word when a word boundary (space/punctuation) is typed.
        if (s.length == 1 && !s[0].isLetter()) {
            currentWordPrefix().let { if (it.length >= 2) learnWord(it) }
            // Also learn the bigram (prevWord → justFinishedWord) — the boundary char
            // isn't committed yet, so getTextBeforeCursor still ends with the finished word.
            lastTwoWords()?.let { learnBigram(it.first, it.second) }
        }
        currentInputConnection?.commitText(s, 1); updateSuggestions(); maybeAutoCap()
    }

    // Space key. Double-space after a word → ". " (period + space), Gboard-style.
    private fun onSpace() {
        if (transformState == TransformState.COMPOSE) { commit(" "); return }
        val ic = currentInputConnection
        if (ic != null) {
            val before = ic.getTextBeforeCursor(2, 0)?.toString() ?: ""
            // Exactly a single trailing space preceded by a word char (letter/digit).
            if (before.length == 2 && before[1] == ' ' && before[0].isLetterOrDigit()) {
                ic.deleteSurroundingText(1, 0)
                commit(". ")   // keeps updateSuggestions + auto-cap in one place
                return
            }
        }
        commit(" ")
    }

    // Move the text cursor one character left/right (Gboard-style spacebar-swipe).
    // Fails closed: a null InputConnection just no-ops.
    private fun sendCursor(right: Boolean) {
        val ic = currentInputConnection ?: return
        val code = if (right) android.view.KeyEvent.KEYCODE_DPAD_RIGHT else android.view.KeyEvent.KEYCODE_DPAD_LEFT
        ic.sendKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_DOWN, code))
        ic.sendKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_UP, code))
    }

    // Dedicated space-key touch handler: dragging horizontally scrubs the cursor
    // (~one char per 12dp of finger travel) instead of inserting a space; a plain tap
    // (little/no movement) still inserts a space via onSpace() on UP. Space commits on
    // UP (not a fast-typed letter, so no risk of dropping it).
    @Suppress("ClickableViewAccessibility")
    private fun spaceTouch(v: TextView) {
        val base = v.background
        var startX = 0f; var lastSteps = 0; var swiped = false
        val stepPx = dp(12).toFloat()
        v.isHapticFeedbackEnabled = true
        v.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    startX = e.rawX; lastSteps = 0; swiped = false
                    v.background = keyDrawable(pressBg)
                    try { v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP, HapticFeedbackConstants.FLAG_IGNORE_VIEW_SETTING) } catch (e2: Exception) {}
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val steps = ((e.rawX - startX) / stepPx).toInt()
                    if (steps != lastSteps) {
                        val delta = steps - lastSteps
                        repeat(kotlin.math.abs(delta)) { sendCursor(delta > 0) }
                        lastSteps = steps
                        if (kotlin.math.abs(steps) >= 1) swiped = true
                    }
                    true
                }
                MotionEvent.ACTION_UP -> { v.background = base; if (!swiped) onSpace(); true }
                MotionEvent.ACTION_CANCEL -> { v.background = base; true }
                else -> false
            }
        }
    }

    // Auto-capitalize at sentence starts: flip one-shot shift to match the editor's
    // caps mode, but only rebuild the keys when it actually changes.
    private fun maybeAutoCap() {
        if (layer != Layer.LETTERS || capsLock) return
        val caps = currentInputConnection?.getCursorCapsMode(
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES) ?: 0
        val desired = caps != 0
        if (desired != shifted) { shifted = desired; refreshLetterCaps() }  // in-place, no rebuild
    }

    private fun onShift() {
        // off → shift(one-shot) → caps-lock → off
        when {
            capsLock -> { capsLock = false; shifted = false }
            shifted -> { capsLock = true }
            else -> { shifted = true }
        }
        refreshLetterCaps()   // in-place caps/glyph swap (no full rebuild)
    }

    private fun onBackspace() {
        if (transformState == TransformState.COMPOSE) {
            if (transformInstruction.isNotEmpty()) transformInstruction = transformInstruction.dropLast(1)
            refreshTransformComposeUI()
            return
        }
        val ic = currentInputConnection ?: return
        val sel = ic.getSelectedText(0)
        if (sel != null && sel.isNotEmpty()) {
            ic.commitText("", 1)
        } else {
            // Delete a whole surrogate pair (emoji) as one, not a broken half-char.
            val before = ic.getTextBeforeCursor(2, 0) ?: ""
            val n = if (before.length >= 2 &&
                        Character.isSurrogatePair(before[before.length - 2], before[before.length - 1])) 2 else 1
            ic.deleteSurroundingText(n, 0)
        }
        updateSuggestions()
    }

    // Gboard-style: fire on touch-DOWN so fast taps that slide within slop are never
    // dropped (setOnClickListener drops them). Haptic + pressed-state on down. If a
    // longPress is given, DOWN starts a 400ms timer; the key commits on UP only if the
    // long-press didn't fire (used by comma → emoji). preview=true (letters only) shows
    // the enlarged-key bubble on down and dismisses it on up/cancel. Fails closed: a
    // haptic/preview error must never break the actual key commit.
    @Suppress("ClickableViewAccessibility")
    private fun keyTouch(v: TextView, baseColor: Int, fire: () -> Unit, longPress: (() -> Unit)? = null, preview: Boolean = false) {
        val base = v.background
        v.isHapticFeedbackEnabled = true
        var handled = false
        var lp: Runnable? = null
        v.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    handled = false
                    v.background = keyDrawable(pressBg)
                    try { v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP, HapticFeedbackConstants.FLAG_IGNORE_VIEW_SETTING) } catch (e2: Exception) {}
                    if (preview) showKeyPreview(v, v.text.toString())   // live case
                    if (longPress != null) {
                        lp = Runnable { handled = true; v.background = base; hideKeyPreview(); longPress() }
                        main.postDelayed(lp!!, 400)
                    } else { fire(); handled = true }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    lp?.let { main.removeCallbacks(it) }
                    v.background = base
                    hideKeyPreview()
                    if (!handled) fire()
                    true
                }
                MotionEvent.ACTION_CANCEL -> { lp?.let { main.removeCallbacks(it) }; v.background = base; hideKeyPreview(); true }
                else -> false
            }
        }
    }

    private fun showKeyPreview(anchor: View, label: String) {
        try {
            if (label.length != 1 || !label[0].isLetter()) return   // letters only
            if (keyPreview == null) {
                val tv = TextView(this).apply {
                    gravity = Gravity.CENTER; setTextColor(keyText); textSize = 26f; typeface = geist
                    background = rounded(keyBg, 10)
                }
                keyPreviewText = tv
                keyPreview = android.widget.PopupWindow(tv, dp(48), dp(56)).apply { isTouchable = false; isClippingEnabled = false }
            }
            keyPreviewText?.text = label
            val loc = IntArray(2); anchor.getLocationInWindow(loc)
            val x = loc[0] + anchor.width / 2 - dp(24)
            val y = loc[1] - dp(58)
            val kp = keyPreview!!
            if (kp.isShowing) kp.update(x, y, dp(48), dp(56)) else kp.showAtLocation(anchor, Gravity.NO_GRAVITY, x, y)
        } catch (e: Exception) {}
    }
    private fun hideKeyPreview() { try { keyPreview?.dismiss() } catch (e: Exception) {} }

    // Press-and-hold auto-repeat (backspace): fire once on down, then repeat every
    // 55ms after a 400ms hold until release.
    @Suppress("ClickableViewAccessibility")
    private fun attachRepeat(v: View, action: () -> Unit) {
        var repeat: Runnable? = null
        v.setOnTouchListener { view, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    try { view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP, HapticFeedbackConstants.FLAG_IGNORE_VIEW_SETTING) } catch (e2: Exception) {}
                    action()
                    repeat = object : Runnable {
                        override fun run() { action(); main.postDelayed(this, 55) }
                    }
                    main.postDelayed(repeat!!, 400)
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    repeat?.let { main.removeCallbacks(it) }; repeat = null
                    view.performClick(); true
                }
                else -> false
            }
        }
    }

    private fun onEnter() {
        if (transformState == TransformState.COMPOSE && transformInstruction.trim().isNotEmpty()) {
            sendTransform(); return
        }
        val ic = currentInputConnection ?: return
        val action = (currentInputEditorInfo?.imeOptions ?: 0) and EditorInfo.IME_MASK_ACTION
        if (action != EditorInfo.IME_ACTION_NONE && action != EditorInfo.IME_ACTION_UNSPECIFIED)
            ic.performEditorAction(action)
        else ic.commitText("\n", 1)
    }

    // ── suggestions (STAGE 1: basic — from vocabulary + current word prefix). ML
    // prediction/autocorrect is a later stage. ─────────────────────────────────────
    // updateSuggestions() is DEBOUNCED (~70ms) so the config read + 25k-word scan +
    // IPC text queries never run synchronously inside a keystroke commit — that was
    // janking the UI thread and dropping fast taps. Coalesced: only the last tap in
    // a burst computes suggestions.
    private fun updateSuggestions() {
        main.removeCallbacks(suggRunnable)
        main.postDelayed(suggRunnable, 70)
    }
    private fun doUpdateSuggestions() {
        if (transformState != TransformState.IDLE) return   // compose UI owns the suggestion strip
        val strip = suggestionStrip ?: return
        strip.removeAllViews()
        if (activeOverlay != null) return
        val word = currentWordPrefix()
        val picks = ArrayList<String>()
        if (word.isEmpty()) {
            // No prefix being typed → offer NEXT-WORD predictions for the previous word.
            val before = currentInputConnection?.getTextBeforeCursor(64, 0)?.toString()?.trimEnd() ?: ""
            // Last alphabetic token (ignoring trailing punctuation) — mirrors iOS and our
            // own learning extraction, so a bigram learned across a comma is offered back.
            val prev = Regex("[\\p{L}']+").findAll(before).lastOrNull()?.value?.lowercase()
            if (prev.isNullOrEmpty()) return
            loadLearnedBg()
            val seen = HashSet<String>(); seen.add(prev)
            fun add(w: String) {
                val lc = w.lowercase()
                if (lc !in seen && picks.size < 3) { seen.add(lc); picks.add(w) }
            }
            // 1) personal bigrams (by how often you've followed prev with this word)
            learnedBg[prev]?.entries?.sortedByDescending { it.value }?.forEach { add(it.key) }
            // 2) bundled bigram table (already ordered most-likely first)
            bigrams[prev]?.forEach { if (picks.size < 3) add(it) }
        } else {
            val pfx = word.lowercase()
            loadLearned()
            val seen = HashSet<String>(); seen.add(pfx)
            fun cased(w: String): String = when {
                word.length > 1 && word.all { it.isUpperCase() } -> w.uppercase()
                word[0].isUpperCase() -> w.replaceFirstChar { it.uppercase() }
                else -> w
            }
            fun add(w: String) { val lc = w.lowercase(); if (lc !in seen && picks.size < 3) { seen.add(lc); picks.add(cased(w)) } }
            // 1) personal learned words (by how often you've used them)
            learned.keys.filter { it.startsWith(pfx) }.sortedByDescending { learned[it] ?: 0 }.forEach { add(it) }
            // 2) your custom vocabulary
            readConfig()?.optJSONArray("vocabulary")?.let { v ->
                for (i in 0 until v.length()) {
                    val w = v.optJSONObject(i)?.optString("word") ?: ""
                    if (w.lowercase().startsWith(pfx)) add(w)
                    if (picks.size >= 3) break
                }
            }
            // 3) frequency dictionary (already ordered most-common first)
            for (w in dictWords) { if (picks.size >= 3) break; if (w.startsWith(pfx)) add(w) }
        }
        // Word→emoji suggestion: an EXACT full-word match on the typed prefix adds an
        // emoji chip (shown first, larger) that REPLACES the word with the emoji.
        val emoji = if (word.isNotEmpty()) emojiKw[word.lowercase()]?.firstOrNull() else null
        val cells = ArrayList<View>()
        if (emoji != null) {
            cells.add(suggestionCell(emoji, isEmoji = true) {
                val ic = currentInputConnection ?: return@suggestionCell
                val w = currentWordPrefix()
                if (w.isNotEmpty()) ic.deleteSurroundingText(w.length, 0)
                ic.commitText("$emoji ", 1)
                updateSuggestions()
            })
        }
        // Fill the remaining cells (up to 3 total) with word completions.
        val wordCap = 3 - cells.size
        for (p in picks.take(wordCap)) {
            cells.add(suggestionCell(p, isEmoji = false) { replaceCurrentWord(p) })
        }
        // Distribute like Gboard (and iOS fillEqually): the present cells split the full
        // width equally with thin dividers between them — so fewer picks each grow wider
        // and stay centered, never left-packed (no blank padding cells on the right).
        for (i in cells.indices) {
            if (i > 0) strip.addView(suggestionDivider())
            strip.addView(cells[i])
        }
    }

    // One equal-width, centered suggestion cell (weight 1). Emoji cells render larger
    // and drop the Geist typeface so the glyph shows in its native color font.
    private fun suggestionCell(label: String, isEmoji: Boolean, onTap: () -> Unit): View =
        TextView(this).apply {
            text = label; setTextColor(keyText); gravity = Gravity.CENTER
            textSize = if (isEmoji) 22f else 14f
            if (!isEmoji) typeface = geist
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
            isClickable = true
            setOnClickListener { onTap() }
        }

    // Thin 1px vertical divider (mutedText @ ~20% alpha) between suggestion cells.
    private fun suggestionDivider(): View = View(this).apply {
        setBackgroundColor((mutedText and 0x00FFFFFF) or (0x33 shl 24))
        layoutParams = LinearLayout.LayoutParams(1, ViewGroup.LayoutParams.MATCH_PARENT)
            .apply { topMargin = dp(8); bottomMargin = dp(8) }
    }

    private fun currentWordPrefix(): String {
        val ic = currentInputConnection ?: return ""
        val before = ic.getTextBeforeCursor(32, 0)?.toString() ?: return ""
        val m = Regex("[\\p{L}']+$").find(before)
        return m?.value ?: ""
    }

    private fun replaceCurrentWord(word: String) {
        val ic = currentInputConnection ?: return
        val prefix = currentWordPrefix()
        if (prefix.isNotEmpty()) ic.deleteSurroundingText(prefix.length, 0)
        ic.commitText("$word ", 1)
        learnWord(word)                     // accepting a suggestion teaches it too
        updateSuggestions()
    }

    // ── overlays ────────────────────────────────────────────────────────────────
    private fun toggleOverlay(which: String) {
        if (activeOverlay == which) { showKeyboard(); return }
        activeOverlay = which
        refreshBar()
        content?.removeAllViews()
        content?.addView(buildOverlay(which))
        suggestionStrip?.removeAllViews()
    }

    private fun buildOverlay(which: String): View {
        val wrap = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(8), dp(8), dp(8), dp(8))
            layoutParams = FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(230))
        }
        val cfg = readConfig()
        val deviceName = cfg?.optString("deviceName", "your computer") ?: "your computer"
        // header: LABEL ........... action  ⌨(back to typing)
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(6), dp(2), dp(6), dp(10))
        }
        header.addView(TextView(this).apply {
            text = which.uppercase(); setTextColor(mutedText); textSize = 11f
            letterSpacing = 0.16f; typeface = mono ?: Typeface.MONOSPACE
        })
        header.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 1, 1f) })
        header.addView(TextView(this).apply {
            text = when (which) {
                "snippets" -> "Tap to expand"
                "history" -> "Tap to insert"
                "clipboard" -> "Tap to insert"
                "vocabulary" -> "${cfg?.optJSONArray("vocabulary")?.length() ?: 0} words"
                else -> "→ $deviceName"
            }
            setTextColor(mutedText); textSize = 11f
            if (which == "vocabulary") typeface = mono ?: Typeface.MONOSPACE
            setPadding(0, 0, dp(10), 0)
        })
        header.addView(TextView(this).apply {   // return-to-keyboard
            text = "⌨"; setTextColor(iconTint); textSize = 15f
            setOnClickListener { showKeyboard() }
        })
        wrap.addView(header)

        val listScroll = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
        }
        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        listScroll.addView(list)
        when (which) {
            "snippets" -> {
                val arr = cfg?.optJSONArray("snippets")
                if (arr == null || arr.length() == 0) list.addView(emptyRow("No snippets yet"))
                else for (i in 0 until arr.length()) {
                    val s = arr.optJSONObject(i) ?: continue
                    val trg = s.optString("label").ifEmpty { s.optString("trigger") }
                    val exp = s.optString("expansion")
                    if (exp.isEmpty()) continue
                    list.addView(overlayRow(trg, exp, ACCENT) { currentInputConnection?.commitText(exp, 1); showKeyboard() })
                }
                list.addView(footerRow("+ New snippet") { openCanvas() })
            }
            "history" -> {
                val arr = cfg?.optJSONArray("history")
                if (arr == null || arr.length() == 0) list.addView(emptyRow("No recent dictations"))
                else for (i in 0 until arr.length()) {
                    val h = arr.optJSONObject(i) ?: continue
                    val t = h.optString("text"); if (t.isEmpty()) continue
                    list.addView(historyRow(formatTime(h.optString("at")), t) {
                        currentInputConnection?.commitText(t, 1); showKeyboard()
                    })
                }
                list.addView(footerRow("See all history") { openCanvas() })
            }
            "clipboard" -> {
                loadClipboardHistoryIfNeeded()
                if (clipboardCache.isEmpty()) list.addView(emptyRow("No clipboard items yet — copy something to get started"))
                else {
                    for ((t, at) in clipboardCache) {
                        list.addView(historyRow(formatTime(at), t) {
                            currentInputConnection?.commitText(t, 1); showKeyboard()
                        })
                    }
                    list.addView(footerRow("Clear clipboard history") { clearClipboardHistory() })
                }
            }
            "vocabulary" -> {
                val arr = cfg?.optJSONArray("vocabulary")
                list.addView(dashedAddRow("+ Add a word Flume keeps mishearing…") { openCanvas() })
                if (arr != null && arr.length() > 0) {
                    val words = ArrayList<Pair<String, String>>()
                    for (i in 0 until arr.length()) {
                        val o = arr.optJSONObject(i) ?: continue
                        val w = o.optString("word"); if (w.isEmpty()) continue
                        words.add(Pair(w, o.optString("phonetic")))
                    }
                    if (words.isNotEmpty()) list.addView(flowChips(words))
                }
            }
            else -> { // canvas — v1.5 (data not plumbed yet)
                list.addView(emptyRow("Open the Flume app to send text, links, and images to $deviceName."))
            }
        }
        wrap.addView(listScroll)
        return wrap
    }

    private fun formatTime(iso: String?): String {
        if (iso == null || iso.length < 16) return ""
        val hm = iso.substring(11, 16)                       // "HH:MM" (UTC)
        val h = hm.substring(0, 2).trimStart('0').ifEmpty { "0" }
        return h + hm.substring(2)                            // "H:MM"
    }

    private fun ellipsize(s: String, max: Int): String {
        if (s.length <= max) return s
        var end = max
        if (Character.isHighSurrogate(s[end - 1])) end--     // don't split a surrogate pair
        return s.substring(0, end) + "…"
    }

    private fun historyRow(time: String, body: String, onTap: () -> Unit): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            background = rounded(cardBg, 12); setPadding(dp(12), dp(12), dp(12), dp(12))
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { bottomMargin = dp(6) }
            isClickable = true; setOnClickListener { onTap() }
        }
        row.addView(TextView(this).apply {
            text = time; setTextColor(mutedText); textSize = 12f; typeface = mono ?: Typeface.MONOSPACE
            setPadding(0, 0, dp(10), 0)
        })
        row.addView(TextView(this).apply {
            text = ellipsize(body, 40); setTextColor(keyText); textSize = 14f; typeface = geist
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        })
        row.addView(TextView(this).apply { text = "→"; setTextColor(mutedText); textSize = 15f })
        return row
    }

    private fun footerRow(label: String, onTap: () -> Unit): View = TextView(this).apply {
        text = label; setTextColor(if (label.startsWith("+")) ACCENT else mutedText); textSize = 13f
        typeface = geist
        gravity = Gravity.CENTER; setPadding(dp(12), dp(12), dp(12), dp(12))
        isClickable = true; setOnClickListener { onTap() }
    }

    private fun dashedAddRow(label: String, onTap: () -> Unit): View {
        val bg = GradientDrawable().apply {
            cornerRadius = dp(12).toFloat()
            setStroke(dp(1), ACCENT, dp(4).toFloat(), dp(3).toFloat())
        }
        return TextView(this).apply {
            text = label; setTextColor(ACCENT); textSize = 14f; typeface = geist
            background = bg; setPadding(dp(12), dp(12), dp(12), dp(12))
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { bottomMargin = dp(8) }
            isClickable = true; setOnClickListener { onTap() }
        }
    }

    // Manual flow-wrap (no Flexbox dep): break to a new row by estimated chip width.
    private fun flowChips(words: List<Pair<String, String>>): View {
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val maxW = resources.displayMetrics.widthPixels - dp(24)
        var row: LinearLayout? = null
        var used = 0
        for ((w, ph) in words) {
            val est = dp(28) + (w.length + (if (ph.isEmpty()) 0 else ph.length + 2)) * dp(9)
            if (row == null || used + est > maxW) {
                row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
                col.addView(row, LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) })
                used = 0
            }
            val chip = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                background = rounded(cardBg, 999); setPadding(dp(12), dp(8), dp(12), dp(8))
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { rightMargin = dp(8) }
                isClickable = true; setOnClickListener { currentInputConnection?.commitText("$w ", 1) }
            }
            chip.addView(TextView(this).apply { text = w; setTextColor(keyText); textSize = 14f; typeface = geist })
            if (ph.isNotEmpty()) chip.addView(TextView(this).apply {
                text = ph; setTextColor(mutedText); textSize = 11f; typeface = mono ?: Typeface.MONOSPACE
                setPadding(dp(6), 0, 0, 0)
            })
            row!!.addView(chip)
            used += est
        }
        return col
    }

    private fun emptyRow(msg: String): View = TextView(this).apply {
        text = msg; setTextColor(mutedText); textSize = 14f; typeface = geist; setPadding(dp(12), dp(16), dp(12), dp(16))
    }

    private fun overlayRow(title: String, sub: String, titleColor: Int, onTap: () -> Unit): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            background = rounded(cardBg, 12); setPadding(dp(12), dp(12), dp(12), dp(12))
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { bottomMargin = dp(6) }
            isClickable = true; setOnClickListener { onTap() }
        }
        row.addView(TextView(this).apply {
            text = ellipsize(title, 40)
            setTextColor(titleColor); textSize = 14f
            typeface = if (titleColor == ACCENT) (mono ?: Typeface.MONOSPACE) else geist
        })
        if (sub.isNotEmpty()) {
            row.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 1, 1f) })
            row.addView(TextView(this).apply {
                text = ellipsize(sub, 28)
                setTextColor(mutedText); textSize = 13f; typeface = geist
            })
        }
        return row
    }

    private fun openCanvas() {
        try {
            val i = packageManager.getLaunchIntentForPackage(packageName)
            i?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            if (i != null) startActivity(i)
        } catch (e: Exception) { setStatus("Couldn't open Flume") }
    }

    // ── emoji: Recents tab + the full bundled library (flume_emoji.txt, 9 groups). ──
    private fun emojiCategories(): List<Pair<String, List<String>>> {
        val out = ArrayList<Pair<String, List<String>>>()
        out.add("🕘" to emojiRecents.toList())
        emojiLib.forEachIndexed { i, (_, list) ->
            out.add((emojiTabGlyphs.getOrNull(i) ?: "•") to list)
        }
        return out
    }

    private fun openEmoji() {
        activeOverlay = null; refreshBar(); suggestionStrip?.removeAllViews()
        content?.removeAllViews(); content?.addView(buildEmoji())
    }

    private fun buildEmoji(): View {
        val cats = emojiCategories()
        if (emojiCatIdx !in cats.indices) emojiCatIdx = 1
        val wrap = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(6), dp(6), dp(6), dp(6))
            layoutParams = FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(230))
        }
        val tabRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        cats.forEachIndexed { i, c ->
            tabRow.addView(TextView(this).apply {
                text = c.first; textSize = 18f; gravity = Gravity.CENTER
                setPadding(dp(10), dp(4), dp(10), dp(4))
                background = rounded(if (i == emojiCatIdx) highlightBg else Color.TRANSPARENT, 8)
                setOnClickListener { emojiCatIdx = i; content?.removeAllViews(); content?.addView(buildEmoji()) }
            })
        }
        wrap.addView(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(tabRow) })

        var list = cats[emojiCatIdx].second
        if (list.isEmpty()) list = cats[1].second   // recents empty → smileys
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        var rowV: LinearLayout? = null
        list.forEachIndexed { idx, e ->
            if (idx % 8 == 0) {
                rowV = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
                col.addView(rowV)
            }
            rowV!!.addView(TextView(this).apply {
                text = e; textSize = 22f; gravity = Gravity.CENTER
                layoutParams = LinearLayout.LayoutParams(0, dp(44), 1f)
                setOnClickListener { commitEmoji(e) }
            })
        }
        wrap.addView(ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
            addView(col)
        })

        val bottom = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46)).apply { topMargin = dp(6) }
        }
        bottom.addView(functionKey("ABC", 2f) { showKeyboard() })
        bottom.addView(functionKey("⌫", 1f) { onBackspace() })
        wrap.addView(bottom)
        return wrap
    }

    private fun commitEmoji(e: String) {
        currentInputConnection?.commitText(e, 1)
        emojiRecents.remove(e); emojiRecents.add(0, e)
        while (emojiRecents.size > 24) emojiRecents.removeAt(emojiRecents.size - 1)
    }

    // ── mic / recording (unchanged: dictation via groq-proxy) ──────────────────────
    private fun onMicTap() {
        if (secure || busy) return
        // In COMPOSE the mic speaks the transform INSTRUCTION (handled in stopAndTranscribe).
        // In BUSY/PREVIEW there is nowhere for a transcript to go except the host field —
        // which would destroy the very selection we're about to replace. Inert instead.
        if (transformState == TransformState.BUSY || transformState == TransformState.PREVIEW) return
        if (activeOverlay != null) showKeyboard()
        if (!recording) startRecording() else stopAndTranscribe()
    }

    private fun startRecording() {
        try {
            val f = File(cacheDir, "flume_rec_" + System.currentTimeMillis() + ".m4a")
            val r = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(this) else @Suppress("DEPRECATION") MediaRecorder()
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioEncodingBitRate(128000)
            r.setAudioSamplingRate(44100)
            r.setOutputFile(f.absolutePath)
            r.prepare(); r.start()
            recorder = r; audioFile = f; recording = true
            // IDI-163: remember WHICH field this dictation belongs to and when it began.
            recordingSession = inputSession
            recordingStartedAtMs = System.currentTimeMillis()
            setMicState(true)
            enterRecordingUI()
            playSound("flume_start")
        } catch (e: Exception) {
            releaseRecorder(); recording = false; setMicState(false)
            setStatus("Mic unavailable — enable microphone for Flume in the app")
        }
    }

    private fun abortRecording(immediate: Boolean = false) {
        stopAndReleaseRecorder()
        setMicState(false)
        if (immediate) resetRecordingUIImmediate() else exitRecordingUI()
    }

    /** Single place that tears the recorder down — safe to call when idle. */
    private fun stopAndReleaseRecorder() {
        recording = false
        try { recorder?.stop() } catch (e: Exception) {}
        releaseRecorder()
        audioFile?.let { try { it.delete() } catch (e: Exception) {} }
        audioFile = null
    }

    private fun stopAndTranscribe() {
        recording = false
        playSound("flume_stop")
        var ok = true
        try { recorder?.stop() } catch (e: Exception) { ok = false }
        releaseRecorder()
        val f = audioFile; audioFile = null; setMicState(false); exitRecordingUI()
        if (!ok || f == null || !f.exists() || f.length() == 0L) {
            f?.let { try { it.delete() } catch (e: Exception) {} }; return
        }
        busy = true
        // Snapshot the field identity NOW; `inputSession` may move while we're on the wire.
        val session = recordingSession
        val startedAt = recordingStartedAtMs
        val composing = transformState == TransformState.COMPOSE
        Thread {
            val text = try { transcribe(f) } catch (e: Exception) { null }
            try { f.delete() } catch (e: Exception) {}
            main.post {
                busy = false
                val t = text
                if (t.isNullOrBlank()) return@post
                if (!canCommitDictation(session, startedAt)) return@post
                // Mic is repurposed while composing a transform instruction (same button,
                // mode-dependent meaning) — route the transcript into the instruction
                // buffer instead of the host app, which would destroy the selection we
                // are about to transform. Mirrors iOS KeyboardViewController.swift:1799.
                if (composing && transformState == TransformState.COMPOSE) {
                    transformInstruction = t.trim()
                    refreshTransformComposeUI()
                    playSound("flume_done")
                    sendTransform()
                    return@post
                }
                currentInputConnection?.commitText(t + " ", 1); updateSuggestions(); playSound("flume_done")
            }
        }.start()
    }

    /**
     * IDI-163 field-identity guard. A transcript may only be inserted when it is going
     * back into the exact field it was dictated into, that field is still not a password
     * field (checked LIVE — `secure` was only sampled at mic-tap time), and the result
     * isn't so old that the user has moved on. Otherwise: drop, and say so.
     */
    private fun canCommitDictation(session: Long, startedAtMs: Long): Boolean {
        if (session != inputSession) {
            flashStatus("Dictation discarded — the text field changed")
            return false
        }
        if (System.currentTimeMillis() - startedAtMs > DICTATION_MAX_AGE_MS) {
            flashStatus("Dictation discarded — took too long")
            return false
        }
        if (isSecureField(currentInputEditorInfo)) {
            flashStatus("Dictation discarded — secure field")
            return false
        }
        return true
    }

    private fun releaseRecorder() { try { recorder?.release() } catch (e: Exception) {}; recorder = null }

    // ── transcription pipeline ─────────────────────────────────────────────────────
    // Config is CACHED in memory and only re-read/parsed when the file's mtime
    // changes — reading + JSON-parsing it on every keystroke was janking the UI
    // thread mid-typing and dropping fast keystrokes.
    private var cfgCache: JSONObject? = null
    private var cfgMtime = -1L
    private fun readConfig(): JSONObject? = try {
        val cfg = File(filesDir, "flume_kbd_config.json")
        if (!cfg.exists()) { cfgCache = null; cfgMtime = -1L; null }
        else {
            val m = cfg.lastModified()
            if (m != cfgMtime || cfgCache == null) {
                val parsed = try { JSONObject(cfg.readText()) } catch (e: Exception) { null }
                // NEVER cache a FAILED parse against its mtime. Doing so poisoned the
                // cache: a half-written / truncated snapshot made every later call
                // return null until the app happened to rewrite the file, which in turn
                // silently threw away transcripts (IDI-162). A failed parse resets the
                // mtime so the very next call retries the read.
                if (parsed != null) { cfgCache = parsed; cfgMtime = m }
                else { cfgCache = null; cfgMtime = -1L }
            }
            cfgCache
        }
    } catch (e: Exception) { null }

    // ── clipboard (self-contained: unlike flume_kbd_config.json above, this file is
    // written AND read by this service itself; the main app never touches clipboard content)
    private fun clipboardFile(): File = File(filesDir, "flume_kbd_clipboard.json")

    private fun loadClipboardHistoryIfNeeded() {
        if (clipboardLoaded) return
        clipboardLoaded = true
        try {
            val f = clipboardFile()
            if (!f.exists()) return
            val obj = JSONObject(f.readText())
            val arr = obj.optJSONArray("items") ?: return
            clipboardCache.clear()
            for (i in 0 until arr.length()) {
                val item = arr.optJSONObject(i) ?: continue
                val text = item.optString("text"); if (text.isEmpty()) continue
                clipboardCache.add(Pair(text, item.optString("at")))
            }
        } catch (e: Exception) {}
    }

    private fun saveClipboardHistory() {
        try {
            val arr = JSONArray()
            for ((text, at) in clipboardCache.take(CLIPBOARD_CAP)) {
                arr.put(JSONObject().apply { put("text", text); put("at", at) })
            }
            val obj = JSONObject().apply { put("items", arr) }
            clipboardFile().writeText(obj.toString())
        } catch (e: Exception) {}
    }

    // java.time requires API 26+ without desugaring (not configured in this project's
    // build.gradle) — SimpleDateFormat works on every supported API level instead.
    private fun nowIsoUtc(): String {
        val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US)
        fmt.timeZone = TimeZone.getTimeZone("UTC")
        return fmt.format(Date())
    }

    private fun clearClipboardHistory() {
        clipboardCache.clear()
        saveClipboardHistory()
        showKeyboard()
    }

    // Fires on every clipboard change (listener) and as a fallback on every new input
    // session (onStartInputView) in case the service was relaunched since the last change.
    private fun checkClipboardForNewContent() {
        try {
            // Inert while a password field is focused (same posture as the mic): whatever
            // is on the clipboard right then is very likely a credential the user is
            // pasting out of a password manager — never persist it (IDI-164).
            if (secure) return
            if (!((readConfig()?.optBoolean("clipboardHistoryEnabled", true)) ?: true)) return
            val cm = getSystemService(CLIPBOARD_SERVICE) as? ClipboardManager ?: return
            val clip = cm.primaryClip ?: return
            val desc = clip.description
            if (!desc.hasMimeType(ClipDescription.MIMETYPE_TEXT_PLAIN) && !desc.hasMimeType(ClipDescription.MIMETYPE_TEXT_HTML)) return
            // Respect the password-manager convention for "don't capture this" content.
            if (Build.VERSION.SDK_INT >= 33 && desc.extras?.getBoolean(ClipDescription.EXTRA_IS_SENSITIVE, false) == true) return
            if (clip.itemCount == 0) return
            val text = clip.getItemAt(0).coerceToText(applicationContext)?.toString() ?: return
            if (text.isEmpty()) return
            val hash = text.hashCode()
            if (hash == lastClipHash) return
            lastClipHash = hash

            loadClipboardHistoryIfNeeded()
            val stored = if (text.length > CLIPBOARD_ENTRY_CHAR_CAP) text.take(CLIPBOARD_ENTRY_CHAR_CAP) else text
            clipboardCache.removeAll { it.first == stored }
            clipboardCache.add(0, Pair(stored, nowIsoUtc()))
            if (clipboardCache.size > CLIPBOARD_CAP) {
                while (clipboardCache.size > CLIPBOARD_CAP) clipboardCache.removeAt(clipboardCache.size - 1)
            }
            saveClipboardHistory()

            pendingQuickPaste = text
            refreshQuickPasteChip()
        } catch (e: Exception) {}
    }

    // Shared bar-chip slot: shows whichever ephemeral affordance is most recent — a
    // just-replaced transform's Undo takes priority over an older pending quick-paste,
    // since it's the more contextually relevant action. The two never show at once;
    // that's an acceptable, expected degrade (newest ephemeral action wins).
    private fun refreshQuickPasteChip() {
        val chip = quickPasteChip ?: return
        val undo = pendingUndo
        val text = pendingQuickPaste
        when {
            undo != null -> { chip.text = "↩︎ Undo (${undo.first} chars)"; chip.visibility = View.VISIBLE }
            text != null && text.isNotEmpty() -> {
                chip.text = "📋 " + if (text.length > 8) text.take(8) + "…" else text
                chip.visibility = View.VISIBLE
            }
            else -> chip.visibility = View.GONE
        }
    }

    private fun tapQuickPasteChip() {
        pendingUndo?.let { (length, original) ->
            undoRunnable?.let { main.removeCallbacks(it) }
            val ic = currentInputConnection
            ic?.deleteSurroundingText(length, 0)
            ic?.commitText(original, 1)
            pendingUndo = null
            refreshQuickPasteChip()
            return
        }
        val text = pendingQuickPaste ?: return
        currentInputConnection?.commitText(text, 1)
        pendingQuickPaste = null
        refreshQuickPasteChip()
    }

    // ── transform (select text elsewhere → instruction → LLM rewrite → replace) ─────────
    /** Opt-in via config AND never on a secure field (same posture as the mic). */
    private fun transformAvailable(): Boolean =
        readConfig()?.optBoolean("transformEnabled", false) == true && !secure

    private fun onTransformTap() {
        // Inert on secure fields — checked BEFORE any getSelectedText() so a password
        // field's contents are never even read, let alone sent to the LLM (IDI-164).
        if (secure || isSecureField(currentInputEditorInfo)) {
            flashTransformMessage("Not available in secure fields")
            return
        }
        if (readConfig()?.optBoolean("transformEnabled", false) != true || transformState != TransformState.IDLE) return
        val selected = currentInputConnection?.getSelectedText(0)?.toString()?.trim() ?: ""
        if (selected.isEmpty()) {
            flashTransformMessage("Select some text first")
            return
        }
        // REFUSE oversized selections. Truncating to the cap and then replacing the WHOLE
        // selection with the transformed prefix silently destroyed the tail (IDI-164).
        if (selected.length > TRANSFORM_SELECTION_CHAR_CAP) {
            flashTransformMessage("Selection too long — max $TRANSFORM_SELECTION_CHAR_CAP characters")
            return
        }
        transformOriginalText = selected
        transformInstruction = ""
        enterCompose()
    }

    private fun flashTransformMessage(msg: String) {
        suggestionStrip?.removeAllViews()
        suggestionStrip?.addView(TextView(this).apply {
            text = msg; setTextColor(mutedText); textSize = 13f; gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        })
        restoreStripSoon(1500)
    }

    /** Transient message in the suggestion strip (mic/permission/guard failures). */
    private fun flashStatus(msg: String) {
        setStatus(msg)
        restoreStripSoon(2000)
    }

    // The suggestion strip is shared by suggestions, the compose UI and transient
    // messages — put back whichever one the CURRENT state owns, not just suggestions
    // (restoring suggestions while composing wiped the instruction preview).
    private fun restoreStripSoon(delayMs: Long) {
        main.postDelayed({
            when (transformState) {
                TransformState.COMPOSE -> refreshTransformComposeUI()
                TransformState.IDLE -> updateSuggestions()
                else -> { }
            }
        }, delayMs)
    }

    private fun enterCompose() {
        transformState = TransformState.COMPOSE
        iconGroup?.visibility = View.GONE
        transformButton?.visibility = View.GONE
        transformCancelButton?.visibility = View.VISIBLE
        refreshTransformComposeUI()
    }

    private fun exitCompose() {
        transformState = TransformState.IDLE
        transformInstruction = ""; transformOriginalText = ""; transformRewrite = ""
        iconGroup?.apply { visibility = View.VISIBLE; alpha = 1f }
        micWrap?.apply { visibility = View.VISIBLE; alpha = 1f }
        transformButton?.visibility = if (transformAvailable()) View.VISIBLE else View.GONE
        transformCancelButton?.visibility = View.GONE
        showKeyboard()
        updateSuggestions()
    }

    /**
     * Hard reset used when the input session changes (new field / app switch). Without
     * it a compose left over from the previous field kept eating every keystroke into
     * `transformInstruction`, and a stale PREVIEW could Replace into the wrong field.
     * The caller is responsible for rebuilding the key area (onStartInputView calls
     * showKeyboard() straight after).
     */
    private fun resetTransformState() {
        val wasActive = transformState != TransformState.IDLE
        transformState = TransformState.IDLE
        transformInstruction = ""; transformOriginalText = ""; transformRewrite = ""
        if (wasActive) {
            iconGroup?.apply { animate().cancel(); visibility = View.VISIBLE; alpha = 1f }
            micWrap?.apply { animate().cancel(); visibility = View.VISIBLE; alpha = 1f }
        }
        transformCancelButton?.visibility = View.GONE
        transformButton?.visibility = if (transformAvailable()) View.VISIBLE else View.GONE
    }

    // Suggestion-strip band is repurposed while composing: the growing instruction
    // preview (typed via the SAME letter keys — see commit()/onSpace()/onBackspace()
    // below) plus a horizontally-scrollable row of one-tap presets.
    private fun refreshTransformComposeUI() {
        val strip = suggestionStrip ?: return
        strip.removeAllViews()
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            setPadding(dp(8), 0, dp(8), 0)
        }
        row.addView(TextView(this).apply {
            text = transformInstruction.ifEmpty { "Type or tap a preset…" }
            setTextColor(if (transformInstruction.isEmpty()) mutedText else keyText)
            textSize = 13f; ellipsize = android.text.TextUtils.TruncateAt.START; maxLines = 1
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        })
        val chipsScroll = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false }
        val chips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        for ((title, instruction) in transformPresets) {
            chips.addView(TextView(this).apply {
                text = title; setTextColor(keyText); textSize = 12f; typeface = geist
                background = rounded(highlightBg, 13)
                setPadding(dp(10), dp(6), dp(10), dp(6))
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                    .apply { marginEnd = dp(6) }
                setOnClickListener { fireTransformPreset(instruction) }
            })
        }
        chipsScroll.addView(chips)
        row.addView(chipsScroll)
        strip.addView(row)
    }

    private fun fireTransformPreset(instruction: String) {
        transformInstruction = instruction
        sendTransform()
    }

    private fun sendTransform() {
        if (transformState != TransformState.COMPOSE) return
        val instruction = transformInstruction.trim()
        transformState = TransformState.BUSY
        refreshTransformBusyUI()
        val isImprovise = instruction.isEmpty()
        val system = if (isImprovise) IMPROVISE_SYSTEM_PROMPT else TRANSFORM_SYSTEM_PROMPT
        val user = if (isImprovise) transformOriginalText
            else "INSTRUCTION: $instruction\n\nTEXT:\n$transformOriginalText"
        Thread {
            val raw = try { proxyChat(system, user) } catch (e: Exception) { null }
            main.post {
                if (transformState != TransformState.BUSY) return@post   // cancelled meanwhile
                try {
                    if (raw.isNullOrEmpty()) {
                        failTransform("Couldn't transform — try again")
                    } else {
                        transformRewrite = stripTransformWrapping(raw, transformOriginalText)
                        transformState = TransformState.PREVIEW
                        refreshTransformPreviewUI()
                    }
                } catch (e: Exception) {
                    failTransform("Couldn't transform — try again")
                }
            }
        }.start()
    }

    /**
     * EVERY transform failure path must land here. BUSY replaced the whole key area
     * with a spinner (refreshTransformBusyUI), so a failure branch that only touched
     * the suggestion strip left the user with a bricked keyboard — no keys at all and
     * no way back (IDI-164). This rebuilds the real keyboard and returns to COMPOSE so
     * the instruction can be edited and retried.
     */
    private fun failTransform(msg: String) {
        transformState = TransformState.COMPOSE
        iconGroup?.visibility = View.GONE
        transformButton?.visibility = View.GONE
        transformCancelButton?.apply { visibility = View.VISIBLE; alpha = 1f }
        micWrap?.apply { visibility = View.VISIBLE; alpha = 1f }
        showKeyboard()                 // ← the spinner is replaced by the real keys again
        refreshTransformComposeUI()
        flashTransformMessage(msg)
    }

    private fun refreshTransformBusyUI() {
        val wrap = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            layoutParams = FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        wrap.addView(android.widget.ProgressBar(this).apply {
            layoutParams = LinearLayout.LayoutParams(dp(28), dp(28))
        })
        wrap.addView(TextView(this).apply {
            text = "Transforming…"; setTextColor(mutedText); textSize = 13f; gravity = Gravity.CENTER
            setPadding(0, dp(8), 0, 0)
        })
        content?.removeAllViews(); content?.addView(wrap)
    }

    private fun refreshTransformPreviewUI() {
        val wrap = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(230))
            setPadding(dp(8), dp(8), dp(8), dp(8))
        }
        val scroll = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
        }
        scroll.addView(TextView(this).apply {
            text = transformRewrite; setTextColor(keyText); textSize = 14f; typeface = geist
        })
        wrap.addView(scroll)
        val buttons = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(44)).apply { topMargin = dp(8) }
        }
        buttons.addView(TextView(this).apply {
            text = "Cancel"; setTextColor(mutedText); textSize = 14f; gravity = Gravity.CENTER
            background = rounded(highlightBg, 10)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply { marginEnd = dp(4) }
            setOnClickListener { exitCompose() }
        })
        buttons.addView(TextView(this).apply {
            text = "Replace"; setTextColor(Color.WHITE); textSize = 14f; gravity = Gravity.CENTER
            background = rounded(ACCENT, 10)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply { marginStart = dp(4) }
            setOnClickListener { applyTransformReplace() }
        })
        wrap.addView(buttons)
        content?.removeAllViews(); content?.addView(wrap)
    }

    private fun applyTransformReplace() {
        if (transformState != TransformState.PREVIEW) return
        // Replace works by commitText() overwriting the CURRENT selection. Between the
        // capture and now the user (or the host app) may have moved, shrunk or dropped
        // that selection — committing then clobbers text that was never transformed.
        // Re-read it and refuse unless it is still byte-for-byte what we sent (IDI-164).
        val current = currentInputConnection?.getSelectedText(0)?.toString()?.trim() ?: ""
        if (current.isEmpty() || current != transformOriginalText) {
            flashTransformMessage("Selection changed — not replaced")
            return
        }
        currentInputConnection?.commitText(transformRewrite, 1)
        val original = transformOriginalText
        val rewriteLen = transformRewrite.length
        transformState = TransformState.IDLE
        transformInstruction = ""; transformOriginalText = ""; transformRewrite = ""
        iconGroup?.apply { visibility = View.VISIBLE; alpha = 1f }
        micWrap?.apply { visibility = View.VISIBLE; alpha = 1f }
        transformButton?.visibility = if (transformAvailable()) View.VISIBLE else View.GONE
        transformCancelButton?.visibility = View.GONE
        showKeyboard()
        pendingUndo = Pair(rewriteLen, original)
        refreshQuickPasteChip()
        undoRunnable?.let { main.removeCallbacks(it) }
        val r = Runnable { pendingUndo = null; refreshQuickPasteChip() }
        undoRunnable = r
        main.postDelayed(r, 6000)
    }

    // Mirrors whisperflow/app/transform.py::_strip_wrapping — models occasionally wrap
    // output in quotes/fences despite the prompt saying not to.
    private fun stripTransformWrapping(out: String, original: String): String {
        var s = out.trim()
        if (s.startsWith("```")) {
            s = s.trim('`').trim()
            for (lang in listOf("text", "markdown", "md")) {
                if (s.startsWith("$lang\n", ignoreCase = true)) s = s.substring(lang.length + 1)
            }
        }
        if (s.length > 1) {
            val first = s.first(); val last = s.last()
            val wrapped = (first == '"' && last == '"') || (first == '\'' && last == '\'') ||
                (first == '“' && last == '”')
            if (wrapped && original.isNotEmpty() && original.first() !in setOf('"', '\'', '“')) {
                s = s.substring(1, s.length - 1)
            }
        }
        return s
    }

    // JSON chat-completions call — sibling of proxyTranscribe() below (same endpoint/auth,
    // same Thread{}.start()+main.post{} threading convention), just a different body shape.
    private fun proxyChat(system: String, user: String): String? {
        val supabaseUrl = "https://ovpcthjingugwvpxlsna.supabase.co"
        val anon = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92cGN0aGppbmd1Z3d2cHhsc25hIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNjQzMDYsImV4cCI6MjA5Mzg0MDMwNn0.XwTBo8L-aEUmmSl6dJXNqA2QXzGFOpIVB5W9eDI8j28"
        val conn = URL(supabaseUrl + "/functions/v1/groq-proxy").openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"; conn.doOutput = true
            conn.connectTimeout = 15000; conn.readTimeout = 30000
            conn.setRequestProperty("Authorization", "Bearer " + anon)
            conn.setRequestProperty("apikey", anon)
            conn.setRequestProperty("x-flume-device", readConfig()?.optString("deviceId", "android-keyboard") ?: "android-keyboard")
            conn.setRequestProperty("Content-Type", "application/json")
            val payload = JSONObject().apply {
                put("model", "llama-3.3-70b-versatile")
                put("messages", JSONArray().apply {
                    put(JSONObject().apply { put("role", "system"); put("content", system) })
                    put(JSONObject().apply { put("role", "user"); put("content", user) })
                })
                put("temperature", 0)
                put("max_tokens", 2048)
            }
            conn.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            if (conn.responseCode !in 200..299) return null
            val resp = conn.inputStream.bufferedReader().use { it.readText() }
            val obj = JSONObject(resp)
            val choices = obj.optJSONArray("choices") ?: return null
            val message = choices.optJSONObject(0)?.optJSONObject("message") ?: return null
            val content = message.optString("content", "").trim()
            return content.ifEmpty { null }
        } finally { conn.disconnect() }
    }

    private fun transcribe(f: File): String? {
        // FAIL OPEN (Hard Rule #1): a missing, unreadable or corrupt config must never
        // cost the user their dictation. Without it we simply transcribe unbiased and
        // skip vocabulary/replacements/snippets rather than dropping the transcript.
        val cfg = readConfig()
        val bias = if (cfg != null) buildPrompt(cfg) else null
        var text = proxyTranscribe(f, bias, cfg) ?: return null
        // Echo scrub FIRST: a glossary parroted back is not speech and must never
        // reach the field. "" here is silence, handled by the caller like any
        // empty transcript.
        text = stripPromptEcho(text, bias)
        if (cfg != null) {
            text = applyReplacements(text, cfg.optJSONArray("replacements"))
            text = applySnippets(text, cfg.optJSONArray("snippets"))
        }
        return text.trim()
    }

    // Whisper bias prompt. Hard Rule #6: Groq rejects (400) any prompt over 896 chars.
    // The caps here are much tighter than that: Whisper only conditions on the LAST
    // ~224 tokens, so a longer glossary is not merely ignored — every extra term is
    // another word it can drop into an unrelated sentence, and another line it can
    // parrot back (see stripPromptEcho). Mirrors lib/dictionary.ts::buildPrompt.
    private val PROMPT_TERM_CAP = 80
    private val PROMPT_CHAR_CAP = 600

    private fun buildPrompt(cfg: JSONObject): String? {
        val vocab = cfg.optJSONArray("vocabulary") ?: return null
        if (vocab.length() == 0) return null
        val words = ArrayList<String>()
        for (i in 0 until vocab.length()) {
            val o = vocab.optJSONObject(i)
            val w = (if (o != null) o.optString("word", "") else vocab.optString(i, "")).trim()
            if (w.isNotEmpty()) words.add(w)   // blank entries can never reach the glossary
        }
        // Keep the terms nearest the END of the list (what the user taught most
        // recently) and trim from the FRONT — clipping the assembled string would
        // throw away exactly the newest terms this ordering is meant to protect.
        while (words.size > PROMPT_TERM_CAP) words.removeAt(0)
        while (words.isNotEmpty() &&
               ("Glossary: " + words.joinToString(", ") + ".").length > PROMPT_CHAR_CAP) {
            words.removeAt(0)
        }
        return if (words.isEmpty()) null else "Glossary: " + words.joinToString(", ") + "."
    }

    // ── bias-prompt echo ("Glossary, M.T.:" arriving AS the transcript) ─────────
    // Whisper's `prompt` is a CONTINUATION prompt, not an instruction: the model is
    // conditioned on it as though it were the transcript so far. On quiet or
    // speech-free audio the likeliest continuation of "Glossary: a, b, c." is MORE
    // glossary — so the bias list comes back as the "transcription" and would be
    // typed into the user's field. Mirrors lib/dictionary.ts::stripPromptEcho,
    // KeyboardViewController.swift::stripPromptEcho and
    // whisperflow/app/dictionary.py::strip_prompt_echo — edit one, edit all four.
    // Pure + fail-closed: anything unexpected returns the text untouched.

    // Chunk on commas/semicolons/newlines and on SENTENCE periods (a period followed
    // by whitespace) so "M.T." and "main.py" survive as single chunks.
    private val ECHO_CHUNK = Regex("""\s*[,;]\s*|\s*\.\s+|\s*\n+\s*""")
    private val ECHO_ANY_LABEL = Regex("""\b(glossary|vocabulary|files)\b\s*:""",
                                       RegexOption.IGNORE_CASE)
    private val ECHO_RUN = Regex("""\s{2,}""")
    private val ECHO_LEAD = Regex("""^[\s,;:.–—-]+""")

    /** The section labels this prompt ACTUALLY carries ("Glossary:", "Files:"). Only
     *  these count as labels when scanning a transcript — which keeps a dictated
     *  "Files, I need to check them" intact on a run where no file list was sent.
     *  We can only be echoed text we spoke first. */
    private fun echoLabelRegex(prompt: String): Regex? {
        val labels = sortedSetOf<String>()
        for (m in ECHO_ANY_LABEL.findAll(prompt)) labels.add(m.groupValues[1].lowercase())
        if (labels.isEmpty()) return null
        // Group 1 is the label WORD (which decides whether it is one of ours per
        // ECHO_OWNED_LABELS), group 2 the ':' that makes it ours regardless.
        return Regex("""^\s*(""" + labels.joinToString("|") + """)\b\s*(:)?\s*""",
                     RegexOption.IGNORE_CASE)
    }

    /** Casefold and reduce every non-alphanumeric run to one space: "M.T.:" and
     *  "m t" both become "m t", so an echo matches the term we sent. */
    private fun normEchoTerm(s: String): String {
        val sb = StringBuilder()
        var pending = false
        for (ch in s.lowercase()) {
            if (ch in 'a'..'z' || ch in '0'..'9') {
                if (pending && sb.isNotEmpty()) sb.append(' ')
                pending = false
                sb.append(ch)
            } else {
                pending = true
            }
        }
        return sb.toString()
    }

    /** Headings WE invented, which therefore can't be something the user said: a bare
     *  "Glossary" chunk is ours whatever punctuation follows it. "files" is
     *  deliberately absent — "Files, I need to check them" is real dictation. */
    private val ECHO_OWNED_LABELS = setOf("glossary", "vocabulary")

    /** (body-after-label, hadLabel, hadColon, isOwnedHeading). A colon means
     *  "Glossary:" — punctuated like a label, so it is ours and never dictation; an
     *  owned heading is ours on any punctuation at all. */
    private data class EchoLabel(val body: String, val label: Boolean,
                                 val colon: Boolean, val owned: Boolean)

    private fun splitEchoLabel(c: String, re: Regex?): EchoLabel {
        val m = re?.find(c) ?: return EchoLabel(c, false, false, false)
        if (m.value.isEmpty()) return EchoLabel(c, false, false, false)
        return EchoLabel(c.substring(m.value.length), true,
                         m.groupValues[2].isNotEmpty(),
                         m.groupValues[1].lowercase() in ECHO_OWNED_LABELS)
    }

    private fun echoSplit(text: String): Pair<MutableList<String>, MutableList<String>> {
        val chunks = ArrayList<String>()
        val seps = ArrayList<String>()
        var idx = 0
        for (m in ECHO_CHUNK.findAll(text)) {
            chunks.add(text.substring(idx, m.range.first))
            seps.add(m.value)
            idx = m.range.last + 1
        }
        chunks.add(text.substring(idx))
        seps.add("")
        return Pair(chunks, seps)
    }

    /** Only words we actually SENT as labels count as labels. Deletes any run
     *  introduced by a bias LABEL that is either followed by terms we sent or STANDS
     *  ALONE as its own fragment (the model often drops the list and echoes just the
     *  heading — "Glossary. So, the thing is…"), plus any bare comma-list of TWO OR
     *  MORE consecutive terms we sent. A LONE dictionary word is never dropped — that
     *  is the user saying a word they taught us — and a label running on inside its
     *  clause ("Files, I need to check them") is speech. "" = echo-only transcript. */
    private fun stripPromptEcho(text: String, prompt: String?): String {
        try {
            if (text.isBlank() || prompt.isNullOrEmpty()) return text
            val labelRe = echoLabelRegex(prompt)
            val terms = HashSet<String>()
            for (piece in echoSplit(prompt).first) {
                val t = normEchoTerm(splitEchoLabel(piece, labelRe).body)
                if (t.isNotEmpty()) terms.add(t)
            }
            if (terms.isEmpty()) return text

            val (chunks, seps) = echoSplit(text)
            val n = chunks.size
            val isTerm = BooleanArray(n)
            val isEmpty = BooleanArray(n)
            val hasLabel = BooleanArray(n)
            val isAlone = BooleanArray(n)
            for (k in 0 until n) {
                val (body, label, colon, owned) = splitEchoLabel(chunks[k], labelRe)
                val norm = normEchoTerm(body)
                hasLabel[k] = label; isTerm[k] = terms.contains(norm); isEmpty[k] = norm.isEmpty()
                // A heading standing on its own — "Glossary:" or a "Glossary." ending
                // the fragment — is ours. One that runs on inside its clause is the user.
                // A bare heading we INVENTED is ours whatever follows it: Whisper emits
                // "Glossary, <speech>" far more often than "Glossary. <speech>", and the
                // comma form used to survive because a comma reads as "clause continues".
                val endsFragment = k == n - 1 || seps[k].contains(".") || seps[k].contains("\n")
                isAlone[k] = label && norm.isEmpty() && (colon || endsFragment || owned)
                // Peel a "Glossary:" prefix even when the chunk itself survives.
                if (label && colon) chunks[k] = body
            }

            val drop = BooleanArray(n)
            var i = 0
            while (i < n) {
                val nextIsTerm = (i + 1 < n) && isTerm[i + 1]
                val start = isAlone[i] ||
                            (hasLabel[i] && isTerm[i]) ||
                            (hasLabel[i] && isEmpty[i] && nextIsTerm) ||
                            (isTerm[i] && nextIsTerm)
                if (!start) { i++; continue }
                var j = i
                while (j < n && (isTerm[j] || isEmpty[j])) { drop[j] = true; j++ }
                i = if (j > i) j else i + 1
            }

            // Rebuild unconditionally: even with no run to delete, a "Glossary:"
            // prefix may have been peeled off an otherwise real sentence above.
            val sb = StringBuilder()
            for (k in 0 until n) if (!drop[k]) sb.append(chunks[k]).append(seps[k])
            var out = ECHO_RUN.replace(sb.toString(), " ").trim()
            out = ECHO_LEAD.replace(out, "").trim()
            return if (normEchoTerm(out).isEmpty()) "" else out
        } catch (e: Exception) {
            return text   // fail-closed: an echo scrub must never cost a dictation
        }
    }

    private fun proxyTranscribe(f: File, prompt: String?, cfg: JSONObject?): String? {
        val supabaseUrl = "https://ovpcthjingugwvpxlsna.supabase.co"
        val anon = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92cGN0aGppbmd1Z3d2cHhsc25hIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNjQzMDYsImV4cCI6MjA5Mzg0MDMwNn0.XwTBo8L-aEUmmSl6dJXNqA2QXzGFOpIVB5W9eDI8j28"
        val boundary = "----FlumeBoundary" + System.currentTimeMillis()
        val conn = URL(supabaseUrl + "/functions/v1/groq-proxy").openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"; conn.doOutput = true
            conn.connectTimeout = 15000; conn.readTimeout = 45000
            conn.setRequestProperty("Authorization", "Bearer " + anon)
            conn.setRequestProperty("apikey", anon)
            conn.setRequestProperty("x-flume-device", cfg?.optString("deviceId", "android-keyboard") ?: "android-keyboard")
            conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary)
            val out = DataOutputStream(conn.outputStream)
            fun field(name: String, value: String) {
                // UTF-8 (not writeBytes, which drops to the low byte) so accented /
                // non-ASCII vocabulary in the prompt isn't corrupted or rejected.
                out.write(("--$boundary\r\n").toByteArray(Charsets.UTF_8))
                out.write(("Content-Disposition: form-data; name=\"$name\"\r\n\r\n").toByteArray(Charsets.UTF_8))
                out.write((value + "\r\n").toByteArray(Charsets.UTF_8))
            }
            field("model", "whisper-large-v3-turbo"); field("temperature", "0")
            // Spoken-language hint from the shared config (written by
            // lib/keyboardBridge.ts, default 'en'); 'auto' → omit so Whisper detects.
            val lang = cfg?.optString("spokenLanguage", "en")?.trim().takeUnless { it.isNullOrEmpty() } ?: "en"
            if (lang != "auto") field("language", lang)
            if (!prompt.isNullOrEmpty()) field("prompt", prompt)
            out.writeBytes("--" + boundary + "\r\n")
            out.writeBytes("Content-Disposition: form-data; name=\"file\"; filename=\"audio.m4a\"\r\n")
            out.writeBytes("Content-Type: audio/m4a\r\n\r\n")
            FileInputStream(f).use { it.copyTo(out) }
            out.writeBytes("\r\n--" + boundary + "--\r\n")
            out.flush(); out.close()
            if (conn.responseCode !in 200..299) return null
            val resp = conn.inputStream.bufferedReader().use { it.readText() }
            return JSONObject(resp).optString("text", "").trim()
        } finally { conn.disconnect() }
    }

    private fun applyReplacements(text: String, arr: JSONArray?): String {
        if (arr == null) return text
        var t = text
        for (i in 0 until arr.length()) {
            val r = arr.optJSONObject(i) ?: continue
            val from = r.optString("from", ""); val to = r.optString("to", "")
            if (from.isEmpty()) continue
            t = Regex("\\b" + Regex.escape(from) + "\\b", RegexOption.IGNORE_CASE).replace(t, Regex.escapeReplacement(to))
        }
        return t
    }

    /**
     * Snippet expansion — the exact contract of `lib/dictionary.ts::applySnippets`
     * (which itself mirrors desktop):
     *   - case-INSENSITIVE whole-phrase match on word boundaries (multi-word aware)
     *   - LONGEST trigger first, so "my email address" wins over "my email"
     *   - SINGLE left-to-right pass: one alternation regex, so an inserted expansion is
     *     never re-scanned and snippets cannot cascade into each other
     *   - snippets with an EMPTY expansion are skipped (the old per-snippet loop
     *     replaced their trigger with "", i.e. silently deleted the user's words)
     *   - fail closed: any error returns `text` unchanged, never throws
     */
    private fun applySnippets(text: String, arr: JSONArray?): String {
        if (arr == null || text.isEmpty()) return text
        return try {
            val valid = ArrayList<Pair<String, String>>()
            for (i in 0 until arr.length()) {
                val s = arr.optJSONObject(i) ?: continue
                val trg = s.optString("trigger", "").trim()
                val exp = s.optString("expansion", "")
                if (trg.isEmpty() || exp.isEmpty()) continue
                valid.add(Pair(trg, exp))
            }
            if (valid.isEmpty()) return text
            // Stable sort → among equal-length triggers the earliest one still wins.
            valid.sortByDescending { it.first.length }
            val byTrigger = HashMap<String, String>()
            val parts = ArrayList<String>()
            for ((trg, exp) in valid) {
                val key = trg.lowercase()
                if (byTrigger.containsKey(key)) continue   // first (longest / earliest) wins
                byTrigger[key] = exp
                parts.add("\\b" + Regex.escape(trg) + "\\b")
            }
            if (parts.isEmpty()) return text
            val re = Regex("(" + parts.joinToString("|") + ")", RegexOption.IGNORE_CASE)
            // The lambda overload of replace() inserts the returned string LITERALLY —
            // no $1 group-reference interpretation, and no re-scan of what it inserted.
            re.replace(text) { m -> byTrigger[m.value.lowercase()] ?: m.value }
        } catch (e: Exception) {
            text
        }
    }

    private fun isSecureField(info: EditorInfo?): Boolean {
        val type = info?.inputType ?: return false
        val cls = type and InputType.TYPE_MASK_CLASS
        val v = type and InputType.TYPE_MASK_VARIATION
        val textPw = cls == InputType.TYPE_CLASS_TEXT && (
            v == InputType.TYPE_TEXT_VARIATION_PASSWORD ||
            v == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD ||
            v == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD)
        val numPw = cls == InputType.TYPE_CLASS_NUMBER && v == InputType.TYPE_NUMBER_VARIATION_PASSWORD
        return textPw || numPw
    }

    private fun setStatus(s: String) = main.post {
        // `status` was never added to the view; surface messages in the suggestion
        // strip instead so mic/permission errors are actually visible.
        suggestionStrip?.apply {
            removeAllViews()
            addView(TextView(this@FlumeInputMethodService).apply {
                text = s; setTextColor(mutedText); textSize = 13f; typeface = geist
                gravity = Gravity.CENTER
                setPadding(dp(14), dp(6), dp(14), dp(6))
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            })
        }
    }
}
