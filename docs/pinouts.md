# Hardware Pinouts

This document serves as the central source of truth for pin assignments and wiring diagrams used across the sandbox projects in this repository.

## CYD (Cheap Yellow Display) Standard Pins

The following pins are typically reserved for the CYD's built-in TFT display:

| Function | ESP32 Pin | Notes |
| :--- | :--- | :--- |
| **TFT_MISO** | 12 | Shared SPI bus |
| **TFT_MOSI** | 13 | Shared SPI bus |
| **TFT_SCLK** | 14 | Shared SPI bus |
| **TFT_CS** | 15 | Display Chip Select |
| **TFT_DC** | 2 | Data/Command |
| **TFT_BL** | 21 | Backlight (HIGH = On) |
| **TFT_RST** | -1 | Usually tied to EN/RST |

## Ethernet (W5500) - Bruce Firmware Wiring

When wiring a W5500 Ethernet module to the CYD (using the Bruce firmware method via the SD card sniffer pads), the following pins are used:

| W5500 Pin | CYD / ESP32 Pin | Notes |
| :--- | :--- | :--- |
| **GND** | GND | Connect to GND on SD Sniffer |
| **3V3** | 3V3 / VCC | Connect to VCC on SD Sniffer |
| **SCLK** | 14 (CLK) | Connect to CLK on SD Sniffer |
| **MOSI** | 13 (CMD) | Connect to CMD on SD Sniffer |
| **MISO** | 12 (DAT0) | Connect to DAT0 on SD Sniffer |
| **SCS (CS)**| 27 | Custom CS pin for Ethernet |
| **INT** | 22 | Hardware interrupt |
| **RST** | NC | Not Connected |

## GPS Module (cyd-ntp-stratum1)

For the Stratum 1 NTP server project (`cyd-ntp-stratum1`), the GPS module is connected using the following pins:

| GPS Pin | CYD / ESP32 Pin | Notes |
| :--- | :--- | :--- |
| **TX (Data Out)** | 33 | ESP32 RX (Hardware Serial 2) |
| **RX (Data In)** | 32 | ESP32 TX (Hardware Serial 2) |
| **PPS** | 34 | Pulse Per Second (Input-only, interrupt driven) |
