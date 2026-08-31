use std::io::{self, Write};

use serde::Serialize;

/// Count the exact compact-JSON representation without allocating an encoded
/// copy. The counter's writer never fails; `serde_json::Error` is retained so
/// callers still handle serialization failures explicitly.
pub(crate) fn encoded_len(value: &impl Serialize) -> Result<usize, serde_json::Error> {
    let mut counter = EncodedByteCounter::default();
    serde_json::to_writer(&mut counter, value)?;
    Ok(counter.bytes)
}

#[derive(Debug, Default)]
struct EncodedByteCounter {
    bytes: usize,
}

impl Write for EncodedByteCounter {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        self.bytes = self.bytes.saturating_add(buffer.len());
        Ok(buffer.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
