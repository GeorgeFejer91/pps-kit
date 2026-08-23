# Privacy-Safe Release Checks

Run the release audit before assembling any Designer, Runner, Shared, Full, or
Pages artifact:

```powershell
python For-AI\engineering\release\tools\release_audit.py
```

The audit and structural tests enforce these boundaries:

- `For-AI/` is tracked development/research material and never ships.
- participant/demographic data, recordings, generated sessions/renders,
  validation outputs, private paths, credentials, and caches never ship.
- only deidentified product sample data under
  `packages/pps-resources/data/sample/` may ship.
- Android companion source, APKs, phone bridges/CLIs/assets, and experimental
  controls do not ship in V1.
- each distributable file has exactly one Shared, Designer, or Runner owner.
- every manifest uses reviewed product roots and explicit exclusion patterns.

Generated releases remain under ignored `dist/`. The component assembler and
inventory validator live under `For-AI/engineering/release/`; their outputs are
release artifacts, not repository source.

To create a reviewed source bundle for development/archive use:

```powershell
python For-AI\engineering\release\tools\make_release_bundle.py
```

That source bundle is not an end-user component payload and must retain its own
privacy audit result.
