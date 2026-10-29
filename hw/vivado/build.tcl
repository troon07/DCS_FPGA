# build.tcl - synthesis, implementation, bitstream and hardware export (.xsa)
set origin [file normalize [file dirname [info script]]]
open_project $origin/build/ldacs_zed/ldacs_zed.xpr
# Module-reference IP cache entries can survive run resets and hide RTL edits.
# Disable cache reuse so each hardware build is derived from current sources.
config_ip_cache -disable_cache
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

# Machine-readable frontend inputs are derived from these real routed-design
# reports.  Keep one report per hierarchy so no paper/reference utilization is
# ever substituted for this build's numbers.
report_utilization -hierarchical -hierarchical_depth 8 -file $origin/build/utilization_hierarchical.rpt

proc report_block_metrics {tag root_pattern seq_pattern origin} {
    set roots [get_cells -quiet -hier -filter "NAME =~ $root_pattern"]
    if {[llength $roots] > 0} {
        report_utilization -cells [lindex $roots 0] -file $origin/build/utilization_${tag}.rpt
    } else {
        puts "WARNING: no routed hierarchy found for utilization_${tag}.rpt"
    }
    set seqs [get_cells -quiet -hier -filter "IS_SEQUENTIAL && NAME =~ $seq_pattern"]
    if {[llength $seqs] > 1} {
        report_timing -from $seqs -to $seqs -max_paths 10 -sort_by group \
            -file $origin/build/timing_${tag}.rpt
    } else {
        puts "WARNING: no internal sequential timing paths found for timing_${tag}.rpt"
    }
}

report_block_metrics viterbi    "*/u_vit"   "*/u_vit/*"   $origin
report_block_metrics block_deint "*/u_deint" "*/u_deint/*" $origin
report_block_metrics rs_decoder  "*/u_rs"    "*/u_rs/*"    $origin
report_block_metrics decoder     "*/dec/inst" "*/dec/inst/*" $origin
write_hw_platform -fixed -include_bit -force -file $origin/build/ldacs_zed.xsa
puts "INFO: done. See build/utilization.rpt, build/timing.rpt, build/ldacs_zed.xsa"
