import re
import os
import json
import time
import uuid
import numpy
import qrcode
import random
import asyncio
import threading
import netifaces
import pytesseract
import websockets
import tkinter as tk
from PIL import Image, ImageTk, ImageGrab, ImageOps, ImageFilter, ImageEnhance
import ctypes
from ctypes import windll, byref, c_ubyte
from ctypes.wintypes import RECT

from sysinfo import bbox_hp, bbox_dmg, tesseract_cmd_path
import tkinter as tk
from ctypes import windll
from collections import Counter

server_uuid = str(uuid.uuid4())
client_uuid = ""
clientws: websockets.WebSocketServerProtocol

dmg_buf = [0, 0, 0, 0, 0]
dmg_buf_idx = 0
dmg_buf_init = 0
dmg_prev = 0

g_exit = 0

wave_data = [
    '["0A0A0A0A00000000","0A0A0A0A0A0A0A0A","0A0A0A0A14141414","0A0A0A0A1E1E1E1E","0A0A0A0A28282828","0A0A0A0A32323232","0A0A0A0A3C3C3C3C","0A0A0A0A46464646","0A0A0A0A50505050","0A0A0A0A5A5A5A5A","0A0A0A0A64646464"]',
    '["0A0A0A0A00000000","0D0D0D0D0F0F0F0F","101010101E1E1E1E","1313131332323232","1616161641414141","1A1A1A1A50505050","1D1D1D1D64646464","202020205A5A5A5A","2323232350505050","262626264B4B4B4B","2A2A2A2A41414141"]',
    '["4A4A4A4A64646464","4545454564646464","4040404064646464","3B3B3B3B64646464","3636363664646464","3232323264646464","2D2D2D2D64646464","2828282864646464","2323232364646464","1E1E1E1E64646464","1A1A1A1A64646464"]'
]

feed_back_msg = {
    "feedback-0": "A通道：○",
    "feedback-1": "A通道：△",
    "feedback-2": "A通道：□",
    "feedback-3": "A通道：☆",
    "feedback-4": "A通道：⬡",
    "feedback-5": "B通道：○",
    "feedback-6": "B通道：△",
    "feedback-7": "B通道：□",
    "feedback-8": "B通道：☆",
    "feedback-9": "B通道：⬡",
}

strength_limit_init = {"a_min": 15, "a_max":30, "b_min": 15, "b_max": 30}
strength_limit_max = {"a_min": 30, "a_max":80, "b_min": 30, "b_max": 80}
strength_limit = {"a_min": 15, "a_max":30, "b_min": 15, "b_max": 30}
strength_a = 15
strength_b = 15


class StatusDisplay:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.title("Status")

        screen_width = root.winfo_screenwidth()
        # print(screen_width)
        self.root.geometry(f"+{screen_width-140}+0")  # 设置窗口位置，紧贴右上角

        self.root.wm_attributes("-transparentcolor", "black")  # 设置透明色

        self.label = tk.Label(root, text="", font=("Microsoft YaHei", 9), fg="white", bg="black")
        self.label.pack()

        self.make_window_click_through()

    def make_window_click_through(self):
        FindWindowA = windll.user32.FindWindowA
        GetWindowLongA = windll.user32.GetWindowLongA
        SetWindowLongA = windll.user32.SetWindowLongA
        SetLayeredWindowAttributes = windll.user32.SetLayeredWindowAttributes

        hwnd = self.root.winfo_id()
        # print(hwnd)
        style = GetWindowLongA(hwnd, -20)  # 获取当前扩展样式
        style |= 0x00080000 | 0x00000020  # 添加透明和点击穿透样式
        SetWindowLongA(hwnd, -20, style)
        SetLayeredWindowAttributes(hwnd, 0x00000000, 0, 1)

    # def update_message(self, message):
    #     self.label.config(text=message)
    #     self.root.after(1000, self.update_message, message)  # 每秒更新一次消息


def capture_window(window_title):
    FindWindowA = windll.user32.FindWindowA
    FindWindowA.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    FindWindowA.restype = ctypes.c_void_p

    hwnd = FindWindowA(None, window_title.encode('gbk'))
    if hwnd == 0:
        raise Exception(f"Window not found: {window_title}")
    
    GetDC = windll.user32.GetDC
    CreateCompatibleDC = windll.gdi32.CreateCompatibleDC
    GetClientRect = windll.user32.GetClientRect
    CreateCompatibleBitmap = windll.gdi32.CreateCompatibleBitmap
    SelectObject = windll.gdi32.SelectObject
    BitBlt = windll.gdi32.BitBlt
    SRCCOPY = 0x00CC0020
    GetBitmapBits = windll.gdi32.GetBitmapBits
    # GetBitmapBits.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
    DeleteObject = windll.gdi32.DeleteObject
    ReleaseDC = windll.user32.ReleaseDC
    windll.user32.SetProcessDPIAware()
    r = RECT()
    GetClientRect(hwnd, byref(r))
    # print(f"win l: {r.left}, r: {r.right}, t: {r.top}, b: {r.bottom}")

    dc = GetDC(hwnd)
    cdc = CreateCompatibleDC(dc)
    bitmap = CreateCompatibleBitmap(dc, r.right, r.bottom)
    SelectObject(cdc, bitmap)
    BitBlt(cdc, 0, 0, r.right, r.bottom, dc, 0, 0, SRCCOPY)
    total_bytes = r.right * r.bottom * 4
    buffer_arr = bytearray(total_bytes)
    buffer = ctypes.c_ubyte * total_bytes
    GetBitmapBits(bitmap, total_bytes, buffer.from_buffer(buffer_arr))
    DeleteObject(bitmap)
    DeleteObject(cdc)
    ReleaseDC(hwnd, dc)
    # print(buffer_arr)
    return Image.frombuffer("RGBA", (r.right, r.bottom), buffer_arr, "raw", "BGRA", 0, 1)


try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def qr_timer(root: tk.Tk):
    if client_uuid != "":
        root.destroy()
    else:
        root.after(500, qr_timer, root)
    

def show_qrcode(image_path: str):
    root = tk.Tk(className="QRCode")
    root.title("请使用郊狼APP在Socket模式扫描此二维码")

    image = Image.open(image_path)
    photo = ImageTk.PhotoImage(image)
    label = tk.Label(root, image=photo)
    label.pack()
    root.update_idletasks()
    # print(root.winfo_screenwidth())
    window_width = root.winfo_width()
    window_height = root.winfo_height()

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    position_top = int((screen_height / 2) - (window_height / 2))
    position_right = int((screen_width / 2) - (window_width / 2))

    root.geometry(f"{window_width}x{window_height}+{position_right}+{position_top}")

    qr_timer(root)

    root.mainloop()

def show_status():
    root = tk.Tk(className="Status")
    display = StatusDisplay(root)

    def update():
        display.label.config(text=f"当前:{strength_a} 最大:{strength_limit["a_max"]} 最小:{strength_limit["a_min"]}")
        root.after(500, update)

    update()
    root.mainloop()

async def conn_handler(websocket: websockets.WebSocketServerProtocol, path):
    global clientws
    global client_uuid
    global g_exit

    print("New conn income")

    # handshk
    print("Sending bind data")
    await websocket.send(
        f'{{"type":"bind","clientId":"{server_uuid}","targetId":"","message":"targetId"}}'
    )
    data = json.loads(await websocket.recv())

    if (
        data["type"] != "bind"
        or data["clientId"] != server_uuid
        or data["message"] != "DGLAB"
    ):
        print(data)
        return -1

    print("Sending bind result")
    await websocket.send(
        f'{{"type":"bind","clientId":"{server_uuid}","targetId":"{client_uuid}","message":"200"}}'
    )

    client_uuid = data["targetId"]
    # handshk finish
    clientws = websocket

    print("Handshk finished.", client_uuid)

    threading.Thread(target=game_detect).start()
    g_exit = 0

    try:
        async for message in websocket:
            # print("收到消息：", message)
            try:
                data = json.loads(
                    message,
                )
            except json.JSONDecodeError:
                await websocket.send(
                    '{"type": "msg", "clientId": "", "targetId": "", "message": "403"}'
                )
                continue

            if (
                data.get("type")
                and data.get("clientId")
                and data.get("message")
                and data.get("targetId")
            ):
                # await msg_handler(websocket, data)
                # client msg proc
                if data["type"] == "msg":
                    # get strength data
                    strength_re = re.search(
                        "strength-(\\d*)\\+(\\d*)\\+(\\d*)\\+(\\d*)", data["message"]
                    )
                    if strength_re != None:
                        # strength_a = strength_re.group(1) # Str A
                        # strength_b = strength_re.group(2) # Str B
                        strength_limit_a = strength_re.group(3)  # Str max A
                        strength_limit_b = strength_re.group(4)  # Str max B
                        # print(f'A: {strength_a}, B: {strength_b}, AM: {strength_limit_a}, BM: {strength_limit_b}')
                if data["type"] == "break":
                    print(f"WebSocket 连接已关闭, client_id: {client_uuid}")
                    g_exit = 1
    except websockets.exceptions.ConnectionClosed:
        print(f"WebSocket 连接已关闭, client_id: {client_uuid}")
        g_exit = 1
        

    # get strength limit
    # data = json.loads(await websocket.recv()) # this can be ignore
    # print(data)


def ocr(bbox, threshold) -> str:
    pytesseract.pytesseract.tesseract_cmd = (tesseract_cmd_path)
    img = capture_window("《战舰世界》").convert("L").crop(bbox)
    
    # enhance
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.8)
    img = img.point(lambda p: p > 253 and 255)

    img = ImageOps.invert(img)

    # 二值化处理
    # if threshold > 0:
    #     img = img.point(lambda p: p > threshold and 255)

    img = ImageOps.invert(img)
    # img = img.filter(ImageFilter.MedianFilter())
    img.save("game.bmp")
    conf = r"--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789/"
    return pytesseract.image_to_string(img, config=conf)


def get_hp_pct() -> float:
    img = capture_window("《战舰世界》").convert("RGB").crop(bbox_hp)
    # img = ImageGrab.grab(bbox=bbox_hp)
    # img = img.convert("RGB")

    img_array = numpy.array(img)
    green_pixels = numpy.logical_and(img_array[:, :, 1] > img_array[:, :, 0], img_array[:, :, 1] > img_array[:, :, 2])
    green_area = numpy.sum(green_pixels)

    total_area = img_array.shape[0] * img_array.shape[1]

    green_percentage = (green_area / total_area)
    return green_percentage


def ocr_dmg() -> int:
    try:
        return int(ocr(bbox_dmg, 0))
    except ValueError:
        return 0


async def strength_ctrl(channel: int, strength: int):
    await clientws.send(
            json.dumps({"type": "msg", "clientId": server_uuid, "targetId": client_uuid, "message": f"strength-{channel}+2+{strength}"})
        )


async def wave_ctrl(channel: str, wave: str):
    await clientws.send(
           json.dumps({"type": "msg", "clientId": server_uuid, "targetId": client_uuid, "message": f"pulse-{channel}:{wave}"})
        )


async def strength_ctrl_init():
    strength_init = 0
    while strength_init <= strength_limit["a_min"] and strength_init <= strength_limit["b_min"]:
        await strength_ctrl(1, strength_init)
        await strength_ctrl(2, strength_init)
        strength_init += 2
        await asyncio.sleep(0.5)
    strength_init = 0


async def strength_ctrl_loop():
    global strength_a, strength_b
    await strength_ctrl_init()
    while g_exit == 0:
        while strength_a <= strength_limit["a_max"] and strength_b <= strength_limit["b_max"]:
            await strength_ctrl(1, strength_a)
            await strength_ctrl(2, strength_b)
            strength_a += 2
            strength_b += 2
            await asyncio.sleep(0.3)
        strength_a -= 2
        strength_b -= 2

        delay_high = random.randint(0, 3)
        if delay_high == 0:
            delay_high = 10
        await asyncio.sleep(delay_high)

        while strength_a >= strength_limit["a_min"] and strength_b >= strength_limit["b_min"]:
            await strength_ctrl(1, strength_a)
            await strength_ctrl(2, strength_b)
            strength_a -= 2
            strength_b -= 2
            await asyncio.sleep(0.4)
        strength_a += 2
        strength_b += 2

        delay_low = random.randint(30, 60)
        await asyncio.sleep(delay_low)

        rest_probability = random.randint(0, 100)
        if rest_probability <= 40:
            await strength_ctrl(1, 0)
            await strength_ctrl(2, 0)
            await asyncio.sleep(60)
            await strength_ctrl_init()


async def wave_ctrl_loop():
    while g_exit == 0:
        await wave_ctrl("A", wave_data[random.randint(0, 2)])
        await wave_ctrl("B", wave_data[random.randint(0, 2)])
        await asyncio.sleep(1)


def set_strength_limit(key: str, value: int):
    global strength_limit
    strength_limit[key] = strength_limit_init[key] + int(value)


def game_detect():
    global strength_limit
    global dmg_buf_idx
    global dmg_buf_init
    global dmg_buf
    global dmg_prev
    loop.create_task(strength_ctrl_loop())
    loop.create_task(wave_ctrl_loop())
    while g_exit == 0:
        hp_pct = get_hp_pct()
        dmg_buf[dmg_buf_idx] = ocr_dmg()
        dmg_buf_idx += 1
        if dmg_buf_idx >= 5:
            dmg_buf_idx = 0

        if dmg_buf_init == 0:
            dmg_buf[1] = dmg_buf[0]
            dmg_buf[2] = dmg_buf[0]
            dmg_buf[3] = dmg_buf[0]
            dmg_buf[4] = dmg_buf[0]
            dmg_buf_init = 1

        counter = Counter(dmg_buf)
        dmg = counter.most_common(1)[0][0]
        
        # 防止伤害异常突变或者减少
        if dmg - dmg_prev >= 150000 or dmg_prev > dmg or dmg > 600000:
            dmg = 0
            dmg_buf[0] = 0
            dmg_buf_init = 0
        dmg_prev = dmg

        switch_val = 60000
        if dmg > 100000:
            dmg_reduct_rate = 100000 / dmg
        try:
            if dmg <= 0:
                pass
            elif dmg < switch_val and hp_pct > 0.9:     # 满血打出伤害，则加上下限
                set_strength_limit("a_max", dmg / 10000 * 3)
                set_strength_limit("a_min", dmg / 10000 * 0.5)
                set_strength_limit("b_max", dmg / 10000 * 3)
                set_strength_limit("b_min", dmg / 10000 * 0.5)
            elif dmg > switch_val and hp_pct > 0.9:
                set_strength_limit("a_max", (dmg - switch_val) / 10000 * 3 + 10)
                set_strength_limit("a_min", (dmg - switch_val) / 10000 * 1 + 10)
                set_strength_limit("b_max", (dmg - switch_val) / 10000 * 3 + 10)
                set_strength_limit("b_min", (dmg - switch_val) / 10000 * 1 + 10)
            elif hp_pct < 0.9 and hp_pct > 0.5:
                set_strength_limit("a_max", ((1 - hp_pct) / 0.04 * 3) - (dmg / 10000 * 2 * dmg_reduct_rate))
                set_strength_limit("a_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5 * dmg_reduct_rate))
                set_strength_limit("b_max", ((1 - hp_pct) / 0.04 * 3) - (dmg / 10000 * 2 * dmg_reduct_rate))
                set_strength_limit("b_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5 * dmg_reduct_rate))
            elif hp_pct < 0.5:
                set_strength_limit("a_max", ((1 - hp_pct) / 0.04 * 1) - (dmg / 10000 * 2) + 38)
                set_strength_limit("a_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5) + 5)
                set_strength_limit("b_max", ((1 - hp_pct) / 0.04 * 1) - (dmg / 10000 * 2) + 38)
                set_strength_limit("b_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5) + 5)
        except TypeError:
            strength_limit.update(strength_limit_init)
        # 防止上下限小于默认值
        if all(strength_limit_init[k] > strength_limit[k] for k in strength_limit):
            strength_limit.update(strength_limit_init)
        # 防止上下限大于最大值
        if all(strength_limit_max[k] < strength_limit[k] for k in strength_limit):
            strength_limit.update(strength_limit_max)
        if dmg == 0:
            strength_limit.update(strength_limit_init)
        print("cur:", strength_a, "hp_pct:", hp_pct, "dmg:", dmg, "ua:", strength_limit["a_max"], "ub:",
              strength_limit["b_max"], "da:", strength_limit["a_min"], "db:", strength_limit["b_min"])
        
        time.sleep(1)

def server_main():
    gateway_lst = netifaces.gateways()
    ip = netifaces.ifaddresses(gateway_lst["default"][netifaces.AF_INET][1])[netifaces.AF_INET][0]["addr"]

    data = (
        "https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#"
        + f"ws://{ip}:9999/"
        + server_uuid
    )
    print(data)
    qr = qrcode.QRCode()
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save("qrcode.png")

    # os.system("adb push qrcode.png /sdcard/DGLAB/")
    show_qrcode("qrcode.png")
    show_status()


if __name__ == "__main__":
    # ocr_dmg()
    server_ws = websockets.serve(conn_handler, "", 9999)

    threading.Thread(target=server_main).start()

    loop.run_until_complete(server_ws)
    loop.run_forever()
