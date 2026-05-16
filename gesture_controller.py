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

BUFFER_SIZE  = 18
SWIPE_THRESH = 0.20
COOLDOWN     = 0.45
POSE_FRAMES  = 8

wrist_buf  = []
last_fired = {}
pose_count = {"fist": 0, "palm": 0}

def extended(lm):
    return [lm[t].y < lm[m].y for t,m in [(8,6),(12,10),(16,14),(20,18)]]

def is_fist(lm): return not any(extended(lm))
def is_palm(lm): return all(extended(lm))

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

def check_swipe(buf):
    if len(buf) < BUFFER_SIZE: return None
    dx = buf[-1][0] - buf[0][0]
    dy = buf[-1][1] - buf[0][1]
    if abs(dx) > abs(dy):
        if dx >  SWIPE_THRESH: return "swipe_right"
        if dx < -SWIPE_THRESH: return "swipe_left"
    else:
        if dy >  SWIPE_THRESH: return "swipe_down"
        if dy < -SWIPE_THRESH: return "swipe_up"
    return None

cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
print("Warming up..."); time.sleep(2)
for _ in range(10): cap.read()
print("Running — swipe L/R=move  swipe up=rotate  swipe down=soft drop  fist=hard drop  palm=pause")

while True:
    ret, frame = cap.read()
    if not ret or frame is None:
        time.sleep(0.05); continue

    frame = cv2.flip(frame, 1)
    rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res   = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))

    if res.hand_landmarks:
        lm = res.hand_landmarks[0]
        wrist_buf.append((lm[0].x, lm[0].y))
        if len(wrist_buf) > BUFFER_SIZE: wrist_buf.pop(0)

        swipe = check_swipe(wrist_buf)
        if   swipe == "swipe_left"  and fire("LEFT",      Key.left):  wrist_buf.clear()
        elif swipe == "swipe_right" and fire("RIGHT",     Key.right): wrist_buf.clear()
        elif swipe == "swipe_up"    and fire("ROTATE",    Key.up):    wrist_buf.clear()
        elif swipe == "swipe_down"  and fire("SOFT DROP", Key.down):  wrist_buf.clear()
        else:
            if is_fist(lm):
                pose_count["fist"] += 1; pose_count["palm"] = 0
                if pose_count["fist"] >= POSE_FRAMES:
                    if fire("HARD DROP", Key.space, hold=True):
                        pose_count["fist"] = 0
            elif is_palm(lm):
                pose_count["palm"] = 0; pose_count["fist"] = 0
            else:
                pose_count["fist"] = pose_count["palm"] = 0
    else:
        wrist_buf.clear()
        pose_count["fist"] = pose_count["palm"] = 0
