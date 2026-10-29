set origin [file normalize [file dirname [info script]]]
set marker [open $origin/build/timing_validated.txt w]
puts $marker "FAILED_OR_NOT_RUN"
close $marker
open_project $origin/build/ldacs_zed/ldacs_zed.xpr
config_ip_cache -disable_cache
reset_run synth_1
foreach run [get_runs -quiet *_synth_1] {reset_run $run}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {[get_property STATUS [get_runs impl_1]] ne "route_design Complete!"} {error "Route did not complete successfully: [get_property STATUS [get_runs impl_1]]"}
open_run impl_1
report_utilization -file $origin/build/utilization.rpt
report_utilization -hierarchical -hierarchical_depth 8 -file $origin/build/utilization_hierarchical.rpt
report_timing_summary -file $origin/build/timing.rpt
report_power -file $origin/build/power_estimate.rpt
# Power report is a Vivado ESTIMATE; external measured board power is separate.
check_timing -verbose -file $origin/build/check_timing.rpt
report_timing -delay_type max -max_paths 25 -path_type full_clock_expanded -file $origin/build/setup_paths.rpt
report_timing -delay_type min -max_paths 25 -path_type full_clock_expanded -file $origin/build/hold_paths.rpt
set setup_paths [get_timing_paths -quiet -delay_type max -max_paths 1]
set hold_paths [get_timing_paths -quiet -delay_type min -max_paths 1]
if {[llength $setup_paths]==0 || [llength $hold_paths]==0} {error "Missing setup/hold paths; verify the clock constraints"}
foreach paths [list $setup_paths $hold_paths] {
    if {[llength $paths]>0 && [get_property SLACK [lindex $paths 0]]<0} {
        error "Timing failed; bitstream must not be used as a validated benchmark image"
    }
}
write_bitstream -force $origin/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit
write_hw_platform -fixed -include_bit -force -file $origin/build/ldacs_zed.xsa
set marker [open $origin/build/timing_validated.txt w]
puts $marker "TIMING_PASSED"
close $marker
puts "BUILD_OK: inspect routed reports before board runs"
