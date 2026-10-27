//! Existing V1 instruction placement around immutable manifest blocks.
//! This does not schedule samples or choose trial/block order.
use pps_session_package::{InstructionSlot, VerifiedPreparedSession};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct NativeStage {
    pub ordinal: u32,
    pub block_ordinal: u32,
    pub instruction: Option<usize>,
    pub needs_continue: bool,
}

pub(crate) fn stages(session: &VerifiedPreparedSession) -> Result<Vec<NativeStage>, &'static str> {
    let count = session.blocks().len();
    if count == 0 || count > pps_session_package::MAX_PREPARED_BLOCKS {
        return Err("native_stage_count_invalid");
    }
    let mut result = Vec::with_capacity(count * 4 + 2);
    // A missing optional recording cannot silently erase the V1 mandatory
    // condition-transition acknowledgement. This native slice requires a
    // verified transition recording for mixed-condition single-part packages.
    let has_transition = session
        .instructions()
        .iter()
        .any(|item| item.slot() == InstructionSlot::BetweenConditions);
    let mut add = |block: usize, slot: Option<InstructionSlot>, needs_continue: bool| {
        let instruction = match slot {
            Some(slot) => match session
                .instructions()
                .iter()
                .position(|item| item.slot() == slot)
            {
                Some(index) => Some(index),
                None => return,
            },
            None => None,
        };
        result.push(NativeStage {
            ordinal: result.len() as u32,
            block_ordinal: block as u32,
            instruction,
            needs_continue,
        });
    };
    if !session.is_split_part() || session.summary().part_number.unwrap_or(1) == 1 {
        add(0, Some(InstructionSlot::BeforeExperiment), true);
    }
    for index in 0..count {
        add(index, Some(InstructionSlot::BeforeEachBlock), true);
        add(index, None, false);
        let same_condition = session.blocks().get(index + 1).is_some_and(|next| {
            let key = |block: &pps_session_package::VerifiedPreparedBlock| {
                let metadata = block.metadata();
                (
                    metadata
                        .get("phase_index")
                        .and_then(|v| v.as_i64())
                        .or_else(|| metadata.get("part_number").and_then(|v| v.as_i64()))
                        .unwrap_or(1),
                    metadata
                        .get("phase")
                        .and_then(|v| v.as_str())
                        .filter(|v| !v.is_empty())
                        .or_else(|| metadata.get("phase_label").and_then(|v| v.as_str()))
                        .unwrap_or("")
                        .trim()
                        .to_lowercase(),
                )
            };
            key(&session.blocks()[index]) == key(next)
        });
        add(index, Some(InstructionSlot::AfterEachBlock), same_condition);
        if index + 1 < count && !same_condition {
            if !has_transition {
                return Err("native_condition_transition_instruction_required");
            }
            add(index, Some(InstructionSlot::BetweenConditions), true);
        }
    }
    let closing = if session.is_split_part() && session.summary().part_number == Some(1) {
        InstructionSlot::BetweenConditions
    } else {
        InstructionSlot::AfterExperiment
    };
    add(count - 1, Some(closing), false);
    Ok(result)
}
