package io.ppskit.runnercompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SnapshotParserTest {
    @Test
    fun parsesSnapshotAndCommandEnablement() {
        val snapshot = SnapshotParser.parse(sampleSnapshot(), receivedLocalUnixMs = 10_000)

        assertEquals(42, snapshot.sequence)
        assertEquals("P001", snapshot.participantId)
        assertTrue(snapshot.setup.ready)
        assertTrue(snapshot.canStartPart(1))
        assertFalse(snapshot.canStartPart(2))
        assertTrue(snapshot.canContinueInstruction())
        assertTrue(snapshot.canPause())
        assertFalse(snapshot.canResume())
        assertEquals("1", snapshot.partStatus.selectedPart)
        assertEquals("Block 01", snapshot.activeBlock.blockLabel)
        assertEquals(2, snapshot.timeline.tactileTotal)
        assertEquals(1, snapshot.timeline.tactilePassed)
        assertEquals(1, snapshot.timeline.trialRows.size)
        assertEquals("pink", snapshot.timeline.trialRows.first().noiseType)
        assertEquals(2, snapshot.timeline.clickMarkers.size)
        assertEquals("tactile_response", snapshot.timeline.clickMarkers.first().responseStatus)
        assertEquals(0.3, snapshot.timeline.clickMarkers.first().rtS ?: -1.0, 0.001)
        assertTrue(snapshot.instructionGate.waiting)

        val pausedSnapshot = SnapshotParser.parse(
            sampleSnapshot(paused = true, allowedCommands = "\"resume\""),
            receivedLocalUnixMs = 10_000,
        )
        assertFalse(pausedSnapshot.canPause())
        assertTrue(pausedSnapshot.canResume())
    }

    @Test
    fun parsesFlexibleTimelineAliasesAndDerivesMissingCounts() {
        val snapshot = SnapshotParser.parse(flexibleTimelineSnapshot(), receivedLocalUnixMs = 10_000)

        assertEquals(120.0, snapshot.activeBlock.durationS, 0.001)
        assertEquals(2, snapshot.timeline.trialRows.size)
        assertEquals("looming", snapshot.timeline.trialRows.first().label)
        assertEquals(0.0, snapshot.timeline.trialRows.first().startS, 0.001)
        assertEquals(30.0, snapshot.timeline.trialRows.first().endS, 0.001)
        assertEquals("white", snapshot.timeline.trialRows.first().noiseType)
        assertEquals(2, snapshot.timeline.tactileCues.size)
        assertEquals(12.5, snapshot.timeline.tactileCues.first().timeS, 0.001)
        assertEquals(2, snapshot.timeline.clickMarkers.size)
        assertEquals(12.8, snapshot.timeline.clickMarkers.first().timeS, 0.001)
        assertEquals(2, snapshot.timeline.clicks)
        assertEquals(2, snapshot.timeline.tactileTotal)
        assertEquals(1, snapshot.timeline.tactilePassed)
    }
}

fun sampleSnapshot(
    running: Boolean = true,
    paused: Boolean = false,
    waiting: Boolean = false,
    elapsedS: Double = 3.0,
    durationS: Double = 10.0,
    allowedCommands: String = "\"start_part_1\", \"continue_instruction\", \"pause\"",
): String =
    """
    {
      "schema": "$SNAPSHOT_SCHEMA",
      "sequence": 42,
      "server_unix_ms": 1000,
      "server_perf_counter_s": 50.0,
      "connection_state": "online",
      "allowed_commands": [$allowedCommands],
      "participant": {"participant_id": "P001"},
      "setup": {
        "submitted": true,
        "ready": true,
        "participant_name_present": true,
        "name_sharing_opt_in": false,
        "age": "30",
        "handedness": "right",
        "gender": "prefer_not_to_say"
      },
      "run_status": {"running": $running, "paused": $paused, "complete": false, "state_label": "Running", "event_label": "Gate"},
      "part_status": {"available_parts": ["1", "2"], "selected_part": "1", "current_package_part": "1", "pending_start_part": ""},
      "run_plan": [],
      "active_block": {
        "active": true,
        "part_number": "1",
        "phase_label": "Condition",
        "block_index": "1",
        "block_label": "Block 01",
        "duration_s": $durationS,
        "elapsed_s": $elapsedS,
        "last_anchor_server_perf_counter_s": 47.0,
        "running": $running,
        "paused": $paused,
        "instruction_waiting": $waiting
      },
      "timeline": {
        "trial_rows": [
          {"trial_number": 1, "trial_uid": "T001", "start_s": 0.0, "end_s": 5.0, "trial_label": "Trial 1", "noise_type": "pink", "soa_ms": "300"}
        ],
        "tactile_cues": [
          {"cue_id": 1, "trial_number": 1, "trial_uid": "T001", "time_s": 2.0, "row_label": "Inhale", "noise_type": "pink", "soa_ms": "300", "status": "passed"},
          {"cue_id": 2, "trial_number": 1, "trial_uid": "T001", "time_s": 4.0, "row_label": "Inhale", "noise_type": "pink", "soa_ms": "300", "status": "next"}
        ],
        "clicks": [
          {"click_id": 1, "time_s": 2.3, "trial_uid": "T001", "response_status": "tactile_response", "cue_id": 1, "cue_trial_uid": "T001", "rt_s": 0.3},
          {"click_id": 2, "time_s": 7.0, "trial_uid": "", "response_status": "off_cue", "cue_id": null, "cue_trial_uid": "", "rt_s": null}
        ],
        "counts": {"tactile_total": 2, "tactile_passed": 1, "clicks": 2, "recentered": 1}
      },
      "topup": {"draft_count": 0},
      "instruction_gate": {"waiting": true, "part2_start_gate": false, "instruction_label": "Gate", "button_label": "Continue"}
    }
    """.trimIndent()

fun flexibleTimelineSnapshot(): String =
    """
    {
      "schema": "$SNAPSHOT_SCHEMA",
      "sequence": 43,
      "server_unix_ms": 1000,
      "server_perf_counter_s": 50.0,
      "connection_state": "online",
      "allowed_commands": ["pause"],
      "participant": {"participant_id": "P009"},
      "setup": {"submitted": true, "ready": true},
      "run_status": {"running": true, "paused": false, "complete": false, "state_label": "Running", "event_label": "Gate"},
      "part_status": {"available_parts": ["1"], "selected_part": "1", "current_package_part": "1", "pending_start_part": ""},
      "active_block": {
        "active": true,
        "part_number": "1",
        "phase_label": "Condition",
        "block_index": "1",
        "block_label": "Two-minute mixed profile",
        "duration_s": 120.0,
        "elapsed_s": 15.0,
        "last_anchor_server_perf_counter_s": 47.0,
        "running": true,
        "paused": false,
        "instruction_waiting": false
      },
      "timeline": {
        "trial_rows": [
          {"trial_number": 2, "trial_uid": "T002", "start_time_s": 30.0, "duration_s": 30.0, "display_label": "recede", "stimulus_label": "pink", "soa": "150"},
          {"trial_number": 1, "trial_uid": "T001", "start_time_s": 0.0, "duration_s": 30.0, "label": "looming", "noise": "white", "soa": "300"}
        ],
        "tactile_cues": [
          {"cue_id": 2, "trial_number": 2, "trial_uid": "T002", "tactile_time_s": 42.5, "phase_label": "Exhale", "noise": "pink", "soa": "150", "status": "next"},
          {"cue_id": 1, "trial_number": 1, "trial_uid": "T001", "tactile_time_s": 12.5, "phase_label": "Inhale", "noise": "white", "soa": "300", "status": "passed"}
        ],
        "clicks": [
          {"click_id": 2, "click_time_s": 45.0, "trial_uid": "T002", "response_status": "off_cue", "cue_id": null},
          {"click_id": 1, "click_time_s": 12.8, "trial_uid": "T001", "response_status": "tactile_response", "cue_id": 1, "rt_s": 0.3}
        ]
      },
      "topup": {"draft_count": 0},
      "instruction_gate": {"waiting": false}
    }
    """.trimIndent()
