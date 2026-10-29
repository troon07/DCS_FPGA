# Standard 7-series DFX flow; all RMs share ONE locked static implementation.
set origin [file normalize [file dirname [info script]]]
set hw [file normalize $origin/..]
set out $origin/build/dfx
file mkdir $out
# Invalidate the success marker before starting a new implementation.
set marker [open $out/routed_manifest.json w]
puts $marker { {"pr_verify_passed":false} }
close $marker
open_project $origin/build/ldacs_zed/ldacs_zed.xpr
config_ip_cache -disable_cache
reset_run synth_1
foreach run [get_runs -quiet *_synth_1] {reset_run $run}
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Static synthesis failed"}
open_run synth_1
set rps [get_cells -hier -filter {REF_NAME == rp_decoder}]
if {[llength $rps]!=1} {error "Expected one preserved rp_decoder black box: $rps"}
set rp_cell [lindex $rps 0]
write_checkpoint -force $out/static_synth.dcp
close_project
foreach rm {full_pl hybrid blank anchor} {
    create_project -in_memory -part xc7z010clg400-1
    read_verilog [glob $hw/shared/*.v]
    read_verilog [glob $hw/rm/$rm/*.v]
    synth_design -mode out_of_context -top rp_decoder -part xc7z010clg400-1
    write_checkpoint -force $out/${rm}_synth.dcp
    close_project
}
proc validate_routed {out rm} {
    report_drc -file $out/${rm}_drc.rpt
    set errors [get_drc_violations -quiet -filter {SEVERITY == Error}]
    if {[llength $errors]>0} {error "DFX DRC failed for $rm: $errors"}
    report_route_status -file $out/${rm}_route.rpt
    report_timing_summary -file $out/${rm}_timing.rpt
    report_utilization -file $out/${rm}_utilization.rpt
    report_utilization -hierarchical -file $out/${rm}_hierarchy.rpt
    report_power -file $out/${rm}_power_estimate.rpt
    foreach delay {max min} {
        set paths [get_timing_paths -quiet -delay_type $delay -max_paths 1]
        if {[llength $paths]>0&&[get_property SLACK [lindex $paths 0]]<0} {error "Timing failed: $rm ($delay)"}
    }
}
open_checkpoint $out/static_synth.dcp
read_checkpoint -cell $rp_cell $out/full_pl_synth.dcp
set_property HD.RECONFIGURABLE TRUE [get_cells $rp_cell]
source $origin/floorplan.tcl
opt_design
place_design
route_design
validate_routed $out full_pl
write_checkpoint -force $out/full_pl_routed.dcp
write_bitstream -force -bin_file $out/full_pl.bit
write_bitstream -force -bin_file -cell $rp_cell $out/full_pl_partial.bit
update_design -cell $rp_cell -black_box
lock_design -level routing
write_checkpoint -force $out/static_locked.dcp
close_design
foreach rm {hybrid blank anchor} {
    open_checkpoint $out/static_locked.dcp
    read_checkpoint -cell $rp_cell $out/${rm}_synth.dcp
    opt_design
    place_design
    route_design
    validate_routed $out $rm
    write_checkpoint -force $out/${rm}_routed.dcp
    pr_verify -full_check $out/full_pl_routed.dcp $out/${rm}_routed.dcp
    write_bitstream -force -bin_file $out/${rm}.bit
    write_bitstream -force -bin_file -cell $rp_cell $out/${rm}_partial.bit
    close_design
}
set tf [open $origin/build/build_token.txt r]
set token [string trim [read $tf]]
close $tf
set f [open $out/routed_manifest.json w]
puts $f [format { {"schema":"ldacs_dfx_routed_v1","part":"xc7z010clg400-1","build_token":%s,"rp_cell":"%s","pr_verify_passed":true,"configurations":["full_pl","hybrid","blank","anchor"]} } $token $rp_cell]
close $f
puts "DFX_ROUTED_OK: run scripts/package_images.py"
