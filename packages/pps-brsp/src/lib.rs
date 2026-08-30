//! Transport-neutral BRSP/1 authentication, negotiation, and lane sequencing.
//!
//! The wire DTOs live in `pps-contracts`. This crate reproduces the normative
//! Browser Remote Sync Protocol canonical hello transcript and role-bound HMAC
//! proof. It deliberately owns no WebSocket, WebRTC, UI, or application state.

use std::collections::BTreeSet;

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use hmac::{Hmac, Mac};
use pps_contracts::{
    BrspRole, Envelope, HelloEnvelope, ProofBody, ProofEnvelope, ReadyBody, Scope, BRSP_PROTOCOL,
    BRSP_VERSION,
};
use rand::{rngs::OsRng, RngCore};
use serde_json::Value;
use sha2::Sha256;
use thiserror::Error;

pub const PAIRING_SECRET_BYTES: usize = 32;
pub const NONCE_BYTES: usize = 24;
pub const HMAC_ALGORITHM: &str = "HMAC-SHA-256";

type HmacSha256 = Hmac<Sha256>;

#[derive(Clone)]
pub struct PairingSecret([u8; PAIRING_SECRET_BYTES]);

impl std::fmt::Debug for PairingSecret {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("PairingSecret([REDACTED])")
    }
}

impl PairingSecret {
    pub fn generate() -> Self {
        let mut bytes = [0_u8; PAIRING_SECRET_BYTES];
        OsRng.fill_bytes(&mut bytes);
        Self(bytes)
    }

    pub fn from_bytes(bytes: [u8; PAIRING_SECRET_BYTES]) -> Self {
        Self(bytes)
    }

    pub fn from_base64(value: &str) -> Result<Self, BrspError> {
        let decoded = URL_SAFE_NO_PAD
            .decode(value)
            .map_err(|_| BrspError::InvalidSecret)?;
        let bytes: [u8; PAIRING_SECRET_BYTES] =
            decoded.try_into().map_err(|_| BrspError::InvalidSecret)?;
        Ok(Self(bytes))
    }

    pub fn expose_base64(&self) -> String {
        URL_SAFE_NO_PAD.encode(self.0)
    }

    /// Compute the normative unpadded base64url HMAC. The BRSP reference uses
    /// the UTF-8 invitation string as the HMAC key, not its decoded random bytes.
    pub fn proof_base64url(
        &self,
        local_role: BrspRole,
        first_hello: &HelloEnvelope,
        second_hello: &HelloEnvelope,
    ) -> Result<String, BrspError> {
        let input = proof_input(local_role, first_hello, second_hello)?;
        let encoded_secret = self.expose_base64();
        let mut mac = HmacSha256::new_from_slice(encoded_secret.as_bytes())
            .expect("HMAC accepts the encoded pairing secret");
        mac.update(input.as_bytes());
        Ok(URL_SAFE_NO_PAD.encode(mac.finalize().into_bytes()))
    }

    pub fn verify_proof(
        &self,
        proof: &ProofEnvelope,
        local_hello: &HelloEnvelope,
        remote_hello: &HelloEnvelope,
    ) -> bool {
        if validate_common(proof, "proof").is_err()
            || proof.body.algorithm != HMAC_ALGORITHM
            || proof.body.role != remote_hello.body.role
            || proof.sender_id != remote_hello.sender_id
            || proof.sender_epoch != remote_hello.sender_epoch
            || !is_base64url(&proof.body.value)
        {
            return false;
        }
        let Ok(expected) = self.proof_base64url(proof.body.role, local_hello, remote_hello) else {
            return false;
        };
        constant_time_equal(expected.as_bytes(), proof.body.value.as_bytes())
    }
}

pub fn create_proof_envelope(
    secret: &PairingSecret,
    local_hello: &HelloEnvelope,
    remote_hello: &HelloEnvelope,
    sequence: u32,
) -> Result<ProofEnvelope, BrspError> {
    validate_hello_pair(local_hello, remote_hello)?;
    let role = local_hello.body.role;
    let value = secret.proof_base64url(role, local_hello, remote_hello)?;
    Ok(Envelope::new(
        "proof",
        local_hello.session_id.clone(),
        local_hello.sender_id.clone(),
        local_hello.sender_epoch,
        sequence,
        ProofBody {
            algorithm: HMAC_ALGORITHM.to_owned(),
            role,
            value,
        },
    ))
}

/// Canonical target/controller transcript as defined by BRSP/1. Only hello
/// envelopes enter this transcript, so all numeric values are exact uint32s.
pub fn proof_transcript(
    first_hello: &HelloEnvelope,
    second_hello: &HelloEnvelope,
) -> Result<String, BrspError> {
    let (target, controller) = hello_pair(first_hello, second_hello)?;
    canonical_json(&serde_json::json!({
        "protocol": BRSP_PROTOCOL,
        "version": BRSP_VERSION,
        "sessionId": target.session_id,
        "targetHello": target,
        "controllerHello": controller,
    }))
}

pub fn proof_input(
    role: BrspRole,
    first_hello: &HelloEnvelope,
    second_hello: &HelloEnvelope,
) -> Result<String, BrspError> {
    Ok(format!(
        "BRSP/1 proof\n{}\n{}",
        role.as_str(),
        proof_transcript(first_hello, second_hello)?
    ))
}

pub fn canonical_json(value: &Value) -> Result<String, BrspError> {
    fn visit(value: &Value, depth: usize) -> Result<String, BrspError> {
        if depth > 8 {
            return Err(BrspError::InvalidJson("maximum depth exceeded"));
        }
        match value {
            Value::Null => Ok("null".to_owned()),
            Value::Bool(value) => Ok(value.to_string()),
            Value::String(value) => serde_json::to_string(value).map_err(BrspError::Serialization),
            Value::Number(value) => Ok(value.to_string()),
            Value::Array(values) => {
                if values.len() > 256 {
                    return Err(BrspError::InvalidJson("array entry limit exceeded"));
                }
                let encoded = values
                    .iter()
                    .map(|value| visit(value, depth + 1))
                    .collect::<Result<Vec<_>, _>>()?;
                Ok(format!("[{}]", encoded.join(",")))
            }
            Value::Object(values) => {
                if values.len() > 128 {
                    return Err(BrspError::InvalidJson("object field limit exceeded"));
                }
                let mut keys = values.keys().collect::<Vec<_>>();
                keys.sort_unstable();
                let mut fields = Vec::with_capacity(keys.len());
                for key in keys {
                    if key.is_empty()
                        || key.len() > 96
                        || matches!(key.as_str(), "__proto__" | "prototype" | "constructor")
                    {
                        return Err(BrspError::InvalidJson("unsafe object field"));
                    }
                    fields.push(format!(
                        "{}:{}",
                        serde_json::to_string(key).map_err(BrspError::Serialization)?,
                        visit(&values[key], depth + 1)?
                    ));
                }
                Ok(format!("{{{}}}", fields.join(",")))
            }
        }
    }
    visit(value, 0)
}

pub fn validate_common<T>(envelope: &Envelope<T>, expected_type: &str) -> Result<(), BrspError> {
    if envelope.protocol != BRSP_PROTOCOL || envelope.version != BRSP_VERSION {
        return Err(BrspError::UnsupportedProtocol);
    }
    if envelope.message_type != expected_type {
        return Err(BrspError::WrongMessageType);
    }
    if !valid_token(&envelope.session_id, 8, 96) || !valid_token(&envelope.sender_id, 8, 96) {
        return Err(BrspError::InvalidToken);
    }
    Ok(())
}

pub fn validate_hello(hello: &HelloEnvelope) -> Result<(), BrspError> {
    validate_common(hello, "hello")?;
    if hello.sequence != 0
        || !is_base64url(&hello.body.nonce)
        || hello.body.nonce.len() < 20
        || hello.body.nonce.len() > 96
    {
        return Err(BrspError::InvalidHello);
    }
    validate_unique_tokens(&hello.body.capabilities)?;
    validate_unique_scopes(&hello.body.requested_scopes)?;
    validate_unique_scopes(&hello.body.granted_scopes)?;
    match hello.body.role {
        BrspRole::Target if !hello.body.requested_scopes.is_empty() => Err(BrspError::InvalidHello),
        BrspRole::Controller if !hello.body.granted_scopes.is_empty() => {
            Err(BrspError::InvalidHello)
        }
        _ => Ok(()),
    }
}

pub fn validate_hello_pair(
    first_hello: &HelloEnvelope,
    second_hello: &HelloEnvelope,
) -> Result<(), BrspError> {
    let _ = hello_pair(first_hello, second_hello)?;
    Ok(())
}

fn hello_pair<'a>(
    first_hello: &'a HelloEnvelope,
    second_hello: &'a HelloEnvelope,
) -> Result<(&'a HelloEnvelope, &'a HelloEnvelope), BrspError> {
    validate_hello(first_hello)?;
    validate_hello(second_hello)?;
    if first_hello.session_id != second_hello.session_id
        || first_hello.sender_id == second_hello.sender_id
        || first_hello.body.role == second_hello.body.role
    {
        return Err(BrspError::InvalidHelloPair);
    }
    match first_hello.body.role {
        BrspRole::Target => Ok((first_hello, second_hello)),
        BrspRole::Controller => Ok((second_hello, first_hello)),
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NegotiatedSession {
    pub capabilities: Vec<String>,
    pub accepted_scopes: Vec<Scope>,
}

pub fn negotiate_session(
    first_hello: &HelloEnvelope,
    second_hello: &HelloEnvelope,
) -> Result<NegotiatedSession, BrspError> {
    let (target, controller) = hello_pair(first_hello, second_hello)?;
    let target_capabilities = target
        .body
        .capabilities
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let mut capabilities = controller
        .body
        .capabilities
        .iter()
        .filter(|capability| target_capabilities.contains(capability.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    capabilities.sort();
    capabilities.dedup();
    let accepted_scopes = negotiate_scopes(
        &controller.body.requested_scopes,
        &target.body.granted_scopes,
    );
    Ok(NegotiatedSession {
        capabilities,
        accepted_scopes,
    })
}

pub fn ready_matches(body: &ReadyBody, negotiated: &NegotiatedSession) -> bool {
    body.capabilities == negotiated.capabilities
        && body.accepted_scopes == negotiated.accepted_scopes
}

pub fn negotiate_scopes(requested: &[Scope], available: &[Scope]) -> Vec<Scope> {
    let available = available.iter().copied().collect::<BTreeSet<_>>();
    requested
        .iter()
        .copied()
        .filter(|scope| available.contains(scope))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

pub fn random_nonce() -> String {
    let mut bytes = [0_u8; NONCE_BYTES];
    OsRng.fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}

pub fn random_epoch() -> u32 {
    let mut bytes = [0_u8; 4];
    OsRng.fill_bytes(&mut bytes);
    u32::from_le_bytes(bytes)
}

pub fn valid_token(value: &str, minimum: usize, maximum: usize) -> bool {
    (minimum..=maximum).contains(&value.len())
        && value.chars().enumerate().all(|(index, character)| {
            character.is_ascii_alphanumeric()
                || (index > 0 && matches!(character, '-' | '_' | '.' | ':'))
        })
}

pub fn valid_peer_id(value: &str) -> bool {
    valid_token(value, 8, 96)
}

pub fn is_newer_sequence(next: u32, previous: u32) -> bool {
    let distance = next.wrapping_sub(previous);
    distance > 0 && distance < 0x8000_0000
}

#[derive(Debug, Clone, Default)]
pub struct SequenceGuard {
    previous: Option<u32>,
}

impl SequenceGuard {
    pub fn after(previous: u32) -> Self {
        Self {
            previous: Some(previous),
        }
    }

    pub fn accept(&mut self, sequence: u32) -> SequenceDecision {
        let accepted = self
            .previous
            .is_none_or(|previous| is_newer_sequence(sequence, previous));
        if accepted {
            self.previous = Some(sequence);
            SequenceDecision::Fresh
        } else {
            SequenceDecision::Rejected
        }
    }

    pub fn previous(&self) -> Option<u32> {
        self.previous
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SequenceDecision {
    Fresh,
    Rejected,
}

fn validate_unique_tokens(values: &[String]) -> Result<(), BrspError> {
    if values.len() > 32
        || values.iter().any(|value| !valid_token(value, 1, 64))
        || values.iter().collect::<BTreeSet<_>>().len() != values.len()
    {
        return Err(BrspError::InvalidTokenArray);
    }
    Ok(())
}

fn validate_unique_scopes(values: &[Scope]) -> Result<(), BrspError> {
    if values.len() > 32 || values.iter().collect::<BTreeSet<_>>().len() != values.len() {
        return Err(BrspError::InvalidTokenArray);
    }
    Ok(())
}

fn is_base64url(value: &str) -> bool {
    !value.is_empty()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn constant_time_equal(left: &[u8], right: &[u8]) -> bool {
    let length = left.len().max(right.len());
    let mut difference = left.len() ^ right.len();
    for index in 0..length {
        difference |= usize::from(
            left.get(index).copied().unwrap_or_default()
                ^ right.get(index).copied().unwrap_or_default(),
        );
    }
    difference == 0
}

#[derive(Debug, Error)]
pub enum BrspError {
    #[error("pairing secret must be exactly 32 unpadded base64url bytes")]
    InvalidSecret,
    #[error("unsupported BRSP protocol or version")]
    UnsupportedProtocol,
    #[error("wrong BRSP message type")]
    WrongMessageType,
    #[error("invalid BRSP token")]
    InvalidToken,
    #[error("invalid or duplicate capability/scope token")]
    InvalidTokenArray,
    #[error("invalid BRSP hello")]
    InvalidHello,
    #[error("BRSP proof requires one target and one controller hello in the same session")]
    InvalidHelloPair,
    #[error("invalid bounded JSON: {0}")]
    InvalidJson(&'static str),
    #[error("JSON serialization failed: {0}")]
    Serialization(serde_json::Error),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> Value {
        serde_json::from_str(include_str!("../test-vectors/brsp1-proof.json")).unwrap()
    }

    fn hellos() -> (HelloEnvelope, HelloEnvelope) {
        let fixture = fixture();
        (
            serde_json::from_value(fixture["targetHello"].clone()).unwrap(),
            serde_json::from_value(fixture["controllerHello"].clone()).unwrap(),
        )
    }

    #[test]
    fn canonical_transcript_is_role_ordered_and_stable() {
        let (target, controller) = hellos();
        let forward = proof_transcript(&target, &controller).unwrap();
        let reverse = proof_transcript(&controller, &target).unwrap();
        assert_eq!(forward, reverse);
        assert_eq!(forward, fixture()["canonicalTranscript"].as_str().unwrap());
        assert!(forward.starts_with(r#"{"controllerHello":{"body":{"capabilities":["command-ack"#));
        assert!(forward.contains(r#""protocol":"brsp"#));
        assert!(forward.ends_with(r#""version":1}"#));
    }

    #[test]
    fn proof_is_base64url_role_bound_and_verifiable() {
        let (target, controller) = hellos();
        let fixture = fixture();
        let secret = PairingSecret::from_base64(fixture["secret"].as_str().unwrap()).unwrap();
        let target_proof = create_proof_envelope(&secret, &target, &controller, 1).unwrap();
        assert_eq!(
            target_proof.body.value,
            fixture["targetProof"].as_str().unwrap()
        );
        assert!(secret.verify_proof(&target_proof, &controller, &target));
        assert!(!target_proof.body.value.contains('='));
        let controller_proof = create_proof_envelope(&secret, &controller, &target, 1).unwrap();
        assert_eq!(
            controller_proof.body.value,
            fixture["controllerProof"].as_str().unwrap()
        );
        assert_ne!(target_proof.body.value, controller_proof.body.value);
    }

    #[test]
    fn negotiation_is_exact_intersection() {
        let (target, controller) = hellos();
        let negotiated = negotiate_session(&target, &controller).unwrap();
        assert_eq!(negotiated.accepted_scopes, vec![Scope::SessionTransport]);
        assert!(negotiated.capabilities.contains(&"command-ack".to_owned()));
    }

    #[test]
    fn per_lane_half_range_sequence_handles_wrap() {
        assert!(is_newer_sequence(0, u32::MAX));
        assert!(!is_newer_sequence(10, 10));
        assert!(!is_newer_sequence(9, 10));
        assert!(!is_newer_sequence(0x8000_0000, 0));
        let mut guard = SequenceGuard::after(u32::MAX);
        assert_eq!(guard.accept(0), SequenceDecision::Fresh);
        assert_eq!(guard.accept(0), SequenceDecision::Rejected);
    }

    #[test]
    fn pairing_secret_round_trips_without_padding() {
        let secret = PairingSecret::from_bytes([19; 32]);
        let encoded = secret.expose_base64();
        assert!(!encoded.contains('='));
        assert_eq!(
            PairingSecret::from_base64(&encoded)
                .unwrap()
                .expose_base64(),
            encoded
        );
    }
}
