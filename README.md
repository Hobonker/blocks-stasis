# Gesture-Controlled Tetris

Play Tetris with your hands and your voice. A webcam tracks the center of your hand for movement to move and drop pieces, yell into the microphone to rotate pieces clockwise the louder you scream, the more the piece spins. The game itself runs on an ESP32-S3 driving a NeoPixel LED matrix, with a 7-segment display for score and a OLED showing the next piece shape.

# How To Play

- Always keep hand open palm facing the screen
- Place hand at center of the screen (neutral zone)
- Swipe your hand to the left or right to move the falling piece, respectively
- Swipe your hand down to hard drop
- Yell to rotate the falling piece clockwise
- Try to clear as many lines as you can by creating rows of 8

# BOM

| Part Name | Count |
|---|---|
| ESP32-S3 | 1 |
| WS2812B NeoPixel Matrix (8x32) | 1 |
| TM1637 4-digit 7-segment display | 1 |
| SSD1306 OLED 0.96" | 1 |
| USB cable (ESP32 to computer) | 1 |
| Webcam (built-in or external) | 1 |
| Microphone (built-in or external) | 1 |
| Computer with USB-C | 1 |
| Perf Board | 1 |
| Jumper Cables | 20 |
| 3D Printed Case | 1 |

