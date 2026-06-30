// Font tables and glyph lookup functions
#ifndef IRIS_FONTS_H
#define IRIS_FONTS_H
#include <Arduino.h>

const uint8_t DIGITS[10][5] = {
  {0b111,0b101,0b101,0b101,0b111},{0b010,0b110,0b010,0b010,0b111},
  {0b111,0b001,0b111,0b100,0b111},{0b111,0b001,0b111,0b001,0b111},
  {0b101,0b101,0b111,0b001,0b001},{0b111,0b100,0b111,0b001,0b111},
  {0b111,0b100,0b111,0b101,0b111},{0b111,0b001,0b001,0b001,0b001},
  {0b111,0b101,0b111,0b101,0b111},{0b111,0b101,0b111,0b001,0b111}
};

const uint8_t LETTER_A[5]={0b111,0b101,0b111,0b101,0b101};
const uint8_t LETTER_B[5]={0b110,0b101,0b110,0b101,0b110};
const uint8_t LETTER_C[5]={0b111,0b100,0b100,0b100,0b111};
const uint8_t LETTER_D[5]={0b110,0b101,0b101,0b101,0b110};
const uint8_t LETTER_E[5]={0b111,0b100,0b110,0b100,0b111};
const uint8_t LETTER_F[5]={0b111,0b100,0b110,0b100,0b100};
const uint8_t LETTER_G[5]={0b111,0b100,0b101,0b101,0b111};
const uint8_t LETTER_H[5]={0b101,0b101,0b111,0b101,0b101};
const uint8_t LETTER_I[5]={0b111,0b010,0b010,0b010,0b111};
const uint8_t LETTER_J[5]={0b011,0b001,0b001,0b101,0b111};
const uint8_t LETTER_K[5]={0b101,0b101,0b110,0b101,0b101};
const uint8_t LETTER_L[5]={0b100,0b100,0b100,0b100,0b111};
const uint8_t LETTER_M[5]={0b101,0b111,0b111,0b101,0b101};
const uint8_t LETTER_N[5]={0b101,0b111,0b111,0b111,0b101};
const uint8_t LETTER_O[5]={0b111,0b101,0b101,0b101,0b111};
const uint8_t LETTER_P[5]={0b110,0b101,0b110,0b100,0b100};
const uint8_t LETTER_Q[5]={0b111,0b101,0b101,0b101,0b011};
const uint8_t LETTER_R[5]={0b110,0b101,0b110,0b101,0b101};
const uint8_t LETTER_S[5]={0b111,0b100,0b111,0b001,0b111};
const uint8_t LETTER_T[5]={0b111,0b010,0b010,0b010,0b010};
const uint8_t LETTER_U[5]={0b101,0b101,0b101,0b101,0b111};
const uint8_t LETTER_V[5]={0b101,0b101,0b101,0b101,0b010};
const uint8_t LETTER_W[5]={0b101,0b101,0b101,0b111,0b101};
const uint8_t LETTER_X[5]={0b101,0b101,0b010,0b101,0b101};
const uint8_t LETTER_Y[5]={0b101,0b101,0b111,0b010,0b010};
const uint8_t LETTER_Z[5]={0b111,0b001,0b010,0b100,0b111};
const uint8_t GLYPH_DOT[5]  ={0,0,0,0,0b010};
const uint8_t GLYPH_SPACE[5]={0,0,0,0,0};
const uint8_t GLYPH_MINUS[5]={0,0,0b111,0,0};

const uint8_t* dayLetterGlyph(char c) {
  switch (c) {
    case 'A': return LETTER_A; case 'B': return LETTER_B; case 'C': return LETTER_C;
    case 'D': return LETTER_D; case 'E': return LETTER_E; case 'F': return LETTER_F;
    case 'G': return LETTER_G; case 'H': return LETTER_H; case 'I': return LETTER_I;
    case 'J': return LETTER_J; case 'K': return LETTER_K; case 'L': return LETTER_L;
    case 'M': return LETTER_M; case 'N': return LETTER_N; case 'O': return LETTER_O;
    case 'P': return LETTER_P; case 'Q': return LETTER_Q; case 'R': return LETTER_R;
    case 'S': return LETTER_S; case 'T': return LETTER_T; case 'U': return LETTER_U;
    case 'V': return LETTER_V; case 'W': return LETTER_W; case 'X': return LETTER_X;
    case 'Y': return LETTER_Y; case 'Z': return LETTER_Z;
    case '.': return GLYPH_DOT; case '-': return GLYPH_MINUS; case ' ': return GLYPH_SPACE;
    default:  if (c>='0'&&c<='9') return DIGITS[c-'0']; return GLYPH_SPACE;
  }
}

const uint8_t TC6_A[6]={0b010,0b101,0b101,0b111,0b101,0b101};
const uint8_t TC6_C[6]={0b111,0b100,0b100,0b100,0b100,0b111};
const uint8_t TC6_D[6]={0b110,0b101,0b101,0b101,0b101,0b110};
const uint8_t TC6_E[6]={0b111,0b100,0b110,0b100,0b100,0b111};
const uint8_t TC6_F[6]={0b111,0b100,0b110,0b100,0b100,0b100};
const uint8_t TC6_H[6]={0b101,0b101,0b111,0b101,0b101,0b101};
const uint8_t TC6_I[6]={0b111,0b010,0b010,0b010,0b010,0b111};
const uint8_t TC6_M[6]={0b101,0b111,0b101,0b101,0b101,0b101};
const uint8_t TC6_N[6]={0b101,0b101,0b111,0b101,0b101,0b101};
const uint8_t TC6_O[6]={0b111,0b101,0b101,0b101,0b101,0b111};
const uint8_t TC6_R[6]={0b110,0b101,0b110,0b101,0b101,0b101};
const uint8_t TC6_S[6]={0b111,0b100,0b111,0b001,0b001,0b111};
const uint8_t TC6_T[6]={0b111,0b010,0b010,0b010,0b010,0b010};
const uint8_t TC6_U[6]={0b101,0b101,0b101,0b101,0b101,0b111};
const uint8_t TC6_W[6]={0b101,0b101,0b101,0b111,0b111,0b101};
const uint8_t TC6_SPC[6]={0,0,0,0,0,0};

const uint8_t* tc6Letter(char c) {
  switch (c) {
    case 'A': return TC6_A; case 'C': return TC6_C; case 'D': return TC6_D;
    case 'E': return TC6_E; case 'F': return TC6_F; case 'H': return TC6_H;
    case 'I': return TC6_I; case 'M': return TC6_M; case 'N': return TC6_N;
    case 'O': return TC6_O; case 'R': return TC6_R; case 'S': return TC6_S;
    case 'T': return TC6_T; case 'U': return TC6_U; case 'W': return TC6_W;
    default:  return TC6_SPC;
  }
}

const uint8_t TC8_0[8]={0b111,0b101,0b101,0b101,0b101,0b101,0b101,0b111};
const uint8_t TC8_1[8]={0b010,0b110,0b010,0b010,0b010,0b010,0b010,0b111};
const uint8_t TC8_2[8]={0b111,0b001,0b001,0b111,0b100,0b100,0b100,0b111};
const uint8_t TC8_3[8]={0b111,0b001,0b001,0b111,0b001,0b001,0b001,0b111};
const uint8_t TC8_4[8]={0b101,0b101,0b101,0b111,0b001,0b001,0b001,0b001};
const uint8_t TC8_5[8]={0b111,0b100,0b100,0b111,0b001,0b001,0b001,0b111};
const uint8_t TC8_6[8]={0b111,0b100,0b100,0b111,0b101,0b101,0b101,0b111};
const uint8_t TC8_7[8]={0b111,0b001,0b001,0b010,0b010,0b100,0b100,0b100};
const uint8_t TC8_8[8]={0b111,0b101,0b101,0b111,0b101,0b101,0b101,0b111};
const uint8_t TC8_9[8]={0b111,0b101,0b101,0b111,0b001,0b001,0b001,0b111};
const uint8_t TC8_BLANK[8]={0,0,0,0,0,0,0,0};

const uint8_t* tc8Digit(int d) {
  switch (d) {
    case 0: return TC8_0; case 1: return TC8_1; case 2: return TC8_2;
    case 3: return TC8_3; case 4: return TC8_4; case 5: return TC8_5;
    case 6: return TC8_6; case 7: return TC8_7; case 8: return TC8_8;
    default: return TC8_9;
  }
}

const uint8_t TC7_0[7]={0b111,0b101,0b101,0b101,0b101,0b101,0b111};
const uint8_t TC7_1[7]={0b010,0b110,0b010,0b010,0b010,0b010,0b111};
const uint8_t TC7_2[7]={0b111,0b001,0b001,0b111,0b100,0b100,0b111};
const uint8_t TC7_3[7]={0b111,0b001,0b001,0b111,0b001,0b001,0b111};
const uint8_t TC7_4[7]={0b101,0b101,0b101,0b111,0b001,0b001,0b001};
const uint8_t TC7_5[7]={0b111,0b100,0b100,0b111,0b001,0b001,0b111};
const uint8_t TC7_6[7]={0b111,0b100,0b100,0b111,0b101,0b101,0b111};
const uint8_t TC7_7[7]={0b111,0b001,0b001,0b010,0b010,0b100,0b100};
const uint8_t TC7_8[7]={0b111,0b101,0b101,0b111,0b101,0b101,0b111};
const uint8_t TC7_9[7]={0b111,0b101,0b101,0b111,0b001,0b001,0b111};
const uint8_t TC7_BLANK[7]={0,0,0,0,0,0,0};

const uint8_t* tc7Digit(int d) {
  switch (d) {
    case 0: return TC7_0; case 1: return TC7_1; case 2: return TC7_2;
    case 3: return TC7_3; case 4: return TC7_4; case 5: return TC7_5;
    case 6: return TC7_6; case 7: return TC7_7; case 8: return TC7_8;
    default: return TC7_9;
  }
}

const uint8_t CL_0[7]={0b01110,0b10001,0b10011,0b10101,0b11001,0b10001,0b01110};
const uint8_t CL_1[7]={0b00100,0b01100,0b00100,0b00100,0b00100,0b00100,0b01110};
const uint8_t CL_2[7]={0b01110,0b10001,0b00001,0b00110,0b01000,0b10000,0b11111};
const uint8_t CL_3[7]={0b11111,0b00010,0b00100,0b00110,0b00001,0b10001,0b01110};
const uint8_t CL_4[7]={0b00010,0b00110,0b01010,0b10010,0b11111,0b00010,0b00010};
const uint8_t CL_5[7]={0b11111,0b10000,0b10000,0b11110,0b00001,0b10001,0b01110};
const uint8_t CL_6[7]={0b00111,0b01000,0b10000,0b11110,0b10001,0b10001,0b01110};
const uint8_t CL_7[7]={0b11111,0b00001,0b00010,0b00100,0b01000,0b01000,0b01000};
const uint8_t CL_8[7]={0b01110,0b10001,0b10001,0b01110,0b10001,0b10001,0b01110};
const uint8_t CL_9[7]={0b01110,0b10001,0b10001,0b01111,0b00001,0b00010,0b01100};

const uint8_t* clockDigit5x7(int d) {
  switch (d) {
    case 0: return CL_0; case 1: return CL_1; case 2: return CL_2;
    case 3: return CL_3; case 4: return CL_4; case 5: return CL_5;
    case 6: return CL_6; case 7: return CL_7; case 8: return CL_8;
    default: return CL_9;
  }
}

const uint8_t SF_A[8]={0b01110,0b10001,0b10001,0b11111,0b10001,0b10001,0b10001,0};
const uint8_t SF_B[8]={0b11110,0b10001,0b10001,0b11110,0b10001,0b10001,0b11110,0};
const uint8_t SF_C[8]={0b01110,0b10001,0b10000,0b10000,0b10000,0b10001,0b01110,0};
const uint8_t SF_D[8]={0b11100,0b10010,0b10001,0b10001,0b10001,0b10010,0b11100,0};
const uint8_t SF_E[8]={0b11111,0b10000,0b10000,0b11110,0b10000,0b10000,0b11111,0};
const uint8_t SF_F[8]={0b11111,0b10000,0b10000,0b11110,0b10000,0b10000,0b10000,0};
const uint8_t SF_G[8]={0b01110,0b10001,0b10000,0b10111,0b10001,0b10001,0b01111,0};
const uint8_t SF_H[8]={0b10001,0b10001,0b10001,0b11111,0b10001,0b10001,0b10001,0};
const uint8_t SF_I[8]={0b01110,0b00100,0b00100,0b00100,0b00100,0b00100,0b01110,0};
const uint8_t SF_J[8]={0b00111,0b00010,0b00010,0b00010,0b10010,0b10010,0b01100,0};
const uint8_t SF_K[8]={0b10001,0b10010,0b10100,0b11000,0b10100,0b10010,0b10001,0};
const uint8_t SF_L[8]={0b10000,0b10000,0b10000,0b10000,0b10000,0b10000,0b11111,0};
const uint8_t SF_M[8]={0b10001,0b11011,0b10101,0b10001,0b10001,0b10001,0b10001,0};
const uint8_t SF_N[8]={0b10001,0b11001,0b10101,0b10011,0b10001,0b10001,0b10001,0};
const uint8_t SF_O[8]={0b01110,0b10001,0b10001,0b10001,0b10001,0b10001,0b01110,0};
const uint8_t SF_P[8]={0b11110,0b10001,0b10001,0b11110,0b10000,0b10000,0b10000,0};
const uint8_t SF_Q[8]={0b01110,0b10001,0b10001,0b10001,0b10101,0b10010,0b01101,0};
const uint8_t SF_R[8]={0b11110,0b10001,0b10001,0b11110,0b10100,0b10010,0b10001,0};
const uint8_t SF_S[8]={0b01111,0b10000,0b10000,0b01110,0b00001,0b00001,0b11110,0};
const uint8_t SF_T[8]={0b11111,0b00100,0b00100,0b00100,0b00100,0b00100,0b00100,0};
const uint8_t SF_U[8]={0b10001,0b10001,0b10001,0b10001,0b10001,0b10001,0b01110,0};
const uint8_t SF_V[8]={0b10001,0b10001,0b10001,0b10001,0b10001,0b01010,0b00100,0};
const uint8_t SF_W[8]={0b10001,0b10001,0b10001,0b10101,0b10101,0b11011,0b10001,0};
const uint8_t SF_X[8]={0b10001,0b10001,0b01010,0b00100,0b01010,0b10001,0b10001,0};
const uint8_t SF_Y[8]={0b10001,0b10001,0b01010,0b00100,0b00100,0b00100,0b00100,0};
const uint8_t SF_Z[8]={0b11111,0b00001,0b00010,0b00100,0b01000,0b10000,0b11111,0};
const uint8_t SF_0[8]={0b01110,0b10001,0b10011,0b10101,0b11001,0b10001,0b01110,0};
const uint8_t SF_1[8]={0b00100,0b01100,0b00100,0b00100,0b00100,0b00100,0b01110,0};
const uint8_t SF_2[8]={0b01110,0b10001,0b00001,0b00110,0b01000,0b10000,0b11111,0};
const uint8_t SF_3[8]={0b11111,0b00010,0b00100,0b00110,0b00001,0b10001,0b01110,0};
const uint8_t SF_4[8]={0b00010,0b00110,0b01010,0b10010,0b11111,0b00010,0b00010,0};
const uint8_t SF_5[8]={0b11111,0b10000,0b10000,0b11110,0b00001,0b10001,0b01110,0};
const uint8_t SF_6[8]={0b00111,0b01000,0b10000,0b11110,0b10001,0b10001,0b01110,0};
const uint8_t SF_7[8]={0b11111,0b00001,0b00010,0b00100,0b01000,0b01000,0b01000,0};
const uint8_t SF_8[8]={0b01110,0b10001,0b10001,0b01110,0b10001,0b10001,0b01110,0};
const uint8_t SF_9[8]={0b01110,0b10001,0b10001,0b01111,0b00001,0b00010,0b01100,0};
const uint8_t SF_SPC[8] ={0,0,0,0,0,0,0,0};
const uint8_t SF_EXCL[8]={0b00100,0b00100,0b00100,0b00100,0b00100,0,0b00100,0};
const uint8_t SF_DQUOT[8]={0b01010,0b01010,0b01010,0,0,0,0,0};
const uint8_t SF_HASH[8]={0b01010,0b01010,0b11111,0b01010,0b11111,0b01010,0b01010,0};
const uint8_t SF_DOLR[8]={0b00100,0b01111,0b10100,0b01110,0b00101,0b11110,0b00100,0};
const uint8_t SF_PCNT[8]={0b11000,0b11001,0b00010,0b00100,0b01000,0b10011,0b00011,0};
const uint8_t SF_AMP[8] ={0b01100,0b10010,0b10010,0b01100,0b10101,0b10010,0b01101,0};
const uint8_t SF_SQUOT[8]={0b00100,0b00100,0b01000,0,0,0,0,0};
const uint8_t SF_LPAR[8]={0b00010,0b00100,0b01000,0b01000,0b01000,0b00100,0b00010,0};
const uint8_t SF_RPAR[8]={0b01000,0b00100,0b00010,0b00010,0b00010,0b00100,0b01000,0};
const uint8_t SF_STAR[8]={0,0b00100,0b10101,0b01110,0b10101,0b00100,0,0};
const uint8_t SF_PLUS[8]={0,0b00100,0b00100,0b11111,0b00100,0b00100,0,0};
const uint8_t SF_COMMA[8]={0,0,0,0,0,0b00100,0b00100,0b01000};
const uint8_t SF_MINUS[8]={0,0,0,0b11111,0,0,0,0};
const uint8_t SF_DOT[8] ={0,0,0,0,0,0,0b00100,0};
const uint8_t SF_SLASH[8]={0b00001,0b00010,0b00100,0b00100,0b01000,0b10000,0,0};
const uint8_t SF_COLON[8]={0,0b00100,0b00100,0,0b00100,0b00100,0,0};
const uint8_t SF_SEMI[8]={0,0b00100,0b00100,0,0b00100,0b00100,0b01000,0};
const uint8_t SF_LT[8]  ={0b00010,0b00100,0b01000,0b10000,0b01000,0b00100,0b00010,0};
const uint8_t SF_EQ[8]  ={0,0,0b11111,0,0b11111,0,0,0};
const uint8_t SF_GT[8]  ={0b01000,0b00100,0b00010,0b00001,0b00010,0b00100,0b01000,0};
const uint8_t SF_QMARK[8]={0b01110,0b10001,0b00001,0b00110,0b00100,0,0b00100,0};
const uint8_t SF_AT[8]  ={0b01110,0b10001,0b10101,0b10111,0b10110,0b10000,0b01110,0};
const uint8_t SF_LBRK[8]={0b01110,0b01000,0b01000,0b01000,0b01000,0b01000,0b01110,0};
const uint8_t SF_RBRK[8]={0b01110,0b00010,0b00010,0b00010,0b00010,0b00010,0b01110,0};
const uint8_t SF_CARET[8]={0b00100,0b01010,0b10001,0,0,0,0,0};
const uint8_t SF_UNDR[8]={0,0,0,0,0,0,0b11111,0};
const uint8_t SF_LBRC[8]={0b00110,0b01000,0b01000,0b11000,0b01000,0b01000,0b00110,0};
const uint8_t SF_RBRC[8]={0b01100,0b00010,0b00010,0b00011,0b00010,0b00010,0b01100,0};
const uint8_t SF_TILD[8]={0,0,0b01000,0b10101,0b00010,0,0,0};

const uint8_t* scrollGlyph(char c) {
  switch (c) {
    case 'A': return SF_A; case 'B': return SF_B; case 'C': return SF_C;
    case 'D': return SF_D; case 'E': return SF_E; case 'F': return SF_F;
    case 'G': return SF_G; case 'H': return SF_H; case 'I': return SF_I;
    case 'J': return SF_J; case 'K': return SF_K; case 'L': return SF_L;
    case 'M': return SF_M; case 'N': return SF_N; case 'O': return SF_O;
    case 'P': return SF_P; case 'Q': return SF_Q; case 'R': return SF_R;
    case 'S': return SF_S; case 'T': return SF_T; case 'U': return SF_U;
    case 'V': return SF_V; case 'W': return SF_W; case 'X': return SF_X;
    case 'Y': return SF_Y; case 'Z': return SF_Z;
    case '0': return SF_0; case '1': return SF_1; case '2': return SF_2;
    case '3': return SF_3; case '4': return SF_4; case '5': return SF_5;
    case '6': return SF_6; case '7': return SF_7; case '8': return SF_8;
    case '9': return SF_9;
    case ' ':  return SF_SPC;  case '!':  return SF_EXCL;
    case '"':  return SF_DQUOT; case '#': return SF_HASH;
    case '$':  return SF_DOLR;  case '%': return SF_PCNT;
    case '&':  return SF_AMP;   case '\'':return SF_SQUOT;
    case '(':  return SF_LPAR;  case ')': return SF_RPAR;
    case '*':  return SF_STAR;  case '+': return SF_PLUS;
    case ',':  return SF_COMMA; case '-': return SF_MINUS;
    case '.':  return SF_DOT;   case '/': return SF_SLASH;
    case ':':  return SF_COLON; case ';': return SF_SEMI;
    case '<':  return SF_LT;    case '=': return SF_EQ;
    case '>':  return SF_GT;    case '?': return SF_QMARK;
    case '@':  return SF_AT;    case '[': return SF_LBRK;
    case ']':  return SF_RBRK;  case '^': return SF_CARET;
    case '_':  return SF_UNDR;  case '{': return SF_LBRC;
    case '}':  return SF_RBRC;  case '~': return SF_TILD;
    default:   return SF_SPC;
  }
}

const uint32_t PCSTATS_TEMP_FPS_G_FRAME[8] = {
  0b00000000000001100000000000000000,0b00000000000001100000000000000000,
  0b00000000000000000000000000000000,0b00000000000001110000000000000000,
  0b00000000000001000000000000000000,0b00000000000001010000000000000000,
  0b00000000000001010000000000000000,0b00000000000001110000000000000000,
};
const uint32_t PCSTATS_TEMP_FPS_C_FRAME[8] = {
  0b00000000000001100000000000000000,0b00000000000001100000000000000000,
  0b00000000000000000000000000000000,0b00000000000001110000000000000000,
  0b00000000000001000000000000000000,0b00000000000001000000000000000000,
  0b00000000000001000000000000000000,0b00000000000001110000000000000000,
};
const uint32_t PCSTATS_TEMPS_FRAME[8] = {
  0b00000000000011000000000000000110,0b00000000000011000000000000000110,
  0b00000000000000000000000000000000,0b00000000000011100000000000000111,
  0b00000000000010000000000000000100,0b00000000000010100000000000000100,
  0b00000000000010100000000000000100,0b00000000000011100000000000000111,
};
const uint32_t PCSTATS3_FRAME[8] = {
  0b11101110111000000000000000000000,0b00101010100000000000001001010111,
  0b00101010111000000000011001010100,0b00101010000011101010001001110111,
  0b00101110111010001010001000010001,0b00000000100011101110001000010001,
  0b00000000101010100010011100010111,0b00000000111011100010000000000000,
};
const uint8_t OV_P[5]={0b111,0b101,0b111,0b100,0b100};
const uint8_t H_GLYPH[6]={0b101,0b101,0b111,0b101,0b101,0b101};
const uint8_t O_GLYPH[6]={0b111,0b101,0b101,0b101,0b101,0b111};
const uint8_t T_GLYPH[6]={0b111,0b010,0b010,0b010,0b010,0b010};

#endif
