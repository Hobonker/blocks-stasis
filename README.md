# TETRIVISION - Gesture Controlled Tetris

<img width="4032" height="3024" alt="IMG_3820" src="https://github.com/user-attachments/assets/d786fd2a-7d7b-42d9-be6d-55144621924c" />

Play Tetris with your hands and your voice. A webcam tracks the center of your hand for movement to move and drop pieces, yell into the microphone to rotate pieces clockwise the louder you scream, the more the piece spins. The game itself runs on an ESP32-WROOM driving a 8x32 NeoPixel LED matrix, with a 7-segment display for score, an OLED showing the next piece shape, and a LED bar for mic input volume.

#Demo

https://www.youtube.com/watch?v=66Lr5TsQWm4

# How To Play

- Always keep hand open palm facing the screen
- Place hand at center of the screen (neutral zone)
- Swipe your hand to the left or right to move the falling piece
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
| Computer | 1 |
| LED Lights | 1 |


# Wiring Diagram

| From | From Label | To | To Label |
| :--- | :--- | :--- | :--- |
| ESP32 | VIN (5V) | WS2812B Matrix | VCC |
| ESP32 | GND | WS2812B Matrix | GND |
| ESP32 | GPIO13 |  WS2812B Matrix | DIN |
| ESP32 | 3V3 | SSD1306 OLED | VCC |
| ESP32 | GND | SSD1306 OLED | GND |
| ESP32 | GPIO18 | SSD1306 OLED | SCK |
| ESP32 | GPIO23 | SSD1306 OLED | SDA |
| ESP32 | 3V3 | TM1637 7-seg | VCC |
| ESP32 | GND | TM1637 7-seg | GND |
| ESP32 | GPIO22 | TM1637 7-seg | CLK |
| ESP32 | GPIO21 | TM1637 7-seg | DIO |
| ESP32 | GPIO14 | Resistor LED1 | IN |
| Resistor LED1 | OUT | Volume Bar LED1 | DIN |
| ESP32 | GPIO27 | Resistor LED2 | IN |
| Resistor LED2 | OUT | Volume Bar LED2 | DIN |
| ESP32 | GPIO26 | Resistor LED3 | IN |
| Resistor LED3 | OUT | Volume Bar LED3 | DIN |
| ESP32 | GPIO25 | Resistor LED4 | IN |
| Resistor LED4 | OUT | Volume Bar LED4 | DIN |
| ESP32 | GPIO33 | Resistor LED5 | IN |
| Resistor LED5 | OUT | Volume Bar LED5 | DIN |
| ESP32 | GPIO32 | Resistor LED6 | IN |
| Resistor LED6 | OUT | Volume Bar LED6 | DIN |
| ESP32 | GPIO5 | Resistor LED7 | IN |
| Resistor LED7 | OUT | Volume Bar LED7 | DIN |
| ESP32 | GPIO19 | Resistor LED8 | IN |
| Resistor LED8 | OUT | Volume Bar LED8 | DIN |
| ESP32 | GPIO2 | Resistor LED9 | IN |
| Resistor LED9 | OUT | Volume Bar LED9 | DIN |
