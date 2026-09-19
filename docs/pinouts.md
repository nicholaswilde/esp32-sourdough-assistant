# ESP32-S3-DevKitC-1-N16R8 Hardware Pinouts & Pin Reservations

This document serves as the authoritative source of truth for pin assignments, internal hardware reservations, and safe expansion pins for the **ESP32-S3-DevKitC-1-N16R8** (16MB Flash, 8MB Octal PSRAM) microcontroller board used in this project.

---

## ⚠️ Critical Reserved Pins (DO NOT USE)

On the **N16R8** variant, the high-speed Octal SPI (OPI) PSRAM and Flash bus uses several GPIO pins internally. Attempting to use, pull, or connect these pins externally will destabilize or corrupt the memory bus, causing immediate hardware panics and boot loops.

| GPIO Pin | Internal Function | Restriction |
| :--- | :--- | :--- |
| **GPIO 26** | `SPICS1` | **Strictly Reserved** (Octal PSRAM Chip Select) |
| **GPIO 27** | `SPIHD` | **Strictly Reserved** (SPI Flash Bus) |
| **GPIO 28** | `SPIWP` | **Strictly Reserved** (SPI Flash Bus) |
| **GPIO 29** | `SPICS0` | **Strictly Reserved** (SPI Flash Chip Select) |
| **GPIO 30** | `SPICLK` | **Strictly Reserved** (SPI Flash Clock) |
| **GPIO 31** | `SPIQ` | **Strictly Reserved** (SPI Flash Data In) |
| **GPIO 32** | `SPID` | **Strictly Reserved** (SPI Flash Data Out) |
| **GPIO 33** | `SPIIO4` | **Strictly Reserved** (Octal PSRAM Data Bit 4) |
| **GPIO 34** | `SPIIO5` | **Strictly Reserved** (Octal PSRAM Data Bit 5) |
| **GPIO 35** | `SPIIO6` | **Strictly Reserved** (Octal PSRAM Data Bit 6) |
| **GPIO 36** | `SPIIO7` | **Strictly Reserved** (Octal PSRAM Data Bit 7) |
| **GPIO 37** | `SPIDQS` | **Strictly Reserved** (Octal PSRAM Data Strobe) |

> [!CAUTION]
> Even if header pins labelled 33, 34, 35, 36, or 37 are physically accessible on your development board, **never connect sensors, jumpers, or pull resistors to them**.

---

## 🔌 Dedicated On-Board Interfaces

| GPIO Pin | Function | Notes |
| :--- | :--- | :--- |
| **GPIO 19** | `USB_D-` | Native USB Controller (USB-CDC Serial REPL & Flashing) |
| **GPIO 20** | `USB_D+` | Native USB Controller (USB-CDC Serial REPL & Flashing) |
| **GPIO 43** | `U0TXD` | Hardware UART0 TX (CP2102 / CH343 USB-to-UART bridge) |
| **GPIO 44** | `U0RXD` | Hardware UART0 RX (CP2102 / CH343 USB-to-UART bridge) |
| **GPIO 48** | `WS2812` | On-board Addressable RGB LED (built-in on DevKitC-1) |

---

## ⚙️ Strapping Pins

These pins configure chip boot modes at power-on / reset. If connected to external circuitry, ensure they do not interfere with default logic levels during boot:

| GPIO Pin | Default | Boot Function | Caution |
| :--- | :--- | :--- | :--- |
| **GPIO 0** | Pull-Up | Boot mode select | Low at reset triggers ROM Download mode |
| **GPIO 3** | Floating | JTAG signal source | Do not pull low during reset |
| **GPIO 45** | Pull-Down | VDD_SPI voltage selection | Internal 3.3V flash power domain |
| **GPIO 46** | Pull-Down | Boot ROM print control | Keeps boot messages enabled |

---

## 🟢 Safe Expansion Pins (Sensors & Peripherals)

The following pins are safe to use for future hardware additions (e.g. proofing box temperature/humidity sensors like BME280/AHT20, I2C OLED/e-paper status displays, or rotary encoders):

### Recommended I2C Bus (Sensors & Displays)
* **SDA**: `GPIO 1` (or `GPIO 4`)
* **SCL**: `GPIO 2` (or `GPIO 5`)

### Recommended ADC / Analog Inputs (ADC1 only — WiFi Compatible)
*ADC2 pins cannot be read while WiFi is actively transmitting.* Use ADC1 channels:
* `GPIO 1`, `GPIO 2`, `GPIO 4`, `GPIO 5`, `GPIO 6`, `GPIO 7`, `GPIO 8`, `GPIO 9`, `GPIO 10`

### Safe General Purpose Digital I/O
* `GPIO 4`, `GPIO 5`, `GPIO 6`, `GPIO 7`, `GPIO 8`, `GPIO 9`, `GPIO 10`, `GPIO 11`, `GPIO 12`, `GPIO 13`, `GPIO 14`, `GPIO 15`, `GPIO 16`, `GPIO 17`, `GPIO 18`, `GPIO 21`, `GPIO 38`, `GPIO 39`, `GPIO 40`, `GPIO 41`, `GPIO 42`, `GPIO 47`
