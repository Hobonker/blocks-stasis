#include <Adafruit_NeoPixel.h>
#include <TM1637Display.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// --- NeoPixel ---
#define PIN 13
#define W 8
#define H 32
#define NUM_LEDS (W * H)
Adafruit_NeoPixel strip(NUM_LEDS, PIN, NEO_GRB + NEO_KHZ800);

// --- TM1637 7-seg (score) ---
#define TM_CLK 22
#define TM_DIO 21
TM1637Display display(TM_CLK, TM_DIO);

// --- SSD1306 OLED (next piece) ---
#define OLED_SDA 23
#define OLED_SCL 18
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 oled(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// --- Volume LED bar ---
const int LED_PINS[]   = {14, 27, 26, 25, 33, 32, 5, 19, 2, 4};
const int NUM_VOL_LEDS = 10;
int currentLevel  = 0;
int targetLevel   = 0;
unsigned long lastDecay = 0;
const int DECAY_INTERVAL = 60;

// --- Start gate ---
bool gameStarted = false;

// --- Game state ---
uint32_t board[H][W];
int curPiece, curRot, curRow, curCol;
uint32_t COLORS[7];
int score = 0;
int incomingPiece = 0;
unsigned long lastFall = 0;
#define FALL_SPEED 600
String serialBuf = "";

const int8_t PIECES[7][4][4][2] = {
  // I
  {{{0,0},{0,1},{0,2},{0,3}},{{0,0},{1,0},{2,0},{3,0}},{{0,0},{0,1},{0,2},{0,3}},{{0,0},{1,0},{2,0},{3,0}}},
  // O
  {{{0,0},{0,1},{1,0},{1,1}},{{0,0},{0,1},{1,0},{1,1}},{{0,0},{0,1},{1,0},{1,1}},{{0,0},{0,1},{1,0},{1,1}}},
  // T
  {{{0,1},{1,0},{1,1},{1,2}},{{0,0},{1,0},{1,1},{2,0}},{{0,0},{0,1},{0,2},{1,1}},{{0,1},{1,0},{1,1},{2,1}}},
  // S
  {{{0,1},{0,2},{1,0},{1,1}},{{0,0},{1,0},{1,1},{2,1}},{{0,1},{0,2},{1,0},{1,1}},{{0,0},{1,0},{1,1},{2,1}}},
  // Z
  {{{0,0},{0,1},{1,1},{1,2}},{{0,1},{1,0},{1,1},{2,0}},{{0,0},{0,1},{1,1},{1,2}},{{0,1},{1,0},{1,1},{2,0}}},
  // J
  {{{0,0},{1,0},{1,1},{1,2}},{{0,0},{0,1},{1,0},{2,0}},{{0,0},{0,1},{0,2},{1,2}},{{0,1},{1,1},{2,0},{2,1}}},
  // L
  {{{0,2},{1,0},{1,1},{1,2}},{{0,0},{1,0},{2,0},{2,1}},{{0,0},{0,1},{0,2},{1,0}},{{0,0},{0,1},{1,1},{2,1}}}
};

const bool PIECE_PREVIEW[7][4][4] = {
  {{0,0,0,0},{1,1,1,1},{0,0,0,0},{0,0,0,0}},  // I
  {{0,1,1,0},{0,1,1,0},{0,0,0,0},{0,0,0,0}},  // O
  {{0,1,0,0},{1,1,1,0},{0,0,0,0},{0,0,0,0}},  // T
  {{0,1,1,0},{1,1,0,0},{0,0,0,0},{0,0,0,0}},  // S
  {{1,1,0,0},{0,1,1,0},{0,0,0,0},{0,0,0,0}},  // Z
  {{1,0,0,0},{1,1,1,0},{0,0,0,0},{0,0,0,0}},  // J
  {{0,0,1,0},{1,1,1,0},{0,0,0,0},{0,0,0,0}}   // L
};

const char* PIECE_NAMES[7] = {"I","O","T","S","Z","J","L"};

// ─── Helpers ─────────────────────────────────────────────

void updateVolumeLEDs() {
  if (millis() - lastDecay > DECAY_INTERVAL) {
    if (currentLevel > 0) currentLevel--;
    lastDecay = millis();
  }
  for (int i = 0; i < NUM_VOL_LEDS; i++)
    digitalWrite(LED_PINS[i], i < currentLevel ? HIGH : LOW);
}

void drawNextPiece(int piece) {
  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 0);
  oled.print("NEXT:");
  oled.print(PIECE_NAMES[piece]);

  int cellSize = 14, gap = 2;
  int gridW = 4 * (cellSize + gap);
  int gridH = 4 * (cellSize + gap);
  int startX = (SCREEN_WIDTH - gridW) / 2;
  int startY = (SCREEN_HEIGHT - gridH) / 2 + 8;

  for (int r = 0; r < 4; r++)
    for (int c = 0; c < 4; c++)
      if (PIECE_PREVIEW[piece][r][c])
        oled.fillRect(startX + c*(cellSize+gap), startY + r*(cellSize+gap), cellSize, cellSize, SSD1306_WHITE);
  oled.display();
}

int xyToLED(int row, int col) {
  int flippedRow = (H - 1) - row;
  if (flippedRow % 2 == 0) return flippedRow * W + col;
  else return flippedRow * W + (W - 1 - col);
}

bool collides(int piece, int rot, int row, int col) {
  for (int i = 0; i < 4; i++) {
    int r = row + PIECES[piece][rot][i][0];
    int c = col + PIECES[piece][rot][i][1];
    if (r < 0 || r >= H || c < 0 || c >= W) return true;
    if (board[r][c]) return true;
  }
  return false;
}

void lockPiece() {
  for (int i = 0; i < 4; i++) {
    int r = curRow + PIECES[curPiece][curRot][i][0];
    int c = curCol + PIECES[curPiece][curRot][i][1];
    if (r >= 0 && r < H && c >= 0 && c < W)
      board[r][c] = COLORS[curPiece];
  }
  score += 10;
  display.showNumberDec(score, false);
  Serial.print("Score: "); Serial.println(score);
}

void clearLines() {
  for (int r = H - 1; r >= 0; r--) {
    bool full = true;
    for (int c = 0; c < W; c++)
      if (!board[r][c]) { full = false; break; }
    if (full) {
      for (int rr = r; rr > 0; rr--)
        for (int c = 0; c < W; c++)
          board[rr][c] = board[rr-1][c];
      for (int c = 0; c < W; c++)
        board[0][c] = 0;
      r++;
      score += 50;
      display.showNumberDec(score, false);
      Serial.print("Score: "); Serial.println(score);
    }
  }
}

void render() {
  for (int r = 0; r < H; r++)
    for (int c = 0; c < W; c++)
      strip.setPixelColor(xyToLED(r, c), board[r][c]);
  for (int i = 0; i < 4; i++) {
    int r = curRow + PIECES[curPiece][curRot][i][0];
    int c = curCol + PIECES[curPiece][curRot][i][1];
    if (r >= 0 && r < H && c >= 0 && c < W)
      strip.setPixelColor(xyToLED(r, c), COLORS[curPiece]);
  }
  strip.show();
}

void showIdleScreen() {
  // Blue border on NeoPixel matrix, everything else black
  strip.clear();
  for (int c = 0; c < W; c++) {
    strip.setPixelColor(xyToLED(0, c),   strip.Color(0, 0, 60));
    strip.setPixelColor(xyToLED(H-1, c), strip.Color(0, 0, 60));
  }
  for (int r = 1; r < H-1; r++) {
    strip.setPixelColor(xyToLED(r, 0),   strip.Color(0, 0, 60));
    strip.setPixelColor(xyToLED(r, W-1), strip.Color(0, 0, 60));
  }
  strip.show();

  // OLED waiting message
  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 20);
  oled.print("  TETRIS");
  oled.setCursor(0, 36);
  oled.print("Press SPACE");
  oled.setCursor(0, 48);
  oled.print("  to start");
  oled.display();

  display.showNumberDec(0, false);
  Serial.println("Waiting for start — press SPACE in the Python controller.");
}

void spawnPiece() {
  curPiece = incomingPiece;
  incomingPiece = random(7);
  curRot = 0; curRow = 0;
  curCol = W / 2 - 1;
  drawNextPiece(incomingPiece);
  Serial.print("Incoming: "); Serial.println(incomingPiece);
  if (collides(curPiece, curRot, curRow, curCol)) {
    memset(board, 0, sizeof(board));
    score = 0;
    display.showNumberDec(0, false);
    oled.clearDisplay();
    oled.setTextSize(2);
    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(10, 20);
    oled.print("GAME OVER");
    oled.display();
    Serial.println("Game over! Score reset.");
    delay(2000);
    // Return to idle — wait for another 'S' to restart
    gameStarted = false;
    showIdleScreen();
  }
}

// ─── Setup ───────────────────────────────────────────────

void setup() {
  for (int i = 0; i < NUM_VOL_LEDS; i++) {
    pinMode(LED_PINS[i], OUTPUT);
    digitalWrite(LED_PINS[i], LOW);
  }

  Serial.begin(115200);
  Wire.begin(OLED_SDA, OLED_SCL);

  display.setBrightness(7);
  display.showNumberDec(0, false);

  if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED init failed");
    while (true);
  }
  oled.setRotation(2);
  oled.clearDisplay();
  oled.display();

  strip.begin();
  strip.setBrightness(40);
  strip.clear();
  strip.show();

  COLORS[0] = strip.Color(0,   200, 200);  // I - cyan
  COLORS[1] = strip.Color(200, 200, 0);    // O - yellow
  COLORS[2] = strip.Color(150, 0,   150);  // T - purple
  COLORS[3] = strip.Color(0,   200, 0);    // S - green
  COLORS[4] = strip.Color(200, 0,   0);    // Z - red
  COLORS[5] = strip.Color(0,   0,   200);  // J - blue
  COLORS[6] = strip.Color(200, 100, 0);    // L - orange

  randomSeed(analogRead(0));
  memset(board, 0, sizeof(board));
  score = 0;
  gameStarted = false;
  incomingPiece = random(7);

  // Force a full clear render so any leftover board from a previous run is wiped
  strip.clear();
  strip.show();
  delay(50);

  showIdleScreen();
}

// ─── Loop ────────────────────────────────────────────────

void loop() {
  while (Serial.available()) {
    char c = Serial.read();

    // Start command
    if (c == 'S' && !gameStarted) {
      gameStarted = true;
      memset(board, 0, sizeof(board));
      score = 0;
      display.showNumberDec(0, false);
      incomingPiece = random(7);
      spawnPiece();
      lastFall = millis();
      Serial.println("Game started!");
      return;
    }

    if (c == '\n') {
      serialBuf.trim();
      if (serialBuf.length() > 0) {
        bool isNumber = true;
        for (int i = 0; i < (int)serialBuf.length(); i++)
          if (!isDigit(serialBuf[i])) { isNumber = false; break; }
        if (isNumber) {
          int val = serialBuf.toInt();
          if (val >= 0 && val <= 10) {
            if (val > currentLevel) currentLevel = val;
            targetLevel = val;
          }
        }
      }
      serialBuf = "";
    } else if (gameStarted && (c == 'L' || c == 'R' || c == 'U' || c == 'D')) {
      serialBuf = "";
      if (c == 'L' && !collides(curPiece, curRot, curRow, curCol - 1)) curCol--;
      if (c == 'R' && !collides(curPiece, curRot, curRow, curCol + 1)) curCol++;
      if (c == 'U') {
        int nr = (curRot + 1) % 4;
        if (!collides(curPiece, nr, curRow, curCol)) curRot = nr;
      }
      if (c == 'D') {
        while (!collides(curPiece, curRot, curRow + 1, curCol)) curRow++;
        lockPiece(); clearLines(); spawnPiece();
        lastFall = millis();
      }
    } else {
      serialBuf += c;
    }
  }

  // Only tick and render when game is live
  if (!gameStarted) {
    updateVolumeLEDs();
    return;  // <-- exits before render(), idle screen stays intact
  }

  if (millis() - lastFall >= FALL_SPEED) {
    lastFall = millis();
    if (!collides(curPiece, curRot, curRow + 1, curCol)) {
      curRow++;
    } else {
      lockPiece(); clearLines(); spawnPiece();
    }
  }

  render();
  updateVolumeLEDs();
}
