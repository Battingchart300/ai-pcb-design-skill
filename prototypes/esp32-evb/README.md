# Olimex ESP32-EVB — reference board

A mature, proven open-source ESP32 development board from Olimex:
a full-featured board (Ethernet, CAN, relays, microSD, LiPo) built
around an ESP32 module — the standard example of a real,
manufactured ESP32 board.

## Source

- Repository: https://github.com/OLIMEX/ESP32-EVB
- Revision used: **Rev L** (latest revision in the repository).
- OSHWA certified open-source hardware
  (https://certification.oshwa.org/bg000011.html).

## License

**Apache License 2.0** (see the `LICENSE` file in the Olimex
repository). The skill itself is MIT; that license does NOT cover
these Olimex files.

## Files in this folder

- `ESP32-EVB_Rev_L.kicad_sch` — KiCad schematic (Rev L).
- `ESP32-EVB_Rev_L.kicad_pcb` — KiCad layout (Rev L, ~3 MB).
- `ESP32-EVB_Rev_K2_BOM.csv` — BOM from Rev K2 (Rev L has no
  BOM file of its own; this is the closest revision's BOM).
- `LICENSE` — Apache License 2.0 from the source repo root.

## Board facts

- MCU module: **ESP32-WROOM-32E** (Wi-Fi + Bluetooth).
- Layers: **2**, 1.6 mm FR-4.
- Size: Rev J measured 75.2 × 74.7 mm with 157 parts; see
  `ESP32-EVB_dimensions.pdf` in the source repo for the exact
  Rev L outline.
- Ethernet: **LAN8710A** wired Ethernet controller (RMII).
- CAN: built-in CAN transceiver.
- Power: LiPo battery support (**TP4054** charger), USB,
  DC input.
- Peripherals: **2 relays**, microSD card slot, IR transmitter
  and receiver, USB-to-UART converter, UEXT connectors for
  add-on modules.
- Designed in KiCad; schematics and sources in the repo's
  `HARDWARE/` folder, PDF exports available for reading without
  KiCad.

## What to learn from this board

- **Module integration**: how a complete product is built around
  an ESP32-WROOM module instead of a bare chip — antenna
  keep-out, module power pins, strapping pins, EN/BOOT handling.
- **Power**: one board, several inputs (USB, DC, LiPo) and a
  charger — how the rails are organized and protected.
- **Ethernet + CAN on one board**: RMII routing to the LAN8710A
  and a CAN transceiver next to the MCU; what a mixed-signal
  2-layer board looks like when it is done properly.
- **Connectors and relays**: mains-capable relays, UEXT
  expansion connectors, microSD — placement, clearances and
  isolation on a board that mixes low voltage and relay outputs.
- **What NOT to copy**: this is a large, feature-packed
  evaluation board (150+ parts). For a small board, take the
  patterns (module power, EN/BOOT, decoupling) and leave the
  peripherals out.
