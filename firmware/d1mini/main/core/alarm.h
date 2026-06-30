// Alarm state machine — hardware buzzer removed, PC handles beeps via serial ALARM:active
#ifndef IRIS_ALARM_H
#define IRIS_ALARM_H
#include <Arduino.h>
#include "time.h"

extern bool alarmEnabled, alarmActive;
extern int alarmHour, alarmMinute;
extern uint8_t alarmDays;
extern int alarmSnoozeMins, alarmDismissedDay;
extern uint32_t alarmSnoozedUntilEpoch;

static uint32_t alarmDismissedMinuteEpoch = 0;

void snoozeAlarm() {
  alarmActive=false;
  alarmDismissedMinuteEpoch = currentEpoch() / 60;
  alarmSnoozedUntilEpoch=currentEpoch()+(uint32_t)(alarmSnoozeMins*60);
}

void dismissAlarmToday() {
  alarmActive=false;
  alarmDismissedDay=currentDayOfMonth;
  alarmDismissedMinuteEpoch = currentEpoch() / 60;
  alarmSnoozedUntilEpoch=0;
}

void checkAlarmState() {
  if (!alarmEnabled||!timeReady) return;
  uint32_t now=currentEpoch();
  
  if (alarmSnoozedUntilEpoch>0&&now>=alarmSnoozedUntilEpoch) {
    alarmSnoozedUntilEpoch=0;
    alarmActive=true;
    Serial.println("ALARM:active");
  }

  if (alarmDismissedDay>=0&&alarmDismissedDay!=currentDayOfMonth) {
    alarmDismissedDay=-1;
  }
  if (alarmDismissedDay==-1) {
    alarmDismissedMinuteEpoch=0;
  }

  if (alarmDismissedDay>=0) return;
  if (alarmSnoozedUntilEpoch>0) return;
  if (alarmActive) return;

  uint32_t currentMinuteEpoch = now / 60;
  if (currentHours24==alarmHour&&currentMinutes==alarmMinute) {
    uint32_t d=(now/86400UL);
    int dow=(int)((d+4)%7);
    if (!((alarmDays>>dow)&1)) return;

    if (currentMinuteEpoch != alarmDismissedMinuteEpoch) {
      alarmActive=true;
      Serial.println("ALARM:active");
    }
  }
}

#endif
