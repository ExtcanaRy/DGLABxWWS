import io
import json
import time
import qrcode
import random
import asyncio
import threading
import netifaces
import tkinter as tk
from ctypes import windll
from data import data_path, EAT_TORPEDO_RATE, PULSE_DATA
from PIL import Image, ImageTk
from pydglab_ws import StrengthData, FeedbackButton, Channel, StrengthOperationType, RetCode, DGLabWSServer

g_client = None

dmg_prev = 0

g_exit = 0
g_eat_torpedo = 0

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
        self.root.geometry(f"+{screen_width-160}+0")  # 设置窗口位置，紧贴右上角

        self.root.wm_attributes("-transparentcolor", "black")  # 设置透明色

        self.label = tk.Label(root, text="", font=("Microsoft YaHei", 11), fg="white", bg="black")
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
    if g_client.not_bind:
        root.after(500, qr_timer, root)
    else:
        root.destroy()


def show_qrcode(data: str):
    qr = qrcode.QRCode()
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save("qrcode.png")

    root = tk.Tk(className="QRCode")
    root.title("请使用郊狼APP在Socket模式扫描此二维码")

    image = Image.open("qrcode.png")
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


def print_qrcode(data: str):
    """输出二维码到终端界面"""
    qr = qrcode.QRCode()
    qr.add_data(data)
    f = io.StringIO()
    qr.print_ascii(out=f)
    f.seek(0)
    print(f.read())


def show_status():
    root = tk.Tk(className="Status")
    display = StatusDisplay(root)

    def update():
        # 当前/最大/最小/吃雷
        display.label.config(text=f"{strength_a}/{strength_limit["a_max"]}/{strength_limit["a_min"]}/{g_eat_torpedo}")
        root.after(500, update)

    update()
    root.mainloop()


async def strength_ctrl(channel: Channel, strength: int):
    await g_client.set_strength(channel, StrengthOperationType.SET_TO, strength)


async def pulse_ctrl(channel: Channel, pulse_name: str):
    await g_client.add_pulses(channel, *(PULSE_DATA[pulse_name] * 5))


async def strength_ctrl_init():
    strength_init = 0
    while strength_init <= strength_limit["a_min"] and strength_init <= strength_limit["b_min"]:
        await strength_ctrl(Channel.A, strength_init)
        await strength_ctrl(Channel.B, strength_init)
        strength_init += 1
        await asyncio.sleep(0.25)
    strength_init = 0


async def strength_ctrl_loop():
    global strength_a, strength_b
    await strength_ctrl_init()
    while g_exit == 0:
        while strength_a <= strength_limit["a_max"] and strength_b <= strength_limit["b_max"]:
            await strength_ctrl(Channel.A, strength_a)
            await strength_ctrl(Channel.B, strength_b)
            strength_a += 1
            strength_b += 1
            await asyncio.sleep(0.15)
        strength_a -= 1
        strength_b -= 1

        delay_high = random.randint(0, 3)
        if delay_high == 0:
            delay_high = 10
        await asyncio.sleep(delay_high)

        while strength_a >= strength_limit["a_min"] and strength_b >= strength_limit["b_min"]:
            await strength_ctrl(Channel.A, strength_a)
            await strength_ctrl(Channel.B, strength_b)
            strength_a -= 1
            strength_b -= 1
            await asyncio.sleep(0.2)
        strength_a += 1
        strength_b += 1

        delay_low = random.randint(30, 40)
        await asyncio.sleep(delay_low)

        rest_probability = random.randint(0, 100)
        if rest_probability <= 40:
            await strength_ctrl(Channel.A, 0)
            await strength_ctrl(Channel.B, 0)
            await asyncio.sleep(30)
            await strength_ctrl_init()


async def wave_ctrl_loop():
    while g_exit == 0:
        await pulse_ctrl(Channel.A, "快速按捏")
        await pulse_ctrl(Channel.B, "快速按捏")
        await asyncio.sleep(1)


def set_strength_limit(key: str, value: int):
    global strength_limit
    strength_limit[key] = strength_limit_init[key] + int(value)


def read_game_data():
    data = {"hp_pct": None, "dmg": None, "eat_torpedo": None}
    with open(data_path, "r") as f:
        while data["hp_pct"] == None and data["dmg"] == None and data["eat_torpedo"] == None:
            try:
                data.update(json.loads(f.read()))
            except json.decoder.JSONDecodeError:
                data = {"hp_pct": None, "dmg": None, "eat_torpedo": None}
                f.seek(0, 0)
            time.sleep(0.1)

    return data["hp_pct"], data["dmg"], data["eat_torpedo"]


def control_algorithm(hp_pct, dmg, eat_torpedo):
    global strength_limit, g_eat_torpedo
    g_eat_torpedo = eat_torpedo
    eat_torpedo_add = eat_torpedo * EAT_TORPEDO_RATE
    dmg_reduct_rate = 0
    switch_val = 60000
    if dmg > 100000:
        dmg_reduct_rate = 100000 / dmg
    try:
        if dmg < switch_val and hp_pct > 0.8:     # 满血打出伤害，则加上下限
            set_strength_limit("a_max", dmg / 10000 * 3 + eat_torpedo_add)
            set_strength_limit("a_min", dmg / 10000 * 0.5 + eat_torpedo_add)
            set_strength_limit("b_max", dmg / 10000 * 3 + eat_torpedo_add)
            set_strength_limit("b_min", dmg / 10000 * 0.5 + eat_torpedo_add)
        elif dmg > switch_val and hp_pct > 0.8:
            set_strength_limit("a_max", (dmg - switch_val) / 10000 * 3 + 10 + eat_torpedo_add)
            set_strength_limit("a_min", (dmg - switch_val) / 10000 * 1 + 10 + eat_torpedo_add)
            set_strength_limit("b_max", (dmg - switch_val) / 10000 * 3 + 10 + eat_torpedo_add)
            set_strength_limit("b_min", (dmg - switch_val) / 10000 * 1 + 10 + eat_torpedo_add)
        elif hp_pct < 0.8 and hp_pct > 0.4:
            set_strength_limit("a_max", ((1 - hp_pct) / 0.04 * 2.5) - (dmg / 10000 * 2 * dmg_reduct_rate) + eat_torpedo_add)
            set_strength_limit("a_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5 * dmg_reduct_rate) + eat_torpedo_add)
            set_strength_limit("b_max", ((1 - hp_pct) / 0.04 * 2.5) - (dmg / 10000 * 2 * dmg_reduct_rate) + eat_torpedo_add)
            set_strength_limit("b_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5 * dmg_reduct_rate) + eat_torpedo_add)
        elif hp_pct < 0.4:
            set_strength_limit("a_max", ((1 - hp_pct) / 0.04 * 1.5) - (dmg / 10000 * 2) + 20 + eat_torpedo_add)
            set_strength_limit("a_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5) + 5 + eat_torpedo_add)
            set_strength_limit("b_max", ((1 - hp_pct) / 0.04 * 1.5) - (dmg / 10000 * 2) + 20 + eat_torpedo_add)
            set_strength_limit("b_min", ((1 - hp_pct) / 0.04 * 0.5) - (dmg / 10000 * 0.5) + 5 + eat_torpedo_add)
    except TypeError:
        strength_limit.update(strength_limit_init)


def get_game_data():
    global strength_limit
    while g_exit == 0:
        hp_pct, dmg, eat_torpedo = read_game_data()

        control_algorithm(hp_pct, dmg, eat_torpedo)
        # 防止上下限小于默认值
        if all(strength_limit_init[k] > strength_limit[k] for k in strength_limit):
            strength_limit.update(strength_limit_init)
        # 防止上下限大于最大值
        if all(strength_limit_max[k] < strength_limit[k] for k in strength_limit):
            strength_limit.update(strength_limit_max)

        # print("cur:", strength_a, "hp_pct:", hp_pct, "dmg:", dmg, "ua:", strength_limit["a_max"], "ub:",
        #       strength_limit["b_max"], "da:", strength_limit["a_min"], "db:", strength_limit["b_min"])
        
        time.sleep(1)


def show_info(url: str):
    print(url)
    print_qrcode(url)
    show_qrcode(url)
    show_status()


async def main():
    global g_client
    async with DGLabWSServer("0.0.0.0", 5678, 60) as server:
        client = server.new_local_client()
        g_client = client
        gateway_lst = netifaces.gateways()
        ip = netifaces.ifaddresses(gateway_lst["default"][netifaces.AF_INET][1])[netifaces.AF_INET][0]["addr"]

        url = client.get_qrcode(f"ws://{ip}:5678")
        print("请用 DG-Lab App 扫描二维码以连接")
        threading.Thread(target=show_info, args=(url,), daemon=True).start()

        threading.Thread(target=get_game_data, daemon=True).start()
        loop.create_task(strength_ctrl_loop())
        loop.create_task(wave_ctrl_loop())

        await client.bind()
        print(f"已与 App {client.target_id} 成功绑定")

        async for data in client.data_generator():
            if isinstance(data, StrengthData):
                pass
            elif isinstance(data, FeedbackButton):
                pass
            elif data == RetCode.CLIENT_DISCONNECTED:
                print("App 已断开连接")
                loop.stop()


if __name__ == "__main__":
    loop.create_task(main())
    loop.run_forever()
