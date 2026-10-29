# Device-derived STARTING floorplan; validate and refine in Vivado.
# Reserves a top-right 24x50 SLICE corner and 10 RAMB36s for static logic.
proc resource_bounds {prefix} {
    set xs {}; set ys {}
    foreach site [get_sites -quiet ${prefix}_X*Y*] {
        if {[regexp {X([0-9]+)Y([0-9]+)$} $site -> x y]} {lappend xs $x; lappend ys $y}
    }
    if {[llength $xs]==0} {error "No resources for $prefix"}
    set xs [lsort -integer $xs]; set ys [lsort -integer $ys]
    return [list [lindex $xs 0] [lindex $ys 0] [lindex $xs end] [lindex $ys end]]
}
create_pblock pblock_decoder
add_cells_to_pblock [get_pblocks pblock_decoder] [get_cells $rp_cell]
if {[file exists $origin/floorplan_override.xdc]} {
    read_xdc $origin/floorplan_override.xdc
} else {
    foreach prefix {SLICE RAMB18 RAMB36 DSP48} {
        lassign [resource_bounds $prefix] x0 y0 x1 y1
        resize_pblock [get_pblocks pblock_decoder] -add ${prefix}_X${x0}Y${y0}:${prefix}_X${x1}Y${y1}
        if {$prefix eq "SLICE"} {
            if {$x1-$x0+1<25 || $y1-$y0+1<51} {error "Unexpected XC7Z010 SLICE geometry"}
            set sx [expr {$x1-23}]; set sy [expr {$y1-49}]
            resize_pblock [get_pblocks pblock_decoder] -remove SLICE_X${sx}Y${sy}:SLICE_X${x1}Y${y1}
        }
        if {$prefix eq "RAMB36" || $prefix eq "RAMB18"} {
            set count [expr {$prefix eq "RAMB36" ? 10 : 20}]
            set by [expr {$y1-$count+1}]
            resize_pblock [get_pblocks pblock_decoder] -remove ${prefix}_X${x1}Y${by}:${prefix}_X${x1}Y${y1}
        }
    }
}
set_property SNAPPING_MODE ON [get_pblocks pblock_decoder]
# Manual slot reset is held throughout isolation and reconfiguration.
set_property RESET_AFTER_RECONFIG FALSE [get_pblocks pblock_decoder]
set_property CONTAIN_ROUTING TRUE [get_pblocks pblock_decoder]
set_property EXCLUDE_PLACEMENT TRUE [get_pblocks pblock_decoder]
set_property IS_SOFT FALSE [get_pblocks pblock_decoder]
