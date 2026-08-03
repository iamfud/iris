// Serial command handler
#ifndef IRIS_SERIAL_H
#define IRIS_SERIAL_H
#include <Arduino.h>
#include "renderer.h"
#include "time.h"
#include "alarm.h"

extern bool featureTimeEnabled, featureDateEnabled;
extern bool featureMinuteBarEnabled, featureEyesEnabled;
extern bool featureNotificationsEnabled;
extern bool featureLargeClockEnabled, featureDayClockEnabled;
extern bool displayOn;
extern uint8_t brightnessIndex;
extern uint8_t pcDispFlags;
extern bool tempAlertEnabled;
extern int cpuTempLim, gpuTempLim;
extern String userName;
extern bool nightModeEnabled;
extern char swDisplay[12];
extern bool swCountdown, swDoneActive;
extern unsigned long swDoneUntilMs;

extern void startNotificationScroll(const String& msg);
extern void startEyeAppearance();
extern void renderCurrentScreen();
extern void applyDisplayOn();
extern void setBrightnessLevelFromIndex();
extern String sanitizeScrollText(String msg);
extern bool notifyScrollOverride;
extern unsigned long notifyScrollUntilMs;
extern bool visionFlashActive;
extern String visionFlashText;
extern int visionFlashOffset;
extern unsigned long visionFlashUntilMs;
extern bool alertBlink;
extern bool stickyActive;
extern bool bigScrollActive;
extern void startStickyScroll(const String& msg);
extern void startBigScroll(const String& msg);
extern unsigned long bootMs;

extern void saveLiveSettings();
extern void checkFailsafeRestore();
extern char vcJoinName[64];
extern unsigned long vcJoinUntilMs;
extern unsigned long _lastSerialCmdMs;
extern uint8_t vuBars[12];
extern unsigned long lastVuMs;
extern uint8_t currentVolume;
extern unsigned long lastVolumeMs;
extern bool progressActive;
extern String progressName;
extern uint8_t progressPercent;
extern unsigned long lastProgressMs;
extern int progressScrollOffset;
extern bool progressScrollDone;
extern String sanitizeProgressName(String msg);

static char _sBuf[320];
static uint16_t _sBufLen = 0;

String jsonEscape(const String& src) {
  String out; out.reserve(src.length() + 8);
  for (uint16_t i = 0; i < src.length(); i++) {
    char c = src[i];
    if (c == '"' || c == '\\') { out += '\\'; out += c; }
    else if (c == '\n' || c == '\r') out += ' ';
    else out += c;
  }
  return out;
}

void processSerialLine(const char* raw) {
  String line(raw); line.trim();
  if (line.length()==0) return;
  _lastSerialCmdMs = millis();
  if (_failsafeActive) checkFailsafeRestore();
  if (!displayOn) {
    displayOn = true;
    applyDisplayOn();
  }
  if ((millis()-bootMs)<BOOT_GRACE_MS) {
    if (!line.startsWith("GET:")&&line!="STATUS?") return;
  }
  if (line.startsWith("VC:")) {
    String name = line.substring(3); name.trim();
    if (name.length() > 0) {
      String safe = sanitizeScrollText(name);
      strncpy(vcJoinName, safe.c_str(), sizeof(vcJoinName) - 1);
      vcJoinName[sizeof(vcJoinName) - 1] = '\0';
      vcJoinUntilMs = millis() + 4000UL;
      renderCurrentScreen();
    }
    Serial.println(F("VC:OK")); return;
  }
  if (line.startsWith("VU:")) {
    String payload=line.substring(3); payload.trim();
    int idx=0; int start=0;
    for (int i=0;i<12&&start<(int)payload.length();i++) {
      int comma=payload.indexOf(',',start);
      String seg=(comma>=0)?payload.substring(start,comma):payload.substring(start);
      seg.trim();
      int v=seg.toInt();
      vuBars[i]=(uint8_t)constrain(v,0,8);
      idx=i;
      if (comma<0) break;
      start=comma+1;
    }
    for (int i=idx+1;i<12;i++) vuBars[i]=0;
    lastVuMs=millis();
    if (featureAudioVizEnabled) renderCurrentScreen();
    return;
  }
  if (line.startsWith("VOL:")) {
    String payload=line.substring(4); payload.trim();
    currentVolume=(uint8_t)constrain(payload.toInt(),0,100);
    lastVolumeMs=millis();
    if (featureVolumeEnabled) renderCurrentScreen();
    return;
  }
  if (line.startsWith("NOTIFY:")) {
    String payload=line.substring(7);
    int sep=payload.indexOf('|');
    String title=(sep>=0)?payload.substring(0,sep):"";
    String msg=(sep>=0)?payload.substring(sep+1):payload;
    title.trim(); msg.trim();
    String display;
    if (title.length()>0&&msg.length()>0) display=title+" - "+msg+" ";
    else if (title.length()>0) display=title+" ";
    else display=msg+" ";
    if (display.length()==0) return;
    notifyScrollOverride=false;
    stickyActive=false;
    if (featureNotificationsEnabled) startNotificationScroll(display);
    return;
  }
  if (line.startsWith("STICKY:")) {
    String payload=line.substring(7); payload.trim();
    if (payload.length()==0 || payload.equalsIgnoreCase("OFF") || payload.equalsIgnoreCase("CLEAR")) {
      stickyActive=false;
      renderCurrentScreen();
      return;
    }
    int sep=payload.indexOf('|');
    String title=(sep>=0)?payload.substring(0,sep):"";
    String msg=(sep>=0)?payload.substring(sep+1):payload;
    title.trim(); msg.trim();
    String display;
    if (title.length()>0&&msg.length()>0) display=title+" - "+msg+" ";
    else if (title.length()>0) display=title+" ";
    else display=msg+" ";
    if (display.length()==0) return;
    notifyScrollUntilMs=0;
    startStickyScroll(display);
    renderCurrentScreen();
    return;
  }
  if (line.startsWith("ALERT:")) {
    String payload=line.substring(6); payload.trim();
    if (payload.length()==0 || payload.equalsIgnoreCase("OFF") || payload.equalsIgnoreCase("CLEAR")) {
      visionFlashActive=false;
      renderCurrentScreen();
      return;
    }
    // ALERT:text or ALERT:text|blink|solid
    int sep=payload.indexOf('|');
    String txt=(sep>=0)?payload.substring(0,sep):payload;
    String mode=(sep>=0)?payload.substring(sep+1):"blink";
    txt.trim(); mode.trim(); mode.toLowerCase();
    txt=sanitizeScrollText(txt);
    if (txt.length()>4) txt=txt.substring(0,4);
    if (txt.length()==0) txt="!!!!";
    visionFlashText=txt;
    visionFlashOffset=max(0,(32-(int)txt.length()*8)/2);
    visionFlashUntilMs=millis()+ALERT_PERSIST_MS;
    visionFlashActive=true;
    alertBlink=!(mode.startsWith("solid"));
    notifyScrollUntilMs=0;
    stickyActive=false;
    bigScrollActive=false;
    renderCurrentScreen();
    return;
  }
  if (line.startsWith("PROG:")) {
    String payload=line.substring(5); payload.trim();
    if (payload.length()==0 || payload.equalsIgnoreCase("OFF") || payload.equalsIgnoreCase("CLEAR")) {
      progressActive=false; lastProgressMs=0; progressName="";
      renderCurrentScreen();
      return;
    }
    int sep=payload.indexOf('|');
    String name=(sep>=0)?payload.substring(0,sep):payload;
    String pct=(sep>=0)?payload.substring(sep+1):"0";
    name.trim(); pct.trim();
    String safe=sanitizeProgressName(name);
    uint8_t pctVal=(uint8_t)constrain(pct.toInt(),0,100);
    if (safe.length()==0) { progressActive=false; renderCurrentScreen(); return; }
    if (progressActive && safe==progressName && pctVal==progressPercent) {
      // Keepalive for the same claim: refresh the auto-hide timer but do
      // NOT restart the name scroll.
      lastProgressMs=millis();
      return;
    }
    progressName=safe;
    progressPercent=pctVal;
    progressScrollOffset=32;
    progressScrollDone=false;
    progressActive=true;
    lastProgressMs=millis();
    renderCurrentScreen();
    return;
  }
  if (line.startsWith("VISION:")) {
    // Legacy alias for emphasis notify (8x8 big scroll).
    String payload=line.substring(7);
    int sep=payload.indexOf('|');
    String title=(sep>=0)?payload.substring(0,sep):"";
    String msg=(sep>=0)?payload.substring(sep+1):payload;
    title.trim(); msg.trim();
    String display;
    if (title.length()>0&&msg.length()>0) display=title+" - "+msg+" ";
    else if (title.length()>0) display=title+" ";
    else display=msg+" ";
    if (display.length()==0) return;
    notifyScrollUntilMs=0;
    stickyActive=false;
    startBigScroll(display);
    renderCurrentScreen();
    return;
  }
  if (line.startsWith("VISIONFLASH:")) {
    // Legacy alias for ALERT:text|blink
    String payload=line.substring(12); payload.trim();
    if (payload.length()==0 || payload.equalsIgnoreCase("OFF")) {
      visionFlashActive=false;
      renderCurrentScreen();
      return;
    }
    String txt=sanitizeScrollText(payload);
    if (txt.length()>4) txt=txt.substring(0,4);
    if (txt.length()==0) txt="!!!!";
    visionFlashText=txt;
    visionFlashOffset=max(0,(32-(int)txt.length()*8)/2);
    visionFlashUntilMs=millis()+ALERT_PERSIST_MS;
    visionFlashActive=true;
    alertBlink=true;
    notifyScrollUntilMs=0;
    stickyActive=false;
    renderCurrentScreen();
    return;
  }
  if (line.startsWith("STATS:")) {
    String p=line.substring(6);
    int s1=p.indexOf('|'), s2=s1>=0?p.indexOf('|',s1+1):-1, s3=s2>=0?p.indexOf('|',s2+1):-1;
    String sTemp=(s1>=0&&s2>=0)?p.substring(s1+1,s2):"";
    String sGpu=(s2>=0&&s3>=0)?p.substring(s2+1,s3):"";
    String sFps=s3>=0?p.substring(s3+1):(s2>=0?p.substring(s2+1):"");
    sTemp.trim(); sGpu.trim(); sFps.trim();
    bool wasActive=pcOverlayActive();
    if (sTemp.length()>0) lastCpuTemp=(sTemp!="-")?sTemp.toFloat():-1.0f;
    if (sGpu.length()>0) lastGpuTemp=(sGpu!="-")?sGpu.toFloat():-1.0f;
    if (sFps.length()>0) lastFps=(sFps!="-")?sFps.toFloat():-1.0f;
    lastPcStatsMs=millis();
    if (pcOverlayActive()||wasActive) renderCurrentScreen();
    return;
  }
  if (line.startsWith("SET:")) {
    String kv=line.substring(4);
    int eq=kv.indexOf('=');
    if (eq<0) { Serial.println(F("SET:ERR:no_equals")); return; }
    String key=kv.substring(0,eq);
    String val=kv.substring(eq+1);
    key.trim(); val.trim();
    bool bval=(val=="1"||val.equalsIgnoreCase("true")||val.equalsIgnoreCase("on"));
    if (key=="utc_offset") { utcOffsetSecs=(int32_t)val.toInt(); if (timeReady) tickClock(); Serial.println("SET:OK:utc_offset"); return; }
    if (key=="time") {
      uint32_t epoch=(uint32_t)strtoul(val.c_str(),nullptr,10);
      if (epoch>946684800UL) {
        bool wasReady=timeReady;
        _syncEpoch=epoch; _syncMillis=millis(); timeReady=true;
        tickClock();
        if (!wasReady) {
          String g=""; int h=currentHours24;
          if (h>=5&&h<12) g="MORNING"; else if (h>=12&&h<18) g="AFTERNOON"; else g="EVENING";
          String name=userName; name.trim(); name.toUpperCase();
          if (name.length()>0) g=g+" "+name;
          extern String greetingMessage; extern int greetingOffset; extern bool greetingActive;
          greetingMessage=sanitizeScrollText(g); greetingOffset=32; greetingActive=true;
        }
        renderCurrentScreen();
      }
      Serial.println("SET:OK:time"); return;
    }
    if (key=="pc_disp") { pcDispFlags=(uint8_t)val.toInt(); renderCurrentScreen(); Serial.println("SET:OK:pc_disp"); return; }
    if (key=="temp_alert") { tempAlertEnabled=bval; extern bool tempFlashState; tempFlashState=true; renderCurrentScreen(); Serial.println("SET:OK:temp_alert"); return; }
    if (key=="cpu_temp_lim"){ cpuTempLim=val.toInt(); Serial.println("SET:OK:cpu_temp_lim"); return; }
    if (key=="gpu_temp_lim"){ gpuTempLim=val.toInt(); Serial.println("SET:OK:gpu_temp_lim"); return; }
    if (key=="stopwatch") {
      if (val=="done") { swDisplay[0]='\0'; swDoneActive=true; swDoneUntilMs=millis()+4000; startEyeAppearance(); }
      else if (val.length()>=2&&(val[0]=='s'||val[0]=='c')&&val[1]==':') { swDoneActive=false; swCountdown=(val[0]=='c'); String disp=val.substring(2); strncpy(swDisplay,disp.c_str(),sizeof(swDisplay)-1); swDisplay[sizeof(swDisplay)-1]='\0'; extern unsigned long lastSwMs; lastSwMs=millis(); }
      else { swDisplay[0]='\0'; swDoneActive=false; }
      renderCurrentScreen(); Serial.println("SET:OK:stopwatch"); return;
    }
    if (key=="alarm_snooze") { snoozeAlarm(); Serial.println("SET:OK:alarm_snooze"); return; }
    if (key=="alarm_dismiss") { dismissAlarmToday(); Serial.println("SET:OK:alarm_dismiss"); return; }
    if (key=="alarm_clear_dismiss") { extern int alarmDismissedDay; alarmDismissedDay=-1; alarmSnoozedUntilEpoch=0; Serial.println("SET:OK:alarm_clear_dismiss"); return; }
    if (key=="feature_time") featureTimeEnabled=bval;
    else if (key=="feature_date") featureDateEnabled=bval;
    else if (key=="feature_minute_bar") { featureMinuteBarEnabled=bval; if (!bval) { minuteBarSettled=0; pipPhase=0; } }
    else if (key=="feature_eyes") featureEyesEnabled=bval;
    else if (key=="feature_notifications") featureNotificationsEnabled=bval;
    else if (key=="feature_large_clock") { featureLargeClockEnabled=bval; if(bval) featureDayClockEnabled=false; }
    else if (key=="feature_day_clock") { featureDayClockEnabled=bval; if(bval) featureLargeClockEnabled=false; }
    else if (key=="feature_audio_viz") { featureAudioVizEnabled=bval; if(!bval) lastVuMs=0; }
    // (volume feature removed)
    else if (key=="display_on") { displayOn=bval; applyDisplayOn(); }
    else if (key=="brightness") { int b=val.toInt(); if(b>=0&&b<BRIGHTNESS_LEVELS){brightnessIndex=(uint8_t)b; setBrightnessLevelFromIndex();} }
    else if (key=="alarm_enabled") alarmEnabled=bval;
    else if (key=="alarm_hour") { int h=val.toInt(); if(h>=0&&h<=23){alarmHour=h; alarmDismissedDay=-1; alarmSnoozedUntilEpoch=0;} }
    else if (key=="alarm_minute") { int m=val.toInt(); if(m>=0&&m<=59){alarmMinute=m; alarmDismissedDay=-1; alarmSnoozedUntilEpoch=0;} }
    else if (key=="alarm_days") { int d=val.toInt(); if(d>=0&&d<=127){alarmDays=(uint8_t)d; alarmDismissedDay=-1; alarmSnoozedUntilEpoch=0;} }
    else if (key=="alarm_show_eyes") alarmShowEyes=bval;
    else if (key=="alarm_message") alarmMessageText=val;
    else if (key=="alarm_snooze_mins") { int m=val.toInt(); if(m>0) alarmSnoozeMins=m; }
    else if (key=="user_name") userName=val;
    else if (key=="night_mode_enabled") { nightModeEnabled=bval; updateNightMode(); setBrightnessLevelFromIndex(); }
    else if (key=="night_lat"||key=="night_lon") {}
    else if (key=="mqtt_host"||key=="mqtt_port"||key=="mqtt_user"||key=="mqtt_pass"||key=="mqtt_client_id") { Serial.println("SET:OK:"+key); return; }
    else { Serial.println("SET:ERR:unknown_key:"+key); return; }
    saveLiveSettings();
    renderCurrentScreen();
    Serial.println("SET:OK:"+key);
    return;
  }
  if (line=="GET:config") {
    String j; j.reserve(768); j="{";
    j+="\"device\":\"d1mini\",";
    j+="\"brightness\":"+String((int)brightnessIndex)+",";
    j+="\"display_on\":"+String(displayOn?"1":"0")+",";
    j+="\"feature_time\":"+String(featureTimeEnabled?"1":"0")+",";
    j+="\"feature_date\":"+String(featureDateEnabled?"1":"0")+",";
    j+="\"feature_minute_bar\":"+String(featureMinuteBarEnabled?"1":"0")+",";
    j+="\"feature_eyes\":"+String(featureEyesEnabled?"1":"0")+",";
    j+="\"feature_notifications\":"+String(featureNotificationsEnabled?"1":"0")+",";
    j+="\"feature_large_clock\":"+String(featureLargeClockEnabled?"1":"0")+",";
    j+="\"feature_day_clock\":"+String(featureDayClockEnabled?"1":"0")+",";
    j+="\"feature_audio_viz\":"+String(featureAudioVizEnabled?"1":"0")+",";
    // (volume feature removed)
    j+="\"alarm_enabled\":"+String(alarmEnabled?"1":"0")+",";
    j+="\"alarm_hour\":"+String(alarmHour)+",";
    j+="\"alarm_minute\":"+String(alarmMinute)+",";
    j+="\"alarm_days\":"+String((int)alarmDays)+",";
    j+="\"alarm_show_eyes\":"+String(alarmShowEyes?"1":"0")+",";
    j+="\"alarm_message\":\""+jsonEscape(alarmMessageText)+"\",";
    j+="\"user_name\":\""+jsonEscape(userName)+"\",";

    j+="\"wifi\":0,\"ip\":\"\",\"portal\":0,\"mqtt_connected\":0,\"wifi_connected\":0";
    j+="}";
    Serial.println("CONFIG:"+j);
    return;
  }
  if (line=="IDENT?") {
    Serial.print(F("IDENT:d1mini_max7219_"));
    Serial.println(MAX_DEVICES);
    return;
  }
  if (line=="STATUS?") { Serial.println(F("STATUS:device=d1mini,wifi=0,portal=0")); return; }
  if (line=="RESET_FACTORY"||line=="RESET") {
    Serial.println(F("STATUS:OK:restarting")); Serial.flush(); delay(200); ESP.restart(); return;
  }
}

void handleSerial() {
  while (Serial.available()) {
    char c=(char)Serial.read();
    if (c=='\n'||c=='\r') {
      if (_sBufLen>0) { _sBuf[_sBufLen]='\0'; processSerialLine(_sBuf); _sBufLen=0; }
    } else if (_sBufLen<(uint16_t)(sizeof(_sBuf)-1)) { _sBuf[_sBufLen++]=c; }
    else { _sBufLen=0; }
  }
}

#endif
