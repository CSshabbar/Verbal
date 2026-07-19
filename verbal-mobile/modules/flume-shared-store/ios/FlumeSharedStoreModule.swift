import ExpoModulesCore
import Foundation

// Bridges JS → the iOS App Group container. The Flume keyboard extension reads
// group.com.verbal.app/flume_kbd_config.json; expo-file-system can only reach the
// app's private sandbox, so this native write is the only way to hand the config
// across the process boundary.
public class FlumeSharedStoreModule: Module {
  public func definition() -> ModuleDefinition {
    Name("FlumeSharedStore")

    AsyncFunction("writeToGroup") { (group: String, name: String, contents: String) -> Bool in
      guard let dir = FileManager.default.containerURL(
        forSecurityApplicationGroupIdentifier: group
      ) else {
        return false
      }
      let url = dir.appendingPathComponent(name)
      do {
        try contents.write(to: url, atomically: true, encoding: .utf8)
        return true
      } catch {
        return false
      }
    }
  }
}
