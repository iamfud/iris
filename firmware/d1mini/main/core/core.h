// ============================================================
// Iris — Shared rendering core
// Included by main.ino. Includes all sub-modules in order.
// ============================================================
#ifndef IRIS_CORE_H
#define IRIS_CORE_H

#include <Arduino.h>
#include <MD_MAX72xx.h>
#include <SPI.h>

#define HARDWARE_TYPE MD_MAX72XX::FC16_HW
#define MAX_DEVICES 4
#define DATA_PIN   13
#define CLK_PIN    14
#define CS_PIN     4
const uint8_t BRIGHTNESS_LEVELS = 7;
const uint8_t BRIGHTNESS_VALS[BRIGHTNESS_LEVELS] = { 0, 1, 3, 5, 7, 10, 14 };

const unsigned long TIME_MODE_MS = 8000;
const unsigned long DATE_MODE_MS = 2000;
const unsigned long NOTIFY_SCROLL_STEP_MS = 120;
const unsigned long TEXT_SCROLL_STEP_MS = 35;
const unsigned long NOTIFY_SCROLL_SHOW_MS = 8000;
#define BOOT_GRACE_MS 0

const unsigned long ACCESSORY_OVERLAY_MS = 1500;
const unsigned long TEMP_FLASH_OFF_MS   = 1000;   // 1s off
const unsigned long TEMP_FLASH_CYCLE_MS = 11000;  // 1s off + 10s on

const unsigned long VISION_FLASH_TOGGLE_MS  = 500;    // blink half-period (on/off)
const unsigned long VISION_FLASH_PERSIST_MS = 60000;  // keep flashing until PC clears it or 60s elapse
// ALERT: aliases the flash path (generic 4-letter bold); same timings.
const unsigned long ALERT_TOGGLE_MS  = VISION_FLASH_TOGGLE_MS;
const unsigned long ALERT_PERSIST_MS = VISION_FLASH_PERSIST_MS;
#define STICKY_SETTLE_LEN 7   // letters held after sticky scroll completes

const unsigned long SERIAL_TIMEOUT_MS = 300000;   // 5 min no serial → display off
const unsigned long REINIT_INTERVAL_MS = 10000;   // re-init MAX7219 regs every 10s
const unsigned long PROGRESS_TIMEOUT_MS = 5000;   // progress bar hides 5s after last update
#define PROGRESS_SETTLE_LEN 7   // letters shown once a long progress name has scrolled once

#define EYE_FRAME_MS         50
#define EYE_IDLE_MIN_MS    60000
#define EYE_IDLE_MAX_MS   300000
#define EYE_VISIBLE_MIN_MS  2200
#define EYE_VISIBLE_MAX_MS  6500
#define EYE_BLINK_MIN_MS    1600
#define EYE_BLINK_MAX_MS    4200
#define EYE_BLINK_CLOSE_MS    90
#define EYE_BLINK_HOLD_MS     45
#define EYE_BLINK_OPEN_MS    110
#define EYE_MOVE_INTERVAL_MIN 250
#define EYE_MOVE_INTERVAL_MAX 900
#define EYE_SMOOTH_DIV_X      3
#define EYE_SMOOTH_DIV_Y      3
#define EYE_DEFAULT_Y         3
#define EYE_ATTENTION_MS   3500
#define EYE_WAKE_MIN_MS    2200
#define EYE_WAKE_MAX_MS    4200

#include "fonts.h"
#include "renderer.h"
#include "eyes.h"
#include "time.h"
#include "alarm.h"
#include "display.h"
#include "serial.h"

#endif
