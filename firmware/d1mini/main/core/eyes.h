// Eye engine state machine and drawing
#ifndef IRIS_EYES_H
#define IRIS_EYES_H
#include "renderer.h"

enum EyeExpression : uint8_t {
  EYE_EXPR_NEUTRAL = 0, EYE_EXPR_WIDE, EYE_EXPR_SLEEPY,
  EYE_EXPR_SQUINT,      EYE_EXPR_ANGRY, EYE_EXPR_CURIOUS
};
enum EyeBlinkPhase : uint8_t {
  EYE_BLINK_IDLE = 0, EYE_BLINK_CLOSING, EYE_BLINK_HOLD, EYE_BLINK_OPENING
};

struct EyeState {
  bool active = false;
  EyeExpression expr = EYE_EXPR_NEUTRAL;
  EyeBlinkPhase blinkPhase = EYE_BLINK_IDLE;
  uint32_t nextAppearMs = 0, visibleUntilMs = 0, nextBlinkMs = 0;
  uint32_t blinkPhaseMs = 0, nextMoveMs = 0, lastFrameMs = 0, attentionUntilMs = 0;
  int targetX = 0, targetY = EYE_DEFAULT_Y, currentX = 0, currentY = EYE_DEFAULT_Y;
  uint8_t eyelidTop = 0, eyelidBottom = 0;
  bool doubleBlink = false; uint8_t blinkCount = 0;
};

extern EyeState eyeState;
extern bool featureEyesEnabled, timeReady;
extern bool forceEyes, alarmActive, nightModeActive;

uint32_t randRange32(uint32_t a, uint32_t b) {
  if (b<=a) return a;
  return a+(uint32_t)random((long)(b-a+1));
}
void scheduleNextEyeAppearance() { eyeState.nextAppearMs=millis()+randRange32(EYE_IDLE_MIN_MS,EYE_IDLE_MAX_MS); }
void scheduleNextBlink() { eyeState.nextBlinkMs=millis()+randRange32(EYE_BLINK_MIN_MS,EYE_BLINK_MAX_MS); }

void chooseEyeExpression() {
  if (alarmActive) { eyeState.expr=EYE_EXPR_WIDE; return; }
  if (eyeState.attentionUntilMs>millis()) {
    uint8_t r=random(100);
    if (r<55) eyeState.expr=EYE_EXPR_CURIOUS;
    else if (r<80) eyeState.expr=EYE_EXPR_WIDE;
    else eyeState.expr=EYE_EXPR_NEUTRAL;
    return;
  }
  uint8_t r=random(100);
  if (r<40) eyeState.expr=EYE_EXPR_NEUTRAL;
  else if (r<58) eyeState.expr=EYE_EXPR_CURIOUS;
  else if (r<72) eyeState.expr=EYE_EXPR_SLEEPY;
  else if (r<84) eyeState.expr=EYE_EXPR_SQUINT;
  else if (r<92) eyeState.expr=EYE_EXPR_WIDE;
  else eyeState.expr=EYE_EXPR_ANGRY;
}

void chooseEyeTarget() {
  if (alarmActive) { eyeState.targetX=0; eyeState.targetY=3; eyeState.nextMoveMs=millis()+180; return; }
  if (eyeState.attentionUntilMs>millis()) {
    eyeState.targetX=random(-1,2); eyeState.targetY=random(2,4);
    eyeState.nextMoveMs=millis()+randRange32(180,500); return;
  }
  eyeState.targetX=random(-2,3); eyeState.targetY=random(2,5);
  eyeState.nextMoveMs=millis()+randRange32(EYE_MOVE_INTERVAL_MIN,EYE_MOVE_INTERVAL_MAX);
}

void startEyeAppearance() {
  eyeState.active=true;
  eyeState.visibleUntilMs=millis()+randRange32(EYE_VISIBLE_MIN_MS,EYE_VISIBLE_MAX_MS);
  eyeState.currentX=0; eyeState.currentY=EYE_DEFAULT_Y;
  eyeState.targetX=0; eyeState.targetY=EYE_DEFAULT_Y;
  eyeState.eyelidTop=0; eyeState.eyelidBottom=0;
  eyeState.blinkPhase=EYE_BLINK_IDLE; eyeState.blinkCount=0;
  eyeState.doubleBlink=(random(100)<18);
  chooseEyeExpression(); chooseEyeTarget(); scheduleNextBlink();
}

void wakeEyes() {
  eyeState.active=true; eyeState.attentionUntilMs=millis()+EYE_ATTENTION_MS;
  eyeState.visibleUntilMs=millis()+randRange32(EYE_WAKE_MIN_MS,EYE_WAKE_MAX_MS);
  if (eyeState.currentY<1||eyeState.currentY>5) eyeState.currentY=EYE_DEFAULT_Y;
  if (eyeState.currentX<-2||eyeState.currentX>2) eyeState.currentX=0;
  eyeState.blinkPhase=EYE_BLINK_IDLE; eyeState.blinkCount=0; eyeState.doubleBlink=true;
  chooseEyeExpression(); chooseEyeTarget();
  eyeState.nextBlinkMs=millis()+randRange32(200,900);
}

void stopEyeAppearance() {
  eyeState.active=false; eyeState.blinkPhase=EYE_BLINK_IDLE;
  eyeState.eyelidTop=0; eyeState.eyelidBottom=0;
  scheduleNextEyeAppearance();
}

void initEyeEngine() {
  randomSeed(analogRead(A0) ^ (ESP.getCycleCount() & 0xFFFF));
  eyeState.lastFrameMs=0; eyeState.attentionUntilMs=0;
  scheduleNextEyeAppearance();
}

void startBlink() { eyeState.blinkPhase=EYE_BLINK_CLOSING; eyeState.blinkPhaseMs=millis(); }

void updateBlinkAnimation() {
  uint32_t now=millis();
  switch (eyeState.blinkPhase) {
    case EYE_BLINK_IDLE: eyeState.eyelidTop=0; eyeState.eyelidBottom=0; break;
    case EYE_BLINK_CLOSING: {
      uint32_t dt=now-eyeState.blinkPhaseMs;
      uint8_t amt=(dt>=EYE_BLINK_CLOSE_MS)?3:(uint8_t)((dt*3)/EYE_BLINK_CLOSE_MS);
      eyeState.eyelidTop=eyeState.eyelidBottom=amt;
      if (dt>=EYE_BLINK_CLOSE_MS) { eyeState.eyelidTop=eyeState.eyelidBottom=3; eyeState.blinkPhase=EYE_BLINK_HOLD; eyeState.blinkPhaseMs=now; }
      break;
    }
    case EYE_BLINK_HOLD:
      eyeState.eyelidTop=eyeState.eyelidBottom=3;
      if (now-eyeState.blinkPhaseMs>=EYE_BLINK_HOLD_MS) { eyeState.blinkPhase=EYE_BLINK_OPENING; eyeState.blinkPhaseMs=now; }
      break;
    case EYE_BLINK_OPENING: {
      uint32_t dt=now-eyeState.blinkPhaseMs;
      uint8_t amt=(dt>=EYE_BLINK_OPEN_MS)?0:(uint8_t)(3-((dt*3)/EYE_BLINK_OPEN_MS));
      eyeState.eyelidTop=eyeState.eyelidBottom=amt;
      if (dt>=EYE_BLINK_OPEN_MS) {
        eyeState.eyelidTop=eyeState.eyelidBottom=0; eyeState.blinkPhase=EYE_BLINK_IDLE; eyeState.blinkCount++;
        if (eyeState.doubleBlink&&eyeState.blinkCount==1) eyeState.nextBlinkMs=millis()+120;
        else { eyeState.doubleBlink=(random(100)<15); eyeState.blinkCount=0; scheduleNextBlink(); }
      }
      break;
    }
  }
}

void updateEyeMotion() {
  uint32_t now=millis();
  if (now>=eyeState.nextMoveMs) { chooseEyeExpression(); chooseEyeTarget(); }
  eyeState.currentX+=(eyeState.targetX-eyeState.currentX)/EYE_SMOOTH_DIV_X;
  eyeState.currentY+=(eyeState.targetY-eyeState.currentY)/EYE_SMOOTH_DIV_Y;
  if (abs(eyeState.targetX-eyeState.currentX)<=1) eyeState.currentX=eyeState.targetX;
  if (abs(eyeState.targetY-eyeState.currentY)<=1) eyeState.currentY=eyeState.targetY;
}

void applyExpressionLids() {
  uint8_t top=0,bottom=0;
  if (!alarmActive) {
    switch (eyeState.expr) {
      case EYE_EXPR_SLEEPY: top=1; break;
      case EYE_EXPR_SQUINT: top=1; bottom=1; break;
      case EYE_EXPR_ANGRY:  top=1; break;
      default: break;
    }
  }
  if (eyeState.eyelidTop<top) eyeState.eyelidTop=top;
  if (eyeState.eyelidBottom<bottom) eyeState.eyelidBottom=bottom;
}

void updateEyeEngine();

void drawRoundEye8x8(int ox,int pox,int poy,uint8_t lt,uint8_t lb) {
  for (int y=0;y<8;y++) {
    for (int x=0;x<8;x++) {
      bool on=false;
      if ((y==0||y==7)&&(x>=2&&x<=5)) on=true;
      else if ((y==1||y==6)&&(x>=1&&x<=6)) on=true;
      else if (y>=2&&y<=5) on=true;
      drawPixel(ox+x,y,on);
    }
  }
  drawPixel(ox+0,0,false); drawPixel(ox+1,0,false);
  drawPixel(ox+6,0,false); drawPixel(ox+7,0,false);
  drawPixel(ox+0,7,false); drawPixel(ox+1,7,false);
  drawPixel(ox+6,7,false); drawPixel(ox+7,7,false);
  for (uint8_t i=0;i<lt&&i<8;i++) drawFilledRect(ox,i,8,1,false);
  for (uint8_t i=0;i<lb&&i<8;i++) drawFilledRect(ox,7-i,8,1,false);
  int px=ox+3+pox, py=3+poy;
  if (px<ox+1) px=ox+1; if (px>ox+5) px=ox+5;
  if (py<1) py=1; if (py>5) py=5;
  drawPixel(px,py,false); drawPixel(px+1,py,false);
  drawPixel(px,py+1,false); drawPixel(px+1,py+1,false);
}

void drawEyes() {
  drawRoundEye8x8(8, eyeState.currentX, eyeState.currentY-3, eyeState.eyelidTop, eyeState.eyelidBottom);
  drawRoundEye8x8(16, eyeState.currentX, eyeState.currentY-3, eyeState.eyelidTop, eyeState.eyelidBottom);
}

#endif
