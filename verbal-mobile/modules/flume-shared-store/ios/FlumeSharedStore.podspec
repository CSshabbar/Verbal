Pod::Spec.new do |s|
  s.name           = 'FlumeSharedStore'
  s.version        = '1.0.0'
  s.summary        = 'Write files into the iOS App Group container for the Flume keyboard extension.'
  s.description    = 'Writes files into the iOS App Group shared container so the keyboard extension can read the app config.'
  s.author         = 'Verbal'
  s.homepage       = 'https://verbal.app'
  s.license        = 'MIT'
  s.platforms      = { :ios => '15.1' }
  s.source         = { :git => '' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'

  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'SWIFT_COMPILATION_MODE' => 'wholemodule'
  }

  s.source_files = "**/*.{h,m,swift}"
end
