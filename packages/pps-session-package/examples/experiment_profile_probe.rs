use std::{
    io::{self, Read},
    path::PathBuf,
};

use pps_session_package::experiment_profile::verify_experiment_profile_inventory;
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct Input {
    paths: Vec<PathBuf>,
}

#[derive(Serialize)]
struct ResultRow {
    accepted: bool,
    code: &'static str,
    ingredient_count: usize,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let input: Input = serde_json::from_str(&input)?;
    let results: Vec<ResultRow> = input
        .paths
        .iter()
        .map(|path| match verify_experiment_profile_inventory(path) {
            Ok(receipt) => ResultRow {
                accepted: true,
                code: "verified",
                ingredient_count: receipt.summary().ingredient_count,
            },
            Err(error) => ResultRow {
                accepted: false,
                code: error.code(),
                ingredient_count: 0,
            },
        })
        .collect();
    serde_json::to_writer(io::stdout().lock(), &results)?;
    Ok(())
}
