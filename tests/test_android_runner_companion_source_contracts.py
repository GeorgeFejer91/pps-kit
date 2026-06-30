from __future__ import annotations

from pathlib import Path


ANDROID_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "android"
    / "runner-companion"
    / "app"
    / "src"
    / "main"
    / "java"
    / "io"
    / "ppskit"
    / "runnercompanion"
)


def _source(name: str) -> str:
    return (ANDROID_SOURCE / name).read_text(encoding="utf-8")


def test_android_phone_runtime_preserves_mobile_package_asset_strategy() -> None:
    models = _source("MobileRuntimeModels.kt")
    main_activity = _source("MainActivity.kt")
    lsl_protocol = _source("PhoneLslProtocol.kt")
    native_bridge = _source("PhoneNativeLslBridge.kt")
    catalog = _source("PhoneRunCatalog.kt")

    assert "val assetStrategy: String" in models
    assert "val packageAssetStrategy: String" in models
    assert 'root.optString("asset_strategy"' in models
    assert 'optString("package_asset_strategy", "")' in models

    for source in [main_activity, lsl_protocol, native_bridge, catalog]:
        assert "mobilePackageAssetStrategy(runPackage)" in source

    assert '.put("asset_strategy", mobilePackageAssetStrategy(runPackage))' in main_activity
    assert '.put("package_asset_strategy", runPackage.reconstruction.packageAssetStrategy)' in main_activity
    assert '.put("asset_strategy", mobilePackageAssetStrategy(runPackage))' in lsl_protocol
    assert '.put("asset_strategy", mobilePackageAssetStrategy(runPackage))' in native_bridge
    assert '.put("asset_strategy", mobilePackageAssetStrategy(runPackage))' in catalog
    assert '.put("package_asset_strategy", runPackage.reconstruction.packageAssetStrategy)' in catalog


def test_android_phone_runtime_uses_audiotrack_timing_not_mediaplayer() -> None:
    playback = _source("PhoneAudioPlayback.kt")
    main_activity = _source("MainActivity.kt")
    all_sources = "\n".join(path.read_text(encoding="utf-8") for path in ANDROID_SOURCE.glob("*.kt"))

    assert "import android.media.AudioTrack" in playback
    assert "internal suspend fun playBlockAudioWithAudioTrack" in playback
    assert "playbackHeadPosition" in playback
    assert "PhoneAudioCueDelivery" in playback
    assert '.put("audio_timing_strategy", "audiotrack_pcm_wav_playback_head")' in main_activity
    assert '.put("audio_scheduler", "audiotrack_playback_head")' in main_activity
    assert "MediaPlayer" not in all_sources


def test_android_companion_discovery_preserves_local_hotspot_privacy_contract() -> None:
    discovery = _source("CompanionDiscovery.kt")

    assert 'COMPANION_DISCOVERY_NETWORK_SCOPE = "same_lan_or_local_hotspot"' in discovery
    assert 'COMPANION_DISCOVERY_TOKEN_DELIVERY = "qr_or_manual_uri_only"' in discovery
    assert 'setOf("lan", "phone_hotspot", "wifi_direct")' in discovery
    assert 'optBoolean("also_sent_as_limited_broadcast", false)' in discovery
    assert 'optInt("ttl", 0) == 1' in discovery
    assert 'optBoolean("contains_pairing_token", true)' in discovery
    assert 'optBoolean("contains_participant_demographics", true)' in discovery
    assert 'optBoolean("stream_names_are_generic", false)' in discovery
    assert "createMulticastLock" in discovery
    assert "MulticastSocket(null)" in discovery
