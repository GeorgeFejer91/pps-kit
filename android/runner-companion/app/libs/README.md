# Optional liblsl Android AAR

Place a pinned `liblsl-Android.aar` here for local native LSL validation builds.

The AAR is intentionally ignored by Git. Do not commit native vendor binaries or
locally built Android artifacts to the public repository. The app still builds
without the AAR and reports `native_transport_available=false` in its runtime
status artifacts.
