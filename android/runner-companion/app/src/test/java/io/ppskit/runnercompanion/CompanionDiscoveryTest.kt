package io.ppskit.runnercompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionDiscoveryTest {
    @Test
    fun parsesTokenFreeDiscoveryAdvertisementAndBuildsPairingUriWithSuppliedToken() {
        val advertisement = CompanionDiscoveryAdvertisement.parse(
            """
            {
              "schema": "$COMPANION_DISCOVERY_SCHEMA",
              "service": "pps-runner-companion",
              "service_name": "PPS Runner Companion",
              "network_scope": "same_lan_or_local_hotspot",
              "discovery": {
                "udp_multicast_group": "$COMPANION_DISCOVERY_MULTICAST_GROUP",
                "udp_port": $COMPANION_DISCOVERY_PORT,
                "also_sent_as_limited_broadcast": true,
                "broadcast_targets": [
                  "$COMPANION_DISCOVERY_LIMITED_BROADCAST_TARGET",
                  "$COMPANION_DISCOVERY_DIRECTED_BROADCAST_TARGET"
                ],
                "ttl": 1
              },
              "pairing": {
                "scheme": "pps-companion",
                "host": "192.168.43.1",
                "port": 8767,
                "session_id": "transfer-001",
                "mode": "phone_export",
                "transport": "phone_hotspot",
                "transfer_id": "transfer-001",
                "token_required": true,
                "token_delivery": "qr_or_manual_uri_only"
              },
              "privacy": {
                "contains_pairing_token": false,
                "contains_participant_demographics": false,
                "stream_names_are_generic": true
              }
            }
            """.trimIndent(),
        )

        assertEquals("192.168.43.1", advertisement.host)
        assertEquals(8767, advertisement.port)
        assertEquals("transfer-001", advertisement.sessionId)
        assertEquals("phone_hotspot", advertisement.transport)
        assertTrue(advertisement.tokenRequired)

        val pairing = advertisement.toPairingInfo("secret-token")

        assertEquals("192.168.43.1", pairing.host)
        assertEquals("phone_export", pairing.mode)
        assertEquals("phone_hotspot", pairing.transport)
        assertEquals("secret-token", pairing.token)
        assertEquals("transfer-001", pairing.transferId)
    }

    @Test
    fun rejectsDiscoveryAdvertisementThatLeaksToken() {
        val advertisement = """
            {
              "schema": "$COMPANION_DISCOVERY_SCHEMA",
              "service": "$COMPANION_DISCOVERY_SERVICE",
              "network_scope": "$COMPANION_DISCOVERY_NETWORK_SCOPE",
              "discovery": {
                "udp_multicast_group": "$COMPANION_DISCOVERY_MULTICAST_GROUP",
                "udp_port": $COMPANION_DISCOVERY_PORT,
                "also_sent_as_limited_broadcast": true,
                "broadcast_targets": [
                  "$COMPANION_DISCOVERY_LIMITED_BROADCAST_TARGET",
                  "$COMPANION_DISCOVERY_DIRECTED_BROADCAST_TARGET"
                ],
                "ttl": 1
              },
              "privacy": {
                "contains_pairing_token": false,
                "contains_participant_demographics": false,
                "stream_names_are_generic": true
              },
              "pairing": {
                "scheme": "pps-companion",
                "host": "192.168.43.1",
                "port": 8767,
                "session_id": "session-001",
                "mode": "pc_runner",
                "transport": "lan",
                "token_required": true,
                "token_delivery": "qr_or_manual_uri_only",
                "token": "secret"
              }
            }
            """.trimIndent()

        assertNull(CompanionDiscoveryAdvertisement.parseOrNull(advertisement))
    }

    @Test
    fun rejectsDiscoveryAdvertisementThatLeaksDemographicPrivacy() {
        val advertisement = """
            {
              "schema": "$COMPANION_DISCOVERY_SCHEMA",
              "service": "$COMPANION_DISCOVERY_SERVICE",
              "network_scope": "$COMPANION_DISCOVERY_NETWORK_SCOPE",
              "discovery": {
                "udp_multicast_group": "$COMPANION_DISCOVERY_MULTICAST_GROUP",
                "udp_port": $COMPANION_DISCOVERY_PORT,
                "also_sent_as_limited_broadcast": true,
                "broadcast_targets": [
                  "$COMPANION_DISCOVERY_LIMITED_BROADCAST_TARGET",
                  "$COMPANION_DISCOVERY_DIRECTED_BROADCAST_TARGET"
                ],
                "ttl": 1
              },
              "privacy": {
                "contains_pairing_token": false,
                "contains_participant_demographics": true,
                "stream_names_are_generic": true
              },
              "pairing": {
                "scheme": "pps-companion",
                "host": "192.168.43.1",
                "port": 8767,
                "session_id": "session-001",
                "mode": "pc_runner",
                "transport": "lan",
                "token_required": true,
                "token_delivery": "qr_or_manual_uri_only"
              }
            }
            """.trimIndent()

        assertNull(CompanionDiscoveryAdvertisement.parseOrNull(advertisement))
    }

    @Test
    fun rejectsDiscoveryAdvertisementWithHiddenTokenField() {
        val advertisement = discoveryAdvertisementWithExtraRootField(
            """"diagnostics": {"companion_token": "secret"},""",
        )

        assertNull(CompanionDiscoveryAdvertisement.parseOrNull(advertisement))
    }

    @Test
    fun rejectsDiscoveryAdvertisementWithHiddenParticipantIdentifier() {
        val advertisement = discoveryAdvertisementWithExtraRootField(
            """"diagnostics": {"participant_id": "P001"},""",
        )

        assertNull(CompanionDiscoveryAdvertisement.parseOrNull(advertisement))
    }

    @Test
    fun rejectsDiscoveryAdvertisementWithHiddenStreamName() {
        val advertisement = discoveryAdvertisementWithExtraRootField(
            """"diagnostics": {"lsl_stream_name": "P001_PPSMarkersV2"},""",
        )

        assertNull(CompanionDiscoveryAdvertisement.parseOrNull(advertisement))
    }

    @Test
    fun rejectsDiscoveryAdvertisementWithUnknownTransport() {
        val advertisement = """
            {
              "schema": "$COMPANION_DISCOVERY_SCHEMA",
              "service": "$COMPANION_DISCOVERY_SERVICE",
              "network_scope": "$COMPANION_DISCOVERY_NETWORK_SCOPE",
              "discovery": {
                "udp_multicast_group": "$COMPANION_DISCOVERY_MULTICAST_GROUP",
                "udp_port": $COMPANION_DISCOVERY_PORT,
                "also_sent_as_limited_broadcast": true,
                "broadcast_targets": [
                  "$COMPANION_DISCOVERY_LIMITED_BROADCAST_TARGET",
                  "$COMPANION_DISCOVERY_DIRECTED_BROADCAST_TARGET"
                ],
                "ttl": 1
              },
              "privacy": {
                "contains_pairing_token": false,
                "contains_participant_demographics": false,
                "stream_names_are_generic": true
              },
              "pairing": {
                "scheme": "pps-companion",
                "host": "192.168.43.1",
                "port": 8767,
                "session_id": "session-001",
                "mode": "pc_runner",
                "transport": "public_internet",
                "token_required": true,
                "token_delivery": "qr_or_manual_uri_only"
              }
            }
            """.trimIndent()

        assertNull(CompanionDiscoveryAdvertisement.parseOrNull(advertisement))
    }

    @Test
    fun rejectsDiscoveryAdvertisementWithoutDirectedBroadcastFallback() {
        val advertisement = discoveryAdvertisementWithExtraRootField(
            """"diagnostics": {"note": "safe"},""",
        ).replace(
            """
            "broadcast_targets": [
              "$COMPANION_DISCOVERY_LIMITED_BROADCAST_TARGET",
              "$COMPANION_DISCOVERY_DIRECTED_BROADCAST_TARGET"
            ],
            """.trimIndent(),
            """"broadcast_targets": ["$COMPANION_DISCOVERY_LIMITED_BROADCAST_TARGET"],""",
        )

        assertNull(CompanionDiscoveryAdvertisement.parseOrNull(advertisement))
    }

    private fun discoveryAdvertisementWithExtraRootField(extraRootField: String): String =
        """
        {
          "schema": "$COMPANION_DISCOVERY_SCHEMA",
          "service": "$COMPANION_DISCOVERY_SERVICE",
          "network_scope": "$COMPANION_DISCOVERY_NETWORK_SCOPE",
          $extraRootField
          "discovery": {
            "udp_multicast_group": "$COMPANION_DISCOVERY_MULTICAST_GROUP",
            "udp_port": $COMPANION_DISCOVERY_PORT,
            "also_sent_as_limited_broadcast": true,
            "broadcast_targets": [
              "$COMPANION_DISCOVERY_LIMITED_BROADCAST_TARGET",
              "$COMPANION_DISCOVERY_DIRECTED_BROADCAST_TARGET"
            ],
            "ttl": 1
          },
          "privacy": {
            "contains_pairing_token": false,
            "contains_participant_demographics": false,
            "stream_names_are_generic": true
          },
          "pairing": {
            "scheme": "pps-companion",
            "host": "192.168.43.1",
            "port": 8767,
            "session_id": "session-001",
            "mode": "pc_runner",
            "transport": "lan",
            "token_required": true,
            "token_delivery": "qr_or_manual_uri_only"
          }
        }
        """.trimIndent()
}
