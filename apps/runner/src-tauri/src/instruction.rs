//! Existing V1 instruction placement around immutable manifest blocks.
//! This does not schedule samples or choose trial/block order.
use pps_session_package::{InstructionSlot, VerifiedPreparedSession};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct NativeStage {
    pub ordinal: u32,
    pub block_ordinal: u32,
    pub instruction: Option<usize>,
    pub needs_continue: bool,
    pub transition_without_audio: bool,
}

pub(crate) fn stages(session: &VerifiedPreparedSession) -> Result<Vec<NativeStage>, &'static str> {
    let count = session.blocks().len();
    if count == 0 || count > pps_session_package::MAX_PREPARED_BLOCKS {
        return Err("native_stage_count_invalid");
    }
    let mut result = Vec::with_capacity(count * 4 + 2);
    // V1 requires a button acknowledgement at a condition transition even
    // when its optional recording is absent. Attach it to the preceding real
    // occurrence; never manufacture PCM or a scored trial for a silent gate.
    let has_transition = session
        .instructions()
        .iter()
        .any(|item| item.slot() == InstructionSlot::BetweenConditions);
    let add = |result: &mut Vec<NativeStage>,
               block: usize,
               slot: Option<InstructionSlot>,
               needs_continue: bool| {
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
            transition_without_audio: false,
        });
    };
    if !session.is_split_part() || session.summary().part_number.unwrap_or(1) == 1 {
        add(
            &mut result,
            0,
            Some(InstructionSlot::BeforeExperiment),
            true,
        );
    }
    for index in 0..count {
        add(
            &mut result,
            index,
            Some(InstructionSlot::BeforeEachBlock),
            true,
        );
        add(&mut result, index, None, false);
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
        add(
            &mut result,
            index,
            Some(InstructionSlot::AfterEachBlock),
            same_condition,
        );
        if index + 1 < count && !same_condition {
            if !has_transition {
                result
                    .last_mut()
                    .ok_or("native_stage_count_invalid")?
                    .transition_without_audio = true;
            } else {
                add(
                    &mut result,
                    index,
                    Some(InstructionSlot::BetweenConditions),
                    true,
                );
            }
        }
    }
    let closing = if session.is_split_part() && session.summary().part_number == Some(1) {
        InstructionSlot::BetweenConditions
    } else {
        InstructionSlot::AfterExperiment
    };
    add(&mut result, count - 1, Some(closing), false);
    Ok(result)
}
