// Display modes, notification, greeting, rendering dispatch
#ifndef IRIS_DISPLAY_H
#define IRIS_DISPLAY_H
#include "renderer.h"
#include "eyes.h"

extern bool featureTimeEnabled, featureDateEnabled;
extern bool featureMinuteBarEnabled, featureEyesEnabled;
extern bool featureNotificationsEnabled;
extern bool featureLargeClockEnabled, featureDayClockEnabled;
extern bool featureAudioVizEnabled, featureVolumeEnabled;
extern uint8_t vuBars[12];
extern unsigned long lastVuMs;
extern uint8_t currentVolume;
extern unsigned long lastVolumeMs;
extern bool showDateMode, eyeOverlayMode, timeReady;
extern unsigned long lastModeSwitch, notifyScrollUntilMs;
extern unsigned long accessoryOverlayUntilMs;
extern unsigned long lastNotifyScrollTick;
extern int currentHours24, currentMinutes, currentSeconds;
extern int currentDayOfMonth, currentMonth;
extern bool colonVisible;
extern String notifyScrollMessage;
extern int notifyScrollOffset;
extern bool notifyScrollStatic;

extern bool swDoneActive;
extern char swDisplay[12];
extern unsigned long swDoneUntilMs;
extern unsigned long lastSwMs;
extern bool alarmActive, alarmShowEyes;
extern String alarmMessageText;
extern bool greetingActive;
extern String greetingMessage;
extern int greetingOffset;
extern unsigned long lastGreetingTickMs;
extern char vcJoinName[64];
extern unsigned long vcJoinUntilMs;

String sanitizeScrollText(String msg) {
  msg.toUpperCase();
  for (size_t i=0;i<msg.length();i++) {
    char c=msg[i];
    bool ok=(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c==' '||c=='.'||c=='-'
            ||c=='!'||c=='"'||c=='#'||c=='$'||c=='?'||c=='@'||c=='\''
            ||c==','||c==':'||c=='('||c==')'||c=='%'||c=='&'||c=='/'||c=='+'
            ||c=='*'||c=='='||c==';'||c=='<'||c=='>'||c=='['||c==']'
            ||c=='^'||c=='_'||c=='{'||c=='}'||c=='~';
    if (!ok) msg.setCharAt(i,' ');
  }
  return msg;
}

bool vcJoinActive() {
  return vcJoinName[0] != '\0' && millis() < vcJoinUntilMs;
}

void drawVCJoin() {
  drawScrollText5x7(String(vcJoinName), 0);
}

void startNotificationScroll(const String& msg) {
  String safe=sanitizeScrollText(msg);
  if (safe.length()==0) safe=" ";
  notifyScrollMessage=safe;
  int tw=(int)safe.length()*6;
  if (tw<=32) {
    notifyScrollOffset=max(0,(32-tw)/2);
    notifyScrollUntilMs=millis()+5000UL;
    notifyScrollStatic=true;
  } else {
    notifyScrollOffset=32; notifyScrollStatic=false;
    unsigned long pixels=32UL+(unsigned long)safe.length()*6UL;
    unsigned long needed=pixels*TEXT_SCROLL_STEP_MS+2000UL;
    notifyScrollUntilMs=millis()+max(needed,NOTIFY_SCROLL_SHOW_MS);
  }
}

bool swOverlayActive() {
  return swDisplay[0]!='\0' && (millis()-lastSwMs)<4000;
}

void drawAlarmScreen() {
  if (alarmShowEyes) {
    clearDisplay(); drawRoundEye8x8(8,0,0,0,0); drawRoundEye8x8(16,0,0,0,0);
    if (((millis()/250)%2)==0) for (int x=0;x<32;x++) drawPixel(x,7,true);
  } else {
    String msg=alarmMessageText.length()>0?sanitizeScrollText(alarmMessageText):String("ALARM! ALARM! ALARM! ");
    if (notifyScrollMessage!=msg) { notifyScrollMessage=msg; notifyScrollOffset=32; notifyScrollStatic=false; }
    drawScrollText5x7(notifyScrollMessage, notifyScrollOffset);
  }
}

void renderCurrentScreen() {
  beginFrame();
  if (greetingActive) drawScrollText5x7(greetingMessage, greetingOffset);
  else if (featureNotificationsEnabled&&notifyScrollUntilMs>millis()) drawScrollText5x7(notifyScrollMessage,notifyScrollOffset);
  else if (vcJoinActive()) drawVCJoin();
  else if (accessoryOverlayUntilMs>millis()) drawAccessoryOverlay();
  else if (alarmActive) drawAlarmScreen();
  else if (swOverlayActive()) { clearDisplay(); drawStopwatchScreen(); }
  else if (swDoneActive) { clearDisplay(); drawEyes(); }
  else if (pcOverlayActive()) { clearDisplay(); drawPcOverlay(); }
  else if (!timeReady) { clearDisplay(); drawEyes(); }
  else if (featureEyesEnabled&&eyeOverlayMode) { clearDisplay(); drawEyes(); }
  else {
    bool snoozed=alarmSnoozedUntilEpoch>0&&(_syncEpoch+(millis()-_syncMillis)/1000UL)<alarmSnoozedUntilEpoch;
    if (featureAudioVizEnabled&&lastVuMs>0&&(millis()-lastVuMs)<1500) drawTimeWithViz(currentHours24,currentMinutes,colonVisible);
    else if (!featureTimeEnabled&&featureDateEnabled) drawDayDate(currentDayOfMonth,currentMonth);
    else if (featureTimeEnabled&&featureDateEnabled&&showDateMode) drawDayDate(currentDayOfMonth,currentMonth);
    else if (featureTimeEnabled&&featureDayClockEnabled&&!snoozed) drawDayClock(currentHours24,currentMinutes,colonVisible,currentSeconds);
    else if (featureTimeEnabled&&featureLargeClockEnabled&&!snoozed) drawTimeHHMM_Large(currentHours24,currentMinutes,colonVisible);
    else if (featureTimeEnabled) drawTimeHHMM(currentHours24,currentMinutes,colonVisible,currentSeconds);
    else clearDisplay();
  }
  // Volume bar overlay (drawn on top of current screen)
  if (featureVolumeEnabled && lastVolumeMs > 0 && (millis() - lastVolumeMs) < 2000) {
    int px = (int)currentVolume * 32 / 100;
    for (int i = 0; i < 32; i++) drawPixel(i, 7, i < px);
  }
  endFrame();
}

void updateColonOnly(bool showColon) {
  if (!timeReady||eyeOverlayMode||showDateMode||alarmActive) return;
  if (featureNotificationsEnabled&&notifyScrollUntilMs>millis()) return;
  if (accessoryOverlayUntilMs>millis()) return;
  if (swOverlayActive()||pcOverlayActive()) return;
  if (!featureTimeEnabled) return;
  if (featureAudioVizEnabled&&lastVuMs>0&&(millis()-lastVuMs)<1500) return;
  bool snoozed=alarmSnoozedUntilEpoch>0&&(_syncEpoch+(millis()-_syncMillis)/1000UL)<alarmSnoozedUntilEpoch;
  beginFrame();
  if (featureDayClockEnabled&&!snoozed) { drawPixel(23,2,showColon); drawPixel(23,5,showColon); }
  else if (featureLargeClockEnabled&&!snoozed) { drawColon5x7(15,0,showColon); }
  else { drawPixel(15,2,showColon); drawPixel(15,4,showColon); }
  endFrame();
}

#endif
