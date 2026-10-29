# Static FULL_PL timing audit - 29 October 2026

User reported approximately -5 ns setup slack. The failing path report is not
available locally; Vivado is not installed here. The precise critical path and
routed timing closure have therefore NOT been established.

Implemented changes remove a 32-bit-expression constant division from the
helical address recurrence, register supported-mode geometry, narrow address
arithmetic and register frame-size products before output/TLAST logic. The
clock target remains unchanged. No false-path or multicycle exceptions were
introduced. All 15 full receiver functional simulations passed after the RTL
changes. These passes do not prove timing closure or absence of all errors.

The build now routes and checks setup/hold slack before producing a bitstream.
It emits setup_paths.rpt, hold_paths.rpt, check_timing.rpt and timing.rpt.
Boot requires the successful timing-verdict marker. Recreate the project and
run build.tcl to validate the changes in Vivado. Retain the detailed timing
reports if any slack remains negative; the next optimization must follow the
actual startpoint/endpoint and logic/routing breakdown.

DPR hardware copies have not been silently changed by this static FULL_PL fix.
The older preservation manifests are historical snapshots; their hash checks
will identify these intentionally modified FULL_PL files as changed. Preserve
both experiment revisions rather than rewriting old benchmark provenance.

Remaining work: inspect the user's failing path, run synthesis/implementation,
review unconstrained paths and DRC warnings, and retest on board. No new FPGA
performance results or error-free guarantee is claimed.
