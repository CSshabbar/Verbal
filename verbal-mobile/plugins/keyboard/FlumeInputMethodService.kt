package com.verbal.app.keyboard

import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.inputmethodservice.InputMethodService
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.Button
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

/**
 * Flume dictation keyboard.
 *
 * Layout (matches the Flume design): a status pill on top; a control row with a
 * backspace/correction button (left), a large mic button (center), and a right
 * column of Snippets / Canvas / History buttons.
 *
 * Functionality:
 *  - Mic: record -> transcribe via Groq (vocabulary bias) -> apply replacements +
 *    snippet expansion -> insert.
 *  - Backspace: delete the character before the cursor.
 *  - Snippets: pick list of the user's snippets -> inserts the expansion.
 *  - History: pick list of recent dictations -> inserts the text.
 *  - Canvas: launches the Flume app.
 *
 * Config (Groq key + dictionary + snippets + recent history) is read from a JSON
 * file the RN app writes to filesDir (see lib/keyboardBridge.ts). Fails closed:
 * secure fields disable the mic; any error shows a message and never crashes.
 */
class FlumeInputMethodService : InputMethodService() {
    private val ACCENT = Color.parseColor("#E8522A")
    private val BG = Color.parseColor("#0d0c0b")
    private val CARD = Color.parseColor("#1c1a18")
    private val TXT = Color.parseColor("#f4f3f1")
    private val MUT = Color.parseColor("#8a8580")

    private var status: TextView? = null
    private var mic: Button? = null
    private var panel: ScrollView? = null
    private var panelList: LinearLayout? = null

    private var recorder: MediaRecorder? = null
    private var audioFile: File? = null
    private var recording = false
    private var secure = false
    private var busy = false
    private val main = Handler(Looper.getMainLooper())

    private fun dp(v: Int): Int =
        TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun rounded(color: Int, radius: Int): GradientDrawable =
        GradientDrawable().apply { setColor(color); cornerRadius = dp(radius).toFloat() }

    override fun onCreateInputView(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(BG)
            setPadding(dp(12), dp(12), dp(12), dp(14))
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }

        // Pick-list panel (hidden until Snippets/History is tapped)
        panelList = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        panel = ScrollView(this).apply {
            visibility = View.GONE
            background = rounded(CARD, 14)
            addView(panelList)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(180)).apply { bottomMargin = dp(10) }
        }
        root.addView(panel)

        // Status pill
        val pill = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = rounded(CARD, 16)
            setPadding(dp(16), dp(14), dp(16), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { bottomMargin = dp(12) }
        }
        pill.addView(TextView(this).apply {
            text = "FLUME"; setTextColor(MUT); textSize = 11f
            letterSpacing = 0.18f; setPadding(0, 0, dp(12), 0)
        })
        status = TextView(this).apply { text = "Tap to speak"; setTextColor(TXT); textSize = 15f }
        pill.addView(status)
        root.addView(pill)

        // Control row: [backspace]  [ mic (weighted) ]  [snip/canvas/hist column]
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        val back = iconButton("⌫", CARD, TXT).apply { setOnClickListener { onBackspace() } }
        row.addView(back)

        mic = Button(this).apply {
            text = "🎤  Tap to dictate"
            setTextColor(Color.WHITE); textSize = 15f
            background = rounded(ACCENT, 18)
            setOnClickListener { onMicTap() }
            layoutParams = LinearLayout.LayoutParams(0, dp(56), 1f)
                .apply { leftMargin = dp(10); rightMargin = dp(10) }
        }
        row.addView(mic)

        val rightCol = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        rightCol.addView(iconButton("⚡", CARD, TXT).apply { setOnClickListener { togglePanel("snippets") } })
        rightCol.addView(iconButton("▦", CARD, TXT).apply {
            (layoutParams as LinearLayout.LayoutParams).topMargin = dp(8)
            setOnClickListener { openCanvas() } })
        rightCol.addView(iconButton("🕒", CARD, TXT).apply {
            (layoutParams as LinearLayout.LayoutParams).topMargin = dp(8)
            setOnClickListener { togglePanel("history") } })
        row.addView(rightCol)

        root.addView(row)
        return root
    }

    private fun iconButton(glyph: String, bg: Int, fg: Int): Button =
        Button(this).apply {
            text = glyph; setTextColor(fg); textSize = 16f
            background = rounded(bg, 14)
            setPadding(0, 0, 0, 0)
            layoutParams = LinearLayout.LayoutParams(dp(48), dp(48))
        }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        secure = isSecureField(info)
        if (recording) abortRecording()
        hidePanel()
        mic?.isEnabled = !secure
        setStatus(if (secure) "Secure field — dictation disabled" else "Tap to speak")
    }

    // ── buttons ─────────────────────────────────────────────────────────────────

    private fun onBackspace() {
        currentInputConnection?.deleteSurroundingText(1, 0)
    }

    private fun openCanvas() {
        try {
            val i = packageManager.getLaunchIntentForPackage(packageName)
            i?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            if (i != null) startActivity(i)
        } catch (e: Exception) { setStatus("Couldn't open Flume") }
    }

    private var openPanel: String? = null
    private fun togglePanel(which: String) {
        if (openPanel == which && panel?.visibility == View.VISIBLE) { hidePanel(); return }
        val cfg = readConfig()
        val items = ArrayList<Pair<String, String>>() // label -> textToInsert
        if (which == "snippets") {
            val arr = cfg?.optJSONArray("snippets")
            if (arr != null) for (i in 0 until arr.length()) {
                val s = arr.optJSONObject(i) ?: continue
                val label = s.optString("label").ifEmpty { s.optString("trigger") }
                val exp = s.optString("expansion")
                if (exp.isNotEmpty()) items.add(Pair(label, exp))
            }
        } else {
            val arr = cfg?.optJSONArray("history")
            if (arr != null) for (i in 0 until arr.length()) {
                val t = arr.optString(i)
                if (t.isNotEmpty()) items.add(Pair(t, t))
            }
        }
        showPanel(which, items)
    }

    private fun showPanel(which: String, items: List<Pair<String, String>>) {
        openPanel = which
        panelList?.removeAllViews()
        if (items.isEmpty()) {
            panelList?.addView(TextView(this).apply {
                text = if (which == "snippets") "No snippets yet" else "No recent dictations"
                setTextColor(MUT); textSize = 14f; setPadding(dp(16), dp(16), dp(16), dp(16))
            })
        } else {
            for (it in items) {
                val label = it.first
                val insert = it.second
                panelList?.addView(TextView(this).apply {
                    text = if (label.length > 60) label.substring(0, 60) + "…" else label
                    setTextColor(TXT); textSize = 15f
                    setPadding(dp(16), dp(14), dp(16), dp(14))
                    isClickable = true
                    setOnClickListener {
                        currentInputConnection?.commitText(insert, 1)
                        hidePanel()
                    }
                })
            }
        }
        panel?.visibility = View.VISIBLE
    }

    private fun hidePanel() { openPanel = null; panel?.visibility = View.GONE }

    // ── mic / recording ──────────────────────────────────────────────────────────

    private fun onMicTap() {
        if (secure || busy) return
        hidePanel()
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
            mic?.text = "■  Stop"
            setStatus("Recording… tap to stop")
        } catch (e: Exception) {
            releaseRecorder(); recording = false
            mic?.text = "🎤  Tap to dictate"
            setStatus("Mic unavailable — enable microphone for Flume in the app")
        }
    }

    private fun abortRecording() {
        recording = false
        try { recorder?.stop() } catch (e: Exception) {}
        releaseRecorder()
        audioFile?.let { try { it.delete() } catch (e: Exception) {} }
        audioFile = null
        mic?.text = "🎤  Tap to dictate"
    }

    private fun stopAndTranscribe() {
        recording = false
        var ok = true
        try { recorder?.stop() } catch (e: Exception) { ok = false }
        releaseRecorder()
        val f = audioFile; audioFile = null
        mic?.text = "🎤  Tap to dictate"
        if (!ok || f == null || !f.exists() || f.length() == 0L) {
            f?.let { try { it.delete() } catch (e: Exception) {} }
            setStatus("Nothing recorded — try again"); return
        }
        busy = true
        setStatus("Transcribing…")
        Thread {
            val text = try { transcribe(f) } catch (e: Exception) { null }
            try { f.delete() } catch (e: Exception) {}
            main.post {
                busy = false
                if (text.isNullOrBlank()) setStatus("Couldn't transcribe — try again")
                else { currentInputConnection?.commitText(text + " ", 1); setStatus("Tap to speak") }
            }
        }.start()
    }

    private fun releaseRecorder() { try { recorder?.release() } catch (e: Exception) {}; recorder = null }

    // ── transcription pipeline (mirrors lib/dictationPipeline.ts) ───────────────

    private fun readConfig(): JSONObject? = try {
        val cfg = File(filesDir, "flume_kbd_config.json")
        if (!cfg.exists()) null else JSONObject(cfg.readText())
    } catch (e: Exception) { null }

    private fun transcribe(f: File): String? {
        val cfg = readConfig() ?: return null
        val key = cfg.optString("groqKey", "")
        if (key.isEmpty()) return null
        var text = groqTranscribe(f, key, buildPrompt(cfg)) ?: return null
        text = applyReplacements(text, cfg.optJSONArray("replacements"))
        text = applySnippets(text, cfg.optJSONArray("snippets"))
        return text.trim()
    }

    private fun buildPrompt(cfg: JSONObject): String? {
        val vocab = cfg.optJSONArray("vocabulary") ?: return null
        if (vocab.length() == 0) return null
        val sb = StringBuilder("Glossary: ")
        for (i in 0 until vocab.length()) { if (i > 0) sb.append(", "); sb.append(vocab.optString(i)) }
        return sb.toString()
    }

    private fun groqTranscribe(f: File, key: String, prompt: String?): String? {
        val boundary = "----FlumeBoundary" + System.currentTimeMillis()
        val conn = URL("https://api.groq.com/openai/v1/audio/transcriptions").openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"; conn.doOutput = true
            conn.connectTimeout = 15000; conn.readTimeout = 45000
            conn.setRequestProperty("Authorization", "Bearer " + key)
            conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary)
            val out = DataOutputStream(conn.outputStream)
            fun field(name: String, value: String) {
                out.writeBytes("--" + boundary + "\r\n")
                out.writeBytes("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n")
                out.writeBytes(value + "\r\n")
            }
            field("model", "whisper-large-v3-turbo"); field("language", "en"); field("temperature", "0")
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

    private fun applySnippets(text: String, arr: JSONArray?): String {
        if (arr == null) return text
        val triggers = ArrayList<Pair<String, String>>()
        for (i in 0 until arr.length()) {
            val s = arr.optJSONObject(i) ?: continue
            val trg = s.optString("trigger", ""); val exp = s.optString("expansion", "")
            if (trg.isNotEmpty()) triggers.add(Pair(trg, exp))
        }
        triggers.sortByDescending { it.first.length }  // longest trigger first
        var t = text
        for (p in triggers) {
            t = Regex("\\b" + Regex.escape(p.first) + "\\b", RegexOption.IGNORE_CASE).replace(t, Regex.escapeReplacement(p.second))
        }
        return t
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

    private fun setStatus(s: String) { main.post { status?.text = s } }
}
