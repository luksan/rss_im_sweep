# -*- coding: utf-8 -*-
"""

@author: Lukas Sandström
"""

import tkinter as tk
from tkinter import messagebox

import logging
import queue
from collections import namedtuple

import RSSscpi.zva
from RSSscpi.zva import Trace
import threading
import pyvisa

from rss_im_sweep.gui import MainWindow, ConfigDialog, MinimizedWindow, IMSweepSoftkeys


class VISAFilter(logging.Filter):
    def filter(self, record):
        """
        :param logging.LogRecord record:
        :return: bool
        """
        if record.name.endswith(".VISA") and record.levelno <= logging.INFO:
            return False
        if record.name.startswith("pyvisa") and record.levelno <= logging.WARNING:
            return False
        return True


class WaveParam(namedtuple("WPT", ["receiver", "dst_port", "src_port"])):
    def get(self):
        return self.receiver, self.dst_port, self.src_port

    def __str__(self):
        return str(Trace.MeasParam.Wave(self.receiver.get(), self.dst_port.get(), self.src_port.get()))


class ZVAIMController(object):
    def __init__(self, model):
        self.model = model
        self.zva = None  # type: RSSscpi.zva.ZVA

        self.ch = {}  # type: {str: RSSscpi.zva.Channel}

    def setup_trace_model(self):
        t = self.model.traces.get()  # type: TraceModel
        t.add_trace("TL_I", "A_srcTL_srcTL", None, 1)

    def connect_vna(self):
        """
        This method is run in a diffrent thread than the mainloop.
        Do not set variables in the model here, since the callbacks would be invoked in this thread
        """
        self.zva = RSSscpi.zva.connect_ethernet(self.model.zva_adress.get())  # type: RSSscpi.zva.ZVA
        self.zva.exception_on_error = False
        self.zva.visa_logger.setLevel(logging.INFO)
        self.zva.visa_logger.addHandler(logging.FileHandler(filename=__file__[:-3] + "_visa_log.txt", mode="w"))
        self.zva.update_display(True)

        def mk_ch(model_param):
            return self.zva.get_channel(self.model.vars[model_param].get())
        self.ch["TL"] = mk_ch("ch_tl")
        self.ch["TU"] = mk_ch("ch_tu")
        self.ch["IM3L"] = mk_ch("ch_im3l")
        self.ch["IM3U"] = mk_ch("ch_im3u")
        self.ch["cal"] = mk_ch("ch_cal")

    @property
    def is_connected(self):
        return self.zva is not None

    def query_zva_settings(self):
        if not self.is_connected:
            return
        zva = self.zva
        ch = self.ch["TL"]  # type: RSSscpi.zva.Channel
        if not ch.state or not ch.name == "TL":
            return
        try:
            self.zva = None  # remove the zva instance from self to prevent model callbacks

            self.model.spacing_start.set(ch.freq_start)
            self.model.spacing_stop.set(ch.freq_stop)
            a, b, fc, mode = ch.SENSe.FREQuency.CONVersion.ARBitrary.q().split_comma()
            self.model.center_freq.set(float(fc))
            self.model.sweep_points.set(ch.sweep.points)
            self.model.if_bandwidth.set(ch.ifbw)
            self.model.if_selectivity.set(ch.if_selectivity.lower())
            self.model.base_power.set(ch.power_level)
            c = ch.calibration.query_calgroup()
            if c:
                self.model.calgroup.set(c)

            x = {"IMM": "Free run", "PGEN": "Pulse"}
            a = str(ch.TRIGger.SEQuence.SOURce.q())
            self.model.trigger_source.set(x[a])
        finally:
            self.zva = zva

    def configure_sweep(self):
        if not self.is_connected:
            return

        src_tl = self.model.src_tl.get()
        src_tu = self.model.src_tu.get()
        dut_out = self.model.port_dut_out.get()
        cf = self.model.center_freq.get()

        self.zva.scpi.INITiate.CONTinuous.w(False)
        ch = self._configure_channel('TL', -1, False, clear=False)
        ch.sweep.points = self.model.sweep_points.get()

        cg = self.model.calgroup.get()
        if cg in ch.calibration.query_calpool_list():
            ch.calibration.load_calibration(cg)

        # FIXME: the other sources need to get a valid frequency config as well, since fb is usually out of range
        # port 4 could be set to not measured
        # also, power sensors need to be considered
        ch.SOURce.FREQuency(src_tl).CONVersion.ARBitrary.IFRequency.w(-1, 2, cf, "SWEep")
        ch.SOURce.FREQuency(src_tu).CONVersion.ARBitrary.IFRequency.w(1, 2, cf, "SWEep")
        ch.SOURce.FREQuency(dut_out).CONVersion.ARBitrary.IFRequency.w(0, 1, cf, "SWEep")
        ch.SOURce.POWer(self.source_low).PERManent.STATe.w(True)
        ch.SOURce.POWer(src_tu).PERManent.STATe.w(True)
        ch.SENSe.FREQuency.CONVersion.AWReceiver.STATe.w(False)  # Measure the a-waves at the source frequency
        ch.SENSe.FREQuency.SBANd.w("NEGative")  # select LO < RF, so that the image is below the lower tone

        self._configure_channel('TU', 1, True)
        self._configure_channel('IM3L', -3, False)
        self._configure_channel('IM3U', 3, True)

        self.create_traces()

        self.zva.INITiate.CONTinuous.w(True)

    def _configure_channel(self, name, fb_mult, lo_high, clear=True):
        # type: (str, int, bool, bool) -> RSSscpi.zva.Channel
        ch = self.ch[name]  # type: RSSscpi.zva.Channel
        if clear and ch.state:
            ch.state = False
        ch.state = True
        ch.name = name
        ch.sweep.type = "LIN"
        ch.freq_start = 10e6  # This is supported by all ZVAs, set this before the arb
        ch.freq_stop = 30e6   # freq config to avoid "freq out of range" errors
        ch.SENSe.FREQuency.CONVersion.ARBitrary.w(fb_mult, 2, self.model.center_freq.get(), "SWEep")
        ch.freq_start = self.model.spacing_start.get()
        ch.freq_stop = self.model.spacing_stop.get()
        if lo_high:
            ch.SENSe.FREQuency.SBANd.w("POSitive")
        else:
            ch.SENSe.FREQuency.SBANd.w("NEGative")
        return ch

    def create_traces(self):
        if not self.is_connected:
            return

        ch = self.ch['TL']  # type: RSSscpi.zva.Channel
        dia1 = self.zva.get_diagram(1)
        src_tl = self.model.src_tl.get()
        src_tu = self.model.src_tu.get()
        port_dut_out = self.model.port_dut_out.get()

        tr = ch.create_trace("TL_I", Trace.MeasParam.Wave('A', src_tl, src_tl), dia1)
        ch.create_trace("TU_I", Trace.MeasParam.Wave('A', src_tu, src_tu), dia1)
        ch.create_trace("TL_O", Trace.MeasParam.Wave('B', port_dut_out, src_tl), dia1)

        self.ch['TU'].create_trace("TU_O", Trace.MeasParam.Wave("B", port_dut_out, src_tl), dia1)
        self.ch['IM3L'].create_trace("IM3L_O", Trace.MeasParam.Wave("B", port_dut_out, src_tl), dia1)
        self.ch['IM3U'].create_trace("IM3U_O", Trace.MeasParam.Wave("B", port_dut_out, src_tl), dia1)

        dia2 = self.zva.get_diagram(2)
        tr.copy_assign_math("IM3L_OR", "IM3L_O / TL_O", dia2)
        tr.copy_assign_math("IM3U_OR", "IM3U_O / TU_O", dia2)

    def create_cal_channel(self, ch_no):
        ch = self.ch["cal"]
        if ch.state:
            ch.state = False
        self.zva.active_channel = 1
        ch.state = True
        ch.name = "cal"
        ch.SENSe.FREQuency.CONVersion.w("FUNDamental")
        d1 = self.model.spacing_start.get()
        d2 = self.model.spacing_stop.get()
        fc = self.model.center_freq.get()
        pts = self.model.sweep_points.get()
        ifbw = self.model.if_bandwidth.get()
        power = -10
        ch.sweep.segments.insert_segment(fc+3*d1/2, fc+3*d2/2, pts, ifbw, power)  # IM3 high
        ch.sweep.segments.insert_segment(fc+d1/2, fc+d2/2, pts, ifbw, power)  # TH
        ch.sweep.segments.insert_segment(fc-d2/2, fc-d1/2, pts, ifbw, power)  # TL
        ch.sweep.segments.insert_segment(fc-3*d2/2, fc-3*d1/2, pts, ifbw, power)  # IM3 low
        ch.sweep.segments.disable_per_segment_power()
        ch.sweep.segments.disable_per_segment_ifbw()
        ch.sweep.type = ch.sweep.SEGMENT
        ch.power_level = self.model.cal_power.get()
        cal_dia = self.zva.get_diagram(3)
        cal_dia.state = True
        ch.create_trace("Cal", Trace.MeasParam.S(2, 1), cal_dia)
        # ch.create_trace("Cal", zva.Trace.MeasParam.S(3,1), cal_dia)
        cg = self.model.calgroup.get()
        if cg in ch.calibration.get_calpool_list():
            ch.calibration.load_calibration(cg)

    def delete_cal_channel(self):
        if "cal" not in self.ch or not self.is_connected:
            return
        if self.ch["cal"].state:
            self.ch["cal"].state = False

    def check_if_cal_in_calgroup(self):
        if "cal" not in self.ch or not self.is_connected:
            return None
        if not self.ch["cal"].state:
            return None
        return self.ch["cal"].calibration.get_calgroup() is not None

    def for_all_channels(self, func):
        if not self.is_connected:
            return
        for ch, name in self.zva.query_channel_list():
            if name in self.ch:  # only apply to the IM channels
                func(ch)

    def apply_calibration(self):
        calgroup = self.model.calgroup.get()
        if "cal" in self.ch and self.ch["cal"].state:
            self.ch["cal"].calibration.store_calibration(calgroup)
        if calgroup not in self.zva.cal_manager.get_calpool_list():
            logger.error("No calibration named %s in the cal pool" % calgroup)
        self.for_all_channels(lambda ch: ch.calibration.load_calibration(calgroup) )

    def set_ifbw(self, ifbw):
        def set_ifbw(ch):
            ch.ifbw = ifbw
        self.for_all_channels(set_ifbw)

    def set_selectivity(self, mode):
        def set_sel(ch):
            ch.if_selectivity = mode
        self.for_all_channels(set_sel)

    def set_power(self, power):
        def pwr(ch):
            ch.power_level = power
        self.for_all_channels(pwr)

    def set_trigger_source(self, src):
        x = {"Free run": "IMM", "Pulse": "PGEN"}
        self.for_all_channels(lambda ch: ch.TRIGger.SEQuence.SOURce.w(x[src]))


class Observable:
    def __init__(self, value=None):
        self._value = value
        self._observers = {}

    def get(self):
        return self._value

    def set(self, value):
        if value == self._value:
            return
        self._value = value
        self.emit(value)

    def emit(self, value):
        for o in self._observers:
            o(value)

    def add_observer(self, func):
        self._observers[func] = 1

    def remove_observer(self, func):
        del self._observers[func]

    def link_tk_var(self, var):
        var.set(self._value)
        var.trace_add("write", lambda n1, n2, op: self.set(var.get()))
        self.add_observer(lambda val: var.set(val))


MeasQtyModel = namedtuple("MQMT", ["receiver", "src_port", "dst_port"])


class TraceModel(Observable):
    def __init__(self):
        super().__init__(value={})

    def set(self, value):
        self._value = value.copy()
        for k in self._value:
            self._value[k]["meas_qty"] = MeasQtyModel._make(self._value[k]["meas_qty"])
        self.emit(self._value)

    def add_trace(self, name, meas_qty, equation, window):
        meas_qty = MeasQtyModel._make(meas_qty)
        x = {name: {"meas_qty": meas_qty, "equation": equation, "window": window}}
        self._value.update(x)
        self.emit(x)

    def remove_trace(self, name):
        x = self._value[name]
        del self._value[name]
        x["meas_qty"] = None
        self.emit(x)

    def link_tk_var(self, var):
        raise NotImplementedError()


class Model:
    def __init__(self):
        self.vars = {}
        self._persist = {}

        self.add_variable("zva_adress", "192.168.56.102")
        self.add_variable("center_freq", 1e9)
        self.add_variable("spacing_start", 1e6)
        self.add_variable("spacing_stop", 30e6)
        self.add_variable("sweep_points", 101)
        self.add_variable("if_bandwidth", 1e3, persistent=True)
        self.add_variable("if_selectivity", "high", persistent=True)
        self.add_variable("base_power", -10, persistent=False)

        self.add_variable("calgroup", "RSS_im_sweep.cal")
        self.add_variable("cal_power", -10)

        self.add_variable("src_tl", 1)
        self.add_variable("src_tu", 3)
        self.add_variable("port_dut_out", 2)
        self.add_variable("combiner_mode", "external")

        self.add_variable("ch_tl", 1)
        self.add_variable("ch_tu", 2)
        self.add_variable("ch_im3l", 3)
        self.add_variable("ch_im3u", 4)
        self.add_variable("ch_cal", 5)

        self.add_variable("trigger_source", "Free run", persistent=False)
        self.add_variable("zva_is_connected", False, persistent=False)
        self.add_variable("connection_status", "Not connected", persistent=False)

        self.add_variable("minimized_pos", "+500+0")
        self.add_variable("is_minimized", False, persistent=False)
        self.add_variable("show_softkeys", True)

        self.vars["traces"] = TraceModel()
        self._persist["traces"] = True

    def load_json(self, fp):
        import json
        try:
            data = json.load(fp)
        except json.JSONDecodeError:
            logging.exception("Error loading stored settings")
            return
        for k in data:
            try:
                self.vars[k].set(data[k])
            except KeyError:
                logging.error("Unexpected key in JSON data: '%s'", k)

    def store_json(self, fp):
        import json
        json.dump({k: v for k, v in self.vars.items() if self._persist[k]}, fp, default=lambda x: x.get(), indent=2)

    def __getattr__(self, item):
        try:
            return self.vars[item]
        except KeyError as e:
            raise AttributeError(e)

    def add_variable(self, name, value, persistent=True):
        self.vars[name] = Observable(value)
        self._persist[name] = persistent


class ConfigController:
    def __init__(self, model, main_window):
        self.model = model
        self.dialog = ConfigDialog(main_window)

        self.dialog.ip_adress.insert(0, model.zva_adress.get())
        self.dialog.show_softkeys.set(self.model.show_softkeys.get())

        self.dialog.apply = self.apply
        self.__class__.active = True
        main_window.wait_window(self.dialog)

    def apply(self):
        self.model.zva_adress.set(self.dialog.ip_adress.get())
        self.model.show_softkeys.set(self.dialog.show_softkeys.get())


class SoftkeysController:
    def __init__(self, main_controller):
        # type: (Controller) -> None
        self.model = main_controller.model
        self.ctrl = main_controller

        self.menus = {}
        self._current_menu = None
        self._init_menus()

        self._sk = IMSweepSoftkeys(self.ctrl.main_view)
        self.enable_softkeys()
        self.model.show_softkeys.add_observer(self.enable_softkeys)

        self.model.is_minimized.add_observer(self.minimized_state_change)
        self.minimized_state_change(self.model.is_minimized.get())

        self.model.zva_is_connected.add_observer(self.connection_state_change)
        self.connection_state_change(self.model.zva_is_connected.get())

    def minimized_state_change(self, is_minimized):
        if not is_minimized:
            self.menus["main"][7] = ("Minimize", lambda: self.model.is_minimized.set(True))
        else:
            self.menus["main"][7] = ("Restore", lambda: self.model.is_minimized.set(False))
        self.menus["not_connected"][7] = self.menus["main"][7]
        if self._current_menu == "main" or self._current_menu == "not_connected":
            self.activate_menu(self._current_menu)

    def connection_state_change(self, state):
        # type: (str) -> None
        if not state:
            self.activate_menu("not_connected")
        else:
            self.activate_menu("main")

    def _init_menus(self):
        self.menus["main"] = \
            [("VNA control ▶", lambda: self.activate_menu("vna_ctrl")),
             ("Calibrate ▶", None),
             (None, None),
             (None, None),
             (None, None),
             (None, None),
             ("Settings...", self.on_show_settings),
             ("Minimize", None),
             ]
        self.menus["not_connected"] = [
            ("Connect to VNA", self.ctrl.connect_vna),
            (None, None),
            (None, None),
            (None, None),
            (None, None),
            (None, None),
            ("Settings...", self.on_show_settings),
            ("Minimize", None),
        ]
        self.menus["vna_ctrl"] = \
            [("Power", lambda: self._sk.show_power_entry()),
             ("IF bandwidth", lambda: self._sk.show_if_entry()),
             (None, None),
             (None, None),
             (None, None),
             (None, None),
             (None, None),
             ("- Menu Up -", lambda: self.activate_menu("main")),
             ]

    def activate_menu(self, name):
        self._sk.load_buttons(self.menus[name])
        self._current_menu = name

    def enable_softkeys(self, visible=None):
        if visible is None:
            visible = self.model.show_softkeys.get()
        if not visible:
            self._sk.withdraw()
        else:
            self._sk.deiconify()

    def on_show_settings(self):
        self.model.is_minimized.set(False)
        self.ctrl.show_config_dialog()


class Controller:
    def __init__(self):
        self.model = Model()
        try:
            with open("settings.json") as fp:
                self.model.load_json(fp)
        except FileNotFoundError:
            pass

        self.tk_root = tk.Tk()
        self.tk_root.option_add('*tearOff', False)
        self.tk_root.title("RSS IM sweep")
        self.main_view = MainWindow(self.tk_root)
        self.main_view.grid(column=0, row=0, sticky="NSEW")
        self.tk_root.columnconfigure(0, weight=1)
        self.tk_root.rowconfigure(0, weight=1)

        self._mini_window = MinimizedWindow(self.tk_root, self.model.minimized_pos.get())
        self._mini_window.restore_btn["command"] = lambda: self.minimize_main_window(False)
        self.model.show_softkeys.link_tk_var(self._mini_window.softkeys)

        self._sk = SoftkeysController(self)

        self.minimized = None

        self.vna_ctrl = ZVAIMController(self.model)
        self._vna_thread = None
        self.connect_vna()

        self._connect_events()

    def _connect_events(self):
        self.main_view.menu.set_command("exit", self.tk_root.destroy)
        self.main_view.menu.set_command("settings", self.show_config_dialog)

        self.main_view.connect_button["command"] = self.connect_vna
        self.main_view.minimize_btn["command"] = self.minimize_main_window

        self.main_view.apply_sweep["command"] = self.vna_ctrl.configure_sweep
        self.main_view.zva_ctrl.rf_off["command"] = lambda: self.vna_ctrl.zva.OUTPut.STATe.w(False)
        self.main_view.zva_ctrl.rf_on["command"] = lambda: self.vna_ctrl.zva.OUTPut.STATe.w(True)

        self.main_view.cal_frame.create_cal_button["command"] = \
            lambda: self.vna_ctrl.create_cal_channel(self.model.ch_cal.get())

        self.main_view.cal_frame.calgroup_select["postcommand"] = self.refresh_calpool
        self.main_view.cal_frame.apply_cal_button["command"] = self.vna_ctrl.apply_calibration
        self.main_view.cal_frame.delete_cal_button["command"] = self.delete_cal_channel

        for name in self.main_view.vars:
            try:
                getattr(self.model, name).link_tk_var(self.main_view.vars[name])
            except AttributeError:
                logging.debug("GUI variable %s has no match in data model", name)

        self.model.if_bandwidth.add_observer(self.vna_ctrl.set_ifbw)
        self.model.if_selectivity.add_observer(self.vna_ctrl.set_selectivity)
        self.model.trigger_source.add_observer(self.vna_ctrl.set_trigger_source)
        self.model.base_power.add_observer(self.vna_ctrl.set_power)
        self.model.is_minimized.add_observer(self.minimize_main_window)
        self.model.zva_is_connected.add_observer(self.monitor_zva_error_queue)

    def minimize_main_window(self, minimize=True):
        if minimize and not self.minimized:
            self.tk_root.withdraw()
            # self.minimized = MinimizedWindow(self.tk_root, self.model.minimized_pos.get())
            # self.minimized.restore_btn["command"] = lambda: self.model.is_minimized.set(False)
            # self.model.show_softkeys.link_tk_var(self.minimized.softkeys)
        elif not minimize:
            self.tk_root.deiconify()
            self.tk_root.lift()
            #if self.minimized:
            #    self.minimized.destroy()
            #    self.minimized = None
        self.model.is_minimized.set(minimize)

    def connect_vna(self):
        if self._vna_thread is not None:
            logging.info("VNA thread already running")
            return

        conn_status = queue.Queue()

        def thread():
            try:
                self.vna_ctrl.connect_vna()
            except pyvisa.errors.VisaIOError:
                logging.exception("Connection to ZVA failed")
                conn_status.put_nowait((False, "Connection failed"))
            else:
                conn_status.put_nowait((True, "Connected to %s, %s" % (self.model.zva_adress.get(), self.vna_ctrl.zva.IDN.q())))
            finally:
                self._vna_thread = None

        def conn_status_monitor():
            try:
                state, state_str = conn_status.get_nowait()
            except queue.Empty:
                self.tk_root.after(50, conn_status_monitor)
            else:
                self.model.connection_status.set(state_str)
                self.model.zva_is_connected.set(state)
                self.vna_ctrl.query_zva_settings()

        self._vna_thread = threading.Thread(target=thread)
        self.model.zva_is_connected.set(False)
        self.model.connection_status.set("Trying to connect to %s" % (self.model.zva_adress.get()))
        self._vna_thread.start()
        conn_status_monitor()

    def monitor_zva_error_queue(self, start_monitoring):
        if not start_monitoring:
            return
        errors = []
        while True:
            try:
                errors.append(self.vna_ctrl.zva.error_queue.get(timeout=1e-4))
            except queue.Empty:
                break
        if errors:
            messagebox.showerror("Instrument error", "\n".join([e.err_str for e in errors]))
        self.tk_root.after(50, self.monitor_zva_error_queue, self.model.zva_is_connected.get())

    def show_config_dialog(self):
        ConfigController(self.model, self.main_view)

    def refresh_calpool(self):
        if self.vna_ctrl.is_connected:
            self.main_view.set_calpool(self.vna_ctrl.zva.cal_manager.get_calpool_list())
        else:
            self.main_view.set_calpool([])

    def delete_cal_channel(self):
        if self.vna_ctrl.check_if_cal_in_calgroup() is False and not self.main_view.cal_frame.ask_verify_delete():
            return
        self.vna_ctrl.delete_cal_channel()

    def run(self):
        self.vna_ctrl.configure_sweep()
        self.vna_ctrl.create_traces()

        self.tk_root.mainloop()
        with open("settings.json", "w") as fp:
            self.model.store_json(fp)

    def app_close(self):
        self.vna_ctrl.zva._visa_res.close()


def main():
    c = Controller()
    c.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger()
    logger.handlers[0].addFilter(VISAFilter())  # don't print VISA INFO logging to the console
    main()
