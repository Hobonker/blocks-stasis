import cv2, mediapipe as mp, time, os, urllib.request, serial
import pyaudio, struct, math, threading, random, signal, sys
import pygame
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# Raw-mode safe print — ensures \r\n so lines don't staircase in raw terminal
def rprint(*args, **kwargs):
    text = " ".join(str(a) for a in args)
    sys.stdout.write(text + "\r\n")
    sys.stdout.flush()

import builtins
builtins.print = rprint

# ─── Config ──────────────────────────────────────────────
SERIAL_PORT       = "/dev/cu.usbserial-0001"
BAUD              = 115200

MODEL_PATH        = "hand_landmarker.task"
MODEL_URL         = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"

CENTER_X          = 0.5
CENTER_Y          = 0.58
X_TRIGGER         = 0.18
Y_TRIGGER         = 0.22
COOLDOWN          = 0.50

CHUNK             = 1024
RATE              = 44100
SILENCE_THRESHOLD = 2400
ROTATE_COOLDOWN   = 1.0

PALM_LANDMARKS    = [0, 5, 9, 13, 17]

NO_CLEAR_WARNING  = 30.0
MUSIC_VOLUME      = 0.35

INSULT_MIN        = 8
INSULT_MAX        = 15

# ─── Suppress MediaPipe/TF C++ logging ───────────────────
os.environ["GLOG_minloglevel"] = "3"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# ─── Audio setup ─────────────────────────────────────────
pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.mixer.init()

def load_sound(path):
    if os.path.exists(path):
        return pygame.mixer.Sound(path)
    print(f"Warning: sound file not found: {path}")
    return None

click_sound    = load_sound("soundeffects/click.wav")
ding_sound     = load_sound("soundeffects/ding.wav")
gameover_sound = load_sound("insults/Arena Hall 12.wav")

# Load music but don't play yet — starts after SPACE
if os.path.exists("soundeffects/791018.mp3"):
    pygame.mixer.music.load("soundeffects/791018.mp3")
    pygame.mixer.music.set_volume(MUSIC_VOLUME)
else:
    print("Warning: soundeffects/791018.mp3 not found")

def play_click():
    if click_sound:
        click_sound.set_volume(0.6)
        click_sound.play()

def play_ding():
    if ding_sound:
        ding_sound.set_volume(0.9)
        ding_sound.play()

# ─── Insult audio ─────────────────────────────────────────
INSULT_DIR     = "insults"
insult_channel = pygame.mixer.Channel(1)

def load_insults(folder):
    supported = (".wav", ".mp3", ".ogg", ".m4a")
    if not os.path.exists(folder):
        print(f"Warning: insults folder not found: {folder}")
        return []
    files = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(supported) and "Arena Hall 12" not in f
    ]
    if not files:
        print(f"Warning: no audio files found in {folder}")
    else:
        print(f"Loaded {len(files)} insults from {folder}")
    return files

insult_files = load_insults(INSULT_DIR)

def insult_loop():
    while True:
        time.sleep(random.uniform(INSULT_MIN, INSULT_MAX))
        if not insult_files or not game_started:
            continue
        path = random.choice(insult_files)
        try:
            snd = pygame.mixer.Sound(path)
            snd.set_volume(1.0)
            pygame.mixer.music.pause()
            insult_channel.play(snd)
            print(f"  >> INSULT: {os.path.basename(path)}")
            while insult_channel.get_busy():
                time.sleep(0.05)
            if game_started:
                pygame.mixer.music.unpause()
        except Exception as e:
            print(f"  Insult play error: {e}")
            if game_started:
                pygame.mixer.music.unpause()

threading.Thread(target=insult_loop, daemon=True).start()

# ─── Setup ───────────────────────────────────────────────
if not os.path.exists(MODEL_PATH):
    print("Downloading hand model...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

detector = vision.HandLandmarker.create_from_options(
    vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
)

esp = serial.Serial(SERIAL_PORT, BAUD, timeout=1)
time.sleep(2)
print(f"Connected to ESP32 on {SERIAL_PORT}")

# ─── Shared state ────────────────────────────────────────
last_fired        = {}
x_side            = 0
y_side            = 0
last_rotate_time  = 0
mic_level         = 0
serial_lock       = threading.Lock()
last_line_clear   = time.time()
game_started      = False
game_over_flag    = False
space_pressed     = False   # set by input thread, consumed by main loop

# ─── Clean exit ──────────────────────────────────────────
cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)

def handle_exit(sig, frame):
    print("\nShutting down...")
    cap.release()
    cv2.destroyAllWindows()
    detector.close()
    esp.close()
    pygame.mixer.quit()
    os._exit(0)

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

# ─── Serial send ─────────────────────────────────────────
def send(name, cmd):
    now = time.time()
    if now - last_fired.get(name, 0) < COOLDOWN:
        return False
    last_fired[name] = now
    with serial_lock:
        esp.write(cmd.encode())
    print(f"  >> {name} ({cmd})")
    if name == "DROP":
        play_click()
    return True

# ─── ESP32 serial reader ─────────────────────────────────
def serial_reader():
    global last_line_clear, game_over_flag
    buf = ""
    while True:
        try:
            with serial_lock:
                if esp.in_waiting:
                    buf += esp.read(esp.in_waiting).decode(errors='ignore')
            lines = buf.split('\n')
            buf = lines[-1]
            for line in lines[:-1]:
                line = line.strip()
                if line:
                    print(f"  [ESP32] {line}")
                if line.startswith("Score:"):
                    try:
                        new_score = int(line.split(":")[1].strip())
                        if not hasattr(serial_reader, "last_score"):
                            serial_reader.last_score = 0
                        delta = new_score - serial_reader.last_score
                        serial_reader.last_score = new_score
                        if delta >= 50:
                            play_ding()
                            last_line_clear = time.time()
                    except Exception:
                        pass
                if "Game over" in line:
                    game_over_flag = True
        except Exception:
            pass
        time.sleep(0.05)

threading.Thread(target=serial_reader, daemon=True).start()

# ─── Mic thread ──────────────────────────────────────────
def mic_thread():
    global mic_level, last_rotate_time

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1,
                    rate=RATE, input=True,
                    frames_per_buffer=CHUNK)
    print("Mic running — shout to rotate! Louder = more rotations")

    last_vol_send = 0

    while True:
        try:
            data    = stream.read(CHUNK, exception_on_overflow=False)
            samples = struct.unpack(f"{CHUNK}h", data)
            peak    = max(abs(s) for s in samples)

            if peak < SILENCE_THRESHOLD:
                mic_level = 0
            else:
                mic_level = min(10, int(
                    math.log10(peak / SILENCE_THRESHOLD + 1) /
                    math.log10(33) * 10 + 1
                ))

            now = time.time()
            if now - last_vol_send > 0.1:
                last_vol_send = now
                try:
                    with serial_lock:
                        esp.write(f"{mic_level}\n".encode())
                except Exception:
                    pass

            if game_started and mic_level >= 6:
                now = time.time()
                if now - last_rotate_time > ROTATE_COOLDOWN:
                    last_rotate_time = now
                    try:
                        with serial_lock:
                            esp.write(b'U')
                    except Exception:
                        pass
                    print(f"  >> ROTATE (mic level {mic_level})")

        except Exception as e:
            print(f"Mic error: {e}")
            time.sleep(0.1)
            continue

    stream.stop_stream()
    stream.close()
    p.terminate()

threading.Thread(target=mic_thread, daemon=True).start()

# ─── Hand landmark connections ───────────────────────────
CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),
    (9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),
    (0,17),
]

def get_palm_center(landmarks):
    xs = [landmarks[i].x for i in PALM_LANDMARKS]
    ys = [landmarks[i].y for i in PALM_LANDMARKS]
    return sum(xs) / len(xs), sum(ys) / len(ys)

def draw_landmarks(frame, landmarks):
    h, w, _ = frame.shape
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (0, 200, 255), 2)
    for (x, y) in pts:
        cv2.circle(frame, (x, y), 4, (0, 255, 0), -1)
    for i in PALM_LANDMARKS:
        cv2.circle(frame, pts[i], 7, (0, 100, 255), -1)

# ─── Input thread — listens for SPACE without blocking camera loop ────
def input_thread():
    global space_pressed
    import sys, tty, termios
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == ' ':
                space_pressed = True
            elif ch in ('\x03', '\x1b'):   # Ctrl+C or Escape → clean exit
                handle_exit(None, None)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

threading.Thread(target=input_thread, daemon=True).start()

# ─── Start game ──────────────────────────────────────────
def start_game():
    global game_started, game_over_flag, x_side, y_side, last_line_clear
    game_over_flag = False
    x_side = 0
    y_side = 0
    if hasattr(serial_reader, "last_score"):
        serial_reader.last_score = 0
    with serial_lock:
        esp.write(b'S')
    game_started = True
    pygame.mixer.music.play(-1)
    last_line_clear = time.time()
    print("Game started!")

# ─── Camera setup ────────────────────────────────────────
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
print("Warming up camera..."); time.sleep(2)
for _ in range(10): cap.read()

print("\n" + "="*50)
print("  TETRIS CONTROLLER — ready")
print("  Press SPACE to start the game...")
print("="*50 + "\n")

# ─── Camera loop ─────────────────────────────────────────
while True:

    # ── Game over handler ─────────────────────────────────
    if game_over_flag and game_started:
        game_started = False
        insult_channel.stop()
        pygame.mixer.music.stop()
        print("  >> GAME OVER — playing Arena Hall (press SPACE to restart)")
        if gameover_sound:
            gameover_sound.set_volume(1.0)
            insult_channel.play(gameover_sound)

    # ── SPACE pressed ─────────────────────────────────────
    if space_pressed:
        space_pressed = False
        insult_channel.stop()      # stop gameover audio immediately
        pygame.mixer.music.stop()  # clean slate before restarting
        start_game()

    ret, frame = cap.read()
    if not ret or frame is None:
        time.sleep(0.05); continue

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape
    cx, cy = int(CENTER_X * w), int(CENTER_Y * h)

    cv2.ellipse(frame, (cx,cy), (int(0.10*w), int(0.14*h)), 0, 0, 360, (100,100,255), 2)
    cv2.ellipse(frame, (cx,cy), (int(X_TRIGGER*w), int(Y_TRIGGER*h)), 0, 0, 360, (50,50,180), 2)
    cv2.drawMarker(frame, (cx,cy), (255,255,255), cv2.MARKER_CROSS, 20, 2)

    bar_color = (0, 200, 0) if mic_level < 4 else \
                (0, 165, 255) if mic_level < 7 else \
                (0, 0, 255)
    cv2.rectangle(frame, (w-30, h-10), (w-10, h-10 - mic_level * 8), bar_color, -1)
    cv2.rectangle(frame, (w-30, h-90), (w-10, h-10), (80,80,80), 1)
    cv2.putText(frame, "VOL", (w-34, h-95),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180,180,180), 1)
    cv2.line(frame, (w-30, h-10 - 4*8), (w-10, h-10 - 4*8), (255,255,255), 1)

    detect_frame = cv2.resize(frame, (640, 360))
    rgb = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2RGB)
    res = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))

    gesture_label = "No hand" if not game_started else "Center — swipe to play"

    if res.hand_landmarks and game_started:
        lm = res.hand_landmarks[0]
        draw_landmarks(frame, lm)

        wx, wy = get_palm_center(lm)
        dx = wx - CENTER_X
        dy = wy - CENTER_Y

        cv2.circle(frame, (int(wx*w), int(wy*h)), 12, (0,255,255), -1)
        cv2.putText(frame, f"dx:{dx:+.3f} dy:{dy:+.3f}", (10, h-35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,0), 1)

        gesture_label = "Center — swipe to play"

        new_x_side = 0
        if dx > X_TRIGGER:    new_x_side = 1
        elif dx < -X_TRIGGER: new_x_side = -1

        # Only fire when crossing from neutral (0) into a side — not on return
        if new_x_side != 0 and x_side == 0:
            if new_x_side == 1:
                send("RIGHT", "R")
            else:
                send("LEFT", "L")
        x_side = new_x_side

        if new_x_side == 0:
            new_y_side = 0
            if dy > Y_TRIGGER: new_y_side = 1
            if new_y_side != 0 and new_y_side != y_side:
                send("DROP", "D")
                gesture_label = ">> DROP"
            y_side = new_y_side
        else:
            y_side = 0

    elif not res.hand_landmarks:
        x_side = 0
        y_side = 0

    if not game_started:
        cv2.putText(frame, "Press SPACE to start", (cx - 170, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 100), 2)


    cv2.imshow("Tetris Controller", frame)
    cv2.waitKey(1)
