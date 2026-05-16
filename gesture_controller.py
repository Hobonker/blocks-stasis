import cv2, mediapipe as mp, time, os, urllib.request
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from pynput.keyboard import Controller, Key

MODEL_PATH = "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
if not os.path.exists(MODEL_PATH):
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

detector = vision.HandLandmarker.create_from_options(
    vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=1,
        min_hand_detection_confidence=0.75,
        min_hand_presence_confidence=0.75,
        min_tracking_confidence=0.65,
    )
)
keyboard = Controller()

COOLDOWN     = 0.45
POSE_FRAMES  = 15
X_NEUTRAL    = 0.10   # dead zone from center, x axis
X_TRIGGER    = 0.18   # trigger threshold, x axis (smaller = easier)
Y_NEUTRAL    = 0.14
Y_TRIGGER    = 0.22

CENTER_X = 0.5
CENTER_Y = 0.58

x_state    = "neutral"
y_state    = "neutral"
pose_count = {"fist": 0}
last_fired = {}

CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),
    (9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),
    (0,17),
]

def draw_landmarks(frame, landmarks):
    h, w, _ = frame.shape
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (0, 200, 255), 2)
    for (x, y) in pts:
        cv2.circle(frame, (x, y), 4, (0, 255, 0), -1)

def extended(lm):
    return [lm[t].y < lm[m].y for t,m in [(8,6),(12,10),(16,14),(20,18)]]

def is_fist(lm): return not any(extended(lm))

def fire(name, key, hold=False):
    if time.time() - last_fired.get(name, 0) < COOLDOWN:
        return False
    last_fired[name] = time.time()
    if hold:
        keyboard.press(key); time.sleep(0.05); keyboard.release(key)
    else:
        keyboard.tap(key)
    print(f"  >> {name}")
    return True

cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
print("Warming up..."); time.sleep(2)
for _ in range(10): cap.read()
print("Running — hold wrist near center cross, swipe out past ellipse then return")

while True:
    ret, frame = cap.read()
    if not ret or frame is None:
        time.sleep(0.05); continue

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape
    cx, cy = int(CENTER_X * w), int(CENTER_Y * h)

    # Draw asymmetric zones as ellipses
    cv2.ellipse(frame, (cx,cy), (int(X_NEUTRAL*w), int(Y_NEUTRAL*h)), 0, 0, 360, (100,100,255), 2)
    cv2.ellipse(frame, (cx,cy), (int(X_TRIGGER*w), int(Y_TRIGGER*h)), 0, 0, 360, (50,50,200), 2)
    cv2.drawMarker(frame, (cx,cy), (255,255,255), cv2.MARKER_CROSS, 20, 2)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))

    gesture_label = "No hand"

    if res.hand_landmarks:
        lm = res.hand_landmarks[0]
        draw_landmarks(frame, lm)
        wx, wy = lm[0].x, lm[0].y
        dx = wx - CENTER_X
        dy = wy - CENTER_Y

        # Show live dx/dy so we can tune
        cv2.putText(frame, f"dx:{dx:+.3f} dy:{dy:+.3f}", (10, h-35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200,200,0), 1)

        # Wrist dot — color shows zone
        in_neutral = abs(dx) < X_NEUTRAL and abs(dy) < Y_NEUTRAL
        dot_color = (0,255,0) if in_neutral else (0,100,255)
        cv2.circle(frame, (int(wx*w), int(wy*h)), 10, dot_color, -1)

        # X axis state machine
        if x_state == "neutral":
            if dx > X_TRIGGER:   x_state = "armed_right"
            elif dx < -X_TRIGGER: x_state = "armed_left"
            gesture_label = "Center"
        elif x_state == "armed_right":
            gesture_label = ">> armed RIGHT — return to center"
            if in_neutral:
                fire("RIGHT", Key.right)
                x_state = "neutral"
        elif x_state == "armed_left":
            gesture_label = ">> armed LEFT — return to center"
            if in_neutral:
                fire("LEFT", Key.left)
                x_state = "neutral"

        # Y axis (only when x neutral)
        if x_state == "neutral":
            if y_state == "neutral":
                if dy < -Y_TRIGGER:  y_state = "armed_up"
                elif dy > Y_TRIGGER: y_state = "armed_down"
            elif y_state == "armed_up":
                gesture_label = ">> armed UP — return to center"
                if in_neutral:
                    fire("ROTATE", Key.up)
                    y_state = "neutral"
            elif y_state == "armed_down":
                gesture_label = ">> armed DOWN — return to center"
                if in_neutral:
                    fire("SOFT DROP", Key.down)
                    y_state = "neutral"

        # Fist = hard drop
        if is_fist(lm):
            pose_count["fist"] += 1
            gesture_label = f"Fist {pose_count['fist']}/{POSE_FRAMES}"
            if pose_count["fist"] >= POSE_FRAMES:
                if fire("HARD DROP", Key.space, hold=True):
                    pose_count["fist"] = 0
        else:
            pose_count["fist"] = 0

    else:
        x_state = y_state = "neutral"
        pose_count["fist"] = 0
        gesture_label = "No hand"

    cv2.putText(frame, gesture_label, (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,100), 2)
    cv2.putText(frame, f"x_state:{x_state}  y_state:{y_state}", (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
    cv2.putText(frame, "Ctrl+C to quit", (10, h-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180,180,180), 1)

    cv2.imshow("Gesture Controller", frame)
    cv2.waitKey(1)

cap.release()
cv2.destroyAllWindows()
detector.close()
