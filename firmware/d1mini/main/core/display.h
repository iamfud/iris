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
extern bool notifyScrollOverride;

extern bool visionFlashActive;
extern String visionFlashText;
extern int visionFlashOffset;
extern unsigned long visionFlashUntilMs;
extern bool alertBlink;

extern bool bigScrollActive;
extern String bigScrollText;
extern int bigScrollOffset;
extern unsigned long bigScrollUntilMs;
extern bool bigScrollStatic;
extern unsigned long lastBigScrollTick;

extern bool stickyActive;
extern String stickyMessage;
extern int stickyOffset;
extern bool stickyScrollDone;
extern bool stickyStatic;
extern unsigned long lastStickyTick;
extern unsigned long stickyUntilMs;

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
extern bool progressActive;
extern String progressName;
extern uint8_t progressPercent;
extern unsigned long lastProgressMs;
extern int progressScrollOffset;
extern bool progressScrollDone;

// True while a notification or forced VISION alert is being scrolled.
// VISION alerts display even when the notifications feature is off.
bool notifyScrollActive(unsigned long nowMs = 0) {
  if (nowMs == 0) nowMs = millis();
  return notifyScrollUntilMs > nowMs && (featureNotificationsEnabled || notifyScrollOverride);
}

// True while a high-priority 4-letter alert is showing (ALERT: / VISIONFLASH:).
bool visionFlashActiveNow() {
  return visionFlashActive && millis() < visionFlashUntilMs;
}

void drawVisionFlash() {
  clearDisplay();
  bool on = !alertBlink || (((millis() / ALERT_TOGGLE_MS) % 2) == 0);
  if (on) {
    for (size_t i = 0; i < visionFlashText.length(); i++)
      drawBitmap8x8(visionFlashOffset + (int)i * 8, 0, glyph8(visionFlashText.charAt(i)));
  }
}

// Sticky: scroll full text once, then hold first STICKY_SETTLE_LEN letters.
bool stickyActiveNow(unsigned long nowMs = 0) {
  if (nowMs == 0) nowMs = millis();
  if (!stickyActive) return false;
  if (stickyUntilMs > 0 && nowMs >= stickyUntilMs) return false;
  return true;
}

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

void startStickyScroll(const String& msg) {
  String safe=sanitizeScrollText(msg);
  if (safe.length()==0) safe=" ";
  stickyMessage=safe;
  int tw=(int)safe.length()*6;
  if (tw<=32) {
    stickyOffset=max(0,(32-tw)/2);
    stickyStatic=true;
    stickyScrollDone=true;  // already fits — hold immediately
  } else {
    stickyOffset=32;
    stickyStatic=false;
    stickyScrollDone=false;
  }
  stickyUntilMs=millis()+120000UL;  // safety cap; PC should clear earlier
  stickyActive=true;
  notifyScrollUntilMs=0;
  bigScrollActive=false;
}

void drawStickyText() {
  clearDisplay();
  int len=(int)stickyMessage.length();
  if (len==0) return;
  if (!stickyScrollDone) {
    drawScrollText5x7(stickyMessage, stickyOffset);
    return;
  }
  // Settled: first STICKY_SETTLE_LEN chars (or full short string), centered.
  int settleLen=len;
  if (!stickyStatic && settleLen > STICKY_SETTLE_LEN) settleLen=STICKY_SETTLE_LEN;
  String hold=stickyMessage.substring(0, settleLen);
  // trim trailing space from settle window
  while (hold.length()>0 && hold.charAt(hold.length()-1)==' ')
    hold.remove(hold.length()-1);
  int tw=(int)hold.length()*6;
  int x0=max(0,(32-tw)/2);
  drawScrollText5x7(hold, x0);
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

// True while a full-size (8x8) vision scroll is showing.
bool bigScrollActiveNow(unsigned long nowMs = 0) {
  if (nowMs == 0) nowMs = millis();
  return bigScrollActive && bigScrollUntilMs > nowMs;
}

// Full-size 8x8 letter-by-letter text. One letter occupies one full
// matrix (8px pitch), so 4 letters fill the 32px row. Text longer than
// 4 letters scrolls left by 1px per TEXT_SCROLL_STEP_MS.
void startBigScroll(const String& msg) {
  String safe=sanitizeScrollText(msg);
  if (safe.length()==0) safe=" ";
  bigScrollText=safe;
  int tw=(int)safe.length()*8;
  if (tw<=32) {
    bigScrollOffset=max(0,(32-tw)/2);
    bigScrollUntilMs=millis()+5000UL;
    bigScrollStatic=true;
  } else {
    bigScrollOffset=32; bigScrollStatic=false;
    unsigned long pixels=32UL+(unsigned long)safe.length()*8UL;
    unsigned long needed=pixels*TEXT_SCROLL_STEP_MS+2000UL;
    bigScrollUntilMs=millis()+max(needed,NOTIFY_SCROLL_SHOW_MS);
  }
  bigScrollActive=true;
}

void drawBigScrollText() {
  clearDisplay();
  for (size_t i = 0; i < bigScrollText.length(); i++)
    drawBitmap8x8(bigScrollOffset + (int)i * 8, 0, glyph8(bigScrollText.charAt(i)));
}

// Progress bar screen: top row is the bar, row 1 is blank, the
// 3x6 name sits below it. Driven by the PC "PROG:name|percent" command.
String sanitizeProgressName(String msg) {
  msg.toUpperCase();
  for (size_t i=0;i<msg.length();i++) {
    char c=msg[i];
    bool ok=(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c==' '||c=='.'||c=='-'||c=='_'||c=='!';
    if (!ok) msg.setCharAt(i,' ');
  }
  return msg;
}

bool progressBarActive() {
  return progressActive;
}

void drawProgressBar() {
  clearDisplay();
  int px=(int)progressPercent*32/100;
  for (int i=0;i<32;i++) drawPixel(i,0,i<px);
  int len=(int)progressName.length();
  if (len==0) return;
  int totalW=len*4-1;
  if (totalW<=32) {
    // Fits on the row: center it statically.
    int x0=max(0,(32-totalW)/2);
    for (int i=0;i<len;i++) drawBitmap3x6(x0+i*4, 2, tc6Letter(progressName.charAt(i)));
    return;
  }
  if (!progressScrollDone) {
    // Too wide: scroll the full name across once (see main loop tick).
    for (int i=0;i<len;i++) drawBitmap3x6(progressScrollOffset+i*4, 2, tc6Letter(progressName.charAt(i)));
    return;
  }
  // Scrolled once: settle on the first PROGRESS_SETTLE_LEN letters, centered.
  int settleLen=(len<PROGRESS_SETTLE_LEN)?len:PROGRESS_SETTLE_LEN;
  int settleW=settleLen*4-1;
  int s0=max(0,(32-settleW)/2);
  for (int i=0;i<settleLen;i++) drawBitmap3x6(s0+i*4, 2, tc6Letter(progressName.charAt(i)));
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
  else if (visionFlashActiveNow()) drawVisionFlash();
  else if (bigScrollActiveNow()) drawBigScrollText();
  else if (notifyScrollActive()) drawScrollText5x7(notifyScrollMessage,notifyScrollOffset);
  else if (stickyActiveNow()) drawStickyText();
  else if (progressBarActive()) drawProgressBar();
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
  if (notifyScrollActive()) return;
  if (visionFlashActiveNow()) return;
  if (bigScrollActiveNow()) return;
  if (stickyActiveNow()) return;
  if (progressBarActive()) return;
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
