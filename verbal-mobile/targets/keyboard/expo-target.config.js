/**
 * Flume iOS keyboard extension — target definition for @bacons/apple-targets.
 *
 * `type: "keyboard"` is a first-class target type: the plugin generates the
 * NSExtension Info.plist (com.apple.keyboard-service) and embeds the Swift
 * runtime. Any *.swift file in this folder is compiled into the extension; the
 * principal class MUST be named `KeyboardViewController`.
 *
 * Milestone 0 (foundation): prove the target builds, appears under Settings →
 * Keyboards, and can insertText into a field. No Full Access / App Group reads
 * yet — those arrive with the mic-handoff bridge (Milestone 1).
 *
 * @type {import('@bacons/apple-targets').Config}
 */
module.exports = (config) => ({
  type: 'keyboard',
  name: 'FlumeKeyboard',
  displayName: 'Flume',
  // Match the simulators in use (iOS 26). Bump/lower here if the build warns of a
  // deployment-target mismatch with the main app.
  deploymentTarget: '16.0',
  frameworks: ['UIKit'],
  // Same App Group as the main app so the handoff bridge (Milestone 1) can share
  // the transcript. Declared now so the entitlement wiring is proven early.
  entitlements: {
    'com.apple.security.application-groups':
      config.ios.entitlements['com.apple.security.application-groups'],
  },
});
