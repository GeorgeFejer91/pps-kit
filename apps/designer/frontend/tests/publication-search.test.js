import assert from "node:assert/strict";
import test from "node:test";
import { publicationMatches, evidenceSummary } from "../publication_network.js";

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
