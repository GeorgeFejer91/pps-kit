import assert from "node:assert/strict";
import test from "node:test";
import { publicationMatches, evidenceSummary, inventoryAuditSummary, inventoryEvidenceLabel, studyDisplayLabel, publicationInclusionBasis } from "../publication_network.js";

test("publication search accepts DOI URLs, author accents and unordered title terms", () => {
  const node = { title: "Audio tactile space", authors: ["Ana García"], doi: "10.1007/example", year: 2013 };
  for (const query of ["", "https://doi.org/10.1007/example", "doi:10.1007/EXAMPLE", "garcia space", "2013 Audio"]) {
    assert.equal(publicationMatches(node, query), true, query);
  }
  for (const query of ["2014", "garcia unrelated", "10.1007/absent"]) assert.equal(publicationMatches(node, query), false, query);
});

test("evidence totals retain unresolved contracts separately from reported and derived completion", () => {
  assert.equal(evidenceSummary({ reported_complete: 2, derived_complete: 1, partial: 8 }), "2 reported complete · 1 derived complete · 11 contracts");
  assert.equal(evidenceSummary({ not_reported: 11 }), "0 reported complete · 0 derived complete · 11 contracts");
});

test("registry coverage never implies Methods review or final-publication equivalence", () => {
  assert.equal(inventoryAuditSummary({ publications: 9, registeredInventories: 8, methodsReviewedInventories: 4, auditedAccessBlockers: 1, inventoryAndContractsAudited: 3, remainingInventoryOrContractAudit: 6 }), "8 of 9 inventories registered · 4 Methods inventories reviewed · 1 documented access blockers · 3 inventory and contract audits complete · 6 remaining");
  assert.match(inventoryAuditSummary(), /unavailable/);
  assert.match(inventoryEvidenceLabel("abstract_or_metadata_inventory"), /Methods inventory unresolved/);
  assert.match(inventoryEvidenceLabel("author_version_methods_reviewed_final_comparison_pending"), /final-version comparison pending/);
  assert.match(inventoryEvidenceLabel("audited_source_access_gap"), /Methods unavailable/);
  assert.match(inventoryEvidenceLabel("not_registered"), /No registered inventory/);
});

test("project lineage reviews remain separate from experimental Methods inventory", () => {
  const audit = { publications: 9, registeredInventories: 8, methodsReviewedInventories: 4, projectLineageReviews: 2, auditedAccessBlockers: 1, inventoryAndContractsAudited: 3, remainingInventoryOrContractAudit: 6 };
  assert.match(inventoryAuditSummary(audit), /4 Methods inventories reviewed · 2 project lineage reviews/);
  assert.equal(inventoryEvidenceLabel("primary_project_lineage_reviewed"), "Primary project lineage reviewed");
  assert.doesNotMatch(inventoryAuditSummary({ ...audit, projectLineageReviews: 0 }), /project lineage/);
});

test("study names expose the protocol variant while older records keep their label", () => {
  assert.equal(studyDisplayLabel({ experimentLabel: "Newborn stimulus-adequacy pilot", label: "Article title (c)" }), "Newborn stimulus-adequacy pilot");
  for (const experimentLabel of [undefined, null, "", "  "]) {
    assert.equal(studyDisplayLabel({ experimentLabel, label: "Earlier study label" }), "Earlier study label");
  }
});

test("frozen inclusion preserves reviewed adjacent boundaries without inferring task eligibility", () => {
  const basis = "Retained in the frozen corpus as a reviewed adjacent sound-to-MEP boundary.";
  assert.equal(publicationInclusionBasis({ scope: { provenance: "later_exact_doi_audit", basis } }), basis);
  for (const scope of [undefined, { provenance: "later_exact_doi_audit" }, { basis: "  " }]) {
    assert.match(publicationInclusionBasis({ scope }), /Membership does not establish direct audiotactile task eligibility/);
    assert.doesNotMatch(publicationInclusionBasis({ scope }), /identifying an in-scope/);
  }
});
