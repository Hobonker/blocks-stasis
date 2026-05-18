import cv2, mediapipe as mp, time, os, urllib.request, serial
import pyaudio, struct, math, threading, random, signal
import pygame
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

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

click_sound = load_sound("soundeffects/click.wav")
ding_sound  = load_sound("soundeffects/ding.wav")

if os.path.exists("soundeffects/791018.mp3"):
    pygame.mixer.music.load("soundeffects/791018.mp3")
    pygame.mixer.music.set_volume(MUSIC_VOLUME)
    pygame.mixer.music.play(-1)
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
        if f.lower().endswith(supported)
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
        if not insult_files:
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
            pygame.mixer.music.unpause()
        except Exception as e:
            print(f"  Insult play error: {e}")
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
cap               = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)

# ─── Clean exit ──────────────────────────────────────────
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
    global last_line_clear
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

            # Send mic level to ESP32 for volume bar — rate limited to
            # every 100ms so it doesn't flood serial, and wrapped in its
            # own try/except so a serial hiccup can't kill the thread.
            now = time.time()
            if now - last_vol_send > 0.1:
                last_vol_send = now
                try:
                    with serial_lock:
                        esp.write(f"{mic_level}\n".encode())
                except Exception:
                    pass  # serial hiccup — ignore, don't die

            if mic_level >= 6:
                now = time.time()
                if now - last_rotate_time > ROTATE_COOLDOWN:
                    last_rotate_time = now
                    rotations = min(4, max(1, (mic_level - 3) // 2))
                    for _ in range(rotations):
                        try:
                            with serial_lock:
                                esp.write(b'U')
                        except Exception:
                            pass
                        time.sleep(0.08)
                    print(f"  >> ROTATE x{rotations} (mic level {mic_level})")

        except Exception as e:
            print(f"Mic error: {e}")
            time.sleep(0.1)
            continue  # keep thread alive instead of dying on any error

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

# ─── Camera loop ─────────────────────────────────────────
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
print("Warming up camera..."); time.sleep(2)
for _ in range(10): cap.read()
print("Running — swipe L/R to move, swipe down to drop, shout to rotate!")

while True:
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

    if time.time() - last_line_clear > NO_CLEAR_WARNING:
        cv2.putText(frame, "CLEAR A LINE!", (cx - 120, cy - 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)

    detect_frame = cv2.resize(frame, (640, 360))
    rgb = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2RGB)
    res = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))

    gesture_label = "No hand"

    if res.hand_landmarks:
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

        if new_x_side != 0 and new_x_side != x_side:
            if new_x_side == 1:
                send("LEFT", "L")
                gesture_label = ">> LEFT"
            else:
                send("RIGHT", "R")
                gesture_label = ">> RIGHT"
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

    else:
        x_side = 0
        y_side = 0
        gesture_label = "No hand"

    cv2.putText(frame, gesture_label, (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,100), 2)
    cv2.putText(frame, "Shout = rotate (louder = more) | Ctrl+C to quit", (10, h-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180,180,180), 1)
    cv2.imshow("Tetris Controller", frame)
    cv2.waitKey(1)
