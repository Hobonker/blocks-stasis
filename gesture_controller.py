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
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.7,
        min_tracking_confidence=0.6,
    )
)
keyboard = Controller()

CENTER_X  = 0.5
CENTER_Y  = 0.58
X_TRIGGER = 0.18   # fire when wrist crosses this distance from center horizontally
Y_TRIGGER = 0.22   # fire when wrist crosses this distance from center vertically
COOLDOWN  = 0.50   # min seconds before same gesture can fire again

last_fired = {}
# Track whether we've already fired for the current excursion
x_fired = False
y_fired = False
# Track which side we're on so return trip is ignored
x_side = 0   # -1 left, 0 neutral, +1 right
y_side = 0

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

def fire(name, key):
    now = time.time()
    if now - last_fired.get(name, 0) < COOLDOWN:
        return False
    last_fired[name] = now
    keyboard.tap(key)
    print(f"  >> {name}")
    return True

cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
print("Warming up..."); time.sleep(2)
for _ in range(10): cap.read()
print("Running — swipe out from center: L/R=move  up=rotate")

while True:
    ret, frame = cap.read()
    if not ret or frame is None:
        time.sleep(0.05); continue

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape
    cx, cy = int(CENTER_X * w), int(CENTER_Y * h)

    # Draw zones
    cv2.ellipse(frame, (cx,cy), (int(0.10*w), int(0.14*h)), 0, 0, 360, (100,100,255), 2)
    cv2.ellipse(frame, (cx,cy), (int(X_TRIGGER*w), int(Y_TRIGGER*h)), 0, 0, 360, (50,50,180), 2)
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

        cv2.circle(frame, (int(wx*w), int(wy*h)), 10, (0,255,255), -1)
        cv2.putText(frame, f"dx:{dx:+.3f} dy:{dy:+.3f}", (10, h-35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,0), 1)

        gesture_label = "Center — swipe out to trigger"

        # X axis: fire once when crossing trigger, reset when back near center
        new_x_side = 0
        if dx > X_TRIGGER:   new_x_side = 1
        elif dx < -X_TRIGGER: new_x_side = -1

        if new_x_side != 0 and new_x_side != x_side:
            # Just crossed into a new trigger zone
            if new_x_side == 1:
                fire("RIGHT", Key.right)
                gesture_label = ">> RIGHT"
            else:
                fire("LEFT", Key.left)
                gesture_label = ">> LEFT"
        x_side = new_x_side

        # Y axis: only when not in x trigger zone
        if new_x_side == 0:
            new_y_side = 0
            if dy < -Y_TRIGGER:  new_y_side = -1
            elif dy > Y_TRIGGER: new_y_side = 1

            if new_y_side != 0 and new_y_side != y_side:
                if new_y_side == -1:
                    fire("ROTATE", Key.up)
                    gesture_label = ">> ROTATE"
            y_side = new_y_side
        else:
            y_side = 0

    else:
        x_side = 0
        y_side = 0
        gesture_label = "No hand"

    cv2.putText(frame, gesture_label, (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,100), 2)
    cv2.putText(frame, "Ctrl+C to quit", (10, h-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180,180,180), 1)
    cv2.imshow("Gesture Controller", frame)
    cv2.waitKey(1)

cap.release()
cv2.destroyAllWindows()
detector.close()
