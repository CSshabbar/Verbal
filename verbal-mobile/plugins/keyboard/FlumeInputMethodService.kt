package com.verbal.app.keyboard

import android.graphics.Color
import android.inputmethodservice.InputMethodService
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.LinearLayout
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
 * Tap mic -> record; tap again -> stop, transcribe via Groq (same pipeline as the
 * app: vocabulary bias + replacement rules + snippet expansion), then insert the
 * text into the focused field. Config (Groq key + dictionary) is read from a JSON
 * file the RN app writes to filesDir (see lib/keyboardBridge.ts) — a Kotlin IME
 * can't call the TS pipeline, so it mirrors the same request shape and rules.
 *
 * Fails closed: secure fields refuse the mic; any recording/network/parse error
 * shows a message and never crashes or leaves the field half-inserted.
 */
class FlumeInputMethodService : InputMethodService() {
    private var status: TextView? = null
    private var mic: Button? = null
    private var recorder: MediaRecorder? = null
    private var audioFile: File? = null
    private var recording = false
    private var secure = false
    private var busy = false
    private val main = Handler(Looper.getMainLooper())

    override fun onCreateInputView(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor("#0d0c0b"))
            setPadding(48, 46, 48, 46)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        mic = Button(this).apply {
            text = "Tap to dictate"
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#E8522A"))
            setOnClickListener { onMicTap() }
        }
        status = TextView(this).apply {
            setTextColor(Color.parseColor("#8a8580"))
            textSize = 12f
            gravity = Gravity.CENTER
            setPadding(0, 24, 0, 0)
        }
        root.addView(mic)
        root.addView(status)
        return root
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        secure = isSecureField(info)
        if (recording) abortRecording()
        if (secure) {
            mic?.isEnabled = false
            setStatus("Secure field — dictation disabled")
        } else {
            mic?.isEnabled = true
            setStatus("")
            setMicLabel("Tap to dictate")
        }
    }

    private fun isSecureField(info: EditorInfo?): Boolean {
        val type = info?.inputType ?: return false
        val cls = type and InputType.TYPE_MASK_CLASS
        val v = type and InputType.TYPE_MASK_VARIATION
        val textPw = cls == InputType.TYPE_CLASS_TEXT && (
            v == InputType.TYPE_TEXT_VARIATION_PASSWORD ||
            v == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD ||
            v == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD
        )
        val numPw = cls == InputType.TYPE_CLASS_NUMBER &&
            v == InputType.TYPE_NUMBER_VARIATION_PASSWORD
        return textPw || numPw
    }

    private fun onMicTap() {
        if (secure || busy) return
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
            r.prepare()
            r.start()
            recorder = r
            audioFile = f
            recording = true
            setMicLabel("Stop")
            setStatus("Recording… tap to stop")
        } catch (e: Exception) {
            releaseRecorder()
            recording = false
            setMicLabel("Tap to dictate")
            setStatus("Mic unavailable — enable microphone for Flume in the app")
        }
    }

    private fun abortRecording() {
        recording = false
        try { recorder?.stop() } catch (e: Exception) {}
        releaseRecorder()
        audioFile?.let { try { it.delete() } catch (e: Exception) {} }
        audioFile = null
    }

    private fun stopAndTranscribe() {
        recording = false
        var ok = true
        try { recorder?.stop() } catch (e: Exception) { ok = false }
        releaseRecorder()
        val f = audioFile
        audioFile = null
        if (!ok || f == null || !f.exists() || f.length() == 0L) {
            f?.let { try { it.delete() } catch (e: Exception) {} }
            setMicLabel("Tap to dictate")
            setStatus("Nothing recorded — try again")
            return
        }
        busy = true
        setMicLabel("…")
        setStatus("Transcribing…")
        Thread {
            val text = try { transcribe(f) } catch (e: Exception) { null }
            try { f.delete() } catch (e: Exception) {}
            main.post {
                busy = false
                setMicLabel("Tap to dictate")
                if (text.isNullOrBlank()) {
                    setStatus("Couldn't transcribe — try again")
                } else {
                    currentInputConnection?.commitText(text + " ", 1)
                    setStatus("")
                }
            }
        }.start()
    }

    private fun releaseRecorder() {
        try { recorder?.release() } catch (e: Exception) {}
        recorder = null
    }

    // ── transcription pipeline (mirrors lib/dictationPipeline.ts) ───────────────

    private fun readConfig(): JSONObject? {
        return try {
            val cfg = File(filesDir, "flume_kbd_config.json")
            if (!cfg.exists()) null else JSONObject(cfg.readText())
        } catch (e: Exception) { null }
    }

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
        for (i in 0 until vocab.length()) {
            if (i > 0) sb.append(", ")
            sb.append(vocab.optString(i))
        }
        return sb.toString()
    }

    private fun groqTranscribe(f: File, key: String, prompt: String?): String? {
        val boundary = "----FlumeBoundary" + System.currentTimeMillis()
        val conn = URL("https://api.groq.com/openai/v1/audio/transcriptions")
            .openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.connectTimeout = 15000
            conn.readTimeout = 45000
            conn.setRequestProperty("Authorization", "Bearer " + key)
            conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary)
            val out = DataOutputStream(conn.outputStream)
            fun field(name: String, value: String) {
                out.writeBytes("--" + boundary + "\r\n")
                out.writeBytes("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n")
                out.writeBytes(value + "\r\n")
            }
            field("model", "whisper-large-v3-turbo")
            field("language", "en")
            field("temperature", "0")
            if (!prompt.isNullOrEmpty()) field("prompt", prompt)
            out.writeBytes("--" + boundary + "\r\n")
            out.writeBytes("Content-Disposition: form-data; name=\"file\"; filename=\"audio.m4a\"\r\n")
            out.writeBytes("Content-Type: audio/m4a\r\n\r\n")
            FileInputStream(f).use { it.copyTo(out) }
            out.writeBytes("\r\n--" + boundary + "--\r\n")
            out.flush()
            out.close()
            if (conn.responseCode !in 200..299) return null
            val resp = conn.inputStream.bufferedReader().use { it.readText() }
            return JSONObject(resp).optString("text", "").trim()
        } finally {
            conn.disconnect()
        }
    }

    private fun applyReplacements(text: String, arr: JSONArray?): String {
        if (arr == null) return text
        var t = text
        for (i in 0 until arr.length()) {
            val r = arr.optJSONObject(i) ?: continue
            val from = r.optString("from", "")
            val to = r.optString("to", "")
            if (from.isEmpty()) continue
            t = Regex("\\b" + Regex.escape(from) + "\\b", RegexOption.IGNORE_CASE)
                .replace(t, Regex.escapeReplacement(to))
        }
        return t
    }

    private fun applySnippets(text: String, arr: JSONArray?): String {
        if (arr == null) return text
        val triggers = ArrayList<Pair<String, String>>()
        for (i in 0 until arr.length()) {
            val s = arr.optJSONObject(i) ?: continue
            val trg = s.optString("trigger", "")
            val exp = s.optString("expansion", "")
            if (trg.isNotEmpty()) triggers.add(Pair(trg, exp))
        }
        // longest trigger first so a substring trigger can't shadow a longer one
        triggers.sortByDescending { it.first.length }
        var t = text
        for (p in triggers) {
            t = Regex("\\b" + Regex.escape(p.first) + "\\b", RegexOption.IGNORE_CASE)
                .replace(t, Regex.escapeReplacement(p.second))
        }
        return t
    }

    // ── UI helpers (always hop to main thread) ──────────────────────────────────

    private fun setStatus(s: String) { main.post { status?.text = s } }
    private fun setMicLabel(s: String) { main.post { mic?.text = s } }
}
