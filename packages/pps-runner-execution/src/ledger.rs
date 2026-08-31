use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::{encoded::encoded_len, ExecutionError, ExecutionErrorCode, JSON_MAX_SAFE_INTEGER};

pub const DEFAULT_LEDGER_CAPACITY: usize = 8_192;
pub const MAX_LEDGER_CAPACITY: usize = 100_000;
pub const MAX_LEDGER_PAYLOAD_BYTES: usize = 64 * 1024;
pub const MAX_LEDGER_ENCODED_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_LEDGER_JSON_DEPTH: usize = 8;
pub const MAX_LEDGER_JSON_NODES: usize = 4_096;

const MAX_EVENT_TYPE_BYTES: usize = 96;
const MAX_SOURCE_BYTES: usize = 64;
const MAX_OPTIONAL_ID_BYTES: usize = 512;
const MAX_JSON_KEY_BYTES: usize = 256;
const MAX_JSON_STRING_BYTES: usize = 16 * 1024;

/// Caller-supplied facts for one audit/event record.
///
/// Native adapters inject timestamps from their clock authority. The ledger
/// never reads either a monotonic or wall clock itself, which keeps tests and
/// replay deterministic.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LedgerEventInput {
    pub event_type: String,
    pub source: String,
    pub authority_id: Option<String>,
    pub command_id: Option<String>,
    pub trigger_key: Option<String>,
    pub monotonic_ns: u64,
    pub unix_ms: Option<u64>,
    pub payload: Value,
}

impl LedgerEventInput {
    pub fn new(
        event_type: impl Into<String>,
        source: impl Into<String>,
        monotonic_ns: u64,
    ) -> Self {
        Self {
            event_type: event_type.into(),
            source: source.into(),
            authority_id: None,
            command_id: None,
            trigger_key: None,
            monotonic_ns,
            unix_ms: None,
            payload: Value::Object(Map::new()),
        }
    }
}

/// Immutable, sequence-assigned event retained by [`EventLedger`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExecutionEventRecord {
    pub sequence: u64,
    pub event_type: String,
    pub source: String,
    pub authority_id: Option<String>,
    pub command_id: Option<String>,
    pub trigger_key: Option<String>,
    pub monotonic_ns: u64,
    pub unix_ms: Option<u64>,
    pub payload: Value,
}

/// Path-free projection of bounded ledger progress.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EventLedgerSummary {
    pub capacity: u32,
    pub event_count: u32,
    pub encoded_bytes: u32,
    pub first_sequence: Option<u64>,
    pub last_sequence: Option<u64>,
    pub first_monotonic_ns: Option<u64>,
    pub last_monotonic_ns: Option<u64>,
}

/// Count-and-byte-bounded, append-only in-memory audit/event ledger.
///
/// The ledger is not a ring buffer: once its record or cumulative encoded-byte
/// budget is full, append fails and every accepted record remains available in
/// original order. This prevents silent loss from masquerading as a complete
/// scientific audit trail. A native persistence adapter can durably flush
/// records later without changing this contract.
#[derive(Debug, Clone)]
pub struct EventLedger {
    capacity: usize,
    encoded_byte_capacity: usize,
    encoded_bytes: usize,
    records: Vec<ExecutionEventRecord>,
}

impl EventLedger {
    pub fn new(capacity: usize) -> Result<Self, ExecutionError> {
        Self::with_encoded_byte_capacity(capacity, MAX_LEDGER_ENCODED_BYTES)
    }

    fn with_encoded_byte_capacity(
        capacity: usize,
        encoded_byte_capacity: usize,
    ) -> Result<Self, ExecutionError> {
        if !(1..=MAX_LEDGER_CAPACITY).contains(&capacity) {
            return Err(error(
                ExecutionErrorCode::LedgerCapacityInvalid,
                "The event ledger capacity is invalid.",
                format!(
                    "ledger capacity must be between 1 and {MAX_LEDGER_CAPACITY}, got {capacity}"
                ),
            ));
        }
        Ok(Self {
            capacity,
            encoded_byte_capacity,
            encoded_bytes: 0,
            records: Vec::with_capacity(capacity.min(4_096)),
        })
    }

    pub const fn capacity(&self) -> usize {
        self.capacity
    }

    pub fn records(&self) -> &[ExecutionEventRecord] {
        &self.records
    }

    pub fn is_full(&self) -> bool {
        self.records.len() == self.capacity || self.encoded_bytes >= self.encoded_byte_capacity
    }

    pub const fn encoded_bytes(&self) -> usize {
        self.encoded_bytes
    }

    pub fn append(
        &mut self,
        input: LedgerEventInput,
    ) -> Result<&ExecutionEventRecord, ExecutionError> {
        if self.records.len() == self.capacity {
            return Err(error(
                ExecutionErrorCode::LedgerFull,
                "The event ledger is full; execution must stop safely.",
                format!(
                    "ledger reached its configured capacity of {} records",
                    self.capacity
                ),
            ));
        }
        if self.encoded_bytes >= self.encoded_byte_capacity {
            return Err(ledger_byte_budget_error(format!(
                "ledger reached its {}-byte cumulative limit",
                self.encoded_byte_capacity
            )));
        }
        validate_input(&input)?;
        if let Some(previous) = self.records.last() {
            if input.monotonic_ns < previous.monotonic_ns {
                return Err(error(
                    ExecutionErrorCode::LedgerTimestampRegression,
                    "The event timestamp moved backwards.",
                    format!(
                        "event monotonic timestamp {} precedes the last accepted timestamp {}",
                        input.monotonic_ns, previous.monotonic_ns
                    ),
                ));
            }
        }
        let sequence =
            u64::try_from(self.records.len()).expect("bounded ledger length fits u64") + 1;
        let record = ExecutionEventRecord {
            sequence,
            event_type: input.event_type,
            source: input.source,
            authority_id: input.authority_id,
            command_id: input.command_id,
            trigger_key: input.trigger_key,
            monotonic_ns: input.monotonic_ns,
            unix_ms: input.unix_ms,
            payload: input.payload,
        };
        let record_bytes = encoded_len(&record).map_err(|cause| {
            payload_invalid(format!("event record could not be measured: {cause}"))
        })?;
        let next_encoded_bytes = self
            .encoded_bytes
            .checked_add(record_bytes)
            .ok_or_else(|| ledger_byte_budget_error("ledger byte count overflowed"))?;
        if next_encoded_bytes > self.encoded_byte_capacity {
            return Err(ledger_byte_budget_error(format!(
                "encoded ledger would exceed its {}-byte cumulative limit",
                self.encoded_byte_capacity
            )));
        }
        self.records.push(record);
        self.encoded_bytes = next_encoded_bytes;
        Ok(self
            .records
            .last()
            .expect("record was appended immediately above"))
    }

    pub fn summary(&self) -> EventLedgerSummary {
        let first = self.records.first();
        let last = self.records.last();
        EventLedgerSummary {
            capacity: u32::try_from(self.capacity).expect("maximum ledger capacity fits u32"),
            event_count: u32::try_from(self.records.len())
                .expect("maximum ledger capacity fits u32"),
            encoded_bytes: u32::try_from(self.encoded_bytes)
                .expect("maximum encoded ledger byte count fits u32"),
            first_sequence: first.map(|record| record.sequence),
            last_sequence: last.map(|record| record.sequence),
            first_monotonic_ns: first.map(|record| record.monotonic_ns),
            last_monotonic_ns: last.map(|record| record.monotonic_ns),
        }
    }
}

impl Default for EventLedger {
    fn default() -> Self {
        Self::new(DEFAULT_LEDGER_CAPACITY).expect("default ledger capacity is valid")
    }
}

fn validate_input(input: &LedgerEventInput) -> Result<(), ExecutionError> {
    validate_token(&input.event_type, MAX_EVENT_TYPE_BYTES, "event type")?;
    validate_token(&input.source, MAX_SOURCE_BYTES, "event source")?;
    for (label, value) in [
        ("authority ID", input.authority_id.as_deref()),
        ("command ID", input.command_id.as_deref()),
        ("trigger key", input.trigger_key.as_deref()),
    ] {
        if let Some(value) = value {
            if value.is_empty()
                || value.len() > MAX_OPTIONAL_ID_BYTES
                || value.chars().any(char::is_control)
            {
                return Err(event_invalid(format!(
                    "{label} must be a non-empty bounded printable string"
                )));
            }
        }
    }
    if input.monotonic_ns > JSON_MAX_SAFE_INTEGER as u64
        || input
            .unix_ms
            .is_some_and(|value| value > JSON_MAX_SAFE_INTEGER as u64)
    {
        return Err(event_invalid(
            "event timestamps exceed the exact JSON integer range",
        ));
    }
    if !input.payload.is_object() {
        return Err(payload_invalid("event payload must be a JSON object"));
    }
    let mut nodes = 0_usize;
    validate_json_shape(&input.payload, 0, &mut nodes)?;
    let encoded_bytes = encoded_len(&input.payload).map_err(|cause| {
        payload_invalid(format!("event payload could not be measured: {cause}"))
    })?;
    if encoded_bytes > MAX_LEDGER_PAYLOAD_BYTES {
        return Err(payload_invalid(format!(
            "event payload has {encoded_bytes} bytes; the limit is {MAX_LEDGER_PAYLOAD_BYTES}"
        )));
    }
    Ok(())
}

fn validate_token(value: &str, maximum_bytes: usize, label: &str) -> Result<(), ExecutionError> {
    let valid = !value.is_empty()
        && value.len() <= maximum_bytes
        && value.chars().enumerate().all(|(index, character)| {
            character.is_ascii_alphanumeric()
                || (index > 0 && matches!(character, '-' | '_' | '.' | ':'))
        });
    if valid {
        Ok(())
    } else {
        Err(event_invalid(format!(
            "{label} must be a bounded ASCII semantic token"
        )))
    }
}

fn validate_json_shape(
    value: &Value,
    depth: usize,
    nodes: &mut usize,
) -> Result<(), ExecutionError> {
    if depth > MAX_LEDGER_JSON_DEPTH {
        return Err(payload_invalid(format!(
            "event payload exceeds maximum JSON depth {MAX_LEDGER_JSON_DEPTH}"
        )));
    }
    *nodes = nodes.saturating_add(1);
    if *nodes > MAX_LEDGER_JSON_NODES {
        return Err(payload_invalid(format!(
            "event payload exceeds maximum JSON node count {MAX_LEDGER_JSON_NODES}"
        )));
    }
    match value {
        Value::Null | Value::Bool(_) | Value::Number(_) => Ok(()),
        Value::String(value) => {
            if value.len() > MAX_JSON_STRING_BYTES
                || value.chars().any(|character| character == '\0')
            {
                Err(payload_invalid(
                    "event payload contains an oversized string or NUL byte",
                ))
            } else {
                Ok(())
            }
        }
        Value::Array(values) => {
            for child in values {
                validate_json_shape(child, depth + 1, nodes)?;
            }
            Ok(())
        }
        Value::Object(values) => {
            for (key, child) in values {
                if key.is_empty()
                    || key.len() > MAX_JSON_KEY_BYTES
                    || key.chars().any(char::is_control)
                {
                    return Err(payload_invalid(
                        "event payload contains an invalid object key",
                    ));
                }
                validate_json_shape(child, depth + 1, nodes)?;
            }
            Ok(())
        }
    }
}

fn event_invalid(diagnostic: impl Into<String>) -> ExecutionError {
    error(
        ExecutionErrorCode::LedgerEventInvalid,
        "The event record is invalid.",
        diagnostic,
    )
}

fn payload_invalid(diagnostic: impl Into<String>) -> ExecutionError {
    error(
        ExecutionErrorCode::LedgerPayloadInvalid,
        "The event payload is invalid or too large.",
        diagnostic,
    )
}

fn ledger_byte_budget_error(diagnostic: impl Into<String>) -> ExecutionError {
    error(
        ExecutionErrorCode::LedgerFull,
        "The event ledger is full; execution must stop safely.",
        diagnostic,
    )
}

fn error(
    code: ExecutionErrorCode,
    public_message: &'static str,
    diagnostic: impl Into<String>,
) -> ExecutionError {
    ExecutionError::new(code, public_message, diagnostic)
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn input(event_type: &str, monotonic_ns: u64) -> LedgerEventInput {
        LedgerEventInput {
            event_type: event_type.to_owned(),
            source: "scheduler".to_owned(),
            authority_id: None,
            command_id: None,
            trigger_key: Some(format!("trigger:{event_type}")),
            monotonic_ns,
            unix_ms: Some(1_800_000_000_000),
            payload: json!({"eventType": event_type}),
        }
    }

    #[test]
    fn append_assigns_stable_sequence_and_summary() {
        let mut ledger = EventLedger::new(3).unwrap();
        let first = ledger.append(input("trial_start", 10)).unwrap();
        assert_eq!(first.sequence, 1);
        let second = ledger.append(input("trial_end", 20)).unwrap();
        assert_eq!(second.sequence, 2);
        assert_eq!(
            ledger.summary(),
            EventLedgerSummary {
                capacity: 3,
                event_count: 2,
                encoded_bytes: u32::try_from(ledger.encoded_bytes()).unwrap(),
                first_sequence: Some(1),
                last_sequence: Some(2),
                first_monotonic_ns: Some(10),
                last_monotonic_ns: Some(20),
            }
        );
    }

    #[test]
    fn ledger_never_overwrites_when_full() {
        let mut ledger = EventLedger::new(1).unwrap();
        ledger.append(input("trial_start", 10)).unwrap();
        let failure = ledger.append(input("trial_end", 20)).unwrap_err();
        assert_eq!(failure.kind(), ExecutionErrorCode::LedgerFull);
        assert_eq!(ledger.records().len(), 1);
        assert_eq!(ledger.records()[0].event_type, "trial_start");
    }

    #[test]
    fn cumulative_encoded_budget_rejects_without_mutating_the_ledger() {
        let first_input = input("trial_start", 10);
        let first_record = ExecutionEventRecord {
            sequence: 1,
            event_type: first_input.event_type.clone(),
            source: first_input.source.clone(),
            authority_id: first_input.authority_id.clone(),
            command_id: first_input.command_id.clone(),
            trigger_key: first_input.trigger_key.clone(),
            monotonic_ns: first_input.monotonic_ns,
            unix_ms: first_input.unix_ms,
            payload: first_input.payload.clone(),
        };
        let first_record_bytes = encoded_len(&first_record).unwrap();
        let mut ledger =
            EventLedger::with_encoded_byte_capacity(3, first_record_bytes + 1).unwrap();
        ledger.append(first_input).unwrap();
        let accepted_bytes = ledger.encoded_bytes();

        let failure = ledger.append(input("trial_end", 20)).unwrap_err();
        assert_eq!(failure.kind(), ExecutionErrorCode::LedgerFull);
        assert_eq!(ledger.records().len(), 1);
        assert_eq!(ledger.encoded_bytes(), accepted_bytes);
        assert_eq!(ledger.summary().encoded_bytes as usize, accepted_bytes);
    }

    #[test]
    fn timestamp_regression_is_rejected_without_consuming_sequence() {
        let mut ledger = EventLedger::new(3).unwrap();
        ledger.append(input("trial_start", 10)).unwrap();
        let failure = ledger.append(input("tactile_onset", 9)).unwrap_err();
        assert_eq!(
            failure.kind(),
            ExecutionErrorCode::LedgerTimestampRegression
        );
        let next = ledger.append(input("trial_end", 10)).unwrap();
        assert_eq!(next.sequence, 2);
    }

    #[test]
    fn payload_depth_and_size_are_bounded() {
        let mut ledger = EventLedger::new(3).unwrap();
        let mut nested = json!(true);
        for _ in 0..=MAX_LEDGER_JSON_DEPTH {
            nested = json!({"child": nested});
        }
        let mut too_deep = input("trial_start", 1);
        too_deep.payload = nested;
        assert_eq!(
            ledger.append(too_deep).unwrap_err().kind(),
            ExecutionErrorCode::LedgerPayloadInvalid
        );

        let mut too_large = input("trial_start", 1);
        too_large.payload = json!({"text": "x".repeat(MAX_LEDGER_PAYLOAD_BYTES)});
        assert_eq!(
            ledger.append(too_large).unwrap_err().kind(),
            ExecutionErrorCode::LedgerPayloadInvalid
        );
        assert!(ledger.records().is_empty());
    }

    #[test]
    fn invalid_capacity_and_tokens_fail_closed() {
        assert_eq!(
            EventLedger::new(0).unwrap_err().kind(),
            ExecutionErrorCode::LedgerCapacityInvalid
        );
        let mut ledger = EventLedger::new(1).unwrap();
        assert_eq!(
            ledger
                .append(input("../not-an-event", 1))
                .unwrap_err()
                .kind(),
            ExecutionErrorCode::LedgerEventInvalid
        );
    }
}
