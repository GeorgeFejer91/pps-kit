//! V1 response scoring and the existing 18-column minimal dataset contract.
//! Native adapters supply observations in one monotonic clock domain. These
//! functions neither acquire input nor certify physical onset or timing.

use std::collections::BTreeSet;

use serde::Serialize;
use serde_json::{Map, Value};

use crate::{ExecutionError, ExecutionErrorCode};

pub const RESPONSE_MIN_RT_NS: u64 = 100_000_000;
pub const RESPONSE_MAX_RT_NS: u64 = 1_300_000_000;
pub const MAX_TRIAL_RESPONSES: usize = 4_096;

pub const DATA_MIN_FIELDNAMES: [&str; 18] = [
    "participant_id",
    "session_id",
    "part_session_id",
    "part_number",
    "part_label",
    "block_number",
    "block_label",
    "trial_number",
    "trial_number_global",
    "trial_uid",
    "condition",
    "phase",
    "noise_type",
    "trial_type",
    "soa_ms",
    "response_given",
    "hit_miss",
    "reaction_time_ms",
];

/// Native observations, never a browser-supplied timestamp. Choice and pointer
/// coordinates are response content; the native adapter owns the event ID,
/// clock, active block, and during-playback/target flags.
#[derive(Debug, Clone)]
pub struct ParticipantResponse {
    pub event_id: u64,
    pub monotonic_ns: u64,
    pub block_number: String,
    pub in_target: bool,
    pub during_playback: bool,
    pub choice: String,
    pub x: Option<f64>,
    pub y: Option<f64>,
}

#[derive(Debug, Clone, Copy)]
pub struct TrialResponseWindow {
    pub trial_start_ns: u64,
    pub response_window_ns: u64,
    pub tactile_onset_ns: Option<u64>,
    pub trial_end_ns: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct TrialResponseScore {
    pub response_event_id: Option<u64>,
    pub response_given: bool,
    pub valid_response: bool,
    pub response_required: bool,
    pub choice_required: bool,
    pub response_choice: String,
    pub response_correct: Option<bool>,
    pub outcome: &'static str,
    pub rt_ms: String,
}

impl TrialResponseScore {
    /// Merge score facts into the original native metadata. Rich records keep
    /// lineage and additional fields; the minimal projection stays unchanged.
    pub fn apply_to(&self, row: &mut Map<String, Value>) {
        for (key, value) in [
            ("response_given", Value::Bool(self.response_given)),
            ("valid_response", Value::Bool(self.valid_response)),
            ("response_required", Value::Bool(self.response_required)),
            ("choice_required", Value::Bool(self.choice_required)),
            (
                "response_choice",
                Value::String(self.response_choice.clone()),
            ),
            (
                "response_correct",
                self.response_correct
                    .map(Value::Bool)
                    .unwrap_or(Value::Null),
            ),
            ("outcome", Value::String(self.outcome.into())),
            ("rt_ms", Value::String(self.rt_ms.clone())),
            (
                "response_event_id",
                self.response_event_id
                    .map(Value::from)
                    .unwrap_or(Value::Null),
            ),
        ] {
            row.insert(key.into(), value);
        }
    }
}

/// Select the same click as V1: first valid response in the inclusive
/// 100–1300 ms window, otherwise the first invalid candidate. Only that
/// selected ID is consumed by the caller, including for overlapping trials.
pub fn score_trial_response(
    row: &Map<String, Value>,
    window: TrialResponseWindow,
    responses: &[ParticipantResponse],
    used_response_ids: &BTreeSet<u64>,
) -> Result<TrialResponseScore, ExecutionError> {
    if responses.len() > MAX_TRIAL_RESPONSES {
        return Err(response_error(ExecutionErrorCode::ResponseCapacityExceeded));
    }
    let trial_type = text(row, &["trial_type", "Trial_Type"]);
    let family = text(row, &["family", "Family"]);
    let kind = format!("{trial_type} {family}").to_lowercase();
    let catch =
        kind.contains("catch") || kind.contains("audio_only") || kind.contains("audio-only");
    let auditory = kind.replace(['-', ' '], "_");
    let auditory = auditory.contains("auditory_only") || auditory.contains("auditoryonly");
    let tactile = window.tactile_onset_ns.is_some()
        || (!catch && !auditory && (kind.contains("tactile") || kind.contains("baseline")));
    let required = response_required(row, &trial_type, &family, catch, tactile, auditory);
    let choice = ChoicePolicy::from_row(row);
    let choice_required = choice.required();
    let mut start = window.response_window_ns;
    let mut end = if window.trial_end_ns > start {
        window.trial_end_ns
    } else {
        start
            .checked_add(RESPONSE_MAX_RT_NS)
            .ok_or_else(|| response_error(ExecutionErrorCode::ResponseWindowInvalid))?
    };
    if tactile {
        if let Some(onset) = window.tactile_onset_ns {
            start = start.min(onset);
            end = end.max(
                onset
                    .checked_add(RESPONSE_MAX_RT_NS)
                    .ok_or_else(|| response_error(ExecutionErrorCode::ResponseWindowInvalid))?,
            );
        }
    }
    if start < window.trial_start_ns || end < start {
        return Err(response_error(ExecutionErrorCode::ResponseWindowInvalid));
    }
    let anchor = window.tactile_onset_ns.filter(|_| tactile).unwrap_or(start);
    let valid_start = anchor
        .checked_add(RESPONSE_MIN_RT_NS)
        .ok_or_else(|| response_error(ExecutionErrorCode::ResponseWindowInvalid))?;
    let valid_end = anchor
        .checked_add(RESPONSE_MAX_RT_NS)
        .ok_or_else(|| response_error(ExecutionErrorCode::ResponseWindowInvalid))?;
    let block = text(row, &["block_number", "block_index", "Block_Number"]);
    let candidates = responses.iter().filter(|response| {
        !used_response_ids.contains(&response.event_id)
            && response.in_target
            && response.during_playback
            && response.block_number.trim() == block.trim()
            && (start..=end).contains(&response.monotonic_ns)
    });
    let first = candidates
        .clone()
        .min_by_key(|response| (response.monotonic_ns, response.event_id));
    let valid = if required {
        candidates
            .filter(|response| (valid_start..=valid_end).contains(&response.monotonic_ns))
            .min_by_key(|response| (response.monotonic_ns, response.event_id))
    } else {
        None
    };
    let selected = valid.or(first);
    let given = selected.is_some();
    let observed = choice.observed(selected);
    let correct = if token(&choice.correct).is_empty() {
        None
    } else {
        Some(!observed.is_empty() && token(&observed) == token(&choice.correct))
    };
    let hit = if required {
        valid.is_some() && (!choice_required || correct == Some(true))
    } else {
        !given
    };
    Ok(TrialResponseScore {
        response_event_id: selected.map(|response| response.event_id),
        response_given: given,
        valid_response: valid.is_some(),
        response_required: required,
        choice_required,
        response_choice: observed,
        response_correct: correct,
        outcome: if hit { "Hit" } else { "Miss" },
        rt_ms: valid
            .map(|response| {
                format!(
                    "{:.3}",
                    (response.monotonic_ns - anchor) as f64 / 1_000_000.0
                )
            })
            .unwrap_or_default(),
    })
}

fn response_error(code: ExecutionErrorCode) -> ExecutionError {
    ExecutionError::new(
        code,
        "The native response observations cannot be scored.",
        code.as_str(),
    )
}

fn response_required(
    row: &Map<String, Value>,
    trial_type: &str,
    family: &str,
    catch: bool,
    tactile: bool,
    auditory: bool,
) -> bool {
    if catch {
        return false;
    }
    for value in [
        text(
            row,
            &[
                "expected_response",
                "Expected_Response",
                "response_expected",
                "Response_Expected",
                "required_response",
                "Required_Response",
            ],
        ),
        text(
            row,
            &[
                "target_role",
                "Target_Role",
                "go_nogo_role",
                "Go_NoGo_Role",
                "stimulus_role",
                "Stimulus_Role",
                "tactile_role",
                "Tactile_Role",
            ],
        ),
        text(
            row,
            &[
                "response_rule",
                "Response_Rule",
                "response_mapping",
                "Response_Mapping",
                "task_response_rule",
                "Task_Response_Rule",
            ],
        ),
        trial_type.into(),
        family.into(),
    ] {
        if let Some(decision) = expectation(&value) {
            return decision;
        }
    }
    tactile || auditory
}

fn expectation(value: &str) -> Option<bool> {
    let normalized = token(value);
    if normalized.is_empty() {
        return None;
    }
    if [
        "0",
        "false",
        "no",
        "none",
        "withhold",
        "withhold_response",
        "no_response",
        "noresponse",
        "no_go",
        "nogo",
        "no_target",
        "not_target",
        "non_target",
        "nontarget",
        "strong",
        "strong_nontarget",
        "strong_non_target",
        "distractor",
    ]
    .contains(&normalized.as_str())
    {
        return Some(false);
    }
    if [
        "1",
        "true",
        "yes",
        "respond",
        "response",
        "click",
        "button_press",
        "go",
        "target",
        "weak",
        "weak_target",
        "weak_go",
    ]
    .contains(&normalized.as_str())
    {
        return Some(true);
    }
    let parts: BTreeSet<_> = normalized.split('_').collect();
    let negative = ["no_response", "no_target", "non_target", "nontarget"]
        .iter()
        .any(|marker| normalized.contains(marker))
        || [
            "withhold",
            "nogo",
            "not",
            "none",
            "strong",
            "distractor",
            "nontarget",
        ]
        .iter()
        .any(|marker| parts.contains(marker));
    let positive = ["respond", "click", "go", "weak"]
        .iter()
        .any(|marker| parts.contains(marker));
    match (negative, positive) {
        (true, true) => None,
        (true, false) => Some(false),
        (false, _) if positive || parts.contains("target") => Some(true),
        _ => None,
    }
}

struct ChoicePolicy {
    mode: String,
    choices: String,
    correct: String,
    policy: String,
}

impl ChoicePolicy {
    fn from_row(row: &Map<String, Value>) -> Self {
        let mut result = Self {
            mode: text(
                row,
                &[
                    "response_mode",
                    "Response_Mode",
                    "choice_mode",
                    "Choice_Mode",
                    "task_response_mode",
                    "Task_Response_Mode",
                ],
            )
            .trim()
            .into(),
            choices: text(
                row,
                &[
                    "response_choice_set",
                    "Response_Choice_Set",
                    "choice_set",
                    "Choice_Set",
                    "response_choices",
                    "Response_Choices",
                    "response_options",
                    "Response_Options",
                ],
            )
            .trim()
            .into(),
            correct: text(
                row,
                &[
                    "correct_response",
                    "Correct_Response",
                    "correct_choice",
                    "Correct_Choice",
                    "target_choice",
                    "Target_Choice",
                    "expected_choice",
                    "Expected_Choice",
                ],
            )
            .trim()
            .into(),
            policy: text(
                row,
                &[
                    "response_scoring_policy",
                    "Response_Scoring_Policy",
                    "choice_scoring_policy",
                    "Choice_Scoring_Policy",
                    "response_mapping_policy",
                    "Response_Mapping_Policy",
                ],
            )
            .trim()
            .into(),
        };
        if result.mode.is_empty() && !result.choices.is_empty() && !result.correct.is_empty() {
            result.mode = "choice".into();
        }
        result
    }

    fn required(&self) -> bool {
        if self.correct.is_empty() || self.choices.is_empty() {
            return false;
        }
        let mode = token(&self.mode);
        mode.is_empty()
            || [
                "choice",
                "discrimination",
                "localization",
                "localisation",
                "tactile_discrimination",
                "tactile_localization",
                "tactile_localisation",
                "spatial_choice",
                "extinction",
                "cross_modal_extinction",
                "cross_modal_extinction_report",
                "tactile_extinction",
                "tactile_report",
                "percept_report",
                "forced_choice",
                "two_alternative_forced_choice",
                "2afc",
            ]
            .iter()
            .any(|allowed| mode == *allowed || mode.split('_').any(|part| part == *allowed))
    }

    fn observed(&self, response: Option<&ParticipantResponse>) -> String {
        if let Some(response) = response.filter(|response| !response.choice.trim().is_empty()) {
            return response.choice.trim().into();
        }
        let choices: Vec<_> = self
            .choices
            .split(['|', '/', ',', ';'])
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .collect();
        if choices.is_empty() {
            return String::new();
        }
        if choices.len() == 1 {
            return choices[0].into();
        }
        let policy = token(&self.policy);
        if policy.contains("mouse_quadrant")
            || (policy.contains("quadrant") && policy.contains("mouse"))
        {
            let Some((left, upper)) = axis_low(response.and_then(|response| response.x))
                .zip(axis_low(response.and_then(|response| response.y)))
            else {
                return String::new();
            };
            let (side, index) = match (left, upper) {
                (true, true) => ("left", 0),
                (false, true) => ("right", 1),
                (true, false) => ("bilateral", 2),
                (false, false) => ("none", 3),
            };
            return choices
                .iter()
                .find(|label| report_side(label) == Some(side))
                .unwrap_or(&choices[index.min(choices.len() - 1)])
                .to_string();
        }
        let vertical = policy.contains("mouse_y_split")
            || (policy.contains("vertical") && policy.contains("mouse"));
        let Some(low) =
            axis_low(response.and_then(|response| if vertical { response.y } else { response.x }))
        else {
            return String::new();
        };
        let side = match (vertical, low) {
            (true, true) => "up",
            (true, false) => "down",
            (false, true) => "left",
            (false, false) => "right",
        };
        choices
            .iter()
            .find(|label| {
                let normalized = token(label);
                normalized == side || normalized.split('_').any(|part| part == side)
            })
            .unwrap_or(&choices[usize::from(!low)])
            .to_string()
    }
}

fn axis_low(value: Option<f64>) -> Option<bool> {
    value
        .filter(|value| value.is_finite())
        .map(|value| value < if value.abs() <= 1.0 { 0.5 } else { 500.0 })
}

fn report_side(value: &str) -> Option<&'static str> {
    match token(value).as_str() {
        "left" | "left_side" | "contralesional_left" | "ipsilesional_left" => Some("left"),
        "right" | "right_side" | "contralesional_right" | "ipsilesional_right" => Some("right"),
        "bilateral" | "both" | "both_sides" | "left_and_right" | "right_and_left" | "double" => {
            Some("bilateral")
        }
        "none" | "no_touch" | "absent" | "nothing" | "no_report" | "not_detected"
        | "undetected" => Some("none"),
        _ => None,
    }
}

fn token(value: &str) -> String {
    let mut result = String::new();
    for character in value.chars().flat_map(char::to_lowercase) {
        if character.is_ascii_alphanumeric() {
            result.push(character);
        } else if !result.is_empty() && !result.ends_with('_') {
            result.push('_');
        }
    }
    result.trim_end_matches('_').into()
}

fn value<'a>(row: &'a Map<String, Value>, names: &[&str]) -> Option<&'a Value> {
    names
        .iter()
        .filter_map(|name| row.get(*name))
        .find(|value| !value.is_null() && **value != Value::String(String::new()))
}

fn text(row: &Map<String, Value>, names: &[&str]) -> String {
    match value(row, names) {
        Some(Value::String(value)) => value.clone(),
        Some(Value::Bool(value)) => if *value { "True" } else { "False" }.into(),
        Some(value) => value.to_string(),
        None => String::new(),
    }
}

/// CSV cells in the canonical header order. Native persistence owns quoting,
/// fsync, partial files, and publication; this type owns no filesystem path.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DataMinRow {
    fields: [String; 18],
}

impl DataMinRow {
    pub fn fields(&self) -> &[String; 18] {
        &self.fields
    }
}

/// Use the existing CSV encoder, including V1 CRLF records and quoting. Disk
/// writes remain the native adapter's responsibility.
pub fn encode_data_min_csv(
    rows: &[DataMinRow],
    include_header: bool,
) -> Result<Vec<u8>, ExecutionError> {
    let mut writer = csv::WriterBuilder::new()
        .terminator(csv::Terminator::CRLF)
        .from_writer(Vec::new());
    if include_header {
        writer.write_record(DATA_MIN_FIELDNAMES).map_err(|error| {
            ExecutionError::new(
                ExecutionErrorCode::CsvInvalid,
                "The result CSV cannot be encoded.",
                error.to_string(),
            )
        })?;
    }
    for row in rows {
        writer.write_record(row.fields()).map_err(|error| {
            ExecutionError::new(
                ExecutionErrorCode::CsvInvalid,
                "The result CSV cannot be encoded.",
                error.to_string(),
            )
        })?;
    }
    writer.into_inner().map_err(|error| {
        ExecutionError::new(
            ExecutionErrorCode::CsvInvalid,
            "The result CSV cannot be encoded.",
            error.to_string(),
        )
    })
}

/// Filler/debug trials do not enter Data_min or advance its global counter.
pub fn data_min_row(row: &Map<String, Value>, trial_number_global: u64) -> Option<DataMinRow> {
    if [
        ["topup_role", "Topup_Role"],
        ["trial_type", "Trial_Type"],
        ["family", "Family"],
    ]
    .iter()
    .any(|names| ["filler", "debug"].contains(&text(row, names).trim().to_lowercase().as_str()))
    {
        return None;
    }
    let phase = text(row, &["respiratory_phase", "phase", "Row_Label"]);
    let phase = phase.trim();
    let phase = if phase.to_lowercase().contains("inhale") {
        "Inhale"
    } else if phase.to_lowercase().contains("exhale") {
        "Exhale"
    } else {
        phase
    };
    let outcome = text(row, &["outcome", "hit_miss", "Hit_Miss"]);
    let outcome = outcome.trim();
    let outcome = if outcome.to_lowercase().contains("miss") {
        "Miss"
    } else if outcome.to_lowercase().contains("hit") {
        "Hit"
    } else {
        outcome
    };
    let given = value(row, &["response_given", "Response_Given"]);
    let given = match given {
        None => false,
        Some(Value::Bool(value)) => *value,
        Some(_) => !["0", "false", "no", "none"].contains(
            &text(row, &["response_given", "Response_Given"])
                .trim()
                .to_lowercase()
                .as_str(),
        ),
    };
    Some(DataMinRow {
        fields: [
            text(row, &["participant_id", "Participant_ID"]),
            text(row, &["session_id", "Session_ID"]),
            text(row, &["part_session_id", "Part_Session_ID"]),
            text(row, &["part_number", "Part_Number"]),
            text(row, &["part_label", "Part_Label"]),
            text(row, &["block_number", "block_index", "Block_Number"]),
            text(row, &["block_label", "Block_Label"]),
            text(row, &["trial_number", "trial_index", "Trial_Number"]),
            trial_number_global.to_string(),
            text(row, &["trial_uid", "Trial_UID"]),
            text(row, &["condition", "Condition"]),
            phase.into(),
            text(row, &["noise_type", "Noise_Type", "noise_label"]),
            text(row, &["trial_type", "Trial_Type"]),
            text(row, &["soa_ms", "SOA_ms"]),
            given.to_string(),
            outcome.into(),
            text(row, &["rt_ms", "RT_ms", "reaction_time_ms"]),
        ],
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn inclusive_window_selection_withholding_and_minimal_projection() {
        let row = json!({"block_index": 1, "trial_type": "Audio-Tactile", "phase": "paced INHALE", "trial_uid": "T1"}).as_object().unwrap().clone();
        let window = TrialResponseWindow {
            trial_start_ns: 1_000_000_000,
            response_window_ns: 2_000_000_000,
            tactile_onset_ns: Some(2_300_000_000),
            trial_end_ns: 4_000_000_000,
        };
        let response = |event_id, monotonic_ns| ParticipantResponse {
            event_id,
            monotonic_ns,
            block_number: "1".into(),
            in_target: true,
            during_playback: true,
            choice: String::new(),
            x: None,
            y: None,
        };
        let clicks = [
            response(1, 2_399_999_999),
            response(2, 2_400_000_000),
            response(3, 3_600_000_000),
        ];
        let mut used = BTreeSet::new();
        let score = score_trial_response(&row, window, &clicks, &used).unwrap();
        assert_eq!(score.response_event_id, Some(2));
        assert_eq!((score.outcome, score.rt_ms.as_str()), ("Hit", "100.000"));
        used.insert(2);
        let score = score_trial_response(&row, window, &clicks, &used).unwrap();
        assert_eq!(
            (score.response_event_id, score.rt_ms.as_str()),
            (Some(3), "1300.000")
        );
        let mut rich = row;
        score.apply_to(&mut rich);
        let minimal = data_min_row(&rich, 1).unwrap();
        assert_eq!(minimal.fields()[11], "Inhale");
        assert_eq!(minimal.fields()[17], "1300.000");
        rich.insert("expected_response".into(), "no-go".into());
        assert_eq!(
            score_trial_response(&rich, window, &clicks, &used)
                .unwrap()
                .outcome,
            "Miss"
        );
        assert_eq!(
            score_trial_response(&rich, window, &[], &used)
                .unwrap()
                .outcome,
            "Hit"
        );
        rich.insert("topup_role".into(), "Debug".into());
        assert!(data_min_row(&rich, 2).is_none());
        assert!(score_trial_response(
            &rich,
            TrialResponseWindow {
                response_window_ns: u64::MAX,
                trial_end_ns: u64::MAX,
                ..window
            },
            &[],
            &used
        )
        .is_err());
        assert!(score_trial_response(
            &rich,
            window,
            &vec![clicks[0].clone(); MAX_TRIAL_RESPONSES + 1],
            &used
        )
        .is_err());
    }
}
