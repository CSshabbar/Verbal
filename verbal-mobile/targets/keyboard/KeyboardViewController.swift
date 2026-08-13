import UIKit
import AVFoundation
import CoreText

/// Flume Keyboard v2 (iOS) — full keyboard extension mirroring the Android IME and
/// FLUME_KEYBOARD_V2_DESIGN.md: a Flume bar (F · ⚡ · ▦ · 🕐 · 📖 · mic), letters /
/// numbers / symbols layers, light+dark theming, emoji picker, and the History /
/// Snippets / Vocabulary overlays (read from the App Group config the app writes).
///
/// STAGE (iOS foundation): typing UI + Flume bar + emoji + overlays + dictation via
/// groq-proxy. Testable on the SIMULATOR with no paid account. DEFERRED (device/
/// account-gated or later stages): reliable in-extension mic + handoff, GIF, glide,
/// ML autocorrect, the ~40MB jetsam-safe emoji, App Store PrivacyInfo.
///
/// Class name MUST stay `KeyboardViewController` (Info.plist principal class).
class KeyboardViewController: UIInputViewController, AVAudioRecorderDelegate, UIInputViewAudioFeedback {

    // MARK: typing-feel (Gboard-style): touch-down commit, pressed state, key-preview bubble, key-click sound
    // iOS keyboard extensions CANNOT do haptics (UIFeedbackGenerator is silently ignored); the sanctioned
    // feedback is UIDevice.current.playInputClick(), which respects the user's "Keyboard Clicks" setting.
    var enableInputClicksWhenVisible: Bool { true }
    private var keyPreview: UILabel?
    private var keyBaseColor: [UIButton: UIColor] = [:]
    // Gapless touch (Gboard): each key BUTTON fills its whole cell so hit areas tile edge-to-edge
    // (no dead gaps between keys), while the VISIBLE rounded key is an inset background subview.
    // keyDownVisual/keyUpVisual drive that inset view's color, not the button's (clear) background.
    private var keyBgView: [UIButton: UIView] = [:]

    @objc private func keyDownVisual(_ b: UIButton) {
        (keyBgView[b] ?? b).backgroundColor = pal.highlightBg
        UIDevice.current.playInputClick()
        if let t = b.title(for: .normal) { showKeyPreview(over: b, t) }   // letters-only guard is inside
    }
    @objc private func keyUpVisual(_ b: UIButton) {
        (keyBgView[b] ?? b).backgroundColor = keyBaseColor[b] ?? pal.keyBg
        hideKeyPreview()
    }

    // Give a key a visible rounded background inset from its (full-cell) touch bounds. The button
    // itself stays clear so its hit area tiles edge-to-edge with its neighbours (rows use spacing 0).
    private func installKeyBackground(_ b: UIButton, color: UIColor, radius: CGFloat = 8, inset: CGFloat = 3) {
        b.backgroundColor = .clear
        keyBaseColor[b] = color
        let bgv = UIView()
        bgv.backgroundColor = color
        bgv.layer.cornerRadius = radius
        bgv.isUserInteractionEnabled = false
        bgv.translatesAutoresizingMaskIntoConstraints = false
        b.insertSubview(bgv, at: 0)                       // behind the (centered) title label
        NSLayoutConstraint.activate([
            bgv.leadingAnchor.constraint(equalTo: b.leadingAnchor, constant: inset),
            bgv.trailingAnchor.constraint(equalTo: b.trailingAnchor, constant: -inset),
            bgv.topAnchor.constraint(equalTo: b.topAnchor, constant: inset),
            bgv.bottomAnchor.constraint(equalTo: b.bottomAnchor, constant: -inset),
        ])
        keyBgView[b] = bgv
    }
    // Recolor a key's base (visible) background after creation (space / return tint).
    private func setKeyBaseColor(_ b: UIButton, _ color: UIColor) {
        keyBaseColor[b] = color
        (keyBgView[b] ?? b).backgroundColor = color
    }

    // Enlarged character bubble just ABOVE a letter key (Gboard preview). Fail-safe: letters only.
    private func showKeyPreview(over b: UIButton, _ label: String) {
        guard label.count == 1, label.first!.isLetter else { return }
        let lbl = keyPreview ?? { let l = UILabel(); l.textAlignment = .center; l.font = uiFont(26); l.textColor = pal.keyText
            l.backgroundColor = pal.keyBg; l.layer.cornerRadius = 10; l.clipsToBounds = true; view.addSubview(l); keyPreview = l; return l }()
        lbl.textColor = pal.keyText
        lbl.backgroundColor = pal.keyBg
        lbl.text = label
        let f = b.convert(b.bounds, to: view)
        lbl.frame = CGRect(x: f.midX - 24, y: f.minY - 58, width: 48, height: 54)
        lbl.isHidden = false; view.bringSubviewToFront(lbl)
    }
    private func hideKeyPreview() { keyPreview?.isHidden = true }

    // MARK: palette
    struct Palette {
        let bg, keyBg, keyText, modBg, barBg, iconTint, mutedText: UIColor
        let returnBg, returnText, micBg, micFg, cardBg, highlightBg: UIColor
    }
    private let accent = UIColor(hex: 0xC85A3E)   // terracotta — THE Flume accent
    private var pal = Palette(
        bg: .white, keyBg: .white, keyText: .black, modBg: .lightGray, barBg: .white,
        iconTint: .darkGray, mutedText: .gray, returnBg: .black, returnText: .white,
        micBg: .black, micFg: .white, cardBg: .white, highlightBg: .lightGray)

    private func applyTheme() {
        let dark = traitCollection.userInterfaceStyle == .dark
        pal = dark ? Palette(  // canonical "Minimalist dark" tokens (colors.ts / CLAUDE_CODE_PROMPT.md); barBg == bg → seamless
            bg: UIColor(hex: 0x0e1012), keyBg: UIColor(hex: 0x2a2d31), keyText: UIColor(hex: 0xf2f2f2),
            modBg: UIColor(hex: 0x1e2124), barBg: UIColor(hex: 0x0e1012), iconTint: UIColor(hex: 0x8b8d90),
            mutedText: UIColor(hex: 0x8b8d90), returnBg: UIColor(hex: 0xf2f2f2), returnText: UIColor(hex: 0x0e1012),
            micBg: UIColor(hex: 0xf2f2f2), micFg: UIColor(hex: 0x0e1012), cardBg: UIColor(hex: 0x26282b), highlightBg: UIColor(hex: 0x26282b))
        : Palette(
            bg: UIColor(hex: 0xECEBEA), keyBg: .white, keyText: UIColor(hex: 0x14110f),
            modBg: UIColor(hex: 0xCBCBCD), barBg: UIColor(hex: 0xECEBEA), iconTint: UIColor(hex: 0x6b6b6b),
            mutedText: UIColor(hex: 0x8a857f), returnBg: UIColor(hex: 0x14110f), returnText: .white,
            micBg: UIColor(hex: 0x14110f), micFg: .white, cardBg: .white, highlightBg: UIColor(hex: 0xE1E0DF))
    }

    // MARK: state
    private enum Layer { case letters, numbers, symbols }
    private var layer: Layer = .letters
    private var shifted = false
    private var capsLock = false
    // Fast-typing correctness (mirrors Android): letter keys update IN PLACE on
    // shift/caps changes instead of rebuilding the whole keyboard, and suggestions
    // run debounced off the commit path — a rebuild or heavy per-keystroke scan
    // mid-typing was dropping the next rapid tap.
    private var letterKeys: [(UIButton, String)] = []   // (button, base label)
    private weak var shiftKeyBtn: UIButton?
    private var suggestWork: DispatchWorkItem?
    private var activeOverlay: String?
    private var emojiCatIdx = 1
    private var emojiRecents: [String] = []

    // Full emoji library (bundled flume_emoji.txt: "Group<TAB>emoji emoji …", 9 groups) and the
    // keyword→emoji map (flume_emoji_kw.txt: "keyword<TAB>emoji emoji …"). Both space-separated.
    private lazy var emojiLib: [(String, [String])] = {
        guard let url = Bundle(for: type(of: self)).url(forResource: "flume_emoji", withExtension: "txt"),
              let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        var out: [(String, [String])] = []
        for line in text.split(separator: "\n") {
            guard let tab = line.firstIndex(of: "\t") else { continue }
            let name = String(line[..<tab])
            let emojis = line[line.index(after: tab)...].split(separator: " ").map(String.init)
            if !emojis.isEmpty { out.append((name, emojis)) }
        }
        return out
    }()
    private lazy var emojiKw: [String: [String]] = {
        var m: [String: [String]] = [:]
        guard let url = Bundle(for: type(of: self)).url(forResource: "flume_emoji_kw", withExtension: "txt"),
              let text = try? String(contentsOf: url, encoding: .utf8) else { return m }
        for line in text.split(separator: "\n") {
            guard let tab = line.firstIndex(of: "\t") else { continue }
            let kw = String(line[..<tab]).lowercased()
            let emojis = line[line.index(after: tab)...].split(separator: " ").map(String.init)
            if !emojis.isEmpty { m[kw] = emojis }
        }
        return m
    }()

    // MARK: word completion (bundled frequency dict + on-device learning)
    // Gboard-style completions: a ~25k lowercase English word list (most-frequent
    // first) bundled into the .appex, plus a small UserDefaults-backed learned map.
    private lazy var dictWords: [String] = {
        guard let url = Bundle(for: type(of: self)).url(forResource: "flume_words", withExtension: "txt"),
              let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        return text.split(separator: "\n").map { String($0) }
    }()
    private var learned: [String: Int] = [:]
    private var learnedLoaded = false
    private func loadLearned() {
        if learnedLoaded { return }
        learnedLoaded = true
        if let dict = UserDefaults.standard.dictionary(forKey: "flume_kbd_learned") as? [String: Int] { learned = dict }
    }
    private func learnWord(_ raw: String) {
        let w = raw.lowercased().filter { $0.isLetter }
        if w.count < 2 { return }
        loadLearned()
        learned[w, default: 0] += 1
        if learned.count > 600 {                       // bound the store: keep the 500 most-used
            let top = learned.sorted { $0.value > $1.value }.prefix(500)
            learned = Dictionary(uniqueKeysWithValues: top.map { ($0.key, $0.value) })
        }
        let snapshot = learned                          // persist off the main thread (was blocking the space keystroke)
        DispatchQueue.global(qos: .utility).async { UserDefaults.standard.set(snapshot, forKey: "flume_kbd_learned") }
    }

    // MARK: next-word prediction (bundled bigram table + on-device bigram learning)
    // flume_bigrams.txt: each line "prev<TAB>next1 next2 next3 ..." (next-words most-likely first).
    private lazy var bigrams: [String: [String]] = {
        var m: [String: [String]] = [:]
        guard let url = Bundle(for: type(of: self)).url(forResource: "flume_bigrams", withExtension: "txt"),
              let text = try? String(contentsOf: url, encoding: .utf8) else { return m }
        for line in text.split(separator: "\n") {
            guard let tab = line.firstIndex(of: "\t") else { continue }
            let prev = String(line[..<tab])
            let nexts = line[line.index(after: tab)...].split(separator: " ").map(String.init)
            if !nexts.isEmpty { m[prev] = nexts }
        }
        return m
    }()
    private var learnedBg: [String: [String: Int]] = [:]
    private var learnedBgLoaded = false
    private func loadLearnedBg() {
        if learnedBgLoaded { return }
        learnedBgLoaded = true
        if let raw = UserDefaults.standard.dictionary(forKey: "flume_kbd_bigrams") as? [String: [String: Int]] { learnedBg = raw }
    }
    private func learnBigram(_ prevRaw: String, _ nextRaw: String) {
        let p = prevRaw.lowercased().filter { $0.isLetter }
        let n = nextRaw.lowercased().filter { $0.isLetter }
        if p.count < 2 || n.count < 2 { return }
        loadLearnedBg()
        var inner = learnedBg[p] ?? [:]
        inner[n, default: 0] += 1
        learnedBg[p] = inner
        if learnedBg.count > 400, let drop = learnedBg.keys.first(where: { $0 != p }) { learnedBg.removeValue(forKey: drop) }
        let snapshot = learnedBg                         // persist off the main thread
        DispatchQueue.global(qos: .utility).async { UserDefaults.standard.set(snapshot, forKey: "flume_kbd_bigrams") }
    }
    // Last two alphabetic words before the cursor (for learning prev→justFinished on a boundary).
    private func lastTwoWords() -> (String, String)? {
        let before = (textDocumentProxy.documentContextBeforeInput ?? "")
        let trimmed = before.replacingOccurrences(of: "\\s+$", with: "", options: .regularExpression)
        let toks = trimmed.components(separatedBy: CharacterSet.letters.inverted).filter { !$0.isEmpty }
        if toks.count < 2 { return nil }
        return (toks[toks.count - 2], toks[toks.count - 1])
    }

    private var suggestionStrip: UIStackView!
    private var contentView: UIView!
    private var micButton: UIButton!
    private var barButtons: [String: UIButton] = [:]
    // Recording UI (waveform + cancel/pause replace the overlay icons while recording).
    private var iconGroup: UIStackView?
    private var flexSpacer: UIView?
    private var recordControls: UIStackView?
    private var waveformView: WaveformView?
    private var pauseButton: UIButton?
    private var timerLabel: UILabel?
    private var isPaused = false
    private var meterTimer: Timer?
    private var elapsedTimer: Timer?
    private var backspaceTimer: Timer?     // hold-to-repeat for the ⌫ key (mirrors Android attachRepeat)
    private var recStart = Date()
    private var pausedTotal: TimeInterval = 0
    private var pauseStart = Date()
    private var heightC: NSLayoutConstraint!

    // MARK: clipboard (App-Group-persisted, self-contained — see readConfig() for the
    // one-directional app→keyboard bridge this is deliberately NOT part of; clipboard
    // content is only ever visible to the extension itself, never synced anywhere)
    private var quickPasteChip: UIButton?
    private var pendingQuickPaste: String?
    private var clipboardCache: [(text: String, at: String)] = []
    private var clipboardLoaded = false
    private var lastClipboardChangeCount = -1
    private let clipboardCap = 15              // mirrors the dictation-history wire cap
    private let clipboardEntryCharCap = 4000    // bound file size / row rendering only

    // MARK: transform (select text elsewhere → instruction → LLM rewrite → replace)
    // Mirrors whisperflow/app/transform.py's Mode B exactly (same prompts, same
    // preview-before-replace contract) — see context/03-features.md for why the
    // mechanism differs (no Accessibility-style selection API, no Cmd+Z equivalent).
    private enum TransformState { case idle, compose, busy, preview }
    private var transformState: TransformState = .idle
    private var transformButton: UIButton?
    private var transformCancelButton: UIButton?
    private var transformOriginalText = ""
    private var transformInstruction = ""
    private var transformRewrite = ""
    // `length` is counted in UTF-16 code units — deleteBackward() removes one UTF-16
    // unit per call, so a grapheme count under-deletes on emoji/combining marks (IDI-164).
    private var pendingUndo: (length: Int, original: String)?
    private var undoWorkItem: DispatchWorkItem?
    // IDI-164: monotonic request token (mirrors the Android IME). A chat response whose
    // seq no longer matches `transformSeq` belongs to a cancelled/restarted request and
    // is dropped; `transformTask` lets us actually cancel the socket on cancel/restart.
    private var transformSeq = 0
    private var transformTask: URLSessionDataTask?
    // Input session (see inputSessionId) the current transform was started against —
    // a field switch mid-flow invalidates the captured selection.
    private var transformSessionId = 0
    private let transformSelectionCharCap = 8000   // smaller than desktop's 12000 — mobile
                                                    // selections are shorter; same shared-key TPM caution
    private let transformPresets: [(String, String)] = [
        ("Improvise", ""),   // "" = IMPROVISE_SYSTEM_PROMPT, no instruction (mirrors desktop's 1-tap)
        ("Formal", "Make this more formal"),
        ("Casual", "Make this more casual"),
        ("Shorten", "Make this shorter and tighter"),
        ("Fix grammar", "Fix grammar and punctuation"),
    ]
    // Verbatim from whisperflow/app/transform.py:48-69 — keep in sync; this is a
    // SEPARATE prompt from the dictation cleanup prompt and must never be merged with it.
    private static let transformSystemPrompt =
        "You transform the user's text according to their instruction.\n" +
        "Rules:\n" +
        "- Return ONLY the transformed text. No preamble, no explanation, no quotes, " +
        "no markdown fences.\n" +
        "- Never add facts, names, numbers or claims that are not in the original text.\n" +
        "- Preserve the language of the original text unless the instruction says to translate.\n" +
        "- Keep meaning intact unless the instruction explicitly asks to change it.\n" +
        "- If the instruction is unclear or impossible, return the original text lightly " +
        "cleaned up (punctuation, casing) instead."
    private static let improviseSystemPrompt =
        "You are a precision editor. Rewrite the user's text to be clearer and tighter.\n" +
        "Rules:\n" +
        "- Return ONLY the rewritten text. No preamble, no explanation, no quotes, " +
        "no markdown fences.\n" +
        "- Preserve the meaning, facts, tone register and language. Never add content.\n" +
        "- Fix grammar, punctuation and awkward phrasing; break up run-ons; remove filler.\n" +
        "- Keep the original structure (paragraphs, lists, greetings/sign-offs) intact.\n" +
        "- Do not shorten by more than ~20% unless the text is redundant."

    // Space-swipe cursor control (Gboard): a horizontal drag on the space key moves the caret
    // one character per ~12pt of finger travel instead of inserting a space.
    private var spacePanStart: CGFloat = 0
    private var spacePanSteps = 0
    private var spaceSwiped = false

    // MARK: recording
    private var recorder: AVAudioRecorder?
    private var audioURL: URL?
    private var isRecording = false
    // IDI-161 re-entrancy latches (mirror the Android IME's `busy`). `isArming` covers the
    // async permission → AVAudioRecorder window — `isRecording` only flips INSIDE that
    // callback, so a double-tap used to build two AVAudioRecorders on the same URL.
    // `isTranscribing` covers the in-flight upload so a second dictation can't start
    // (and race the insert guard) while one is still resolving.
    private var isArming = false
    private var isTranscribing = false
    private var soundPlayers: [String: AVAudioPlayer] = [:]
    // IDI-161: bounded network. 15s per-request idle timeout + a 45s hard resource cap
    // (matches the Android IME's connectTimeout=15s / readTimeout=45s) so a hung proxy
    // can never leave the keyboard permanently "busy".
    private lazy var netSession: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 15
        c.timeoutIntervalForResource = 45
        c.waitsForConnectivity = false
        return URLSession(configuration: c)
    }()
    // Groq rejects a Whisper bias prompt over 896 chars (project Hard Rule #6); trim to
    // 850 at a comma boundary exactly like whisperflow/app/transcriber.py.
    private let groqPromptCharCap = 850
    private let groqPromptTermCap = 200            // mirrors dictionary.ts::buildPrompt
    private let supabaseURL = "https://ovpcthjingugwvpxlsna.supabase.co"
    private let supabaseAnon = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92cGN0aGppbmd1Z3d2cHhsc25hIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNjQzMDYsImV4cCI6MjA5Mzg0MDMwNn0.XwTBo8L-aEUmmSl6dJXNqA2QXzGFOpIVB5W9eDI8j28"

    // MARK: input-session identity (IDI-163)
    // An async transcript must only ever land in the SAME field it was dictated into —
    // otherwise a network round-trip that resolves after the user tapped into the next
    // field (worst case a password field) types the transcript there.
    //
    // The signal is `UITextDocumentProxy.documentIdentifier`: a UUID the system mints per
    // text-entry session. It is STABLE across ordinary keystrokes/autocorrect inside one
    // field (so same-field dictation is never false-dropped) and changes when focus moves
    // to another field — exactly the granularity we need. The secure flag rides along so a
    // host that mutates a field into a secure one in place still invalidates the session.
    private var inputSessionId = 0
    private var lastDocSignature: String?

    private func currentDocSignature() -> String {
        // `isSecureTextEntry` is an @objc-optional UITextInputTraits member; `== true`
        // reads correctly whether it imports as Bool or Bool?.
        "\(textDocumentProxy.documentIdentifier.uuidString)|\(textDocumentProxy.isSecureTextEntry == true)"
    }

    /// Bump the session counter when the focused document changed. Cheap enough to call
    /// from textWillChange/textDidChange (a UUID compare, no document-context queries).
    private func syncInputSession() {
        let sig = currentDocSignature()
        guard sig != lastDocSignature else { return }
        let first = lastDocSignature == nil
        lastDocSignature = sig
        inputSessionId &+= 1
        if first { return }
        // A new field invalidates every host-mutating thing scoped to the old one.
        clearPendingUndo()
        if transformState != .idle { abortTransform(reason: nil) }
    }

    /// True when this proxy is a password / secure field — never dictate or transform into one.
    private func isSecureField() -> Bool { textDocumentProxy.isSecureTextEntry == true }

    // MARK: lifecycle
    override func viewDidLoad() {
        super.viewDidLoad()
        registerFonts()
        applyTheme()
        buildUI()
    }

    // Fires each time the keyboard becomes visible again (new field, new app, reopen) —
    // the only reliable moment an extension can notice a clipboard change made elsewhere,
    // since extensions don't run in the background to observe it happen live.
    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        syncInputSession()          // reappearing usually means a new field / new app
        checkClipboardForNewContent()
        if transformState == .idle {
            transformButton?.isHidden = !((readConfig()?["transformEnabled"] as? Bool) ?? false)
        }
    }

    // Register the bundled TTFs so UIFont(name:) resolves them inside the extension.
    private func registerFonts() {
        for name in ["Geist-Regular", "Geist-Medium", "JetBrainsMono-Medium"] {
            guard let url = Bundle(for: type(of: self)).url(forResource: name, withExtension: "ttf") else { continue }
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
    }
    private func uiFont(_ size: CGFloat) -> UIFont { UIFont(name: "Geist-Medium", size: size) ?? .systemFont(ofSize: size, weight: .medium) }
    private func uiFontReg(_ size: CGFloat) -> UIFont { UIFont(name: "Geist-Regular", size: size) ?? .systemFont(ofSize: size) }
    private func monoFont(_ size: CGFloat) -> UIFont { UIFont(name: "JetBrainsMono-Medium", size: size) ?? .monospacedSystemFont(ofSize: size, weight: .medium) }

    // Fires just BEFORE the host's text changes — the earliest hook that already sees the
    // new document when focus moves between fields (IDI-163).
    override func textWillChange(_ textInput: UITextInput?) {
        super.textWillChange(textInput)
        syncInputSession()
    }

    // Fires on input-start and after each text change (incl. our own inserts) → sentence-start auto-cap.
    override func textDidChange(_ textInput: UITextInput?) {
        super.textDidChange(textInput)
        syncInputSession()
        maybeAutoCap()
    }

    override func traitCollectionDidChange(_ previous: UITraitCollection?) {
        super.traitCollectionDidChange(previous)
        if traitCollection.userInterfaceStyle != previous?.userInterfaceStyle {
            applyTheme(); rebuild()
        }
    }

    private func rebuild() {
        backspaceTimer?.invalidate(); backspaceTimer = nil   // don't let a repeat outlive its (removed) key
        view.subviews.forEach { $0.removeFromSuperview() }
        keyPreview = nil                 // was a subview of `view`; drop the stale reference
        keyBaseColor.removeAll(); keyBgView.removeAll()
        buildUI()
        // A theme change mid-transform would desync the freshly-rebuilt bar/content from
        // transformState — simplest safe behavior is to cancel back to idle rather than
        // try to replay busy/preview against a stale network callback.
        transformSeq &+= 1                    // invalidate any in-flight rewrite (IDI-164)
        transformTask?.cancel(); transformTask = nil
        transformState = .idle
        transformInstruction = ""
        refreshQuickPasteChip()   // buildFlumeBar() just recreated the chip hidden — restore its state
    }

    private func buildUI() {
        view.backgroundColor = pal.bg
        // Install the height once (rebuild() only drops subviews). Priority < 1000 so
        // it never fights the system's own input-view height constraint.
        if heightC == nil {
            heightC = view.heightAnchor.constraint(equalToConstant: 300)
            heightC.priority = UILayoutPriority(999)
            heightC.isActive = true
        }

        let root = UIStackView()
        root.axis = .vertical
        root.spacing = 6
        root.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(root)
        NSLayoutConstraint.activate([
            root.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 2),
            root.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -2),
            root.topAnchor.constraint(equalTo: view.topAnchor, constant: 4),
            root.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -4),
        ])

        // suggestion strip
        suggestionStrip = UIStackView()
        suggestionStrip.axis = .horizontal
        suggestionStrip.distribution = .fillEqually
        suggestionStrip.alignment = .fill                 // equal cells spanning the full width (Gboard)
        suggestionStrip.heightAnchor.constraint(equalToConstant: 38).isActive = true
        root.addArrangedSubview(suggestionStrip)

        root.addArrangedSubview(buildFlumeBar())

        contentView = UIView()
        root.addArrangedSubview(contentView)

        showKeyboard()
        updateSuggestions()
    }

    // MARK: Flume bar
    private func buildFlumeBar() -> UIView {
        let bar = UIStackView()
        bar.axis = .horizontal
        bar.alignment = .center
        bar.spacing = 6
        bar.heightAnchor.constraint(equalToConstant: 48).isActive = true

        let f = UILabel()
        f.text = "F"; f.textColor = accent; f.textAlignment = .center   // inverted: keyText square, terracotta F
        f.font = uiFont(15)
        f.backgroundColor = pal.keyText; f.layer.cornerRadius = 8; f.clipsToBounds = true
        f.widthAnchor.constraint(equalToConstant: 34).isActive = true
        f.heightAnchor.constraint(equalToConstant: 34).isActive = true
        bar.addArrangedSubview(f)

        let chip = UIButton(type: .system)
        chip.setTitleColor(.white, for: .normal)
        chip.titleLabel?.font = uiFont(13)
        chip.backgroundColor = accent
        chip.layer.cornerRadius = 14
        chip.contentEdgeInsets = UIEdgeInsets(top: 6, left: 12, bottom: 6, right: 12)
        chip.addAction(UIAction { [weak self] _ in self?.tapQuickPasteChip() }, for: .touchUpInside)
        chip.isHidden = true
        quickPasteChip = chip
        bar.addArrangedSubview(chip)

        let spacer = UIView()                      // flexible spacer (hidden while recording)
        flexSpacer = spacer
        bar.addArrangedSubview(spacer)

        // SF Symbols — the same line-icon set as the design: flash / grid / clock / clipboard / book / mic.
        let icons = UIStackView(); icons.axis = .horizontal; icons.spacing = 6; icons.alignment = .center
        for (glyph, ov) in [("bolt.fill","snippets"), ("square.grid.2x2","canvas"), ("clock","history"),
                            ("doc.on.clipboard","clipboard"), ("book.closed","vocabulary")] {
            icons.addArrangedSubview(barIcon(glyph, ov))
        }
        iconGroup = icons
        bar.addArrangedSubview(icons)
        bar.addArrangedSubview(buildRecordControls())
        bar.addArrangedSubview(buildTransformCancelControl())

        // Transform — a live action on the current selection, same category as mic/dictation,
        // not a browse-a-list overlay, so it sits next to mic rather than in the icon group.
        let tf = circleButton("wand.and.stars", bg: pal.highlightBg, fg: pal.keyText)
        tf.addAction(UIAction { [weak self] _ in self?.onTransformTap() }, for: .touchUpInside)
        tf.isHidden = !((readConfig()?["transformEnabled"] as? Bool) ?? false)
        transformButton = tf
        bar.addArrangedSubview(tf)

        micButton = circleButton("mic.fill", bg: pal.micBg, fg: pal.micFg)
        micButton.addTarget(self, action: #selector(onMicTap), for: .touchUpInside)
        let micDot = UIView()                    // orange dot badge (top-right)
        micDot.backgroundColor = accent
        micDot.layer.cornerRadius = 4
        micDot.translatesAutoresizingMaskIntoConstraints = false
        micButton.addSubview(micDot)
        NSLayoutConstraint.activate([
            micDot.widthAnchor.constraint(equalToConstant: 8),
            micDot.heightAnchor.constraint(equalToConstant: 8),
            micDot.topAnchor.constraint(equalTo: micButton.topAnchor, constant: 2),
            micDot.trailingAnchor.constraint(equalTo: micButton.trailingAnchor, constant: -2),
        ])
        bar.addArrangedSubview(micButton)
        return bar
    }

    // Recording bar (RECORDING_BAR_PROMPT.md, #51/#52): F · ✕ · waveform · 0:04 · terracotta.
    private func buildRecordControls() -> UIView {
        let row = UIStackView(); row.axis = .horizontal; row.spacing = 10; row.alignment = .center
        row.isHidden = true
        row.setContentHuggingPriority(.defaultLow, for: .horizontal)

        // ✕ cancel — neutral circle icon chip
        let cancel = UIButton(type: .system)
        cancel.setImage(UIImage(systemName: "xmark", withConfiguration: UIImage.SymbolConfiguration(pointSize: 15, weight: .semibold)), for: .normal)
        cancel.tintColor = pal.keyText
        cancel.backgroundColor = pal.highlightBg; cancel.layer.cornerRadius = 19
        cancel.widthAnchor.constraint(equalToConstant: 38).isActive = true
        cancel.heightAnchor.constraint(equalToConstant: 38).isActive = true
        cancel.addAction(UIAction { [weak self] _ in self?.cancelRecording() }, for: .touchUpInside)

        // live waveform — text-colored bars, fills the middle
        let wave = WaveformView()
        wave.color = pal.keyText
        wave.setContentHuggingPriority(.defaultLow, for: .horizontal)
        wave.heightAnchor.constraint(equalToConstant: 20).isActive = true
        waveformView = wave

        // M:SS mono timer
        let timer = UILabel()
        timer.text = "0:00"; timer.textColor = pal.mutedText; timer.font = monoFont(12)
        timerLabel = timer

        // ⏸ pause — neutral circle, tap = pause/resume
        let pause = UIButton(type: .system)
        pause.setImage(UIImage(systemName: "pause.fill", withConfiguration: UIImage.SymbolConfiguration(pointSize: 14, weight: .semibold)), for: .normal)
        pause.tintColor = pal.keyText
        pause.backgroundColor = pal.highlightBg; pause.layer.cornerRadius = 19
        pause.widthAnchor.constraint(equalToConstant: 38).isActive = true
        pause.heightAnchor.constraint(equalToConstant: 38).isActive = true
        pause.addAction(UIAction { [weak self] _ in self?.togglePause() }, for: .touchUpInside)
        pauseButton = pause

        // ■ stop — terracotta circle, tap = stop & send
        let stop = UIButton(type: .system)
        stop.setImage(UIImage(systemName: "stop.fill", withConfiguration: UIImage.SymbolConfiguration(pointSize: 14, weight: .bold)), for: .normal)
        stop.tintColor = .white
        stop.backgroundColor = accent; stop.layer.cornerRadius = 21
        stop.widthAnchor.constraint(equalToConstant: 42).isActive = true
        stop.heightAnchor.constraint(equalToConstant: 42).isActive = true
        stop.addAction(UIAction { [weak self] _ in self?.stopAndTranscribe() }, for: .touchUpInside)

        row.addArrangedSubview(cancel)
        row.addArrangedSubview(wave)
        row.addArrangedSubview(timer)
        row.addArrangedSubview(pause)
        row.addArrangedSubview(stop)
        recordControls = row
        return row
    }

    // Compose-mode bar swap (mirrors buildRecordControls' role): replaces the icon group
    // + transform button with a single ✕ while the user is composing a transform instruction.
    private func buildTransformCancelControl() -> UIView {
        let cancel = UIButton(type: .system)
        cancel.setImage(UIImage(systemName: "xmark", withConfiguration: UIImage.SymbolConfiguration(pointSize: 15, weight: .semibold)), for: .normal)
        cancel.tintColor = pal.keyText
        cancel.backgroundColor = pal.highlightBg; cancel.layer.cornerRadius = 19
        cancel.widthAnchor.constraint(equalToConstant: 38).isActive = true
        cancel.heightAnchor.constraint(equalToConstant: 38).isActive = true
        cancel.isHidden = true
        cancel.addAction(UIAction { [weak self] _ in self?.exitCompose() }, for: .touchUpInside)
        transformCancelButton = cancel
        return cancel
    }

    private func pauseIcon(_ name: String) {
        pauseButton?.setImage(UIImage(systemName: name, withConfiguration: UIImage.SymbolConfiguration(pointSize: 14, weight: .semibold)), for: .normal)
    }

    private func enterRecordingUI() {
        isPaused = false; pauseButton?.alpha = 1; pauseIcon("pause.fill"); waveformView?.reset()
        recStart = Date(); pausedTotal = 0; timerLabel?.text = "0:00"
        recordControls?.alpha = 0
        // Compose mode's own ✕ would otherwise sit alongside recordControls' cancel —
        // hide it for the duration of the recording, restored in exitRecordingUI().
        transformCancelButton?.isHidden = true
        UIView.animate(withDuration: 0.25) {
            self.iconGroup?.isHidden = true
            self.flexSpacer?.isHidden = true
            self.micButton?.isHidden = true                 // mic fades out too (spec)
            self.recordControls?.isHidden = false
            self.recordControls?.alpha = 1
        }
        startMeter(); startElapsed()
    }

    private func exitRecordingUI() {
        stopMeter(); stopElapsed(); isPaused = false
        iconGroup?.alpha = 0
        // Mic can be repurposed to "speak a transform instruction" — if a transform flow
        // is still active (compose/busy), restore ITS bar state, not the normal one.
        if transformState != .idle {
            UIView.animate(withDuration: 0.25) {
                self.recordControls?.isHidden = true
                self.transformCancelButton?.isHidden = false
            }
            return
        }
        UIView.animate(withDuration: 0.25) {
            self.recordControls?.isHidden = true
            self.iconGroup?.isHidden = false
            self.flexSpacer?.isHidden = false
            self.micButton?.isHidden = false
            self.iconGroup?.alpha = 1
        }
    }

    private func togglePause() {
        guard let rec = recorder else { return }
        if !isPaused { rec.pause(); isPaused = true; pauseStart = Date(); pauseIcon("play.fill") }
        else { rec.record(); isPaused = false; pausedTotal += Date().timeIntervalSince(pauseStart); pauseIcon("pause.fill") }
    }

    private func cancelRecording() {
        stopMeter(); stopElapsed()
        recorder?.stop(); recorder = nil
        try? AVAudioSession.sharedInstance().setActive(false)
        if let url = audioURL { try? FileManager.default.removeItem(at: url) }
        audioURL = nil; isRecording = false
        micSymbol("mic.fill"); exitRecordingUI()
    }

    private func startMeter() {
        recorder?.isMeteringEnabled = true
        meterTimer?.invalidate()
        meterTimer = Timer.scheduledTimer(withTimeInterval: 0.033, repeats: true) { [weak self] _ in
            guard let self = self, let rec = self.recorder, self.isRecording, !self.isPaused else { return }
            rec.updateMeters()
            let lin: Double = pow(10.0, Double(rec.averagePower(forChannel: 0)) / 20.0)   // dB → 0..1
            self.waveformView?.tick(CGFloat(min(1.0, max(0.0, lin))))
        }
    }
    private func stopMeter() { meterTimer?.invalidate(); meterTimer = nil }

    private func startElapsed() {
        elapsedTimer?.invalidate()
        elapsedTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            guard let self = self, self.isRecording else { return }
            let ref = self.isPaused ? self.pauseStart : Date()
            let s = Int(max(0, ref.timeIntervalSince(self.recStart) - self.pausedTotal))
            self.timerLabel?.text = "\(s / 60):\(String(format: "%02d", s % 60))"
        }
    }
    private func stopElapsed() { elapsedTimer?.invalidate(); elapsedTimer = nil }

    // Desktop-widget waveform: a continuous travelling wave (whisperflow overlay_html bars
    // animate 4↔15px on a ~0.9s loop with a per-bar stagger). Louder voice → taller.
    final class WaveformView: UIView {
        var color: UIColor = .systemOrange
        private let n = 18
        private var phase: Double = 0
        private var level: CGFloat = 0            // 0..1 smoothed real loudness (0 on simulator)
        func tick(_ realLevel: CGFloat) {
            phase += 0.22                          // ~30fps → ~0.9s period like the desktop keyframes
            level += (min(1, max(0, realLevel)) - level) * 0.35
            setNeedsDisplay()
        }
        func reset() { phase = 0; level = 0; setNeedsDisplay() }
        override func draw(_ rect: CGRect) {
            guard let ctx = UIGraphicsGetCurrentContext() else { return }
            let bw: CGFloat = 2, gap: CGFloat = 2, minH: CGFloat = 3, maxH: CGFloat = 18
            let totalW = CGFloat(n) * bw + CGFloat(n - 1) * gap
            let startX = (rect.width - totalW) / 2
            let cy = rect.height / 2
            ctx.setFillColor(color.cgColor)
            for i in 0..<n {
                let osc = 0.5 + 0.5 * sin(phase - Double(i) * 0.55)     // travelling wave, staggered per bar
                let amp = 0.55 + 0.45 * level                            // louder voice → taller (still animates at 0)
                var h = minH + (maxH - minH) * CGFloat(osc) * amp
                h = min(maxH, max(minH, h))
                let x = startX + CGFloat(i) * (bw + gap)
                ctx.addPath(UIBezierPath(roundedRect: CGRect(x: x, y: cy - h/2, width: bw, height: h), cornerRadius: bw/2).cgPath)
                ctx.fillPath()
            }
        }
    }

    private func barIcon(_ symbol: String, _ overlay: String) -> UIButton {
        let b = UIButton(type: .system)
        let cfg = UIImage.SymbolConfiguration(pointSize: 18, weight: .regular)
        b.setImage(UIImage(systemName: symbol, withConfiguration: cfg), for: .normal)
        b.tintColor = pal.iconTint
        b.backgroundColor = activeOverlay == overlay ? pal.highlightBg : .clear
        b.layer.cornerRadius = 10
        b.widthAnchor.constraint(equalToConstant: 40).isActive = true
        b.heightAnchor.constraint(equalToConstant: 40).isActive = true
        b.addAction(UIAction { [weak self] _ in self?.toggleOverlay(overlay) }, for: .touchUpInside)
        barButtons[overlay] = b
        return b
    }

    private func circleButton(_ symbol: String, bg: UIColor, fg: UIColor) -> UIButton {
        let b = UIButton(type: .system)
        let cfg = UIImage.SymbolConfiguration(pointSize: 18, weight: .semibold)
        b.setImage(UIImage(systemName: symbol, withConfiguration: cfg), for: .normal)
        b.tintColor = fg
        b.backgroundColor = bg; b.layer.cornerRadius = 20
        b.widthAnchor.constraint(equalToConstant: 40).isActive = true
        b.heightAnchor.constraint(equalToConstant: 40).isActive = true
        return b
    }

    // Swap the mic glyph between idle (mic) and recording (stop) — SF Symbols, tinted by fg.
    private func micSymbol(_ name: String) {
        let cfg = UIImage.SymbolConfiguration(pointSize: 18, weight: .semibold)
        micButton.setImage(UIImage(systemName: name, withConfiguration: cfg), for: .normal)
    }

    private func refreshBar() {
        for (ov, b) in barButtons { b.backgroundColor = activeOverlay == ov ? pal.highlightBg : .clear }
    }

    // MARK: key layers
    private let lettersRows = [["q","w","e","r","t","y","u","i","o","p"],
                               ["a","s","d","f","g","h","j","k","l"],
                               ["z","x","c","v","b","n","m"]]
    private let numbersRows = [["1","2","3","4","5","6","7","8","9","0"],
                               ["@","#","$","_","&","-","+","(",")","/"],
                               ["*","\"","'",":",";","!","?"]]
    private let symbolsRows = [["~","`","|","•","√","π","÷","×","¶","∆"],
                               ["£","¢","€","¥","^","°","=","{","}","\\"],
                               ["%","©","®","™","✓","[","]"]]

    private func showKeyboard() {
        activeOverlay = nil
        refreshBar()
        setContent(buildKeyboard())
        updateSuggestions()
    }

    private func setContent(_ v: UIView) {
        contentView.subviews.forEach { $0.removeFromSuperview() }
        v.translatesAutoresizingMaskIntoConstraints = false
        contentView.addSubview(v)
        NSLayoutConstraint.activate([
            v.leadingAnchor.constraint(equalTo: contentView.leadingAnchor),
            v.trailingAnchor.constraint(equalTo: contentView.trailingAnchor),
            v.topAnchor.constraint(equalTo: contentView.topAnchor),
            v.bottomAnchor.constraint(equalTo: contentView.bottomAnchor),
        ])
    }

    private func buildKeyboard() -> UIView {
        keyBaseColor.removeAll(); keyBgView.removeAll()   // keys are rebuilt here; drop the previous layer's button refs
        letterKeys.removeAll(); shiftKeyBtn = nil          // rebuilt fresh below (in-place caps refresh)
        // spacing 0 on every key row (and the vertical stack) → gapless touch; the visual gap comes
        // from each key's inset background subview (installKeyBackground), so taps never fall in a dead zone.
        let kb = UIStackView(); kb.axis = .vertical; kb.spacing = 0
        let rows = layer == .letters ? lettersRows : (layer == .numbers ? numbersRows : symbolsRows)
        kb.addArrangedSubview(keyRow(rows[0]))
        kb.addArrangedSubview(keyRow(rows[1], inset: layer == .letters ? 18 : 0))
        // row 3: shift/toggle + keys + backspace
        let r3 = UIStackView(); r3.axis = .horizontal; r3.spacing = 0; r3.distribution = .fill
        let leftLabel = layer == .letters ? (capsLock ? "⇪" : "⇧") : (layer == .numbers ? "=\\<" : "?123")
        let shiftBtn = funcKey(leftLabel, width: 44) { [weak self] in
            guard let self = self else { return }
            if self.layer == .letters { self.onShift() }
            else { self.layer = self.layer == .numbers ? .symbols : .numbers; self.showKeyboard() }
        }
        if layer == .letters { shiftKeyBtn = shiftBtn }
        r3.addArrangedSubview(shiftBtn)
        let mid = UIStackView(); mid.axis = .horizontal; mid.spacing = 0; mid.distribution = .fillEqually
        for k in rows[2] { mid.addArrangedSubview(charKey(k)) }
        r3.addArrangedSubview(mid)
        r3.addArrangedSubview(backspaceKey(width: 44))
        kb.addArrangedSubview(r3)
        // row 4
        let r4 = UIStackView(); r4.axis = .horizontal; r4.spacing = 0; r4.distribution = .fill
        r4.addArrangedSubview(funcKey(layer == .letters ? "?123" : "ABC", width: 50) { [weak self] in
            guard let self = self else { return }
            self.layer = self.layer == .letters ? .numbers : .letters; self.showKeyboard()
        })
        let comma = commaKey()
        comma.widthAnchor.constraint(equalToConstant: 34).isActive = true
        r4.addArrangedSubview(comma)
        r4.addArrangedSubview(buildSpaceKey())
        let period = charKey("."); period.widthAnchor.constraint(equalToConstant: 34).isActive = true
        r4.addArrangedSubview(period)
        let ret = funcKey("↵", width: 60) { [weak self] in
            guard let self = self else { return }
            if self.transformState == .compose && !self.transformInstruction.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                self.sendTransform()
            } else {
                self.textDocumentProxy.insertText("\n")
            }
        }
        setKeyBaseColor(ret, pal.returnBg); ret.setTitleColor(pal.returnText, for: .normal)
        r4.addArrangedSubview(ret)
        kb.addArrangedSubview(r4)
        return kb
    }

    private func keyRow(_ keys: [String], inset: CGFloat = 0) -> UIView {
        let row = UIStackView(); row.axis = .horizontal; row.spacing = 0; row.distribution = .fillEqually
        row.heightAnchor.constraint(equalToConstant: 46).isActive = true
        for k in keys { row.addArrangedSubview(charKey(k)) }
        if inset > 0 {
            let wrap = UIStackView(arrangedSubviews: [spacer(inset), row, spacer(inset)])
            wrap.axis = .horizontal; wrap.spacing = 0
            return wrap
        }
        return row
    }

    private func spacer(_ w: CGFloat) -> UIView {
        let v = UIView(); v.widthAnchor.constraint(equalToConstant: w).isActive = true; return v
    }

    /// The title to SHOW/COMMIT for a base key, given the live shift/caps state.
    private func casedChar(_ base: String) -> String {
        (layer == .letters && (shifted || capsLock) && base.count == 1 && (base.first?.isLetter ?? false))
            ? base.uppercased() : base
    }

    /// Update letter titles + the shift glyph without tearing down the view tree.
    private func refreshLetterCaps() {
        for (b, base) in letterKeys { b.setTitle(casedChar(base), for: .normal) }
        shiftKeyBtn?.setTitle(capsLock ? "⇪" : "⇧", for: .normal)
    }

    private func charKey(_ label: String) -> UIButton {
        let isLetter = label.count == 1 && (label.first?.isLetter ?? false)
        let b = UIButton(type: .system)
        b.setTitle(casedChar(label), for: .normal)
        b.setTitleColor(pal.keyText, for: .normal)
        b.titleLabel?.font = uiFont(20)
        b.heightAnchor.constraint(equalToConstant: 46).isActive = true
        installKeyBackground(b, color: pal.keyBg)
        // Fire on touch-DOWN so fast taps that slide slightly are never dropped. Case is
        // read LIVE so a one-shot/auto-cap flip (applied in place) commits the right case.
        b.addAction(UIAction { [weak self] _ in guard let self = self else { return }; self.onCharKey(self.casedChar(label)) }, for: .touchDown)
        b.addTarget(self, action: #selector(keyDownVisual(_:)), for: .touchDown)
        b.addTarget(self, action: #selector(keyUpVisual(_:)), for: [.touchUpInside, .touchDragExit, .touchCancel])
        if isLetter { letterKeys.append((b, label)) }
        return b
    }

    private func funcKey(_ label: String, width: CGFloat, flexible: Bool = false, _ action: @escaping () -> Void) -> UIButton {
        let b = UIButton(type: .system)
        b.setTitle(label, for: .normal)
        b.setTitleColor(pal.keyText, for: .normal)
        b.titleLabel?.font = uiFont(label.count > 2 ? 13 : 16)
        b.heightAnchor.constraint(equalToConstant: 46).isActive = true
        installKeyBackground(b, color: pal.modBg)
        if flexible {
            b.setContentHuggingPriority(.defaultLow, for: .horizontal)
            b.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        } else {
            b.widthAnchor.constraint(equalToConstant: width).isActive = true
        }
        b.addAction(UIAction { _ in action() }, for: .touchDown)
        b.addTarget(self, action: #selector(keyDownVisual(_:)), for: .touchDown)
        b.addTarget(self, action: #selector(keyUpVisual(_:)), for: [.touchUpInside, .touchDragExit, .touchCancel])
        return b
    }

    // Comma: mirrors Android — commits "," on touch-UP only if the long-press→emoji did NOT
    // fire. (charKey commits on touch-DOWN, which would insert a stray "," before the long-press
    // opened emoji.) The long-press recognizer cancels the button touch on recognition, so
    // .touchUpInside does not fire after a hold. Pressed-state + input-click kept.
    private func commaKey() -> UIButton {
        let b = UIButton(type: .system)
        b.setTitle(",", for: .normal)
        b.setTitleColor(pal.keyText, for: .normal)
        b.titleLabel?.font = uiFont(20)
        b.heightAnchor.constraint(equalToConstant: 46).isActive = true
        installKeyBackground(b, color: pal.keyBg)
        b.addAction(UIAction { [weak self] _ in self?.onCharKey(",") }, for: .touchUpInside)   // commit on UP
        b.addTarget(self, action: #selector(keyDownVisual(_:)), for: .touchDown)
        b.addTarget(self, action: #selector(keyUpVisual(_:)), for: [.touchUpInside, .touchDragExit, .touchCancel])
        let long = UILongPressGestureRecognizer(target: self, action: #selector(onCommaLong(_:)))
        b.addGestureRecognizer(long)
        return b
    }

    // Backspace with hold-to-repeat (mirrors Android attachRepeat): delete once on down, then
    // repeat every 55ms after a 400ms hold. Pressed-state + input-click via keyDownVisual/keyUpVisual.
    private func backspaceKey(width: CGFloat) -> UIButton {
        let b = UIButton(type: .system)
        b.setTitle("⌫", for: .normal)
        b.setTitleColor(pal.keyText, for: .normal)
        b.titleLabel?.font = uiFont(16)
        b.heightAnchor.constraint(equalToConstant: 46).isActive = true
        b.widthAnchor.constraint(equalToConstant: width).isActive = true
        installKeyBackground(b, color: pal.modBg)
        b.addTarget(self, action: #selector(keyDownVisual(_:)), for: .touchDown)
        b.addTarget(self, action: #selector(keyUpVisual(_:)), for: [.touchUpInside, .touchDragExit, .touchCancel])
        b.addTarget(self, action: #selector(backspaceDown), for: .touchDown)
        b.addTarget(self, action: #selector(backspaceUp), for: [.touchUpInside, .touchUpOutside, .touchCancel, .touchDragExit])
        return b
    }
    @objc private func backspaceDown() {
        onBackspace()
        backspaceTimer?.invalidate()
        backspaceTimer = Timer.scheduledTimer(withTimeInterval: 0.4, repeats: false) { [weak self] _ in
            self?.backspaceTimer?.invalidate()
            self?.backspaceTimer = Timer.scheduledTimer(withTimeInterval: 0.055, repeats: true) { [weak self] _ in
                self?.onBackspace()
            }
        }
    }
    @objc private func backspaceUp() { backspaceTimer?.invalidate(); backspaceTimer = nil }

    // Space key: cursor-swipe (Gboard). A horizontal drag moves the caret one char per ~12pt of
    // travel (via onSpacePan → adjustTextPosition); a plain tap inserts a space. Built WITHOUT
    // funcKey's touch-DOWN insert so a swipe never types a space. Space now commits on LIFT:
    //   • a drag that crossed >=1 step → cursor moved, NO space (pan .ended, spaceSwiped == true)
    //   • a drag too small to cross a step → space (pan .ended, spaceSwiped == false)
    //   • a pure tap that never starts the pan → space (button .touchUpInside)
    // Those three are mutually exclusive (the pan's cancelsTouchesInView cancels the button touch
    // once it begins, so .touchUpInside can't also fire), so a space is inserted at most once.
    private func buildSpaceKey() -> UIButton {
        let b = UIButton(type: .system)
        b.setTitle("English (US)", for: .normal)
        b.titleLabel?.font = uiFont(13)
        b.heightAnchor.constraint(equalToConstant: 46).isActive = true
        installKeyBackground(b, color: pal.keyBg)
        setKeyBaseColor(b, pal.keyBg)
        b.setTitleColor(pal.mutedText, for: .normal)
        b.setContentHuggingPriority(.defaultLow, for: .horizontal)
        b.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        // Pressed-state visual + input-click on down, but NO text insertion on down.
        b.addTarget(self, action: #selector(keyDownVisual(_:)), for: .touchDown)
        b.addTarget(self, action: #selector(keyUpVisual(_:)), for: [.touchUpInside, .touchDragExit, .touchCancel])
        // Pure tap (pan never begins → no cursor move) inserts a space on lift.
        b.addAction(UIAction { [weak self] _ in self?.onSpace() }, for: .touchUpInside)
        let pan = UIPanGestureRecognizer(target: self, action: #selector(onSpacePan(_:)))
        pan.maximumNumberOfTouches = 1
        b.addGestureRecognizer(pan)
        return b
    }

    @objc private func onSpacePan(_ g: UIPanGestureRecognizer) {
        switch g.state {
        case .began:
            spacePanStart = 0; spacePanSteps = 0; spaceSwiped = false
        case .changed:
            // A transform flow owns the host document (the selection must survive untouched
            // until Replace) — moving the caret mid-compose/busy/preview would silently
            // collapse it. Swallow the drag; a lift still feeds a space to the instruction
            // buffer via onSpace() (IDI-164).
            guard transformState == .idle else { return }
            let dx = g.translation(in: g.view).x
            let steps = Int(dx / 12)
            if steps != spacePanSteps {
                let delta = steps - spacePanSteps
                textDocumentProxy.adjustTextPosition(byCharacterOffset: delta)   // + = right, - = left
                spacePanSteps = steps
                if abs(steps) >= 1 { spaceSwiped = true }
            }
        case .ended, .cancelled:
            // A drag that began but never crossed a full step → treat as a plain tap → space.
            if !spaceSwiped && g.state == .ended { onSpace() }
        default: break
        }
    }

    // MARK: key handling
    private func onCharKey(_ ch: String) {
        commit(ch)
        // one-shot shift clears after a letter — update titles IN PLACE (a full
        // showKeyboard() rebuild here raced the next rapid tap and dropped it).
        if layer == .letters && shifted && !capsLock { shifted = false; refreshLetterCaps() }
    }
    private func commit(_ s: String) {
        // While composing a transform instruction, the SAME letter keys feed a local
        // buffer instead of the host app — the original selection is never touched
        // until Replace, which is what keeps it alive through the whole flow.
        if transformState == .compose {
            transformInstruction += s
            refreshTransformComposeUI()
            return
        }
        // Learn the just-finished word when a single non-letter boundary (space/punctuation)
        // is committed — capture BEFORE inserting so currentWordPrefix() still sees the word.
        if s.count == 1, let ch = s.first, !ch.isLetter {
            learnWord(currentWordPrefix())
            if let tw = lastTwoWords() { learnBigram(tw.0, tw.1) }
        }
        // Once the user types, the soft-undo's "delete N chars back" no longer addresses the
        // rewrite it was created for — retire it rather than eat the new text (IDI-164).
        clearPendingUndo()
        textDocumentProxy.insertText(s); updateSuggestions()
    }
    // Space key: double-space → ". " (Gboard). If the text before the cursor ends with a single
    // space that is itself preceded by a letter/digit, replace that space with ". "; else a normal space.
    private func onSpace() {
        if transformState == .compose { commit(" "); return }
        let before = textDocumentProxy.documentContextBeforeInput ?? ""
        if before.hasSuffix(" ") && before.count >= 2 {
            let prev = before[before.index(before.endIndex, offsetBy: -2)]
            if prev.isLetter || prev.isNumber {
                clearPendingUndo()
                textDocumentProxy.deleteBackward()
                textDocumentProxy.insertText(". ")
                updateSuggestions()
                return
            }
        }
        commit(" ")
    }

    // Auto-capitalize at the start of a sentence: flip `shifted` on when the document is empty or the
    // text ends with a sentence terminator followed by a space. Only rebuilds when the state flips.
    private func maybeAutoCap() {
        guard layer == .letters, !capsLock else { return }
        if textDocumentProxy.autocapitalizationType == UITextAutocapitalizationType.none { return }
        let before = textDocumentProxy.documentContextBeforeInput ?? ""
        var want = false
        if before.isEmpty {
            want = true
        } else if before.hasSuffix(" ") {
            let woSpace = before.dropLast()
            if let last = woSpace.last, last == "." || last == "!" || last == "?" { want = true }
        }
        if want != shifted {
            shifted = want
            refreshLetterCaps()   // in-place, no rebuild
        }
    }

    private func onShift() {
        if capsLock { capsLock = false; shifted = false }
        else if shifted { capsLock = true }
        else { shifted = true }
        refreshLetterCaps()   // in-place caps/glyph swap (no full rebuild)
    }
    private func onBackspace() {
        if transformState == .compose {
            if !transformInstruction.isEmpty { transformInstruction.removeLast() }
            refreshTransformComposeUI()
            return
        }
        clearPendingUndo()   // manual editing invalidates the soft-undo span (IDI-164)
        textDocumentProxy.deleteBackward(); updateSuggestions()
    }

    @objc private func onCommaLong(_ g: UILongPressGestureRecognizer) {
        if g.state == .began { openEmoji() }
    }

    // MARK: suggestions (word→emoji → personal learned → user vocabulary → bundled dictionary)
    // DEBOUNCED (~70ms): the config read + 25k-word scan + document-context queries never
    // run synchronously inside a keystroke commit (that janked the main thread and dropped
    // fast taps). Coalesced — only the last tap in a burst computes suggestions.
    private func updateSuggestions() {
        suggestWork?.cancel()
        let w = DispatchWorkItem { [weak self] in self?.doUpdateSuggestions() }
        suggestWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.07, execute: w)
    }
    private func doUpdateSuggestions() {
        guard suggestionStrip != nil else { return }
        if transformState != .idle { return }   // compose UI owns the suggestion strip
        if activeOverlay != nil { renderSuggestionCells([]); return }
        let raw = currentWordPrefix()
        let word = raw.lowercased()
        var cells: [UIView] = []

        if word.isEmpty {
            // EMPTY prefix → next-word predictions keyed on the previous word.
            let before = textDocumentProxy.documentContextBeforeInput ?? ""
            let trimmed = before.replacingOccurrences(of: "\\s+$", with: "", options: .regularExpression)
            let letterToks = trimmed.components(separatedBy: CharacterSet.letters.inverted).filter { !$0.isEmpty }
            if let prevRaw = letterToks.last {
                let prev = prevRaw.lowercased()
                if !prev.isEmpty {
                    loadLearnedBg()
                    var nextPicks: [String] = []
                    var nextSeen = Set<String>()
                    func considerNext(_ candidate: String) {
                        let lc = candidate.lowercased()
                        if lc.isEmpty || lc == prev { return }
                        if nextSeen.contains(lc) { return }
                        nextSeen.insert(lc)
                        nextPicks.append(candidate)
                    }
                    // 1) personal learned bigrams, most-used first
                    if let inner = learnedBg[prev] {
                        for (w, _) in inner.sorted(by: { $0.value > $1.value }) {
                            considerNext(w); if nextPicks.count >= 3 { break }
                        }
                    }
                    // 2) bundled bigram table, in order
                    if nextPicks.count < 3, let nexts = bigrams[prev] {
                        for w in nexts {
                            considerNext(w); if nextPicks.count >= 3 { break }
                        }
                    }
                    for w in nextPicks { cells.append(wordSuggestionButton(w)) }
                }
            }
            renderSuggestionCells(cells)
            return
        }
        loadLearned()

        // Word→emoji suggestion for an EXACT full word (shown first); then up to 2 completions.
        var emojiPick: String? = nil
        if let list = emojiKw[word], let first = list.first { emojiPick = first }
        let wordLimit = emojiPick != nil ? 2 : 3

        var picks: [String] = []
        var seen = Set<String>()                       // dedupe case-insensitively across sources
        func consider(_ candidate: String) {
            let lc = candidate.lowercased()
            if lc == word || lc.isEmpty { return }     // skip the prefix itself
            if seen.contains(lc) { return }
            seen.insert(lc)
            picks.append(candidate)
        }

        // 1) personal learned words, most-used first
        let learnedMatches = learned.filter { $0.key.hasPrefix(word) }.sorted { $0.value > $1.value }
        for (w, _) in learnedMatches {
            consider(w); if picks.count >= wordLimit { break }
        }
        // 2) user vocabulary
        if picks.count < wordLimit, let cfg = readConfig(), let vocab = cfg["vocabulary"] as? [[String: Any]] {
            for v in vocab {
                let w = v["word"] as? String ?? ""
                if !w.isEmpty && w.lowercased().hasPrefix(word) {
                    consider(w); if picks.count >= wordLimit { break }
                }
            }
        }
        // 3) bundled frequency dictionary (already frequency-ranked; stop once we have enough)
        if picks.count < wordLimit {
            for w in dictWords {
                if w.hasPrefix(word) {
                    consider(w); if picks.count >= wordLimit { break }
                }
            }
        }

        // Preserve the user's casing.
        let upper = raw.count > 1 && raw == raw.uppercased()
        let cap = !upper && (raw.first?.isUppercase ?? false)
        if let e = emojiPick { cells.append(emojiSuggestionButton(e)) }
        for p in picks {
            let shown: String
            if upper { shown = p.uppercased() }
            else if cap { shown = p.prefix(1).uppercased() + p.dropFirst() }
            else { shown = p }
            cells.append(wordSuggestionButton(shown))
        }
        renderSuggestionCells(cells)
    }

    // A centered word-completion cell (tap replaces the current word).
    private func wordSuggestionButton(_ shown: String) -> UIButton {
        let b = UIButton(type: .system)
        b.setTitle(shown, for: .normal); b.setTitleColor(pal.keyText, for: .normal)
        b.titleLabel?.font = uiFont(14)
        b.addAction(UIAction { [weak self] _ in self?.replaceCurrentWord(shown) }, for: .touchUpInside)
        return b
    }
    // A word→emoji cell (tap replaces the typed word with the emoji + a trailing space).
    private func emojiSuggestionButton(_ e: String) -> UIButton {
        let b = UIButton(type: .system)
        b.setTitle(e, for: .normal)
        b.titleLabel?.font = .systemFont(ofSize: 22)
        b.addAction(UIAction { [weak self] _ in self?.replaceCurrentWordWithEmoji(e) }, for: .touchUpInside)
        return b
    }
    private func replaceCurrentWordWithEmoji(_ emoji: String) {
        clearPendingUndo()
        let prefix = currentWordPrefix()
        for _ in 0..<prefix.count { textDocumentProxy.deleteBackward() }
        textDocumentProxy.insertText(emoji + " ")
        updateSuggestions()
    }
    // Distribute the strip like Gboard: up to 3 EQUAL cells (fillEqually) with thin vertical
    // dividers between them. Fewer than 3 picks stay distributed across the present cells.
    private func renderSuggestionCells(_ cells: [UIView]) {
        guard let strip = suggestionStrip else { return }
        strip.arrangedSubviews.forEach { $0.removeFromSuperview() }
        for (i, content) in cells.prefix(3).enumerated() {
            strip.addArrangedSubview(suggestionCell(content, showLeadingDivider: i > 0))
        }
    }
    private func suggestionCell(_ content: UIView, showLeadingDivider: Bool) -> UIView {
        let cell = UIView()
        content.translatesAutoresizingMaskIntoConstraints = false
        cell.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: cell.leadingAnchor),
            content.trailingAnchor.constraint(equalTo: cell.trailingAnchor),
            content.topAnchor.constraint(equalTo: cell.topAnchor),
            content.bottomAnchor.constraint(equalTo: cell.bottomAnchor),
        ])
        if showLeadingDivider {
            let div = UIView()
            div.backgroundColor = pal.mutedText.withAlphaComponent(0.2)
            div.isUserInteractionEnabled = false
            div.translatesAutoresizingMaskIntoConstraints = false
            cell.addSubview(div)
            NSLayoutConstraint.activate([
                div.leadingAnchor.constraint(equalTo: cell.leadingAnchor),
                div.widthAnchor.constraint(equalToConstant: 1),
                div.topAnchor.constraint(equalTo: cell.topAnchor, constant: 8),
                div.bottomAnchor.constraint(equalTo: cell.bottomAnchor, constant: -8),
            ])
        }
        return cell
    }
    private func currentWordPrefix() -> String {
        let before = textDocumentProxy.documentContextBeforeInput ?? ""
        let parts = before.components(separatedBy: CharacterSet.alphanumerics.inverted)
        return parts.last ?? ""
    }
    private func replaceCurrentWord(_ word: String) {
        clearPendingUndo()
        let prefix = currentWordPrefix()
        for _ in 0..<prefix.count { textDocumentProxy.deleteBackward() }
        textDocumentProxy.insertText(word + " ")
        learnWord(word)
        updateSuggestions()
    }
    private func formatTime(_ iso: String?) -> String {
        guard let iso = iso, iso.count >= 16 else { return "" }
        let start = iso.index(iso.startIndex, offsetBy: 11)
        let end = iso.index(iso.startIndex, offsetBy: 16)
        var hm = String(iso[start..<end])   // "HH:MM" (UTC)
        if hm.hasPrefix("0") { hm.removeFirst() }
        return hm
    }

    // MARK: overlays
    private func toggleOverlay(_ which: String) {
        if activeOverlay == which { showKeyboard(); return }
        activeOverlay = which; refreshBar()
        suggestionStrip.arrangedSubviews.forEach { $0.removeFromSuperview() }
        setContent(buildOverlay(which))
    }

    private func buildOverlay(_ which: String) -> UIView {
        let wrap = UIStackView(); wrap.axis = .vertical; wrap.spacing = 6
        let header = UILabel()
        header.text = which.uppercased(); header.textColor = pal.mutedText
        header.font = monoFont(11)
        wrap.addArrangedSubview(header)

        let scroll = UIScrollView()
        let list = UIStackView(); list.axis = .vertical; list.spacing = 6
        list.translatesAutoresizingMaskIntoConstraints = false
        scroll.addSubview(list)
        NSLayoutConstraint.activate([
            list.leadingAnchor.constraint(equalTo: scroll.leadingAnchor),
            list.trailingAnchor.constraint(equalTo: scroll.trailingAnchor),
            list.topAnchor.constraint(equalTo: scroll.topAnchor),
            list.bottomAnchor.constraint(equalTo: scroll.bottomAnchor),
            list.widthAnchor.constraint(equalTo: scroll.widthAnchor),
        ])
        let cfg = readConfig()
        switch which {
        case "snippets":
            let arr = (cfg?["snippets"] as? [[String: Any]]) ?? []
            if arr.isEmpty { list.addArrangedSubview(emptyRow("No snippets yet")) }
            for s in arr {
                let trg = (s["label"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? (s["trigger"] as? String ?? "")
                let exp = s["expansion"] as? String ?? ""
                if exp.isEmpty { continue }
                list.addArrangedSubview(overlayRow(trg, exp, accent) { [weak self] in
                    self?.textDocumentProxy.insertText(exp); self?.showKeyboard() })
            }
        case "history":
            let arr = (cfg?["history"] as? [[String: Any]]) ?? []
            if arr.isEmpty { list.addArrangedSubview(emptyRow("No recent dictations")) }
            for h in arr {
                let t = h["text"] as? String ?? ""
                if t.isEmpty { continue }
                let time = formatTime(h["at"] as? String)
                list.addArrangedSubview(overlayRow(time.isEmpty ? t : "\(time)   \(t)", "", pal.keyText) { [weak self] in
                    self?.textDocumentProxy.insertText(t); self?.showKeyboard() })
            }
        case "clipboard":
            if !hasFullAccess {
                list.addArrangedSubview(overlayRow("Clipboard needs Full Access", "Tap to open Settings", accent) { [weak self] in
                    guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
                    self?.extensionContext?.open(url, completionHandler: nil)
                })
            } else {
                loadClipboardHistoryIfNeeded()
                if clipboardCache.isEmpty { list.addArrangedSubview(emptyRow("No clipboard items yet — copy something to get started")) }
                for c in clipboardCache {
                    let time = formatTime(c.at)
                    list.addArrangedSubview(overlayRow(time.isEmpty ? c.text : "\(time)   \(c.text)", "", pal.keyText) { [weak self] in
                        self?.textDocumentProxy.insertText(c.text); self?.showKeyboard() })
                }
            }
        case "vocabulary":
            let arr = (cfg?["vocabulary"] as? [[String: Any]]) ?? []
            if arr.isEmpty { list.addArrangedSubview(emptyRow("No words yet")) }
            for v in arr {
                let w = v["word"] as? String ?? ""
                if w.isEmpty { continue }
                let ph = v["phonetic"] as? String ?? ""
                list.addArrangedSubview(overlayRow(w, ph, pal.keyText) { [weak self] in
                    self?.textDocumentProxy.insertText(w + " ") })
            }
        default: // canvas (v1.5)
            list.addArrangedSubview(emptyRow("Open the Flume app to use Canvas"))
        }
        wrap.addArrangedSubview(scroll)
        return wrap
    }

    private func emptyRow(_ msg: String) -> UIView {
        let l = UILabel(); l.text = msg; l.textColor = pal.mutedText; l.font = uiFont(14); return l
    }

    private func overlayRow(_ title: String, _ sub: String, _ titleColor: UIColor, _ action: @escaping () -> Void) -> UIView {
        let b = UIButton(type: .system)
        let t = title.count > 44 ? String(title.prefix(44)) + "…" : title
        b.setTitle(sub.isEmpty ? t : "\(t)   \(sub.count > 26 ? String(sub.prefix(26)) + "…" : sub)", for: .normal)
        b.setTitleColor(titleColor, for: .normal)
        b.contentHorizontalAlignment = .left
        b.contentEdgeInsets = UIEdgeInsets(top: 12, left: 12, bottom: 12, right: 12)
        b.titleLabel?.font = titleColor == accent
            ? monoFont(14)
            : uiFont(14)
        b.backgroundColor = pal.cardBg; b.layer.cornerRadius = 12
        b.addAction(UIAction { _ in action() }, for: .touchUpInside)
        return b
    }

    // MARK: emoji
    // Recents first, then the 9 bundled groups (flume_emoji.txt) with representative tab glyphs.
    private func emojiCategories() -> [(String, [String])] {
        let glyphs = ["😀", "🧑", "🐶", "🍔", "✈️", "⚽", "💡", "❤️", "🏳️"]   // Smileys…Flags
        var cats: [(String, [String])] = [("🕘", emojiRecents)]
        for (i, group) in emojiLib.enumerated() {
            let glyph = i < glyphs.count ? glyphs[i] : "•"
            cats.append((glyph, group.1))
        }
        return cats
    }

    private func openEmoji() {
        activeOverlay = nil; refreshBar()
        suggestionStrip.arrangedSubviews.forEach { $0.removeFromSuperview() }
        setContent(buildEmoji())
    }

    private func buildEmoji() -> UIView {
        keyBaseColor.removeAll(); keyBgView.removeAll()   // the ABC / ⌫ funcKeys are rebuilt here too
        let cats = emojiCategories()
        if emojiCatIdx < 0 || emojiCatIdx >= cats.count { emojiCatIdx = 1 }
        let wrap = UIStackView(); wrap.axis = .vertical; wrap.spacing = 6

        let tabs = UIStackView(); tabs.axis = .horizontal; tabs.spacing = 4; tabs.distribution = .fillEqually
        for (i, c) in cats.enumerated() {
            let b = UIButton(type: .system)
            b.setTitle(c.0, for: .normal); b.titleLabel?.font = .systemFont(ofSize: 18)
            b.backgroundColor = i == emojiCatIdx ? pal.highlightBg : .clear
            b.layer.cornerRadius = 8
            b.addAction(UIAction { [weak self] _ in self?.emojiCatIdx = i; self?.setContent(self!.buildEmoji()) }, for: .touchUpInside)
            tabs.addArrangedSubview(b)
        }
        tabs.heightAnchor.constraint(equalToConstant: 34).isActive = true
        wrap.addArrangedSubview(tabs)

        var list = cats[emojiCatIdx].1
        if list.isEmpty { list = cats[1].1 }
        let scroll = UIScrollView()
        let col = UIStackView(); col.axis = .vertical; col.spacing = 2
        col.translatesAutoresizingMaskIntoConstraints = false
        scroll.addSubview(col)
        NSLayoutConstraint.activate([
            col.leadingAnchor.constraint(equalTo: scroll.leadingAnchor),
            col.trailingAnchor.constraint(equalTo: scroll.trailingAnchor),
            col.topAnchor.constraint(equalTo: scroll.topAnchor),
            col.bottomAnchor.constraint(equalTo: scroll.bottomAnchor),
            col.widthAnchor.constraint(equalTo: scroll.widthAnchor),
        ])
        var rowV: UIStackView?
        for (idx, e) in list.enumerated() {
            if idx % 8 == 0 { rowV = UIStackView(); rowV!.axis = .horizontal; rowV!.distribution = .fillEqually; col.addArrangedSubview(rowV!) }
            let b = UIButton(type: .system)
            b.setTitle(e, for: .normal); b.titleLabel?.font = .systemFont(ofSize: 24)
            b.heightAnchor.constraint(equalToConstant: 44).isActive = true
            b.addAction(UIAction { [weak self] _ in self?.commitEmoji(e) }, for: .touchUpInside)
            rowV!.addArrangedSubview(b)
        }
        wrap.addArrangedSubview(scroll)

        let bottom = UIStackView(); bottom.axis = .horizontal; bottom.spacing = 6; bottom.distribution = .fill
        bottom.addArrangedSubview(funcKey("ABC", width: 0, flexible: true) { [weak self] in self?.showKeyboard() })
        bottom.addArrangedSubview(funcKey("⌫", width: 60) { [weak self] in self?.onBackspace() })
        wrap.addArrangedSubview(bottom)
        return wrap
    }

    private func commitEmoji(_ e: String) {
        // Gated on transformState exactly like commit()/onSpace()/onBackspace(): while a
        // transform is in flight the host document must not be mutated, or the captured
        // selection is destroyed before Replace can use it (IDI-164).
        switch transformState {
        case .compose:
            transformInstruction += e
            refreshTransformComposeUI()
        case .busy, .preview:
            return
        case .idle:
            clearPendingUndo()
            textDocumentProxy.insertText(e)
        }
        emojiRecents.removeAll { $0 == e }; emojiRecents.insert(e, at: 0)
        if emojiRecents.count > 24 { emojiRecents = Array(emojiRecents.prefix(24)) }
    }

    // MARK: config (App Group — the app writes flume_kbd_config.json here)
    // Config is CACHED and only re-read/parsed when the file's modified-date changes —
    // reading + JSON-parsing it on every keystroke janked the main thread mid-typing.
    private var cfgCache: [String: Any]?
    private var cfgMtime: Date?
    private func readConfig() -> [String: Any]? {
        guard let dir = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.verbal.app") else { return nil }
        let url = dir.appendingPathComponent("flume_kbd_config.json")
        let m = (try? FileManager.default.attributesOfItem(atPath: url.path)[.modificationDate]) as? Date
        if let m = m, m == cfgMtime { return cfgCache }
        cfgMtime = m
        guard let data = try? Data(contentsOf: url),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { cfgCache = nil; return nil }
        cfgCache = obj
        return obj
    }

    // MARK: clipboard (self-contained: unlike `flume_kbd_config.json` above, this file is
    // written AND read by the extension itself — the main app never touches clipboard content)
    private func clipboardFileURL() -> URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.verbal.app")?
            .appendingPathComponent("flume_kbd_clipboard.json")
    }

    private func loadClipboardHistoryIfNeeded() {
        guard !clipboardLoaded else { return }
        clipboardLoaded = true
        guard let url = clipboardFileURL(),
              let data = try? Data(contentsOf: url),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        lastClipboardChangeCount = obj["lastChangeCount"] as? Int ?? -1
        let items = (obj["items"] as? [[String: Any]]) ?? []
        clipboardCache = items.compactMap { item -> (text: String, at: String)? in
            guard let text = item["text"] as? String, !text.isEmpty else { return nil }
            return (text: text, at: item["at"] as? String ?? "")
        }
    }

    private func saveClipboardHistory() {
        guard let url = clipboardFileURL() else { return }
        let items = clipboardCache.prefix(clipboardCap).map { ["text": $0.text, "at": $0.at] }
        let obj: [String: Any] = ["items": items, "lastChangeCount": lastClipboardChangeCount]
        guard let data = try? JSONSerialization.data(withJSONObject: obj) else { return }
        try? data.write(to: url, options: .atomic)
    }

    // Called on every keyboard-show (viewWillAppear). Cheap in the steady state — an int
    // compare — since it only does real work when UIPasteboard.general.changeCount moved.
    private func checkClipboardForNewContent() {
        guard hasFullAccess else { return }
        loadClipboardHistoryIfNeeded()
        let pb = UIPasteboard.general
        let cc = pb.changeCount
        guard cc != lastClipboardChangeCount else { return }
        lastClipboardChangeCount = cc
        defer { saveClipboardHistory() }   // persist the seen changeCount even if we skip recording below

        guard (readConfig()?["clipboardHistoryEnabled"] as? Bool) ?? true else { return }
        // Respect the password-manager convention for "don't capture this" content
        // (1Password/Bitwarden et al. tag concealed copies with this UTI).
        guard !pb.types.contains("org.nspasteboard.ConcealedType"), let text = pb.string, !text.isEmpty else { return }

        let stored = text.count > clipboardEntryCharCap ? String(text.prefix(clipboardEntryCharCap)) : text
        clipboardCache.removeAll { $0.text == stored }
        clipboardCache.insert((text: stored, at: ISO8601DateFormatter().string(from: Date())), at: 0)
        if clipboardCache.count > clipboardCap { clipboardCache = Array(clipboardCache.prefix(clipboardCap)) }

        pendingQuickPaste = text
        refreshQuickPasteChip()
    }

    // Shared bar-chip slot: shows whichever ephemeral affordance is most recent — a
    // just-replaced transform's Undo takes priority over an older pending quick-paste,
    // since it's the more contextually relevant action. The two never show at once;
    // that's an acceptable, expected degrade (newest ephemeral action wins).
    private func refreshQuickPasteChip() {
        guard let chip = quickPasteChip else { return }
        if let undo = pendingUndo {
            chip.setTitle("↩︎ Undo (\(undo.length) chars)", for: .normal)
            chip.isHidden = false
        } else if let text = pendingQuickPaste, !text.isEmpty {
            let preview = text.count > 8 ? String(text.prefix(8)) + "…" : text
            chip.setTitle("📋 " + preview, for: .normal)
            chip.isHidden = false
        } else {
            chip.isHidden = true
        }
    }

    /// Retire the soft-undo affordance (typing, a field switch, or an expiry all invalidate
    /// the "delete N units back" span it encodes) — IDI-164.
    private func clearPendingUndo() {
        guard pendingUndo != nil else { return }
        undoWorkItem?.cancel(); undoWorkItem = nil
        pendingUndo = nil
        refreshQuickPasteChip()
    }

    private func tapQuickPasteChip() {
        if let undo = pendingUndo {
            undoWorkItem?.cancel()
            // `undo.length` is UTF-16 code units — one deleteBackward() per unit.
            for _ in 0..<undo.length { textDocumentProxy.deleteBackward() }
            textDocumentProxy.insertText(undo.original)
            pendingUndo = nil
            refreshQuickPasteChip()
            return
        }
        guard let text = pendingQuickPaste else { return }
        textDocumentProxy.insertText(text)
        pendingQuickPaste = nil
        refreshQuickPasteChip()
    }

    // MARK: transform (select text elsewhere → instruction → LLM rewrite → replace)
    private func onTransformTap() {
        guard ((readConfig()?["transformEnabled"] as? Bool) ?? false), transformState == .idle else { return }
        guard !isSecureField() else { flashStatus("Can't transform here"); return }
        let selected = (textDocumentProxy.selectedText ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !selected.isEmpty else {
            flashStatus("Select some text first")
            return
        }
        // REFUSE, never truncate (IDI-164): Replace overwrites the WHOLE selection, so
        // transforming only the first 8000 chars would silently destroy the tail.
        guard selected.count <= transformSelectionCharCap else {
            flashStatus("Selection too long (max \(transformSelectionCharCap))")
            return
        }
        transformOriginalText = selected
        transformInstruction = ""
        transformSessionId = inputSessionId
        transformSeq &+= 1                       // any older in-flight rewrite is now stale
        transformTask?.cancel(); transformTask = nil
        enterCompose()
    }

    // Transient status band (IDI-161/164). The suggestion strip is the one always-visible,
    // always-present surface in this keyboard, so every user-facing error/notice reuses it.
    // Restoring is STATE-AWARE — the old version only restored when transformState == .idle,
    // which is why a failure during compose left the strip permanently blank.
    private var statusFlashSeq = 0
    private func flashStatus(_ msg: String) {
        guard let strip = suggestionStrip else { return }
        suggestWork?.cancel()                                  // don't let a queued suggestion pass overwrite us
        strip.arrangedSubviews.forEach { $0.removeFromSuperview() }
        let lbl = UILabel(); lbl.text = msg; lbl.textColor = pal.mutedText; lbl.font = uiFont(13)
        lbl.textAlignment = .center
        strip.addArrangedSubview(lbl)
        statusFlashSeq &+= 1
        let seq = statusFlashSeq
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.8) { [weak self] in
            guard let self = self, seq == self.statusFlashSeq else { return }   // superseded by a newer flash
            switch self.transformState {
            case .idle:              self.updateSuggestions()
            case .compose:           self.refreshTransformComposeUI()
            case .busy, .preview:    break                       // those states own the strip themselves
            }
        }
    }

    private func enterCompose() {
        transformState = .compose
        UIView.animate(withDuration: 0.2) {
            self.iconGroup?.isHidden = true
            self.transformButton?.isHidden = true
            self.transformCancelButton?.isHidden = false
        }
        refreshTransformComposeUI()
    }

    private func exitCompose() { abortTransform(reason: nil) }

    /// Single exit door for the transform flow: invalidate the request token, cancel the
    /// socket, and put the bar + content back to a fully usable keyboard (IDI-164).
    private func abortTransform(reason: String?) {
        transformSeq &+= 1
        transformTask?.cancel(); transformTask = nil
        transformState = .idle
        transformInstruction = ""
        UIView.animate(withDuration: 0.2) {
            self.iconGroup?.isHidden = false
            self.flexSpacer?.isHidden = false
            self.transformButton?.isHidden = !((self.readConfig()?["transformEnabled"] as? Bool) ?? false)
            self.transformCancelButton?.isHidden = true
        }
        showKeyboard()
        if let reason = reason { flashStatus(reason) }
    }

    /// A transform attempt failed but the captured selection is still valid — go back to
    /// compose. MUST rebuild the CONTENT too: refreshTransformBusyUI()/PreviewUI() replaced
    /// the key rows with a spinner/preview, so restoring only the strip left a dead keyboard.
    private func failTransform(_ msg: String) {
        transformSeq &+= 1
        transformTask?.cancel(); transformTask = nil
        transformState = .compose
        activeOverlay = nil; refreshBar()
        setContent(buildKeyboard())                    // spinner/preview → real keys again
        UIView.animate(withDuration: 0.2) {
            self.iconGroup?.isHidden = true
            self.transformButton?.isHidden = true
            self.transformCancelButton?.isHidden = false
        }
        refreshTransformComposeUI()
        flashStatus(msg)                               // restores the compose row when it expires
    }

    // Suggestion-strip band is repurposed while composing: the growing instruction
    // preview (typed via the SAME letter keys — see commit()/onSpace()/onBackspace()
    // below) plus a horizontally-scrollable row of one-tap presets.
    private func refreshTransformComposeUI() {
        suggestionStrip.arrangedSubviews.forEach { $0.removeFromSuperview() }
        let row = UIStackView(); row.axis = .horizontal; row.spacing = 8; row.alignment = .center
        row.translatesAutoresizingMaskIntoConstraints = false

        let label = UILabel()
        label.text = transformInstruction.isEmpty ? "Type or tap a preset…" : transformInstruction
        label.textColor = transformInstruction.isEmpty ? pal.mutedText : pal.keyText
        label.font = uiFont(13)
        label.lineBreakMode = .byTruncatingHead
        label.setContentHuggingPriority(.defaultLow, for: .horizontal)

        let scroll = UIScrollView(); scroll.showsHorizontalScrollIndicator = false
        let chips = UIStackView(); chips.axis = .horizontal; chips.spacing = 6
        chips.translatesAutoresizingMaskIntoConstraints = false
        for (title, instruction) in transformPresets {
            let b = UIButton(type: .system)
            b.setTitle(title, for: .normal)
            b.setTitleColor(pal.keyText, for: .normal)
            b.titleLabel?.font = uiFont(12)
            b.backgroundColor = pal.highlightBg; b.layer.cornerRadius = 13
            b.contentEdgeInsets = UIEdgeInsets(top: 6, left: 10, bottom: 6, right: 10)
            b.addAction(UIAction { [weak self] _ in self?.fireTransformPreset(instruction) }, for: .touchUpInside)
            chips.addArrangedSubview(b)
        }
        scroll.addSubview(chips)
        NSLayoutConstraint.activate([
            chips.leadingAnchor.constraint(equalTo: scroll.leadingAnchor),
            chips.trailingAnchor.constraint(equalTo: scroll.trailingAnchor),
            chips.topAnchor.constraint(equalTo: scroll.topAnchor),
            chips.bottomAnchor.constraint(equalTo: scroll.bottomAnchor),
            chips.heightAnchor.constraint(equalTo: scroll.heightAnchor),
        ])

        row.addArrangedSubview(label)
        row.addArrangedSubview(scroll)
        suggestionStrip.addArrangedSubview(row)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: suggestionStrip.leadingAnchor, constant: 8),
            row.trailingAnchor.constraint(equalTo: suggestionStrip.trailingAnchor, constant: -8),
            row.topAnchor.constraint(equalTo: suggestionStrip.topAnchor),
            row.bottomAnchor.constraint(equalTo: suggestionStrip.bottomAnchor),
        ])
    }

    private func fireTransformPreset(_ instruction: String) {
        transformInstruction = instruction
        sendTransform()
    }

    private func sendTransform() {
        guard transformState == .compose else { return }
        let instruction = transformInstruction.trimmingCharacters(in: .whitespacesAndNewlines)
        transformState = .busy
        refreshTransformBusyUI()
        let isImprovise = instruction.isEmpty
        let system = isImprovise ? Self.improviseSystemPrompt : Self.transformSystemPrompt
        let user = isImprovise ? transformOriginalText
            : "INSTRUCTION: \(instruction)\n\nTEXT:\n\(transformOriginalText)"
        // Monotonic token: a restart (Return / another preset) or a cancel bumps `transformSeq`,
        // so the earlier response — even if it lands later — is dropped instead of overwriting
        // the newer one's preview (IDI-164).
        transformSeq &+= 1
        let seq = transformSeq
        transformTask?.cancel()
        transformTask = chatViaProxy(system: system, user: user) { [weak self] result in
            guard let self = self else { return }
            guard seq == self.transformSeq, self.transformState == .busy else { return }  // stale/cancelled
            self.transformTask = nil
            guard let raw = result, !raw.isEmpty else {
                self.failTransform("Couldn't transform — try again")
                return
            }
            self.transformRewrite = Self.stripTransformWrapping(raw, original: self.transformOriginalText)
            self.transformState = .preview
            self.refreshTransformPreviewUI()
        }
    }

    private func refreshTransformBusyUI() {
        let wrap = UIStackView(); wrap.axis = .vertical; wrap.alignment = .center; wrap.spacing = 8
        let spinner = UIActivityIndicatorView(style: .medium); spinner.color = pal.mutedText; spinner.startAnimating()
        let label = UILabel(); label.text = "Transforming…"; label.textColor = pal.mutedText; label.font = uiFont(13)
        wrap.addArrangedSubview(spinner); wrap.addArrangedSubview(label)
        setContent(wrap)
    }

    private func refreshTransformPreviewUI() {
        let wrap = UIStackView(); wrap.axis = .vertical; wrap.spacing = 8
        let scroll = UIScrollView()
        let label = UILabel()
        label.text = transformRewrite; label.numberOfLines = 0; label.font = uiFont(14); label.textColor = pal.keyText
        label.translatesAutoresizingMaskIntoConstraints = false
        scroll.addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: scroll.leadingAnchor, constant: 8),
            label.trailingAnchor.constraint(equalTo: scroll.trailingAnchor, constant: -8),
            label.topAnchor.constraint(equalTo: scroll.topAnchor, constant: 4),
            label.bottomAnchor.constraint(equalTo: scroll.bottomAnchor, constant: -4),
            label.widthAnchor.constraint(equalTo: scroll.widthAnchor, constant: -16),
        ])
        wrap.addArrangedSubview(scroll)

        let buttons = UIStackView(); buttons.axis = .horizontal; buttons.spacing = 8; buttons.distribution = .fillEqually
        buttons.heightAnchor.constraint(equalToConstant: 44).isActive = true
        let cancelBtn = UIButton(type: .system)
        cancelBtn.setTitle("Cancel", for: .normal); cancelBtn.setTitleColor(pal.mutedText, for: .normal)
        cancelBtn.backgroundColor = pal.highlightBg; cancelBtn.layer.cornerRadius = 10
        cancelBtn.addAction(UIAction { [weak self] _ in self?.exitCompose() }, for: .touchUpInside)
        let replaceBtn = UIButton(type: .system)
        replaceBtn.setTitle("Replace", for: .normal); replaceBtn.setTitleColor(.white, for: .normal)
        replaceBtn.backgroundColor = accent; replaceBtn.layer.cornerRadius = 10
        replaceBtn.addAction(UIAction { [weak self] _ in self?.applyTransformReplace() }, for: .touchUpInside)
        buttons.addArrangedSubview(cancelBtn); buttons.addArrangedSubview(replaceBtn)
        wrap.addArrangedSubview(buttons)
        setContent(wrap)
    }

    private func applyTransformReplace() {
        guard transformState == .preview else { return }
        // REVALIDATE before mutating the host (IDI-164). insertText() overwrites whatever is
        // selected RIGHT NOW — if the user re-selected, deselected or switched field while the
        // rewrite was in flight, replacing would destroy text the model never saw.
        guard inputSessionId == transformSessionId, !isSecureField() else {
            flashStatus("Selection changed")
            return
        }
        let live = (textDocumentProxy.selectedText ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard live == transformOriginalText else {
            flashStatus("Selection changed")
            return
        }
        textDocumentProxy.insertText(transformRewrite)
        let original = transformOriginalText
        // UTF-16 code units — deleteBackward() removes one unit per call, so a grapheme
        // count under-deletes for emoji / combining marks and leaves debris behind.
        let rewriteLen = transformRewrite.utf16.count
        transformState = .idle
        UIView.animate(withDuration: 0.2) {
            self.iconGroup?.isHidden = false
            self.flexSpacer?.isHidden = false
            self.transformButton?.isHidden = !((self.readConfig()?["transformEnabled"] as? Bool) ?? false)
            self.transformCancelButton?.isHidden = true
        }
        showKeyboard()
        pendingUndo = (length: rewriteLen, original: original)
        refreshQuickPasteChip()
        undoWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self = self else { return }
            self.pendingUndo = nil
            self.refreshQuickPasteChip()
        }
        undoWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 6.0, execute: work)
    }

    // Mirrors whisperflow/app/transform.py::_strip_wrapping — models occasionally wrap
    // output in quotes/fences despite the prompt saying not to.
    private static func stripTransformWrapping(_ out: String, original: String) -> String {
        var s = out.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("```") {
            s = s.trimmingCharacters(in: CharacterSet(charactersIn: "`")).trimmingCharacters(in: .whitespacesAndNewlines)
            for lang in ["text", "markdown", "md"] where s.lowercased().hasPrefix(lang + "\n") {
                s = String(s.dropFirst(lang.count + 1))
            }
        }
        let quoteChars: Set<Character> = ["\"", "'", "\u{201C}"]
        if s.count > 1, let first = s.first, let last = s.last,
           (first == "\"" && last == "\"") || (first == "'" && last == "'") || (first == "\u{201C}" && last == "\u{201D}"),
           let origFirst = original.first, !quoteChars.contains(origFirst) {
            s = String(s.dropFirst().dropLast())
        }
        return s
    }

    // JSON chat-completions call — sibling of transcribe(data:) below (same endpoint/auth,
    // same async URLSession + main-queue-callback convention), just a different body shape.
    @discardableResult
    private func chatViaProxy(system: String, user: String, completion: @escaping (String?) -> Void) -> URLSessionDataTask? {
        guard let url = URL(string: "\(supabaseURL)/functions/v1/groq-proxy") else { completion(nil); return nil }
        var req = URLRequest(url: url); req.httpMethod = "POST"
        // A non-streaming chat completion sends nothing until the model is done, so the
        // per-request (idle) timeout has to cover the whole generation — 45s, matching the
        // Android IME's readTimeout. `timeoutIntervalForResource` on netSession still caps it.
        req.timeoutInterval = 45
        req.setValue("Bearer \(supabaseAnon)", forHTTPHeaderField: "Authorization")
        req.setValue(supabaseAnon, forHTTPHeaderField: "apikey")
        req.setValue(proxyDeviceId(), forHTTPHeaderField: "x-flume-device")   // proxy rate-limit identity
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let payload: [String: Any] = [
            "model": "llama-3.3-70b-versatile",
            "messages": [["role": "system", "content": system], ["role": "user", "content": user]],
            "temperature": 0, "max_tokens": 2048,
        ]
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { completion(nil); return nil }
        req.httpBody = body
        let task = netSession.dataTask(with: req) { data, response, _ in
            if let code = (response as? HTTPURLResponse)?.statusCode, !(200...299).contains(code) {
                DispatchQueue.main.async { completion(nil) }; return
            }
            guard let data = data,
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let choices = obj["choices"] as? [[String: Any]],
                  let message = choices.first?["message"] as? [String: Any],
                  let content = (message["content"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !content.isEmpty
            else { DispatchQueue.main.async { completion(nil) }; return }
            DispatchQueue.main.async { completion(content) }
        }
        task.resume()
        return task
    }

    /// The proxy's per-device rate-limit identity (`x-flume-device`), written into the shared
    /// config by lib/keyboardBridge.ts. Without it every iOS keyboard shares one bucket.
    private func proxyDeviceId() -> String {
        let id = (readConfig()?["deviceId"] as? String) ?? ""
        return id.isEmpty ? "ios-keyboard" : id
    }

    // MARK: dictation (record → groq-proxy). In-extension mic is a device-only
    // unknown (spec risk #1); the button is present and works where the OS allows it.
    // Input session captured at record-START; the transcript may only land in that field (IDI-163).
    private var dictationSessionId = 0

    @objc private func onMicTap() {
        // Re-entrancy (IDI-161, mirrors the Android IME's `busy`): a tap during the async
        // permission/recorder-setup window or during an in-flight upload is a no-op.
        // Without this a double-tap built two AVAudioRecorders on the same URL, because
        // `isRecording` only flips inside requestMic's callback.
        if isArming || isTranscribing { return }
        if isRecording { stopAndTranscribe() } else { startRecording() }
    }

    private func startRecording() {
        // Both the microphone and ANY network call from a keyboard extension require Full
        // Access. Without it the dictation used to fail invisibly (the check existed only on
        // the clipboard path) — IDI-161.
        guard hasFullAccess else { flashMic("Allow Full Access to dictate"); return }
        guard !isSecureField() else { flashMic("Can't dictate here"); return }
        isArming = true
        requestMic { [weak self] ok in
            guard let self = self else { return }
            guard ok else { self.isArming = false; self.flashMic("Mic access needed"); return }
            do {
                let session = AVAudioSession.sharedInstance()
                try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
                try session.setActive(true)
                let url = FileManager.default.temporaryDirectory.appendingPathComponent("flume_rec.m4a")
                try? FileManager.default.removeItem(at: url)
                let settings: [String: Any] = [
                    AVFormatIDKey: Int(kAudioFormatMPEG4AAC), AVSampleRateKey: 16000,
                    AVNumberOfChannelsKey: 1, AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue]
                let rec = try AVAudioRecorder(url: url, settings: settings)
                rec.isMeteringEnabled = true
                guard rec.record() else {
                    self.isArming = false
                    try? FileManager.default.removeItem(at: url)
                    self.flashMic("Couldn't start recording")
                    return
                }
                self.recorder = rec; self.audioURL = url; self.isRecording = true
                self.dictationSessionId = self.inputSessionId
                self.isArming = false
                self.micSymbol("stop.fill")
                self.enterRecordingUI()
                self.playSound("flume_start")
            } catch {
                self.isArming = false
                self.recorder = nil
                self.audioURL = nil
                self.flashMic("Couldn't start recording")
            }
        }
    }

    private func requestMic(_ completion: @escaping (Bool) -> Void) {
        if #available(iOS 17.0, *) {
            AVAudioApplication.requestRecordPermission { g in DispatchQueue.main.async { completion(g) } }
        } else {
            AVAudioSession.sharedInstance().requestRecordPermission { g in DispatchQueue.main.async { completion(g) } }
        }
    }

    private func stopAndTranscribe() {
        guard isRecording, !isTranscribing else { return }   // re-entrancy latch (IDI-161)
        isRecording = false
        stopMeter()
        recorder?.stop(); recorder = nil
        try? AVAudioSession.sharedInstance().setActive(false)
        // Switch to playback so the stop SFX is audible (recording set the category to .playAndRecord).
        try? AVAudioSession.sharedInstance().setCategory(.playback, options: [.mixWithOthers])
        try? AVAudioSession.sharedInstance().setActive(true)
        playSound("flume_stop")
        micSymbol("mic.fill"); exitRecordingUI()
        // Consume the recording exactly ONCE: clear `audioURL` and delete the file as soon as
        // the bytes are in memory. It used to linger in /tmp forever and a second stop could
        // re-read the same clip.
        guard let url = audioURL else { flashMic("No speech detected"); return }
        audioURL = nil
        let data = try? Data(contentsOf: url)
        try? FileManager.default.removeItem(at: url)
        guard let data = data, !data.isEmpty else { flashMic("No speech detected"); return }
        isTranscribing = true
        transcribe(data: data)
    }

    /// Visible, transient dictation feedback: a message on the suggestion strip plus a mic
    /// tint pulse. This was an empty stub, which is why every failure above was silent (IDI-161).
    private func flashMic(_ msg: String) {
        flashStatus(msg)
        guard let mic = micButton else { return }
        mic.backgroundColor = accent
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.9) { [weak self] in
            guard let self = self, !self.isRecording else { return }
            self.micButton?.backgroundColor = self.pal.micBg
        }
    }

    // Stop/done SFX need the session back on .playback (recording left it on .playAndRecord).
    private func playDoneCue() {
        try? AVAudioSession.sharedInstance().setCategory(.playback, options: [.mixWithOthers])
        try? AVAudioSession.sharedInstance().setActive(true)
        playSound("flume_done")
    }

    // Recording SFX (mirrors the desktop start/stop/done sounds). Load once + cache.
    // FAIL CLOSED — a sound error must never break the record→transcribe→inject path.
    private func playSound(_ name: String, volume: Float = 0.35) {
        do {
            let player: AVAudioPlayer
            if let cached = soundPlayers[name] {
                player = cached
            } else {
                guard let url = Bundle(for: type(of: self)).url(forResource: name, withExtension: "wav") else { return }
                player = try AVAudioPlayer(contentsOf: url)
                player.prepareToPlay()
                soundPlayers[name] = player
            }
            player.volume = volume
            player.currentTime = 0
            player.play()
        } catch { /* ignore */ }
    }

    // Full dictation pipeline, mirroring lib/dictationPipeline.ts and the Android IME's
    // transcribe(): vocabulary-biased + language-hinted + deterministic transcription,
    // then dictionary replacements, then snippet expansion. Every post-transcription step
    // fails CLOSED — a bad rule yields the best text obtained so far, never a lost dictation.
    private func transcribe(data: Data) {
        // Snapshot on the MAIN thread: readConfig() mutates a cache and must not run on the
        // URLSession queue, and the insert guards below have to compare against the field /
        // instant the dictation STARTED in, not whatever is focused when the reply lands.
        let cfg = readConfig()
        let sessionAtStart = dictationSessionId
        let issuedAt = Date()
        guard let url = URL(string: "\(supabaseURL)/functions/v1/groq-proxy") else {
            isTranscribing = false; flashMic("Transcription failed"); return
        }
        let boundary = "Boundary-\(UUID().uuidString)"
        var req = URLRequest(url: url); req.httpMethod = "POST"
        req.timeoutInterval = 15                       // + netSession's 45s resource cap
        req.setValue("Bearer \(supabaseAnon)", forHTTPHeaderField: "Authorization")
        req.setValue(supabaseAnon, forHTTPHeaderField: "apikey")
        req.setValue(proxyDeviceId(), forHTTPHeaderField: "x-flume-device")   // proxy rate-limit identity
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        func field(_ n: String, _ v: String) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(n)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(v)\r\n".data(using: .utf8)!)
        }
        field("model", "whisper-large-v3-turbo"); field("response_format", "json")
        field("temperature", "0")                      // deterministic, like every other front door
        // Only send `language` when the user actually picked one — an unset/blank hint must be
        // OMITTED so Whisper keeps auto-detecting rather than being forced to a wrong language.
        if let lang = (cfg?["spokenLanguage"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
           !lang.isEmpty {
            field("language", lang)
        }
        let biasPrompt = buildBiasPrompt(cfg)
        if let prompt = biasPrompt { field("prompt", prompt) }
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"audio.m4a\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: audio/m4a\r\n\r\n".data(using: .utf8)!)
        body.append(data); body.append("\r\n".data(using: .utf8)!)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        req.httpBody = body
        netSession.dataTask(with: req) { [weak self] data, response, error in
            // The URLResponse used to be discarded, so a 4xx/5xx from the proxy (incl. the
            // 429 rate limit) read as "nothing happened" — IDI-161.
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            let ok = error == nil && (200...299).contains(code)
            var raw: String? = nil
            if ok, let data = data,
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                raw = (obj["text"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            // Dictionary post-processing runs off the main thread on captured, immutable input.
            var finalText: String? = nil
            if let t = raw, !t.isEmpty {
                // Echo scrub FIRST: the glossary parroted back is not speech, and
                // must never reach the field. "" here falls through to the
                // "No speech detected" branch below, which is exactly what it was.
                var out = KeyboardViewController.stripPromptEcho(t, biasPrompt)
                out = KeyboardViewController.applyReplacements(out, cfg?["replacements"] as? [[String: Any]])
                out = KeyboardViewController.applySnippets(out, cfg?["snippets"] as? [[String: Any]])
                out = out.trimmingCharacters(in: .whitespacesAndNewlines)
                finalText = out.isEmpty ? nil : out
            }
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.isTranscribing = false
                guard ok else { self.flashMic("Transcription failed"); return }
                guard let text = finalText else { self.flashMic("No speech detected"); return }
                self.deliverTranscript(text, sessionAtStart: sessionAtStart, issuedAt: issuedAt)
            }
        }.resume()
    }

    /// The ONE path that writes an async transcript into the host document (IDI-163).
    /// Guarantees: a transcript never lands in a field other than the one it was dictated
    /// into, and never in a secure field.
    private func deliverTranscript(_ text: String, sessionAtStart: Int, issuedAt: Date) {
        // Mic is repurposed while composing a transform instruction (same button,
        // mode-dependent meaning) — that route never touches the host document, so the
        // field guard below does not apply to it.
        if transformState == .compose {
            playDoneCue()
            transformInstruction = text
            refreshTransformComposeUI()
            sendTransform()
            return
        }
        guard transformState == .idle else { return }        // busy/preview own the document
        // (a) same input session as at record-start,
        guard inputSessionId == sessionAtStart else { flashMic("Can't dictate here"); return }
        // (b) re-checked at INSERT time — a host can turn the focused field secure in place,
        guard !isSecureField() else { flashMic("Can't dictate here"); return }
        // (c) and a result this stale is never wanted (the session caps at 45s, so this is
        //     the belt to that braces).
        guard Date().timeIntervalSince(issuedAt) <= 90 else { flashMic("Dictation expired"); return }
        playDoneCue()
        clearPendingUndo()
        textDocumentProxy.insertText(text + " ")
        updateSuggestions()
    }

    /// Whisper vocabulary bias — mirrors dictionary.ts::buildPrompt ("Glossary: a, b, c.").
    /// Capped at 200 terms AND 850 chars trimmed at a comma boundary: Groq 400s any Whisper
    /// prompt over 896 chars (project Hard Rule #6), same as whisperflow/app/transcriber.py.
    private func buildBiasPrompt(_ cfg: [String: Any]?) -> String? {
        guard let vocab = cfg?["vocabulary"] as? [[String: Any]], !vocab.isEmpty else { return nil }
        var terms: [String] = []
        for v in vocab {
            let w = (v["word"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if w.isEmpty { continue }                  // skip empty / malformed entries
            terms.append(w)
            if terms.count >= groqPromptTermCap { break }
        }
        if terms.isEmpty { return nil }
        var prompt = "Glossary: " + terms.joined(separator: ", ") + "."
        if prompt.count > groqPromptCharCap {
            let head = String(prompt.prefix(groqPromptCharCap))
            if let comma = head.range(of: ",", options: .backwards) {
                prompt = String(head[head.startIndex..<comma.lowerBound]) + "."
            } else {
                prompt = head
            }
        }
        return prompt
    }

    // ── bias-prompt echo ("Glossary, M.T.:" arriving AS the transcript) ──────────
    // Whisper's `prompt` is a CONTINUATION prompt, not an instruction: the model is
    // conditioned on it as though it were the transcript so far. On quiet or
    // speech-free audio the likeliest continuation of "Glossary: a, b, c." is MORE
    // glossary — so the bias list comes back as the "transcription" and would be
    // typed into the user's field. Mirrors lib/dictionary.ts::stripPromptEcho and
    // whisperflow/app/dictionary.py::strip_prompt_echo — edit one, edit all three.
    // Pure + fail-closed: anything unexpected returns the text untouched.

    /// Chunk on commas/semicolons/newlines and on SENTENCE periods (a period
    /// followed by whitespace) so "M.T." and "main.py" survive as single chunks.
    private static let echoChunkRE = try? NSRegularExpression(pattern: #"\s*[,;]\s*|\s*\.\s+|\s*\n+\s*"#)
    private static let echoAnyLabelRE = try? NSRegularExpression(
        pattern: #"\b(glossary|vocabulary|files)\b\s*:"#, options: [.caseInsensitive])
    private static let echoRunRE = try? NSRegularExpression(pattern: #"\s{2,}"#)
    private static let echoLeadRE = try? NSRegularExpression(pattern: #"^[\s,;:.–—-]+"#)

    /// The section labels this prompt ACTUALLY carries ("Glossary:", "Files:").
    /// Only these count as labels when scanning a transcript — which keeps a
    /// dictated "Files, I need to check them" intact on a run where no file list
    /// was sent. We can only be echoed text we spoke first.
    private static func echoLabelRE(for prompt: String) -> NSRegularExpression? {
        guard let any = echoAnyLabelRE else { return nil }
        let ns = prompt as NSString
        var labels = Set<String>()
        for m in any.matches(in: prompt, range: NSRange(location: 0, length: ns.length))
        where m.range(at: 1).location != NSNotFound {
            labels.insert(ns.substring(with: m.range(at: 1)).lowercased())
        }
        guard !labels.isEmpty else { return nil }
        // Group 1 is the label WORD (which decides whether it is one of ours per
        // echoOwnedLabels), group 2 the ':' that makes it ours regardless.
        return try? NSRegularExpression(
            pattern: #"^\s*("# + labels.sorted().joined(separator: "|") + #")\b\s*(:)?\s*"#,
            options: [.caseInsensitive])
    }

    /// Headings WE invented, which therefore can't be something the user said: a
    /// bare "Glossary" chunk is ours whatever punctuation follows it. "files" is
    /// deliberately absent — "Files, I need to check them" is real dictation.
    private static let echoOwnedLabels: Set<String> = ["glossary", "vocabulary"]

    /// Casefold and reduce every non-alphanumeric run to one space: "M.T.:" and
    /// "m t" both become "m t", so an echo matches the term we sent.
    private static func normEchoTerm(_ s: String) -> String {
        var out = "", pendingSpace = false
        for ch in s.lowercased() {
            if ch.isASCII && (ch.isLetter || ch.isNumber) {
                if pendingSpace && !out.isEmpty { out.append(" ") }
                pendingSpace = false
                out.append(ch)
            } else {
                pendingSpace = true
            }
        }
        return out
    }

    /// Split off a leading bias label. `colon` marks "Glossary:" — punctuated like
    /// a label, so it is ours and never dictation. `owned` marks a heading we
    /// invented, which is ours on any punctuation at all.
    private static func splitEchoLabel(_ c: String, _ re: NSRegularExpression?) -> (body: String, label: Bool, colon: Bool, owned: Bool) {
        let ns = c as NSString
        guard let re = re,
              let m = re.firstMatch(in: c, range: NSRange(location: 0, length: ns.length)),
              m.range.length > 0 else { return (c, false, false, false) }
        let word = m.range(at: 1).location != NSNotFound
            ? ns.substring(with: m.range(at: 1)).lowercased() : ""
        return (ns.substring(from: m.range.length), true,
                m.range(at: 2).location != NSNotFound, echoOwnedLabels.contains(word))
    }

    private static func echoSplit(_ text: String) -> (chunks: [String], seps: [String]) {
        guard let re = echoChunkRE else { return ([text], [""]) }
        let ns = text as NSString
        var chunks: [String] = [], seps: [String] = [], idx = 0
        for m in re.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
            chunks.append(ns.substring(with: NSRange(location: idx, length: m.range.location - idx)))
            seps.append(ns.substring(with: m.range))
            idx = m.range.location + m.range.length
        }
        chunks.append(ns.substring(from: idx)); seps.append("")
        return (chunks, seps)
    }

    /// Remove regurgitated bias-prompt text. Only words we actually SENT as labels
    /// count as labels. Deletes any run introduced by a bias LABEL that is either
    /// followed by terms we sent or STANDS ALONE as its own fragment (the model
    /// often drops the list and echoes just the heading — "Glossary. So, the thing
    /// is…"), plus any bare comma-list of TWO OR MORE consecutive terms we sent. A
    /// LONE dictionary word is never dropped — that is the user saying a word they
    /// taught us — and a label running on inside its clause ("Files, I need to
    /// check them") is speech. Returns "" when the transcript was nothing but echo,
    /// which the caller already shows as "No speech detected".
    static func stripPromptEcho(_ text: String, _ prompt: String?) -> String {
        guard let prompt = prompt, !prompt.isEmpty,
              !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return text }
        let labelRE = echoLabelRE(for: prompt)
        var terms = Set<String>()
        for piece in echoSplit(prompt).chunks {
            let t = normEchoTerm(splitEchoLabel(piece, labelRE).body)
            if !t.isEmpty { terms.insert(t) }
        }
        if terms.isEmpty { return text }

        var (chunks, seps) = echoSplit(text)
        let n = chunks.count
        var isTerm = [Bool](), isEmpty = [Bool](), hasLabel = [Bool](), isAlone = [Bool]()
        for k in 0..<n {
            let (body, label, colon, owned) = splitEchoLabel(chunks[k], labelRE)
            let norm = normEchoTerm(body)
            hasLabel.append(label); isTerm.append(terms.contains(norm)); isEmpty.append(norm.isEmpty)
            // A heading standing on its own — "Glossary:" or a "Glossary." ending
            // the fragment — is ours. One that runs on inside its clause is the user.
            // A bare heading we INVENTED is ours whatever follows it: Whisper emits
            // "Glossary, <speech>" far more often than "Glossary. <speech>", and the
            // comma form used to survive because a comma reads as "clause continues".
            let endsFragment = k == n - 1 || seps[k].contains(".") || seps[k].contains("\n")
            isAlone.append(label && norm.isEmpty && (colon || endsFragment || owned))
            // Peel a "Glossary:" prefix even when the chunk itself survives.
            if label && colon { chunks[k] = body }
        }

        var drop = [Bool](repeating: false, count: n)
        var i = 0
        while i < n {
            let nextIsTerm = (i + 1 < n) && isTerm[i + 1]
            let start = isAlone[i]
                || (hasLabel[i] && isTerm[i])
                || (hasLabel[i] && isEmpty[i] && nextIsTerm)
                || (isTerm[i] && nextIsTerm)
            if !start { i += 1; continue }
            var j = i
            while j < n && (isTerm[j] || isEmpty[j]) { drop[j] = true; j += 1 }
            i = max(j, i + 1)
        }

        // Rebuild unconditionally: even with no run to delete, a "Glossary:"
        // prefix may have been peeled off an otherwise real sentence above.
        var out = ""
        for k in 0..<n where !drop[k] { out += chunks[k] + seps[k] }
        let ns0 = out as NSString
        if let re = echoRunRE {
            out = re.stringByReplacingMatches(in: out, range: NSRange(location: 0, length: ns0.length),
                                              withTemplate: " ")
        }
        out = out.trimmingCharacters(in: .whitespacesAndNewlines)
        if let re = echoLeadRE {
            out = re.stringByReplacingMatches(in: out, range: NSRange(location: 0, length: (out as NSString).length),
                                              withTemplate: "")
        }
        out = out.trimmingCharacters(in: .whitespacesAndNewlines)
        return normEchoTerm(out).isEmpty ? "" : out
    }

    /// Word-boundary, case-INSENSITIVE, applied IN ARRAY ORDER — mirrors
    /// dictionary.ts::applyReplacements. Pure (no instance state) so it can run off-main.
    /// Fail-closed: an uncompilable rule degrades to a literal replace.
    private static func applyReplacements(_ text: String, _ rules: [[String: Any]]?) -> String {
        guard let rules = rules, !rules.isEmpty, !text.isEmpty else { return text }
        var out = text
        for r in rules {
            let from = (r["from"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let to = (r["to"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if from.isEmpty || to.isEmpty { continue }
            let pattern = "\\b" + NSRegularExpression.escapedPattern(for: from) + "\\b"
            if let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) {
                out = re.stringByReplacingMatches(
                    in: out, options: [], range: NSRange(location: 0, length: (out as NSString).length),
                    withTemplate: NSRegularExpression.escapedTemplate(for: to))
            } else {
                out = out.replacingOccurrences(of: from, with: to)
            }
        }
        return out
    }

    /// Snippet expansion — mirrors dictionary.ts::applySnippets exactly:
    ///   • case-insensitive whole-phrase match on word boundaries (multi-word aware)
    ///   • LONGEST trigger first (so "my email address" beats "my email")
    ///   • SINGLE left-to-right pass — an inserted expansion is never rescanned (no cascade)
    ///   • snippets with an empty trigger or empty expansion are skipped
    /// Pure + fail-closed: any problem returns the input unchanged.
    private static func applySnippets(_ text: String, _ snippets: [[String: Any]]?) -> String {
        guard let snippets = snippets, !snippets.isEmpty, !text.isEmpty else { return text }
        func trig(_ s: [String: Any]) -> String {
            (s["trigger"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        }
        var byTrigger: [String: String] = [:]
        var ordered: [String] = []
        for s in snippets.sorted(by: { trig($0).count > trig($1).count }) {
            let t = trig(s)
            let exp = s["expansion"] as? String ?? ""
            if t.isEmpty || exp.isEmpty { continue }
            let key = t.lowercased()
            if byTrigger[key] != nil { continue }      // first (longest) wins
            byTrigger[key] = exp
            ordered.append(t)
        }
        if ordered.isEmpty { return text }
        let alternation = ordered
            .map { "\\b" + NSRegularExpression.escapedPattern(for: $0) + "\\b" }
            .joined(separator: "|")
        guard let re = try? NSRegularExpression(pattern: "(" + alternation + ")", options: [.caseInsensitive]) else {
            return text
        }
        let ns = text as NSString
        var out = ""
        var cursor = 0
        re.enumerateMatches(in: text, options: [], range: NSRange(location: 0, length: ns.length)) { m, _, _ in
            guard let m = m, m.range.location >= cursor else { return }
            guard let exp = byTrigger[ns.substring(with: m.range).lowercased()] else { return }
            out += ns.substring(with: NSRange(location: cursor, length: m.range.location - cursor))
            out += exp
            cursor = m.range.location + m.range.length
        }
        if cursor == 0 { return text }                 // nothing matched
        out += ns.substring(from: cursor)
        return out
    }
}

private extension UIColor {
    convenience init(hex: Int) {
        self.init(red: CGFloat((hex >> 16) & 0xFF) / 255.0,
                  green: CGFloat((hex >> 8) & 0xFF) / 255.0,
                  blue: CGFloat(hex & 0xFF) / 255.0, alpha: 1.0)
    }
}
