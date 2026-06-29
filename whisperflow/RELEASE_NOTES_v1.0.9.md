# Verbal v1.0.9 Release Notes

## UI Improvements
- Completely redesigned listening widget with smoother, less boxy appearance
- Enhanced visual effects with improved shadows, glows, and 3D effects
- Smoother animations at 60fps for better responsiveness
- Better positioning of elements to match Mac aesthetic
- Added subtle text shadows for improved readability

## Audio Quality Enhancements
- Implemented advanced noise reduction for low-quality microphones
- Added high-pass filtering to remove low-frequency rumble and hum
- Applied dynamic range compression to enhance speech clarity
- Used pre-emphasis and formant enhancement to boost speech frequencies
- Added filtering for common transcription hallucinations ("uh", "um", "ah", "hm")
- Improved handling of silent or nearly silent audio segments

## Bug Fixes
- Fixed version inconsistency issues
- Improved error handling for transcription failures
- Enhanced resource cleanup to prevent memory leaks
- Fixed auto-update mechanism with better error handling and retry logic
- Fixed text duplication issue when receiving transcriptions from mobile devices

## Performance Improvements
- Optimized overlay rendering for smoother animations
- Reduced latency in audio recording for better responsiveness
- Improved resource management to prevent accumulation over time