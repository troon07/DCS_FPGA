# DPR platform contract

All integers are unsigned little-endian. The static shell base is `0x40000000`;
AXI DMA remains at `0x40400000`. There is one serialized command loop and no
background frame queue or automatic CPU fallback scheduler.

## Static AXI-Lite registers

Decoder accesses below 0x80 are proxied to the current RM. They receive SLVERR
when the slot is isolated or reset. Registers at/above 0x80 belong to static logic.

| Offset | Access | Definition |
|---|---|---|
| 0x80 | RW | bit 0 isolate, bit 1 hold local reset; initial value 3 |
| 0x84 | R | bits 0/1 as above, bit 2 frame active |
| 0x88 | R | Module ID, or 0xffffffff while isolated |
| 0x8C | R | Shell identity 0x44505231, `DPR1` |
| 0x90 | R | Generation; increments when isolation is released |
| 0x94 | R | Build token chosen at project creation |
| 0x98 | R | Raw module ID monitor; valid only after loading has completed |

Isolation/reset writes are rejected while a frame, accepted input beat, or RP
read transaction is active. Write address and data may arrive independently.
The custom proxy supports one outstanding read and one outstanding write; it
is not a general multi-outstanding AXI shutdown IP implementation.

## UART commands

`DPS1` returns `DPSR` followed by eight u32 fields: firmware architecture,
shell identity, build token, module ID, isolation/reset, generation, global
timer frequency, last loader error.

`DPU1` uploads one partial image:

```text
host: DPU1 + module_id:u8 + build_token:u32 + bytes:u32 + crc32:u32
board: RDY1                         (or DPRE + error:u32)
host: image[bytes]
board: DPUA + module_id:u32 + bytes:u32 + crc32:u32
```

The host verifies manifest SHA-256 and size before sending. The firmware checks
token, bounds, four-byte alignment, CRC32 and an aligned native-word sync value.
Each ID has its own 8 MiB DDR cache slot at `0x03000000 + ID * 0x00800000`.
CRC32 and the build token provide accidental-corruption/family checks, not
cryptographic authentication. Incomplete uploads require a firmware restart.

`DPR1 + target_id:u8` switches to an uploaded image. A successful response is
`DPRR`, seven u32 fields and seven u64 counters:

```text
u32: previous ID, new ID, build token, generation, global-timer Hz,
     partial bytes, DevCfg interrupt status
u64: isolation ticks, PCAP ticks, restart ticks, total switch ticks,
     RP-unavailable ticks, precheck ticks, complete service ticks
```

The 84-byte payload excludes the four-byte magic. `total` starts after cached
CRC verification. `service_total` includes the CRC precheck and is used for
amortized CPU/service-cost comparisons. UART staging is outside both counters.
The configuration sync word is 0xaa995566 when read as a native u32; packaging
converts Vivado raw big-endian words to the little-endian DDR representation.

## Receiver commands

The existing `LDB1` benchmark request and `LDAC` trace request retain their field
layouts. DPR firmware replies with **DDBR** for benchmark batches and **DTR4**
for traces, so captures can be distinguished from static firmware. Decoder
requests are rejected unless the slot identity matches the compiled architecture
and isolation/reset is clear. FULL_PS expects the blank module, ID 2.

Only `host/dpr_client.py` should collect DPR benchmark records. Its helper
`board_client.py` has its standalone CLI disabled to prevent dropping DPR image
and switch provenance when a capture is labeled.

## Loader errors

`DPRE` is followed by one u32:

| Code | Meaning |
|---:|---|
| 1 | Invalid upload header, size, ID or build token |
| 2 | Uploaded CRC mismatch |
| 3 | Missing aligned configuration sync word |
| 4 | No cached image for target/current static family |
| 5 | Cached image CRC changed |
| 6 | DMA or frame pipeline not idle |
| 7 | Isolation did not take effect |
| 10 | PROGRAM_B already low; partial loader refuses global reset |
| 11 | PCAP not initialized or command queue full |
| 12 | DevCfg error interrupt |
| 13 | Configuration INIT deasserted |
| 14 | PCAP timeout |
| 15 | Loaded identity or release state incorrect |
| 16 | Prior PCAP fault latched; reboot required before another partial load |

Errors after isolation leave the slot isolated/reset. Status remains accessible
through the static shell; the loader does not issue a global reset as a recovery
shortcut. A reboot/full-image reload may be required.

PCAP transfer/identity failures latch a fault until firmware restart; subsequent
partial-load commands cannot overlap a possibly unfinished timed-out transfer.
