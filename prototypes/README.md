# prototypes/ — reference boards

Complete, proven, manufactured boards to learn from. When the
skill tells you to design a board, **study the matching reference
board here first** — then design your own. See `SKILL.md` §1,
"Reference boards first".

## Index

| Board | What it is | License | Folder |
|---|---|---|---|
| Olimex ESP32-EVB (Rev L) | Full-featured ESP32 development board: WROOM module, Ethernet, CAN, relays, microSD, LiPo | Apache 2.0 | `esp32-evb/` |
| Arduino UNO R3 | The canonical beginner MCU board: ATmega328, ATmega16U2 USB-to-UART, 5 V / 3.3 V regulators | CC BY-SA | `arduino-uno-r3/` |

## Status

- `arduino-uno-r3/` — **complete**: EAGLE schematic + layout,
  schematic PDF, LICENSE and README are in the folder.
- `esp32-evb/` — **complete**: Rev L KiCad schematic + layout,
  Rev K2 BOM (Rev L has no BOM of its own), Apache 2.0 LICENSE
  and README are in the folder.

## How to use (rules for the AI)

1. **Read this file, then the README of the matching board,**
   before designing a similar board. ESP32 board → study
   `esp32-evb/`; ATmega/Arduino-compatible board → study
   `arduino-uno-r3/`.
2. **Use a reference board as a pattern, never copy it blindly.**
   Learn how it solves power, reset, decoupling, connectors and
   routing — then apply the pattern to your own spec. Do not
   paste its schematic or layout into your design.
3. **All values still have to be verified against datasheets.**
   The skill's hard rules (§0) apply to reference boards too:
   a value in a reference design is a hint, not a verified fact.
   If the reference and the datasheet disagree, the datasheet
   wins — and the disagreement goes into the review report.
4. **Licenses stay with the boards.** The reference boards keep
   their own licenses (Apache 2.0 for ESP32-EVB, CC BY-SA for
   Arduino UNO R3). The skill itself stays MIT. Never re-license
   a reference file as MIT, and keep each board's LICENSE file
   next to its design files.
