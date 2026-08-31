use std::fmt;

/// Stable failure categories suitable for matching in native adapters.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionErrorCode {
    ManifestMissing,
    ManifestUnreadable,
    ManifestTooLarge,
    ManifestIdentityMismatch,
    CsvInvalid,
    TooManyColumns,
    TooManyRows,
    TooManyEvents,
    ScheduleTooLarge,
    InvalidScheduleOptions,
    SampleIndexOutOfRange,
    LedgerCapacityInvalid,
    LedgerFull,
    LedgerBatchStale,
    LedgerTimestampRegression,
    LedgerEventInvalid,
    LedgerPayloadInvalid,
}

impl ExecutionErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ManifestMissing => "manifest_missing",
            Self::ManifestUnreadable => "manifest_unreadable",
            Self::ManifestTooLarge => "manifest_too_large",
            Self::ManifestIdentityMismatch => "manifest_identity_mismatch",
            Self::CsvInvalid => "csv_invalid",
            Self::TooManyColumns => "too_many_columns",
            Self::TooManyRows => "too_many_rows",
            Self::TooManyEvents => "too_many_events",
            Self::ScheduleTooLarge => "schedule_too_large",
            Self::InvalidScheduleOptions => "invalid_schedule_options",
            Self::SampleIndexOutOfRange => "sample_index_out_of_range",
            Self::LedgerCapacityInvalid => "ledger_capacity_invalid",
            Self::LedgerFull => "ledger_full",
            Self::LedgerBatchStale => "ledger_batch_stale",
            Self::LedgerTimestampRegression => "ledger_timestamp_regression",
            Self::LedgerEventInvalid => "ledger_event_invalid",
            Self::LedgerPayloadInvalid => "ledger_payload_invalid",
        }
    }
}

impl fmt::Display for ExecutionErrorCode {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Execution failure with a path-free public message and a native diagnostic.
///
/// The type intentionally does not implement `Serialize`: callers must choose
/// [`ExecutionError::code`] and [`ExecutionError::public_message`] explicitly
/// before crossing a WebView or network boundary. [`fmt::Display`] is for
/// trusted native diagnostics and may contain a filesystem path.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExecutionError {
    code: ExecutionErrorCode,
    public_message: &'static str,
    diagnostic: String,
}

impl ExecutionError {
    pub(crate) fn new(
        code: ExecutionErrorCode,
        public_message: &'static str,
        diagnostic: impl Into<String>,
    ) -> Self {
        Self {
            code,
            public_message,
            diagnostic: diagnostic.into(),
        }
    }

    pub const fn kind(&self) -> ExecutionErrorCode {
        self.code
    }

    pub const fn code(&self) -> &'static str {
        self.code.as_str()
    }

    pub const fn public_message(&self) -> &'static str {
        self.public_message
    }
}

impl fmt::Display for ExecutionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.diagnostic)
    }
}

impl std::error::Error for ExecutionError {}
