// ============================================================
// IRIS  —  Wemos D1 Mini (ESP8266)
// USB-only PC companion.  Serial protocol from PC tray app.
// All rendering lives in core/*.h headers.
// ============================================================
#include "core/core.h"

// ── Hardware ───────────────────────────────────────────────────
MD_MAX72XX mx = MD_MAX72XX(HARDWARE_TYPE, CS_PIN, MAX_DEVICES);

// ── Time ──────────────────────────────────────────────────────
uint32_t      _syncEpoch  = 0;
unsigned long _syncMillis = 0;
bool    timeReady      = false;
int32_t utcOffsetSecs  = 0;

// ── Clock display state ───────────────────────────────────────
int  currentHours24    = 12;
int  currentMinutes    = 34;
int  currentSeconds    = 0;
int  currentDayOfMonth = 1;
int  currentMonth      = 0;
char currentDayText[4] = "MON";
bool colonVisible      = true;
bool showDateMode      = false;

// ── Feature flags ─────────────────────────────────────────────
bool featureTimeEnabled          = true;
bool featureDateEnabled          = false;
bool featureMinuteBarEnabled     = true;
bool featureEyesEnabled          = true;
bool featureNotificationsEnabled = true;
bool featureLargeClockEnabled    = false;
bool featureDayClockEnabled      = true;
bool featureAudioVizEnabled      = true;
bool featureVolumeEnabled        = true;

// ── Night mode ────────────────────────────────────────────────
bool nightModeEnabled = false;
bool nightModeActive  = false;

// ── Brightness / display ──────────────────────────────────────
uint8_t brightnessIndex = 3;
bool    displayOn       = true;

// ── PC stats ──────────────────────────────────────────────────
float   lastCpuTemp  = -1.0f;
float   lastGpuTemp  = -1.0f;
float   lastFps      = -1.0f;
uint8_t pcDispFlags  = 0;
unsigned long lastPcStatsMs = 0;
bool tempAlertEnabled = false;
int  cpuTempLim       = 90;
int  gpuTempLim       = 90;
bool tempFlashState   = true;
unsigned long tempFlashMs = 0;
bool tempOverheatBeeped = false;

// ── Stopwatch ─────────────────────────────────────────────────
char          swDisplay[12]  = "";
unsigned long lastSwMs       = 0;
bool          swCountdown    = false;
bool          swDoneActive   = false;
unsigned long swDoneUntilMs  = 0;

// ── Notification scroll ───────────────────────────────────────
String        notifyScrollMessage = "";
int           notifyScrollOffset  = 32;
unsigned long notifyScrollUntilMs = 0;
bool          notifyScrollStatic  = false;

// ── Alarm ─────────────────────────────────────────────────────
bool   alarmEnabled   = false;
int    alarmHour      = 7;
int    alarmMinute    = 0;
uint8_t alarmDays     = 0x7F;
bool   alarmActive    = false;
bool   alarmShowEyes  = false;
String alarmMessageText = "";
int    alarmSnoozeMins  = 10;
int    alarmDismissedDay       = -1;
uint32_t alarmSnoozedUntilEpoch = 0;
String userName = "";

// ── Accessory overlay ─────────────────────────────────────────
uint8_t       accessoryOverlayMode    = 0;
unsigned long accessoryOverlayUntilMs = 0;
bool          accFlashOn              = true;
unsigned long lastAccFlashMs          = 0;

// ── Eye overlay ───────────────────────────────────────────────
bool eyeOverlayMode = false;
bool forceEyes      = false;
EyeState eyeState;

// ── VC join display ───────────────────────────────────────────
char          vcJoinName[64]  = "";
unsigned long vcJoinUntilMs   = 0;

// ── Audio visualizer ──────────────────────────────────────────
uint8_t       vuBars[12]   = {0};
unsigned long lastVuMs     = 0;

// ── Volume display ────────────────────────────────────────────
uint8_t       currentVolume    = 0;
unsigned long lastVolumeMs     = 0;

// ── Greeting ──────────────────────────────────────────────────
bool   greetingActive      = false;
String greetingMessage     = "";
int    greetingOffset      = 32;
unsigned long lastGreetingTickMs = 0;

// ── Pip-bar animation ─────────────────────────────────────────
uint8_t  minuteBarSettled = 0;
uint8_t  minuteBarTarget  = 0;
int16_t  pipAnimX         = 0;
uint8_t  pipPhase         = 0;
unsigned long lastPipFrameMs  = 0;
int8_t  barStartX  = 7;
int8_t  barY       = 7;
int8_t  barWidth   = 18;
int16_t barLaunchX = 25;

// ── Timers ────────────────────────────────────────────────────
unsigned long lastSecondTick        = 0;
unsigned long lastBlinkTick         = 0;
unsigned long lastModeSwitch        = 0;
unsigned long lastNotifyScrollTick  = 0;
unsigned long bootMs                = 0;

// ── Failsafe ──────────────────────────────────────────────────
bool          _failsafeActive   = false;
uint16_t      _litPixelCount    = 0;
unsigned long _lastSerialCmdMs  = 0;
unsigned long _lastReinitMs     = 0;
uint8_t       _recoveryCount    = 0;
unsigned long _recoveryWindowMs = 0;

// ============================================================
void saveLiveSettings() {}

void setBrightnessLevelFromIndex() {
  if (brightnessIndex >= BRIGHTNESS_LEVELS) brightnessIndex = BRIGHTNESS_LEVELS - 1;
  uint8_t val = (nightModeActive) ? 1 : BRIGHTNESS_VALS[brightnessIndex];
  mx.control(MD_MAX72XX::INTENSITY, val);
}

void applyDisplayOn() {
  mx.control(MD_MAX72XX::SHUTDOWN, displayOn ? MD_MAX72XX::OFF : MD_MAX72XX::ON);
}

void updateEyeEngine() {
  if ((!featureEyesEnabled&&timeReady)||nightModeActive) { eyeState.active=false; return; }
  bool eyesBase=!timeReady||(!featureTimeEnabled&&!featureDateEnabled);
  uint32_t now=millis();
  if ((forceEyes||eyesBase)&&!eyeState.active) startEyeAppearance();
  if (now-eyeState.lastFrameMs<EYE_FRAME_MS) return;
  eyeState.lastFrameMs=now;
  if (!eyeState.active) { if (now>=eyeState.nextAppearMs) startEyeAppearance(); return; }
  if (!eyesBase&&!forceEyes&&now>=eyeState.visibleUntilMs) { stopEyeAppearance(); return; }
  if (eyeState.blinkPhase==EYE_BLINK_IDLE&&now>=eyeState.nextBlinkMs) startBlink();
  updateEyeMotion(); updateBlinkAnimation(); applyExpressionLids();
}

// ── Failsafe helpers ──────────────────────────────────────────
void reinitMAX7219() {
  mx.control(MD_MAX72XX::TEST, MD_MAX72XX::OFF);
  mx.control(MD_MAX72XX::DECODE, 0);
  mx.control(MD_MAX72XX::SCANLIMIT, 7);
  mx.control(MD_MAX72XX::INTENSITY, BRIGHTNESS_VALS[brightnessIndex]);
}

void trackReinit() {
  unsigned long now = millis();
  if (now - _recoveryWindowMs > 60000) {
    _recoveryCount = 0;
    _recoveryWindowMs = now;
  }
  _recoveryCount++;
  if (_recoveryCount >= 3) {
    Serial.println("SAFETY:rebooting");
    Serial.flush();
    delay(100);
    ESP.restart();
  }
}

void triggerFailsafe() {
  if (_failsafeActive) return;
  _failsafeActive = true;
  for (int attempt = 0; attempt < 5; attempt++) {
    mx.control(MD_MAX72XX::INTENSITY, 0);
    mx.control(MD_MAX72XX::SHUTDOWN, MD_MAX72XX::ON);
    beginFrame(); clearDisplay(); endFrame();
    mx.control(MD_MAX72XX::SHUTDOWN, MD_MAX72XX::ON);
    yield();
  }
  Serial.println("SAFETY:led_overload");
}

void checkFailsafeRestore() {
  if (!_failsafeActive) return;
  trackReinit();
  _failsafeActive = false;
  reinitMAX7219();
  renderCurrentScreen();
}

// ============================================================
void setup() {
  Serial.begin(115200); Serial.setTimeout(10);
  mx.begin();

  // Boot self-test: prove SPI works before entering normal operation
  Serial.println("BOOT:self_test");
  beginFrame(); clearDisplay(); endFrame();
  delay(50);
  mx.control(MD_MAX72XX::TEST, MD_MAX72XX::ON);
  delay(250);
  mx.control(MD_MAX72XX::TEST, MD_MAX72XX::OFF);
  beginFrame(); clearDisplay(); endFrame();
  reinitMAX7219();
  Serial.println("BOOT:self_test_pass");

  ESP.wdtEnable(5000);
  ESP.wdtFeed();

  initEyeEngine();
  notifyScrollMessage.reserve(200);
  renderCurrentScreen();
  lastSecondTick = lastBlinkTick = lastModeSwitch = millis();
  lastNotifyScrollTick = millis(); lastGreetingTickMs = millis();
  bootMs = millis();
  delay(50); while (Serial.available()) Serial.read();
}

// ============================================================
void loop() {
  handleSerial();
  unsigned long nowMs = millis();
  bool dirty = false;

  if (!_failsafeActive && displayOn && _lastSerialCmdMs > 0
      && (nowMs - _lastSerialCmdMs) > SERIAL_TIMEOUT_MS) {
    displayOn = false;
    applyDisplayOn();
    Serial.println("TIMEOUT:display_off");
  }
  if (!_failsafeActive && displayOn
      && (nowMs - _lastReinitMs) >= REINIT_INTERVAL_MS) {
    _lastReinitMs = nowMs;
    reinitMAX7219();
  }
  if (_failsafeActive) {
    if (nowMs - lastSecondTick >= 1000) {
      lastSecondTick += 1000;
      tickClock();
      updateNightMode();
      checkAlarmState();
    }
    return;
  }

  if (greetingActive) {
    if (nowMs-lastGreetingTickMs>=TEXT_SCROLL_STEP_MS) {
      lastGreetingTickMs=nowMs; greetingOffset--;
      if (greetingOffset < -(int)(greetingMessage.length()*6+4)) greetingActive=false;
      renderCurrentScreen();
    } return;
  }

  if (featureNotificationsEnabled&&notifyScrollUntilMs>nowMs&&nowMs-lastNotifyScrollTick>=TEXT_SCROLL_STEP_MS) {
    lastNotifyScrollTick=nowMs;
    if (!notifyScrollStatic) {
      notifyScrollOffset--;
      if (notifyScrollOffset<-(int)(notifyScrollMessage.length()*6)) { notifyScrollUntilMs=0; renderCurrentScreen(); return; }
    } dirty=true;
  }

  if (alarmActive&&!alarmShowEyes&&nowMs-lastNotifyScrollTick>=TEXT_SCROLL_STEP_MS) {
    lastNotifyScrollTick=nowMs; notifyScrollOffset--;
    int msgLen=(alarmMessageText.length()>0?(int)alarmMessageText.length():21);
    if (notifyScrollOffset<-(msgLen*6)) notifyScrollOffset=32; dirty=true;
  }

  if (nowMs-lastSecondTick>=1000) {
    lastSecondTick+=1000; tickClock(); updateNightMode(); setBrightnessLevelFromIndex(); checkAlarmState();
    eyeOverlayMode=(!alarmActive&&featureEyesEnabled&&!nightModeActive)?eyeState.active:false;
    dirty=true;
  }

  bool vuActive=featureAudioVizEnabled&&lastVuMs>0&&(nowMs-lastVuMs)<1500;

  if (timeReady&&featureTimeEnabled&&!vuActive&&!pcOverlayActive()&&!showDateMode&&!eyeOverlayMode&&
      !alarmActive&&!(featureNotificationsEnabled&&notifyScrollUntilMs>nowMs)&&
      nowMs-lastBlinkTick>=500) {
    lastBlinkTick+=500; colonVisible=!colonVisible;
    if (!dirty) updateColonOnly(colonVisible);
  }

  if (vuActive&&featureTimeEnabled&&!pcOverlayActive()&&!showDateMode&&!eyeOverlayMode&&
      !alarmActive&&!(featureNotificationsEnabled&&notifyScrollUntilMs>nowMs)&&
      nowMs-lastBlinkTick>=500) {
    lastBlinkTick+=500; colonVisible=!colonVisible; dirty=true;
  }
  if (!vuActive&&featureTimeEnabled&&featureMinuteBarEnabled&&!featureLargeClockEnabled&&!featureDayClockEnabled&&
      !showDateMode&&!eyeOverlayMode&&!alarmActive&&
      !(featureNotificationsEnabled&&notifyScrollUntilMs>nowMs)) dirty|=tickMinuteBar();
  if (!vuActive&&featureTimeEnabled&&featureDayClockEnabled&&featureMinuteBarEnabled&&
      !showDateMode&&!eyeOverlayMode&&!alarmActive&&
      !(featureNotificationsEnabled&&notifyScrollUntilMs>nowMs)) { setBarGeometry(0,0,11); dirty|=tickMinuteBar(); }

  if (accessoryOverlayUntilMs>nowMs&&nowMs-lastAccFlashMs>=167) { lastAccFlashMs=nowMs; accFlashOn=!accFlashOn; dirty=true; }

  if (tempAlertEnabled&&pcOverlayActive()) {
    bool anyAlert=(lastCpuTemp>=0&&lastCpuTemp>=(float)cpuTempLim)||(lastGpuTemp>=0&&lastGpuTemp>=(float)gpuTempLim);
    if (anyAlert) {
      unsigned long cyclePos=(nowMs-tempFlashMs)%TEMP_FLASH_CYCLE_MS;
      bool ns=cyclePos>=TEMP_FLASH_OFF_MS;
      if (ns!=tempFlashState) { tempFlashState=ns; dirty=true; }
      if (!tempOverheatBeeped) { tempOverheatBeeped=true; Serial.println("OVERHEAT:active"); }
    } else {
      if (!tempFlashState) { tempFlashState=true; dirty=true; }
      tempOverheatBeeped=false;
    }
  }

  if (!alarmActive&&!(featureNotificationsEnabled&&notifyScrollUntilMs>nowMs)&&
      accessoryOverlayUntilMs<=nowMs&&!eyeOverlayMode) {
    if (featureTimeEnabled&&featureDateEnabled) {
      if (!showDateMode&&nowMs-lastModeSwitch>=TIME_MODE_MS) { showDateMode=true; lastModeSwitch=nowMs; dirty=true; }
      else if (showDateMode&&nowMs-lastModeSwitch>=DATE_MODE_MS) { showDateMode=false; lastModeSwitch=nowMs; dirty=true; }
    } else showDateMode=false;
  }

  if (!alarmActive&&(featureEyesEnabled||!timeReady)&&nowMs-eyeState.lastFrameMs>=EYE_FRAME_MS) {
    updateEyeEngine();
    bool prev=eyeOverlayMode;
    eyeOverlayMode=featureEyesEnabled&&eyeState.active;
    if (!timeReady||eyeOverlayMode||prev!=eyeOverlayMode) dirty=true;
  }

  if (swDoneActive) {
    if (nowMs>=swDoneUntilMs) { swDoneActive=false; dirty=true; }
    else if (nowMs-eyeState.lastFrameMs>=EYE_FRAME_MS) {
      eyeState.lastFrameMs=nowMs;
      if (!eyeState.active) startEyeAppearance();
      if (eyeState.blinkPhase==EYE_BLINK_IDLE&&nowMs>=eyeState.nextBlinkMs) startBlink();
      updateEyeMotion(); updateBlinkAnimation(); applyExpressionLids(); dirty=true;
    }
  }

  if (featureAudioVizEnabled&&lastVuMs>0&&nowMs-lastVuMs>1500) { lastVuMs=0; dirty=true; }

  if (dirty) renderCurrentScreen();
}
