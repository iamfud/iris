// Drawing primitives and screen rendering
#ifndef IRIS_RENDERER_H
#define IRIS_RENDERER_H
#include "fonts.h"

extern MD_MAX72XX mx;

extern uint32_t _syncEpoch;
extern unsigned long _syncMillis;
extern char currentDayText[4];
extern String notifyScrollMessage;
extern int notifyScrollOffset;
extern bool notifyScrollStatic;
extern bool alarmShowEyes;
extern String alarmMessageText;
extern int alarmSnoozeMins;
extern uint32_t alarmSnoozedUntilEpoch;
extern bool accFlashOn;
extern uint8_t accessoryOverlayMode;
extern char swDisplay[12];
extern bool swCountdown;
extern float lastCpuTemp, lastGpuTemp, lastFps;
extern uint8_t pcDispFlags;
extern unsigned long lastPcStatsMs;
extern bool tempAlertEnabled;
extern int cpuTempLim, gpuTempLim;
extern bool tempFlashState;
extern bool featureMinuteBarEnabled;
extern int8_t barStartX, barY, barWidth;
extern int16_t barLaunchX, pipAnimX;
extern uint8_t minuteBarSettled, minuteBarTarget, pipPhase;
extern unsigned long lastPipFrameMs;

extern bool _failsafeActive;
extern uint16_t _litPixelCount;

inline void beginFrame() { mx.control(MD_MAX72XX::UPDATE, MD_MAX72XX::OFF); }
inline void endFrame()   {
  mx.control(MD_MAX72XX::UPDATE, MD_MAX72XX::ON);
  uint16_t px = 0; uint8_t buf[MAX_DEVICES * 8];
  mx.getBuffer(0, MAX_DEVICES * 8, buf);
  for (int i = 0; i < MAX_DEVICES * 8; i++) { uint8_t v = buf[i]; while (v) { px += v & 1; v >>= 1; } }
  if (px > 160) { Serial.print("FB_HOT:"); Serial.println(px); }
  mx.update();
}
inline void clearDisplay() { mx.clear(); }

inline void drawPixel(int x, int y, bool on) {
  if (x < 0 || x >= 32 || y < 0 || y > 7) return;
  mx.setPoint(y, 31 - x, on);
}

inline void drawFilledRect(int x,int y,int w,int h,bool on=true) {
  for (int yy=y;yy<y+h;yy++) for (int xx=x;xx<x+w;xx++) drawPixel(xx,yy,on);
}

inline void drawBitmap3x5(int x, int y, const uint8_t* g) {
  for (int r=0;r<5;r++) for (int c=0;c<3;c++) drawPixel(x+c, y+r, (g[r]>>(2-c))&1);
}
inline void drawBitmap3x6(int x, int y, const uint8_t* g) {
  for (int r=0;r<6;r++) for (int c=0;c<3;c++) drawPixel(x+c, y+r, (g[r]>>(2-c))&1);
}
inline void drawBitmap3x7(int x, int y, const uint8_t* g) {
  for (int r=0;r<7;r++) for (int c=0;c<3;c++) drawPixel(x+c, y+r, (g[r]>>(2-c))&1);
}
inline void drawBitmap3x8(int x, int y, const uint8_t* g) {
  for (int r=0;r<8;r++) for (int c=0;c<3;c++) drawPixel(x+c, y+r, (g[r]>>(2-c))&1);
}
inline void drawBitmap5x8(int x, int y, const uint8_t* g) {
  for (int col=0;col<5;col++)
    for (int row=0;row<8;row++)
      drawPixel(x+col, y+row, (g[row]>>(4-col))&1);
}
inline void drawBitmap8x8(int x, int y, const uint8_t* g) {
  for (int col=0;col<8;col++)
    for (int row=0;row<8;row++)
      drawPixel(x+col, y+row, (g[row]>>(7-col))&1);
}
inline void drawDigit3x5(int x, int y, int d) {
  if (d<0||d>9) return;
  drawBitmap3x5(x, y, DIGITS[d]);
}
inline void drawClockDigit5x7(int x, int y, int d) {
  const uint8_t* g = clockDigit5x7(d);
  for (int r=0;r<7;r++) for (int c=0;c<5;c++) drawPixel(x+c, y+r, (g[r]>>(4-c))&1);
}
inline void drawColon(int x, int y, bool on) {
  if (!on) return;
  drawPixel(x, y+1, true); drawPixel(x, y+3, true);
}
inline void drawColon5x7(int x, int y, bool on) {
  drawPixel(x, y+2, on); drawPixel(x, y+4, on);
}

void drawScrollText5x7(const String& text, int offsetX) {
  clearDisplay();
  int cx=offsetX;
  for (size_t i=0;i<text.length();i++) { drawBitmap5x8(cx, 0, scrollGlyph(text.charAt(i))); cx+=6; }
}

void drawDayDate(int dateNum, int month) {
  clearDisplay();
  const char* months[]={"JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"};
  const char* mon=months[month>=0&&month<=11?month:0];
  drawClockDigit5x7(0, 0, dateNum/10);
  drawClockDigit5x7(6, 0, dateNum%10);
  drawBitmap5x8(14, 0, scrollGlyph(mon[0]));
  drawBitmap5x8(20, 0, scrollGlyph(mon[1]));
  drawBitmap5x8(26, 0, scrollGlyph(mon[2]));
}

void drawTimeHHMM_Large(int hh, int mm, bool showColon) {
  clearDisplay();
  drawClockDigit5x7( 3, 0, hh/10); drawClockDigit5x7( 9, 0, hh%10);
  drawColon5x7(15, 0, showColon);
  drawClockDigit5x7(18, 0, mm/10); drawClockDigit5x7(24, 0, mm%10);
}

const unsigned long PIP_SLIDE_MS  = 22;
const unsigned long PIP_BOUNCE_MS = 55;

void setBarGeometry(int sx, int y, int w) {
  if (barStartX!=sx||barY!=y||barWidth!=w) {
    barStartX=(int8_t)sx; barY=(int8_t)y; barWidth=(int8_t)w;
    barLaunchX=sx+w; minuteBarSettled=0; minuteBarTarget=0; pipPhase=0;
  }
}
void updateMinuteBarTarget(int s) {
  minuteBarTarget=(uint8_t)map(s,0,59,0,barWidth);
}
bool tickMinuteBar() {
  unsigned long now=millis(); bool changed=false;
  if (minuteBarTarget<minuteBarSettled) { minuteBarSettled=minuteBarTarget; pipPhase=0; changed=true; }
  if (pipPhase==0&&minuteBarSettled<minuteBarTarget) { pipAnimX=barLaunchX; pipPhase=1; lastPipFrameMs=now; changed=true; }
  if (pipPhase==1) {
    if (now-lastPipFrameMs>=PIP_SLIDE_MS) {
      lastPipFrameMs=now; pipAnimX--;
      int dest=barStartX+(int)minuteBarSettled;
      if (pipAnimX<=dest) { pipAnimX=dest-1; pipPhase=2; lastPipFrameMs=now; }
      changed=true;
    }
  } else if (pipPhase==2) {
    if (now-lastPipFrameMs>=PIP_BOUNCE_MS) { minuteBarSettled++; pipPhase=0; changed=true; }
  }
  return changed;
}
void drawMinuteLine(int s) {
  setBarGeometry(7,7,18); updateMinuteBarTarget(s);
  for (int i=0;i<(int)minuteBarSettled&&i<barWidth;i++) drawPixel(barStartX+i,barY,true);
  if (pipPhase>0&&pipAnimX>=barStartX&&pipAnimX<32) drawPixel(pipAnimX,barY,true);
}

void drawSnoozeLine() {
  if (alarmSnoozedUntilEpoch==0) return;
  uint32_t now=(uint32_t)(_syncEpoch+(millis()-_syncMillis)/1000UL);
  if (now>=alarmSnoozedUntilEpoch) return;
  long remaining=(long)(alarmSnoozedUntilEpoch-now);
  long total=(long)(alarmSnoozeMins*60L);
  int barPx=(int)map(remaining,0,total,0,18);
  for (int i=0;i<18;i++) drawPixel(7+i,7,i<barPx);
}

extern uint8_t vuBars[12];

void drawTimeWithViz(int hh,int mm,bool showColon) {
  clearDisplay();
  for (int b=0;b<12;b++) {
    int h=vuBars[b]; if (h>8) h=8;
    for (int r=0;r<h;r++) drawPixel(b,7-r,true);
  }
  drawBitmap3x8(15,0,tc8Digit(hh/10)); drawBitmap3x8(19,0,tc8Digit(hh%10));
  if (showColon) { drawPixel(23,2,true); drawPixel(23,5,true); }
  drawBitmap3x8(25,0,tc8Digit(mm/10)); drawBitmap3x8(29,0,tc8Digit(mm%10));
}

void drawTimeHHMM(int hh,int mm,bool showColon,int s) {
  clearDisplay(); int y=1;
  drawDigit3x5(7,y,hh/10); drawDigit3x5(11,y,hh%10);
  drawColon(15,y,showColon);
  drawDigit3x5(18,y,mm/10); drawDigit3x5(22,y,mm%10);
  if (featureMinuteBarEnabled) {
    if (alarmSnoozedUntilEpoch==0) drawMinuteLine(s);
    else drawSnoozeLine();
  } else if (alarmSnoozedUntilEpoch>0) {
    drawSnoozeLine();
  }
}

void drawDayClock(int hh,int mm,bool showColon,int s) {
  clearDisplay();
  if (featureMinuteBarEnabled) {
    setBarGeometry(0,0,11); updateMinuteBarTarget(s);
    for (int i=0;i<(int)minuteBarSettled&&i<barWidth;i++) drawPixel(barStartX+i,barY,true);
    if (pipPhase>0&&pipAnimX>=0&&pipAnimX<32) drawPixel(pipAnimX,0,true);
  }
  drawBitmap3x6(0,2,tc6Letter(currentDayText[0]));
  drawBitmap3x6(4,2,tc6Letter(currentDayText[1]));
  drawBitmap3x6(8,2,tc6Letter(currentDayText[2]));
  drawBitmap3x8(15,0,tc8Digit(hh/10)); drawBitmap3x8(19,0,tc8Digit(hh%10));
  if (showColon) { drawPixel(23,2,true); drawPixel(23,5,true); }
  drawBitmap3x8(25,0,tc8Digit(mm/10)); drawBitmap3x8(29,0,tc8Digit(mm%10));
}



void drawAccessoryOverlay() {
  clearDisplay(); if (!accFlashOn) return;
  const char* label=(accessoryOverlayMode==1)?"ACC ONE":"ACC TWO";
  for (int i=0;i<7;i++) drawBitmap3x6(2+i*4, 1, tc6Letter(label[i]));
}

void drawStopwatchScreen() {
  if (strlen(swDisplay)<5) return;
  clearDisplay();
  int d0=constrain(swDisplay[0]-'0',0,9), d1=constrain(swDisplay[1]-'0',0,9);
  int d2=constrain(swDisplay[3]-'0',0,9), d3=constrain(swDisplay[4]-'0',0,9);
  drawDigit3x5(7, 1,d0); drawDigit3x5(11,1,d1);
  drawColon(15,1,true);
  drawDigit3x5(18,1,d2); drawDigit3x5(22,1,d3);
  if (swCountdown&&!(strlen(swDisplay)==8&&swDisplay[5]==':')) {
    int mm=d0*10+d1, ss=d2*10+d3;
    if (mm==0&&ss<=10) { int px=ss*3; for (int x=1;x<31;x++) drawPixel(x,7,x<=px); }
  }
}

void drawHot(int x0) {
  for (int r=0;r<8;r++) for (int c=x0;c<x0+16;c++) drawPixel(c,r,false);
  const uint8_t* letters[3]={H_GLYPH,O_GLYPH,T_GLYPH};
  for (int li=0;li<3;li++) {
    int lx=x0+1+li*4;
    for (int r=0;r<6;r++) for (int b=0;b<3;b++) drawPixel(lx+b,1+r,(letters[li][r]>>(2-b))&1);
  }
  for (int r=1;r<=4;r++) drawPixel(x0+13,r,true);
  drawPixel(x0+13,6,true);
}

bool pcOverlayActive() {
  return pcDispFlags!=0 && lastPcStatsMs>0 && (millis()-lastPcStatsMs)<15000;
}

void drawIntTC8Centered(int zoneX, int zoneW, int val) {
  int d=(val>=100)?3:(val>=10)?2:1;
  int totalW=d*4-1;
  int x=zoneX+max(0,(zoneW-totalW)/2);
  if (d==3) { drawBitmap3x8(x,0,tc8Digit(val/100));       x+=4; }
  if (d>=2) { drawBitmap3x8(x,0,tc8Digit((val/10)%10));   x+=4; }
             drawBitmap3x8(x,0,tc8Digit(val%10));
}

void drawPcOverlay() {
  bool showCt=(pcDispFlags&1)&&lastCpuTemp>=0;
  bool showGt=(pcDispFlags&2)&&lastGpuTemp>=0;
  bool showFp=(pcDispFlags&4)&&lastFps>=0;
  int count=(showCt?1:0)+(showGt?1:0)+(showFp?1:0);
  if (count==0) return;
  bool cpuAlert=tempAlertEnabled&&showCt&&lastCpuTemp>=(float)cpuTempLim;
  bool gpuAlert=tempAlertEnabled&&showGt&&lastGpuTemp>=(float)gpuTempLim;
  bool showCpuDigs=!cpuAlert||tempFlashState;
  bool showGpuDigs=!gpuAlert||tempFlashState;
  int vals[3]; int n=0;
  if (showCt) vals[n++]=max(0,(int)lastCpuTemp);
  if (showGt) vals[n++]=max(0,(int)lastGpuTemp);
  if (showFp) vals[n++]=max(0,(int)lastFps);
  if (count==1) {
    if (showFp) { drawIntTC8Centered(0,32,vals[0]); }
    else if (showGt) {
      if (showGpuDigs) drawIntTC8Centered(0,14,vals[0]);
      drawBitmap3x5(16,0,LETTER_G); drawBitmap3x5(20,0,OV_P); drawBitmap3x5(24,0,LETTER_U);
    } else {
      if (showCpuDigs) drawIntTC8Centered(0,14,vals[0]);
      drawBitmap3x5(16,0,LETTER_C); drawBitmap3x5(20,0,OV_P); drawBitmap3x5(24,0,LETTER_U);
    }
  } else if (count==2) {
    if (showCt&&showGt) {
      for (int row=0;row<8;row++) for (int col=0;col<32;col++) drawPixel(col,row,(PCSTATS_TEMPS_FRAME[row]>>(31-col))&1);
      int gt=max(0,(int)lastGpuTemp), ct=max(0,(int)lastCpuTemp);
      if (showGpuDigs) { drawBitmap3x8(0,0,gt>=100?tc8Digit(gt/100):TC8_BLANK); drawBitmap3x8(4,0,gt>=10?tc8Digit((gt/10)%10):TC8_BLANK); drawBitmap3x8(8,0,tc8Digit(gt%10)); }
      if (showCpuDigs) { drawBitmap3x8(17,0,ct>=100?tc8Digit(ct/100):TC8_BLANK); drawBitmap3x8(21,0,ct>=10?tc8Digit((ct/10)%10):TC8_BLANK); drawBitmap3x8(25,0,tc8Digit(ct%10)); }
    } else {
      const uint32_t* frame=showGt?PCSTATS_TEMP_FPS_G_FRAME:PCSTATS_TEMP_FPS_C_FRAME;
      for (int row=0;row<8;row++) for (int col=0;col<32;col++) drawPixel(col,row,(frame[row]>>(31-col))&1);
      int temp=vals[0], fps=vals[1];
      bool showTD=showGt?showGpuDigs:showCpuDigs;
      if (showTD) { drawBitmap3x8(1,0,temp>=100?tc8Digit(temp/100):TC8_BLANK); drawBitmap3x8(5,0,temp>=10?tc8Digit((temp/10)%10):TC8_BLANK); drawBitmap3x8(9,0,tc8Digit(temp%10)); }
      drawBitmap3x8(18,0,fps>=100?tc8Digit(fps/100):TC8_BLANK); drawBitmap3x8(22,0,fps>=10?tc8Digit((fps/10)%10):TC8_BLANK); drawBitmap3x8(26,0,tc8Digit(fps%10));
    }
  } else {
    for (int row=0;row<8;row++) for (int col=0;col<32;col++) drawPixel(col,row,(PCSTATS3_FRAME[row]>>(31-col))&1);
    if (showCpuDigs) { int v=vals[0],d=(v>=100)?3:(v>=10)?2:1,tw=d*4-1,x=max(0,(7-tw)/2); if(d==3){drawDigit3x5(x,0,v/100);x+=4;} if(d>=2){drawDigit3x5(x,0,(v/10)%10);x+=4;} drawDigit3x5(x,0,v%10); }
    if (showGpuDigs) { drawDigit3x5(12,3,(vals[1]/10)%10); drawDigit3x5(16,3,vals[1]%10); } else { drawBitmap3x5(12,3,GLYPH_SPACE); drawBitmap3x5(16,3,GLYPH_SPACE); }
    { int fps=vals[2]; if(fps>=100){drawBitmap3x7(21,1,tc7Digit(fps/100));drawBitmap3x7(25,1,tc7Digit((fps/10)%10));drawBitmap3x7(29,1,tc7Digit(fps%10));} else{drawBitmap3x7(21,1,TC7_BLANK);drawBitmap3x7(25,1,tc7Digit(fps/10));drawBitmap3x7(29,1,tc7Digit(fps%10));} }
  }
}

void drawRoundEye8x8(int ox,int pox,int poy,uint8_t lt,uint8_t lb);

#endif
