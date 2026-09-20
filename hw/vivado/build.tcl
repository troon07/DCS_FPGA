# build.tcl - synthesis, implementation, bitstream and hardware export (.xsa)
set origin [file normalize [file dirname [info script]]]
open_project $origin/build/ldacs_zed/ldacs_zed.xpr
reset_run synth_1
# Module-reference and block-design out-of-context checkpoints must also be
# invalidated; otherwise RTL edits can leave a stale decoder checkpoint in the
# top-level implementation.
foreach ooc_run [get_runs -quiet *_synth_1] {
    reset_run $ooc_run
}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "implementation failed" }
open_run impl_1
report_utilization    -file $origin/build/utilization.rpt
report_timing_summary -file $origin/build/timing.rpt
write_hw_platform -fixed -include_bit -force -file $origin/build/ldacs_zed.xsa
puts "INFO: done. See build/utilization.rpt, build/timing.rpt, build/ldacs_zed.xsa"
