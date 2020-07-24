import wx
import sys
import logging
import time
from pubsub import pub
from console import __version__
from console import threads
from console import environ
from console import arena
from console.exceptions import ConsoleException
from console.config import config
from console.client import client
from console.logging import setup_logging


def _exception_hook(exctype, value, traceback):
    if isinstance(value, ConsoleException):
        if value.logger and not config.get("traceback", False):
            logging.getLogger(value.logger).error(value.msg)
        else:
            logging.getLogger("console").error(value.msg)
    else:
        sys.__excepthook__(exctype, value, traceback)


class UIHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        wx.CallAfter(pub.sendMessage, "logging", msg=msg)


class AppFrame(wx.Frame):
    def __init__(self, *args, **kw):
        # ensure the parent's __init__ is called
        super().__init__(*args, **kw)
        self._thead_container = threads.ThreadContainer()
        self._arena_thread = None
        self.init_ui()
        self.setup_logging()

    def init_ui(self):
        self.Bind(wx.EVT_CLOSE, self.on_close)
        panel = wx.Panel(self)

        font = wx.SystemSettings.GetFont(wx.SYS_SYSTEM_FONT)
        font.SetPointSize(12)

        vbox = wx.BoxSizer(wx.VERTICAL)
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        vbox1 = wx.BoxSizer(wx.VERTICAL)
        self.reboot_button = wx.Button(panel, label="Reboot", size=(100, -1))
        self.reboot_button.SetFont(font)
        self.reboot_button.Bind(wx.EVT_BUTTON, self.reboot)
        vbox1.Add(self.reboot_button)
        button = wx.Button(panel, label="Clear log", size=(100, -1))
        button.SetFont(font)
        button.Bind(wx.EVT_BUTTON, lambda e: self.logger.Clear())
        vbox1.Add(button, 0, wx.TOP, 5)
        hbox.Add(vbox1, 0, wx.EXPAND, 0)

        vbox1 = wx.BoxSizer(wx.VERTICAL)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(panel, label="Arena", size=(40, -1), style=wx.ALIGN_RIGHT)
        label.SetFont(font)
        hbox1.Add(label)
        choice = wx.Choice(panel, choices=["10", "15"], size=(100, -1))
        choice.SetFont(font)
        choice.SetSelection(choice.FindString(str(config.get("arena:type"))))
        choice.Bind(wx.EVT_CHOICE, self.set_arena_type)
        hbox1.Add(choice, 1, wx.LEFT, 10)
        vbox1.Add(hbox1)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(panel, label="Kind", size=(40, -1), style=wx.ALIGN_RIGHT)
        label.SetFont(font)
        hbox1.Add(label)
        choice = wx.Choice(panel, choices=["food", "ticket"], size=(100, -1))
        choice.SetFont(font)
        choice.SetSelection(choice.FindString(str(config.get("arena:kind"))))
        choice.Bind(wx.EVT_CHOICE, self.set_arena_kind)
        hbox1.Add(choice, 1, wx.LEFT, 10)
        vbox1.Add(hbox1, 0, wx.TOP, 7)
        hbox.Add(vbox1, 0, wx.LEFT, 20)

        vbox1 = wx.BoxSizer(wx.VERTICAL)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(panel, label="Max force", size=(60, -1), style=wx.ALIGN_RIGHT)
        label.SetFont(font)
        hbox1.Add(label)
        self.max_force_spin = wx.SpinCtrl(panel, min=0, max=50000000, value=str(config.get("arena:max-force")))
        self.max_force_spin.SetFont(font.Bold())
        self.max_force_spin.Bind(wx.EVT_TEXT, self.set_max_force)
        hbox1.Add(self.max_force_spin, 1, wx.LEFT, 10)
        vbox1.Add(hbox1)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(panel, label="Run count", size=(60, -1), style=wx.ALIGN_RIGHT)
        label.SetFont(font)
        hbox1.Add(label)
        self.run_count_spin = wx.SpinCtrl(panel, min=1, max=99, value=str(config.get("arena:run-count")))
        self.run_count_spin.SetFont(font.Bold())
        self.run_count_spin.Bind(wx.EVT_TEXT, self.set_run_count)
        hbox1.Add(self.run_count_spin, 1, wx.LEFT, 10)
        vbox1.Add(hbox1, 0, wx.TOP, 4)
        hbox.Add(vbox1, 0, wx.LEFT, 20)

        vbox1 = wx.BoxSizer(wx.VERTICAL)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.start_arena_button = wx.Button(panel, label="Start arena", size=(90, -1))
        self.start_arena_button.SetFont(font)
        self.start_arena_button.Bind(wx.EVT_BUTTON, self.start_stop_arena)
        self.start_arena_button.Disable()
        hbox1.Add(self.start_arena_button)
        vbox1.Add(hbox1)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.arena_counter = wx.StaticText(panel, label="", size=(90, -1), style=wx.ALIGN_CENTER)
        self.arena_counter.SetFont(font)
        hbox1.Add(self.arena_counter, 0, wx.TOP, 7)
        vbox1.Add(hbox1)
        hbox.Add(vbox1, 0, wx.LEFT, 20)

        vbox1 = wx.BoxSizer(wx.VERTICAL)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(panel, label="FPS", style=wx.ALIGN_RIGHT)
        label.SetFont(font)
        hbox1.Add(label, 1, wx.EXPAND)
        self.fps_label = wx.StaticText(panel, label="OFFLINE")
        self.fps_label.SetFont(font.Bold())
        hbox1.Add(self.fps_label)
        vbox1.Add(hbox1, 1, wx.EXPAND)
        hbox.Add(vbox1, 1, wx.EXPAND | wx.LEFT, 20)

        vbox.Add(hbox, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.logger = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY
        )
        self.logger.SetFont(font)
        vbox.Add(self.logger, 1, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(vbox)
        pub.subscribe(self.logger_listener, "logging")

    def set_arena_type(self, ev):
        arena.set_arena_type(int(ev.GetString()))

    def set_arena_kind(self, ev):
        arena.set_arena_kind(ev.GetString())

    def set_max_force(self, ev):
        try:
            value = int(ev.GetString())
        except (TypeError, ValueError):
            self.max_force_spin.SetValue(config.get("arena:max-force"))
        else:
            if value < 0 or value > 50000000:
                self.max_force_spin.SetValue(config.get("arena:max-force"))
            else:
                arena.set_arena_max_force(value)

    def set_run_count(self, ev):
        try:
            value = int(ev.GetString())
        except (TypeError, ValueError):
            self.run_count_spin.SetValue(config.get("arena:run-count"))
        else:
            if value < 1 or value > 99:
                self.run_count_spin.SetValue(config.get("arena:run-count"))
            else:
                arena.set_arena_run_count(value)

    def start_stop_arena(self, ev):
        if self._arena_thread:
            self.start_arena_button.SetLabelText("Start arena")
            self.arena_counter.SetLabelText("")
            self._arena_thread.raise_exception()
            self._arena_thread = None
        else:
            run_count = config.get("arena:run-count")
            if run_count < 1:
                return

            num = 1

            def run_arena():
                self.start_arena_button.SetLabelText("Stop arena")
                self.arena_counter.SetLabelText("arena #%s" % num)
                self._arena_thread = self.run_in_thread(
                    arena.start_arena_once,
                    args=(num,),
                    after=restart
                )

            def restart():
                nonlocal num
                num += 1
                if self._arena_thread is None:
                    return
                count = config.get("arena:run-count")
                if num > count:
                    self.start_arena_button.SetLabelText("Start arena")
                    self.arena_counter.SetLabelText("")
                    self._arena_thread = None
                else:
                    run_arena()

            run_arena()

    def setup_logging(self):
        setup_logging("console.ui.UIHandler")
        sys.excepthook = _exception_hook

    def logger_listener(self, msg):
        self.logger.AppendText(msg + "\n")

    def on_close(self, event=None):
        self._thead_container.close()
        client.close()
        self.Destroy()

    def init(self):
        self.start_fps_watcher()
        self.reboot()

    def reboot(self, event=None):
        self.reboot_button.Disable()
        self.logger.Clear()
        self.run_in_thread(environ.reboot, after=self.reboot_button.Enable)

    def start_fps_watcher(self):
        def set_fps_value(value):
            if value == "OFFLINE":
                self.start_arena_button.Disable()
            else:
                self.start_arena_button.Enable()
            self.fps_label.SetLabelText(value)

        def watcher():
            prev_key = 0
            while 1:
                tm = time.time()
                time.sleep(1)
                buf = client.videobuf
                if not buf:
                    wx.CallAfter(set_fps_value, "OFFLINE")
                    continue
                delta = time.time() - tm
                new_key = buf[0]
                fps = (new_key - prev_key) / delta
                prev_key = new_key
                wx.CallAfter(set_fps_value, "{:.1f}".format(fps))

        self._thead_container.run(watcher)

    def run_in_thread(self, func, args=(), kwargs=None, *, after=None):
        def thread_func():
            try:
                func(*args, **(kwargs or {}))
            finally:
                if after:
                    wx.CallAfter(after)
        return self._thead_container.run(thread_func)


def run_app():
    app = wx.App()
    frm = AppFrame(
        None,
        title="Robobo %s" % __version__,
        size=(800, 600)
    )
    frm.Show()
    frm.init()
    app.MainLoop()
