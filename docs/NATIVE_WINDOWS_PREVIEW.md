# Python-free Windows preview

The Rust/Tauri Designer and Runner share PPS Kit's scientific formats with the
existing V1 applications. They are separate preview products. Their local
candidate builds do not replace the published V1 downloads. Use the
[release page](https://github.com/GeorgeFejer91/pps-kit/releases) to identify
which product and revision a download actually contains.

The native runtime uses Rust, the bundled C++ 3DTI renderer and WebView2.
It does not run Python or require a source checkout. The Windows candidate
builder includes offline WebView2 setup and the required Microsoft runtime
files. Installed operation and clean-Windows qualification are separate checks;
neither is established by compiling the source.

## Choose the workflow

| Workflow | Available behavior | Boundary |
| --- | --- | --- |
| Online Designer | Inspect publications and presets, configure premade assets, preview, save/reload and export `.pps-profile` bundles | Custom generation requires the desktop Designer. Online preparation is not participant acquisition. |
| Native Designer preview | Import a portable bundle, customize endpoint trajectories, generate through Rust/3DTI, review and accept the schedule, prepare immutable experiment parts | Imported audio and embedded assets must pass verification. Changing accepted inputs invalidates review. |
| Native Runner preview | Verify a selected experiment, prepare native audio, execute ordered blocks and instruction gates, score responses, publish part and group results | Physical timing is unqualified. Existing results can be inspected after interruption; an interrupted acquisition is not automatically resumed. |
| V1 Windows products | Existing Python/PySide workflow, including its LSL/LabRecorder and analysis integrations | Its installed executables and qualification records are distinct from the native preview. |

The native preview writes durable event journals, response datasets and result
receipts. It does **not** implement live LSL outlets, LabRecorder/XDF capture,
analog loopback recording, automatic missed-trial top-up or the V1 analysis UI.
The V1 guides for those features do not describe the native preview. Remote
control remains an explicitly enabled preview route; its presence does not
qualify a particular phone, network or acquisition setup.

## Prepare an experiment

1. In the Online Designer, select a preset and its premade assets. Preview the
   saved timing, then export the portable `.pps-profile` bundle. Keep any
   reported source limitations with the protocol.
2. Open the bundle in the native Designer. Import verifies and materializes
   embedded audio, including instruction recordings, before adopting the draft.
   Missing or corrupted assets produce an error; the prior draft remains usable.
3. Customize the trajectory using the existing polar/Cartesian endpoints,
   approach, recede, lateral or stationary controls. Regenerate changed stimuli;
   an old premade preview cannot represent new generation parameters.
4. Inspect the source blocks and participant schedule. Accept that exact review
   and prepare the experiment. Editing inputs revokes acceptance; cancelled or
   failed preparation must not publish a complete experiment.
5. In Runner, use **Choose participant session group** for a multi-part
   experiment. Use the single-session selector only for an independent session.
   Inspect the compiled schedule, prepare the next audio occurrence and choose
   a matching output configuration. Submit participant setup and arm locally
   before starting. Instruction gates and **Next part** follow the saved order.
6. Review the final result status. Completing one part is not whole-experiment
   completion. A complete group needs every ordered part and a verified group
   receipt. Keep the selected immutable package with its output files.

## Results and interruptions

Part receipts bind the package, journal and response dataset by hash. A complete
multi-part attempt also has a `native_group_<attempt>.results.json` receipt.
Pending receipts and interrupted attempts remain inspectable evidence; they
are not counted as complete sessions. Selecting the package again shows prior
result assessments without restoring live execution or overwriting those files.
An assessment that reaches its resource budget is explicitly incomplete.

Native file dialogs are the authority for selecting local packages and output
destinations. Browser pages cannot supply arbitrary native paths. Resource,
verification and native-command failures remain visible errors; the desktop
application does not silently switch to hosted generation.

Source tests and software callback fixtures establish software behavior only.
Physical output timing remains unqualified for this preview. Catalogue coverage,
successful generation and installation do not establish behavioral replication
or physical onset accuracy.

See [V1 downloads](PPS_DOWNLOADS.md), [Windows operation](WINDOWS_APP.md) and
[native architecture](CROSS_PLATFORM_RUNNER_AND_REMOTE.md) for the corresponding
product boundaries.
