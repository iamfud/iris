// Time sync, clock ticking, night mode
#ifndef IRIS_TIME_H
#define IRIS_TIME_H
#include <Arduino.h>

extern uint32_t _syncEpoch;
extern unsigned long _syncMillis;
extern bool timeReady;
extern int32_t utcOffsetSecs;
extern int currentHours24, currentMinutes, currentSeconds;
extern int currentDayOfMonth, currentMonth;
extern char currentDayText[4];
extern bool nightModeEnabled, nightModeActive;
extern uint8_t brightnessIndex;

uint32_t currentEpoch() {
  if (!timeReady) return 0;
  return _syncEpoch + (uint32_t)((millis() - _syncMillis) / 1000UL);
}

void tickClock() {
  if (!timeReady) return;
  int32_t localSecs = (int32_t)currentEpoch() + utcOffsetSecs;
  uint32_t t = (localSecs > 0) ? (uint32_t)localSecs : 0;
  uint32_t d = t / 86400UL;
  uint32_t s = t % 86400UL;
  currentSeconds = (int)(s % 60);
  currentMinutes = (int)((s / 60) % 60);
  currentHours24 = (int)(s / 3600);
  static const char* DNAMES[]={"SUN","MON","TUE","WED","THU","FRI","SAT"};
  strncpy(currentDayText, DNAMES[(d+4)%7], 3); currentDayText[3]='\0';
  int32_t z = (int32_t)d + 719468L;
  int32_t era = (z >= 0 ? z : z - 146096L) / 146097L;
  int32_t doe = z - era * 146097L;
  int32_t yoe = (doe - doe/1460 + doe/36524 - doe/146096) / 365;
  int32_t doy = doe - (365*yoe + yoe/4 - yoe/100);
  int32_t mp = (5*doy + 2) / 153;
  currentDayOfMonth = (int)(doy - (153*mp+2)/5 + 1);
  int mo = (int)(mp < 10 ? mp+3 : mp-9);
  currentMonth = mo - 1;
}

void updateNightMode() {
  if (!nightModeEnabled) { nightModeActive=false; return; }
  nightModeActive=(currentHours24>=22||currentHours24<6);
}

extern void setBrightnessLevelFromIndex();

#endif
