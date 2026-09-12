# State NOC checklists (framework only, deliberately deprioritized)

Product scope §B.10 / §A.3 call for Gujarat and Maharashtra as the launch
states, each with its own Fire NOC application checklist layered on top of
the NBCS 2026 Part F classification. This directory is the **framework** for
that: one placeholder JSON file per launch state (schema below), wired all
the way through to `ClassificationResult.applicable_state_checklist_id` and
the report's "State NOC Checklist" section.

**No file in this directory contains a real government checklist**, and this
is not being actively worked on right now - a deliberate product decision,
not an oversight: the product's plan is India-wide NBCS 2026 Part F
classification first, with state-specific checklists added later only if
they turn out to be needed. Separately, even if/when that decision changes,
building real content would need the actual source documents: unlike NBCS
2026 Part F and NBC 2016 Part 4 - which were supplied as source documents
and digitized clause-by-clause - nobody has supplied the actual Gujarat Fire
Prevention & Life Safety Measures NOC checklist or the Maharashtra Fire
Prevention & Life Safety Measures NOC checklist. Fabricating checklist
content that *looks* official for a compliance product would be actively
harmful (a user could mistake a plausible-sounding invented item for a real
filing requirement), so every `items` entry stays a literal `"TODO: ..."`
placeholder and every file's `status` stays `"placeholder"` until both
conditions are met.

## Schema

```json
{
  "state": "Gujarat",
  "checklist_id": "GJ-FIRE-NOC-PLACEHOLDER",
  "status": "placeholder",
  "source": null,
  "disclaimer": "...",
  "items": ["TODO: ...", "..."]
}
```

- `checklist_id` is what `ClassificationResult.applicable_state_checklist_id`
  gets set to (see `app/engine/state_checklists.py`) - the `-PLACEHOLDER`
  suffix is intentional so a report can never be mistaken for citing a real
  checklist ID.
- `status` is either `"placeholder"` (no real content yet) or `"digitized"`
  (once real content is added) - the report generator renders a loud warning
  banner for `"placeholder"` and a normal citation for `"digitized"`.
- `source` should become a citation (document name/date/URL) once real
  content is added; `null` while still a placeholder.

## Adding the real content later

Once the actual state checklist documents are available, replace an
existing file's `items`/`source`/`status`/`checklist_id` in place (same
pattern as how NBCS 2026 Part F's tables were digitized into
`data/rules/nbcs_2026_partf/`) - no code changes should be needed in
`app/engine/state_checklists.py` or the report generator, since both already
read `status` to decide how to render.
