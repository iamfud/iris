// Buzzer stubs — hardware removed; PC handles alarm/overheat beeps via winsound
#ifndef IRIS_BUZZER_H
#define IRIS_BUZZER_H
#include <Arduino.h>

struct BuzzStep { uint16_t freq; uint16_t ms; };

static const BuzzStep BUZZ_NOTIFY[]   = {{3500,50},{0,0}};
static const BuzzStep BUZZ_ALARM[]    = {{1400,160},{0,80},{1700,160},{0,80},{2000,160},{0,700},{0,0}};
static const BuzzStep BUZZ_OVERHEAT[] = {{3000,60},{0,50},{3000,60},{0,0}};

inline void buzzStop() {}
inline void buzzPlay(const BuzzStep*, bool = false) {}
inline void tickBuzzer() {}

#endif
