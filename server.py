import re
import json
import time
import uuid
import qrcode
import random
import asyncio
import threading
import netifaces
import websockets
import tkinter as tk
from ctypes import windll
from sysinfo import data_path
from PIL import Image, ImageTk

server_uuid = str(uuid.uuid4())
client_uuid = ""
clientws: websockets.WebSocketServerProtocol

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

# 初始限制
strength_limit_init = {"a_min": 15, "a_max":30, "b_min": 15, "b_max": 30}
# 最大限制
strength_limit_max = {"a_min": 30, "a_max":80, "b_min": 30, "b_max": 80}
# 当前限制
strength_limit = {"a_min": 15, "a_max":30, "b_min": 15, "b_max": 30}
# 当前强度
strength_a = 15
strength_b = 15


class StatusDisplay:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.title("Status")

        screen_width = root.winfo_screenwidth()
        self.root.geometry(f"+{screen_width-140}+0")  # 设置窗口位置，紧贴右上角

        self.root.wm_attributes("-transparentcolor", "black")  # 设置透明色

        self.label = tk.Label(root, text="", font=("Microsoft YaHei", 9), fg="white", bg="black")
        self.label.pack()

        self.make_window_click_through()

    def make_window_click_through(self):
        GetWindowLongA = windll.user32.GetWindowLongA
        SetWindowLongA = windll.user32.SetWindowLongA
        SetLayeredWindowAttributes = windll.user32.SetLayeredWindowAttributes

        hwnd = self.root.winfo_id()
        style = GetWindowLongA(hwnd, -20)  # 获取当前扩展样式
        style |= 0x00080000 | 0x00000020  # 添加透明和点击穿透样式
        SetWindowLongA(hwnd, -20, style)
        SetLayeredWindowAttributes(hwnd, 0x00000000, 0, 1)


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
                # client msg proc
                if data["type"] == "msg":
                    # get strength data
                    strength_re = re.search(
                        "strength-(\\d*)\\+(\\d*)\\+(\\d*)\\+(\\d*)", data["message"]
                    )
                    if strength_re != None:
                        pass
                if data["type"] == "break":
                    print(f"WebSocket 连接已关闭, client_id: {client_uuid}")
                    g_exit = 1
    except websockets.exceptions.ConnectionClosed:
        print(f"WebSocket 连接已关闭, client_id: {client_uuid}")
        g_exit = 1
        


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


def read_game_data():
    data = {"hp_pct": None, "dmg": None}
    with open(data_path, "r") as f:
        while data["hp_pct"] == None and data["dmg"] == None:
            try:
                data.update(json.loads(f.read()))
            except json.decoder.JSONDecodeError:
                data = {"hp_pct": None, "dmg": None}
                f.seek(0, 0)
            time.sleep(0.1)

    return data["hp_pct"], data["dmg"]


def game_detect():
    global strength_limit
    dmg_reduct_rate = 0
    loop.create_task(strength_ctrl_loop())
    loop.create_task(wave_ctrl_loop())
    while g_exit == 0:
        hp_pct, dmg = read_game_data()

        switch_val = 60000
        if dmg > 100000:
            dmg_reduct_rate = 100000 / dmg
        try:
            if dmg < switch_val and hp_pct > 0.99:     # 满血打出伤害，则加上下限
                set_strength_limit("a_max", dmg / 10000 * 3)
                set_strength_limit("a_min", dmg / 10000 * 0.5)
                set_strength_limit("b_max", dmg / 10000 * 3)
                set_strength_limit("b_min", dmg / 10000 * 0.5)
            elif dmg > switch_val and hp_pct > 0.99:
                set_strength_limit("a_max", (dmg - switch_val) / 10000 * 3 + 10)
                set_strength_limit("a_min", (dmg - switch_val) / 10000 * 1 + 10)
                set_strength_limit("b_max", (dmg - switch_val) / 10000 * 3 + 10)
                set_strength_limit("b_min", (dmg - switch_val) / 10000 * 1 + 10)
            elif hp_pct < 0.99 and hp_pct > 0.5:
                set_strength_limit("a_max", ((1 - hp_pct) / 0.04 * 2.5) - (dmg / 10000 * 2 * dmg_reduct_rate))
                set_strength_limit("a_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5 * dmg_reduct_rate))
                set_strength_limit("b_max", ((1 - hp_pct) / 0.04 * 2.5) - (dmg / 10000 * 2 * dmg_reduct_rate))
                set_strength_limit("b_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5 * dmg_reduct_rate))
            elif hp_pct < 0.5:
                set_strength_limit("a_max", ((1 - hp_pct) / 0.04 * 1.5) - (dmg / 10000 * 2) + 10)
                set_strength_limit("a_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5) + 5)
                set_strength_limit("b_max", ((1 - hp_pct) / 0.04 * 1.5) - (dmg / 10000 * 2) + 10)
                set_strength_limit("b_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5) + 5)
        except TypeError:
            strength_limit.update(strength_limit_init)
        # 防止上下限小于默认值
        if all(strength_limit_init[k] > strength_limit[k] for k in strength_limit):
            strength_limit.update(strength_limit_init)
        # 防止上下限大于最大值
        if all(strength_limit_max[k] < strength_limit[k] for k in strength_limit):
            strength_limit.update(strength_limit_max)

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

    show_qrcode("qrcode.png")
    show_status()


if __name__ == "__main__":
    server_ws = websockets.serve(conn_handler, "", 9999)

    threading.Thread(target=server_main).start()

    loop.run_until_complete(server_ws)
    loop.run_forever()
