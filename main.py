# -*- coding: utf-8 -*-
"""
万方科研诚信培训平台 · 自动刷课工具（GUI）

功能：
  1. 自动打开活动页，检测播放进度
  2. 播放进度 100% 自动切换下一课时
  3. 整门课程结束后自动切换到下一门课程
"""

import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import engine

APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CFG = {
    "url": "https://cx.wanfangdata.com.cn/e-training/activity/info?aId=24fc4810-f096-4f49-b039-8682c5e2c388",
    "browser": "edge",
    "driver_path": "",
    "phone": "",
    "password": "",
    "rate": 1,
    "poll": 3,
    "need_duration": True,
    "duration_threshold": 90,
    "mute": True,
    "close_browser": False,
    "login_timeout": 600,
    "record_dir": os.path.join(APP_DIR, "record"),
}


class App(object):
    def __init__(self, root):
        self.root = root
        self.cfg = dict(DEFAULT_CFG)
        self.load_cfg()

        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None

        root.title("万方培训 · 自动刷课")
        root.geometry("940x660")
        root.minsize(860, 600)

        self._build()
        self.root.after(200, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- 配置 ----------
    def load_cfg(self):
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.cfg.update({k: v for k, v in data.items() if k in DEFAULT_CFG})
        except Exception:
            pass
        # 旧版本把「分钟」直接写进了秒字段，这里做兼容修正
        try:
            lt = int(self.cfg.get("login_timeout") or 0)
        except Exception:
            lt = 0
        if lt < 60:
            lt = lt * 60 if lt > 0 else 600
        self.cfg["login_timeout"] = lt
        if not self.cfg.get("record_dir"):
            self.cfg["record_dir"] = os.path.join(APP_DIR, "record")

    def save_cfg(self):
        data = {
            "url": self.var_url.get().strip(),
            "browser": self.var_browser.get(),
            "driver_path": self.var_driver.get().strip(),
            "phone": self.var_phone.get().strip(),
            "password": self.var_pwd.get(),
            "rate": float(self.var_rate.get()),
            "poll": int(self.var_poll.get()),
            "need_duration": bool(self.var_need_dur.get()),
            "duration_threshold": int(self.var_th.get()),
            "mute": bool(self.var_mute.get()),
            "close_browser": bool(self.var_close.get()),
            "login_timeout": int(self.var_login.get()) * 60,
            "record_dir": self.cfg.get("record_dir"),
        }
        self.cfg.update(data)
        try:
            with open(CFG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 界面 ----------
    def _build(self):
        pad = {"padx": 6, "pady": 4}

        frm = ttk.LabelFrame(self.root, text="配置")
        frm.pack(fill="x", padx=10, pady=(10, 4))

        r = ttk.Frame(frm)
        r.pack(fill="x", **pad)
        ttk.Label(r, text="活动地址").pack(side="left")
        self.var_url = tk.StringVar(value=self.cfg["url"])
        ttk.Entry(r, textvariable=self.var_url).pack(side="left", fill="x", expand=True, padx=6)

        r = ttk.Frame(frm)
        r.pack(fill="x", **pad)
        ttk.Label(r, text="账号(手机号)").pack(side="left")
        self.var_phone = tk.StringVar(value=self.cfg["phone"])
        ttk.Entry(r, textvariable=self.var_phone, width=18).pack(side="left", padx=(6, 14))
        ttk.Label(r, text="密码").pack(side="left")
        self.var_pwd = tk.StringVar(value=self.cfg["password"])
        ttk.Entry(r, textvariable=self.var_pwd, width=18, show="*").pack(side="left", padx=6)
        ttk.Label(r, text="（留空则手动登录）", foreground="#888").pack(side="left")

        r = ttk.Frame(frm)
        r.pack(fill="x", **pad)
        ttk.Label(r, text="浏览器").pack(side="left")
        self.var_browser = tk.StringVar(value=self.cfg["browser"])
        ttk.Combobox(r, textvariable=self.var_browser, values=["edge", "chrome"], width=8,
                     state="readonly").pack(side="left", padx=6)
        ttk.Label(r, text="驱动路径(可选)").pack(side="left", padx=(10, 0))
        self.var_driver = tk.StringVar(value=self.cfg["driver_path"])
        ttk.Entry(r, textvariable=self.var_driver).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(r, text="选择", width=6, command=self.pick_driver).pack(side="left")

        r = ttk.Frame(frm)
        r.pack(fill="x", **pad)
        ttk.Label(r, text="倍速").pack(side="left")
        self.var_rate = tk.StringVar(value=str(self.cfg["rate"]))
        self.cmb_rate = ttk.Combobox(r, textvariable=self.var_rate, width=6, state="readonly",
                                     values=["1", "1.25", "1.5", "2", "3", "4"])
        self.cmb_rate.pack(side="left", padx=6)
        ttk.Label(r, text="轮询(秒)").pack(side="left", padx=(10, 0))
        self.var_poll = tk.StringVar(value=str(self.cfg["poll"]))
        ttk.Combobox(r, textvariable=self.var_poll, width=4, state="readonly",
                     values=["2", "3", "5", "10"]).pack(side="left", padx=6)

        self.var_need_dur = tk.BooleanVar(value=self.cfg["need_duration"])
        self.chk_dur = ttk.Checkbutton(r, text="兼顾时长进度 ≥", variable=self.var_need_dur,
                                       command=self.on_need_dur)
        self.chk_dur.pack(side="left", padx=(12, 0))
        self.var_th = tk.StringVar(value=str(self.cfg["duration_threshold"]))
        self.cmb_th = ttk.Combobox(r, textvariable=self.var_th, width=4, state="readonly",
                                   values=["80", "90", "95", "100"])
        self.cmb_th.pack(side="left", padx=4)
        ttk.Label(r, text="%").pack(side="left")

        r = ttk.Frame(frm)
        r.pack(fill="x", **pad)
        self.var_mute = tk.BooleanVar(value=self.cfg["mute"])
        ttk.Checkbutton(r, text="静音", variable=self.var_mute).pack(side="left")
        self.var_close = tk.BooleanVar(value=self.cfg["close_browser"])
        ttk.Checkbutton(r, text="完成后关闭浏览器", variable=self.var_close).pack(side="left", padx=12)
        ttk.Label(r, text="登录等待(分)").pack(side="left", padx=(10, 0))
        self.var_login = tk.StringVar(value=str(max(1, int(self.cfg["login_timeout"]) // 60)))
        ttk.Combobox(r, textvariable=self.var_login, width=4, state="readonly",
                     values=["3", "5", "10", "20", "30"]).pack(side="left", padx=6)

        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=10, pady=6)
        self.btn_start = ttk.Button(bar, text="开始刷课", command=self.on_start)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="停止", command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=8)
        self.btn_diag = ttk.Button(bar, text="页面诊断", command=self.on_diagnose)
        self.btn_diag.pack(side="left", padx=8)
        ttk.Button(bar, text="打开记录目录", command=self.open_record).pack(side="left", padx=8)
        self.var_state = tk.StringVar(value="就绪")
        ttk.Label(bar, textvariable=self.var_state, foreground="#0a6").pack(side="right")

        self.txt = ScrolledText(self.root, height=24, font=("Consolas", 9), wrap="word",
                                bg="#fbfbfb", fg="#222", relief="solid", borderwidth=1)
        self.txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.txt.configure(state="disabled")

        self.on_need_dur()

    def on_need_dur(self):
        if self.var_need_dur.get():
            self.cmb_rate.configure(state="disabled")
            self.var_rate.set("1")
            self.cmb_th.configure(state="readonly")
        else:
            self.cmb_rate.configure(state="readonly")
            self.cmb_th.configure(state="disabled")

    def pick_driver(self):
        p = filedialog.askopenfilename(title="选择浏览器驱动",
                                       filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")])
        if p:
            self.var_driver.set(p)

    def open_record(self):
        d = self.cfg.get("record_dir") or os.path.join(APP_DIR, "record")
        os.makedirs(d, exist_ok=True)
        try:
            os.startfile(d)
        except Exception:
            pass

    # ---------- 日志 ----------
    def log(self, msg):
        self.q.put(("log", msg))

    def state(self, msg):
        self.q.put(("state", msg))

    def _drain(self):
        try:
            while True:
                kind, msg = self.q.get_nowait()
                if kind == "log":
                    self.txt.configure(state="normal")
                    self.txt.insert("end", "%s  %s\n" % (engine.now_str(), msg))
                    self.txt.see("end")
                    self.txt.configure(state="disabled")
                elif kind == "state":
                    self.var_state.set(msg)
                elif kind == "done":
                    self.btn_start.configure(state="normal")
                    self.btn_diag.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(200, self._drain)

    # ---------- 运行 ----------
    def on_start(self):
        self._start(diagnose=False)

    def on_diagnose(self):
        self._start(diagnose=True)

    def _start(self, diagnose=False):
        if self.worker and self.worker.is_alive():
            return
        self.save_cfg()
        if not self.var_url.get().strip():
            messagebox.showwarning("提示", "请填写活动地址")
            return

        self.stop_event.clear()
        self.btn_start.configure(state="disabled")
        self.btn_diag.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.var_state.set("启动中…")
        cfg = dict(self.cfg)
        cfg["app_dir"] = APP_DIR
        cfg["diagnose_only"] = diagnose

        if diagnose:
            self.log("======== 页面诊断 ========")
            self.log("诊断会打开页面并等待登录，完成后在当前目录生成 debug_*.txt")
        else:
            self.log("======== 开始运行 ========")
            if self.var_need_dur.get():
                self.log("模式：兼顾时长进度（1 倍速）。平台完成条件为「播放进度 + 时长进度」，时长按真实时间累计。")
            else:
                self.log("模式：极速（%.2f 倍速，仅按播放进度 100%% 切课）。注意：可能只记录播放进度，不判定完成。"
                         % float(self.var_rate.get()))

        runner = engine.Runner(cfg, self.log, self.state, self.stop_event)
        self.worker = threading.Thread(target=self._run, args=(runner,), daemon=True)
        self.worker.start()

    def _run(self, runner):
        try:
            runner.run()
        except Exception as e:
            self.log("线程异常：%s" % e)
        finally:
            self.q.put(("done", None))

    def on_stop(self):
        if self.worker and self.worker.is_alive():
            self.log("正在停止…")
            self.stop_event.set()
            self.var_state.set("停止中…")

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("退出", "任务正在运行，确定退出？"):
                return
            self.stop_event.set()
        self.save_cfg()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if sys.platform.startswith("win"):
            style.theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
