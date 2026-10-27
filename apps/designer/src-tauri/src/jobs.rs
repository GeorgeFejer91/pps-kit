use serde::Serialize;
use serde_json::Value;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};

#[derive(Debug, Clone, Serialize)]
pub struct JobSnapshot {
    pub job_id: String,
    pub kind: &'static str,
    pub status: &'static str,
    pub revision: u64,
    pub message: &'static str,
    pub result: Option<Value>,
}

#[derive(Clone)]
pub struct JobTicket {
    pub id: u64,
    pub revision: u64,
    pub cancel: Arc<AtomicBool>,
}

/// A single bounded generation slot. The host holds this owner and its draft
/// under one mutex so revision checks and filesystem publication are indivisible.
#[derive(Default)]
pub struct JobOwner {
    revision: u64,
    sequence: u64,
    active: Option<JobTicket>,
    latest: Option<JobSnapshot>,
}

impl JobOwner {
    pub fn revision(&self) -> u64 {
        self.revision
    }

    pub fn revise(&mut self, expected: u64) -> Result<u64, &'static str> {
        if expected != self.revision {
            return Err("revision_conflict");
        }
        self.revision = self.revision.checked_add(1).ok_or("revision_exhausted")?;
        self.cancel();
        Ok(self.revision)
    }

    pub fn start(&mut self, expected: u64) -> Result<JobTicket, &'static str> {
        if expected != self.revision {
            return Err("revision_conflict");
        }
        if self.active.is_some() {
            return Err("generation_busy");
        }
        self.sequence = self.sequence.checked_add(1).ok_or("job_id_exhausted")?;
        let ticket = JobTicket {
            id: self.sequence,
            revision: self.revision,
            cancel: Arc::new(AtomicBool::new(false)),
        };
        self.latest = Some(JobSnapshot {
            job_id: ticket.id.to_string(),
            kind: "stimulus_bake",
            status: "running",
            revision: ticket.revision,
            message: "Preparing native stimulus",
            result: None,
        });
        self.active = Some(ticket.clone());
        Ok(ticket)
    }

    pub fn snapshot(&self, id: &str) -> Option<JobSnapshot> {
        self.latest.as_ref().filter(|job| job.job_id == id).cloned()
    }

    pub fn cancel(&mut self) {
        if let Some(ticket) = &self.active {
            ticket.cancel.store(true, Ordering::Release);
            if let Some(job) = &mut self.latest {
                job.status = "cancelling";
                job.message = "Cancelling native generation";
            }
        }
    }

    pub fn publish<T>(
        &mut self,
        ticket: &JobTicket,
        commit: impl FnOnce() -> Result<T, &'static str>,
    ) -> Result<T, &'static str> {
        if !self.is_current(ticket) {
            return Err("generation_cancelled");
        }
        commit()
    }

    pub fn finish(
        &mut self,
        ticket: &JobTicket,
        status: &'static str,
        message: &'static str,
        result: Option<Value>,
    ) {
        if self.active.as_ref().map(|active| active.id) != Some(ticket.id) {
            return;
        }
        let current = self.is_current(ticket);
        self.latest = Some(JobSnapshot {
            job_id: ticket.id.to_string(),
            kind: "stimulus_bake",
            revision: ticket.revision,
            status: if current { status } else { "cancelled" },
            message: if current {
                message
            } else {
                "Obsolete output was discarded"
            },
            result: if current { result } else { None },
        });
        self.active = None;
    }

    fn is_current(&self, ticket: &JobTicket) -> bool {
        self.revision == ticket.revision
            && !ticket.cancel.load(Ordering::Acquire)
            && self.active.as_ref().map(|active| active.id) == Some(ticket.id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn revision_change_cancels_and_prevents_staging_publication() {
        let mut owner = JobOwner::default();
        let ticket = owner.start(0).unwrap();
        owner.revise(0).unwrap();
        assert!(ticket.cancel.load(Ordering::Acquire));
        let mut published = false;
        assert_eq!(
            owner.publish(&ticket, || {
                published = true;
                Ok(())
            }),
            Err("generation_cancelled")
        );
        assert!(!published);
        assert_eq!(owner.start(1).err(), Some("generation_busy"));
        owner.finish(&ticket, "cancelled", "Cleanup finished", None);
        assert!(owner.start(1).is_ok());
    }

    #[test]
    fn cancellation_retains_the_worker_slot_until_cleanup_finishes() {
        let mut owner = JobOwner::default();
        let ticket = owner.start(0).unwrap();
        owner.cancel();
        assert_eq!(owner.start(0).err(), Some("generation_busy"));
        owner.finish(
            &ticket,
            "succeeded",
            "Finished",
            Some(serde_json::json!({"asset":"obsolete"})),
        );
        assert!(owner.snapshot("1").unwrap().result.is_none());
        assert!(owner.start(0).is_ok());
    }

    #[test]
    fn stale_completion_cannot_replace_a_new_job() {
        let mut owner = JobOwner::default();
        let old = owner.start(0).unwrap();
        owner.publish(&old, || Ok(())).unwrap();
        owner.finish(&old, "succeeded", "Finished", None);
        let current = owner.start(0).unwrap();
        owner.finish(&old, "failed", "Old failure", None);
        assert_eq!(
            owner.snapshot(&current.id.to_string()).unwrap().status,
            "running"
        );
    }
}
