import { requireOptionalNativeModule } from 'expo';

// Native only exists on iOS (see expo-module.config.json → apple). On Android /
// Expo Go the module is absent and every call returns false, so callers fall
// back to their existing path (documentDirectory == filesDir works on Android).
const FlumeSharedStore = requireOptionalNativeModule('FlumeSharedStore');

/**
 * Write `contents` to `<AppGroupContainer>/<name>` for the given App Group id.
 * This is the ONLY channel the sandboxed keyboard extension can read from on iOS
 * — the main app's documentDirectory is a separate sandbox it cannot see.
 * Returns false when the native module / entitlement is unavailable so the
 * caller can fall back. Never throws.
 */
export async function writeToGroup(
  group: string,
  name: string,
  contents: string,
): Promise<boolean> {
  if (!FlumeSharedStore) return false;
  try {
    return await FlumeSharedStore.writeToGroup(group, name, contents);
  } catch {
    return false;
  }
}
