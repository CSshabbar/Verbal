/**
 * Shared tap-feedback token (IDI-169).
 *
 * Every tappable element in the app dims to the SAME opacity while pressed.
 * This matches the treatment already baked into the shared components
 * (`Button`, `IconButton`, `Card`, `ListRow`), which are the reference.
 *
 * Usage on a raw Pressable:
 *
 *   <Pressable style={({ pressed }) => [styles.btn, pressed && pressedStyle]} />
 *
 * The token is named `pressedStyle` (not `pressed`) so it never shadows the
 * `pressed` flag destructured from the Pressable style callback.
 */
export const PRESSED_OPACITY = 0.85;

export const pressedStyle = { opacity: PRESSED_OPACITY } as const;
