use pps_designer_core::{run_order::preview_run_order, GenerationError};
use serde_json::{json, Value};
use std::sync::atomic::AtomicBool;

#[test]
fn existing_participant_algorithms_match_complete_python_oracle() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/run_order_oracle.json")).unwrap();
    for (i, case) in fixture["cases"].as_array().unwrap().iter().enumerate() {
        let result = preview_run_order(
            &case["design"],
            &case["source_preview"],
            &AtomicBool::new(false),
        )
        .unwrap();
        assert_eq!(result["rows"], case["rows"], "summary case {i}");
        assert_eq!(
            result["csv_rows"], case["csv_rows"],
            "complete occurrences case {i}"
        );
        assert_eq!(result["accepted"], false);
        assert_eq!(result["prepared"], false);
    }
}

#[test]
fn unsupported_or_ambiguous_order_inputs_fail_without_fallback() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/run_order_oracle.json")).unwrap();
    let case = &fixture["cases"][4];
    for value in [json!("17"), json!(17.5), json!(true)] {
        let mut design = case["design"].clone();
        design["protocol"]["participant_order_policy"]["seed"] = value;
        assert!(matches!(
            preview_run_order(&design, &case["source_preview"], &AtomicBool::new(false)),
            Err(GenerationError::Invalid("run_order_integer_seed_required"))
        ));
    }
    let mut design = case["design"].clone();
    design["protocol"]["participant_order_policy"]["algorithm"] = json!("new-silent-default");
    assert!(preview_run_order(&design, &case["source_preview"], &AtomicBool::new(false)).is_err());
    design["protocol"]["participant_order_policy"]["algorithm"] = json!("fixed");
    design["protocol"]["participant_order_policy"]["part_membership"] = json!({"pre":["missing"]});
    assert!(preview_run_order(&design, &case["source_preview"], &AtomicBool::new(false)).is_err());
    assert!(matches!(
        preview_run_order(
            &case["design"],
            &case["source_preview"],
            &AtomicBool::new(true)
        ),
        Err(GenerationError::Cancelled)
    ));
    let mut blocks = case["source_preview"].clone();
    blocks["blocks"][1]["block_label"] = blocks["blocks"][0]["block_label"].clone();
    assert!(preview_run_order(&case["design"], &blocks, &AtomicBool::new(false)).is_err());
}

#[test]
#[ignore = "requires real browser capture paths PPS_BROWSER_BLOCK_PLAN and PPS_BROWSER_ORDER_ORACLE"]
fn actual_browser_design_matches_all_600_python_occurrences() {
    let capture: Value = serde_json::from_slice(
        &std::fs::read(std::env::var("PPS_BROWSER_BLOCK_PLAN").unwrap()).unwrap(),
    )
    .unwrap();
    let oracle: Value = serde_json::from_slice(
        &std::fs::read(std::env::var("PPS_BROWSER_ORDER_ORACLE").unwrap()).unwrap(),
    )
    .unwrap();
    let result = preview_run_order(
        &capture["design"],
        &capture["block_csv_preview"],
        &AtomicBool::new(false),
    )
    .unwrap();
    assert_eq!(result["rows"], oracle["rows"]);
    assert_eq!(result["csv_rows"], oracle["csv_rows"]);
    assert_eq!(result["csv_rows"].as_array().unwrap().len(), 600);
}
