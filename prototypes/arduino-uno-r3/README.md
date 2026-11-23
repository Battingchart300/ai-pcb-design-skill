# Arduino UNO R3 — reference board

The official Arduino UNO R3 reference design: the canonical
beginner microcontroller board, and the standard example of a
well-built minimal ATmega board.

## Source

- EAGLE files: `arduino_Uno_Rev3-02-TH.zip` from
  https://arduino.cc/en/uploads/Main/arduino_Uno_Rev3-02-TH.zip
- Schematic PDF: https://arduino.cc/en/uploads/Main/Arduino_Uno_Rev3-schematic.pdf
- Files in this folder: `arduino_Uno_Rev3-02-TH.sch` (EAGLE
  schematic), `arduino_Uno_Rev3-02-TH.brd` (EAGLE layout),
  `Arduino_Uno_Rev3-schematic.pdf` (schematic as PDF).

## License

**CC BY-SA** (Creative Commons Attribution-ShareAlike), Arduino
hardware license. Attribution to Arduino — see `LICENSE` in this
folder. The skill itself is MIT; that license does NOT cover these
Arduino files.

## Board facts

- MCU: **ATmega328** (ATmega328P-PU; the schematic notes that an
  ATmega8 is shown for reference, but current models use the
  ATmega328 — the pin configuration is identical).
- Size: **68.6 × 53.4 mm**, 2 layers, 4 mounting holes.
- USB-to-UART bridge: **ATmega16U2** (earlier revisions used the
  8U2), USB Type-B connector.
- Power: DC jack + USB; **NCP1117 5 V regulator** (SOT-223) and
  **LP2985 3.3 V regulator**; M7 diode (SMB) for reverse-polarity
  protection on the DC input; auto-select between USB and external
  power (LMV358 comparator + FDN340P MOSFET).
- Clock: 16 MHz ceramic resonator for the ATmega328.
- Reset circuit: reset button + 10 kΩ pull-up, DTR auto-reset
  capacitor from the ATmega16U2.
- Headers: 14 digital I/O (6 PWM), 6 analog inputs, AREF, SDA/SCL
  next to AREF, IOREF, ICSP header for both MCUs.

## Format note — EAGLE, not KiCad

These design files are **EAGLE 6.1** format (`.sch` / `.brd`),
not KiCad. KiCad can import EAGLE schematic and board files
(File → Import → EAGLE), so the design can still be opened,
studied and converted — but it is not a native `.kicad_sch` /
`.kicad_pcb` project.

## No official BOM exists

Arduino never published an official BOM for the UNO R3. To get a
parts list, open the `.sch` in EAGLE (or import it into KiCad)
and export the parts list from there. Do not invent part numbers
from the schematic alone — verify each MPN against its datasheet
(skill hard rule §0).

## What to learn from this board

- **A minimal MCU circuit, done right**: decoupling on every
  supply pin, reset pull-up + button, crystal/resonator with load
  capacitors, ICSP for programming.
- **USB-to-UART done with a second MCU**: how the ATmega16U2
  bridges USB to the main MCU's UART, including the DTR
  auto-reset path — the pattern every Arduino-compatible board
  copies.
- **Power architecture**: one DC input, one USB input, automatic
  selection between them, reverse-polarity protection, and two
  rails (5 V and 3.3 V) from two separate regulators.
- **Headers as the product**: the pin headers ARE the user
  interface — their placement (including the odd 0.16" offset
  between the two digital header rows) is part of the Arduino
  standard and must not be "fixed".
- **What NOT to copy**: the board is from 2012 — USB Type-B and
  the ATmega16U2 bridge are dated. Learn the patterns (power
  selection, reset, decoupling), not the connector choices.
