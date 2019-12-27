# -*- coding: utf-8 -*-
"""

@author: Lukas Sandström
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import tkinter as tk
from tkinter import ttk, messagebox

from tk_zva import FreqEntry, IFFreqSpinbox, PowerEntry, PowerSpinbox, IntEntry, ZVASoftkeys
from .tkSimpleDialog import Dialog


class MinimizedWindow(tk.Toplevel):
    def __init__(self, main_window, position, **kwargs):
        super().__init__(**kwargs)
        self.main_window = main_window

        self.wm_attributes("-topmost", 1)
        self.overrideredirect(1)
        self.geometry(position)

        fr = ttk.Frame(self, relief=tk.GROOVE, borderwidth=2)
        fr.pack()

        self.restore_btn = ttk.Button(fr, text="RSS IM sweep")
        self.restore_btn.pack(side=tk.LEFT)

        self.softkeys = tk.BooleanVar()
        ttk.Checkbutton(fr, text="Softkeys", onvalue=True, offvalue=False, variable=self.softkeys).pack(side=tk.RIGHT)


class ConfigDialog(Dialog):
    def body(self, frame):
        conn_frame = ttk.Labelframe(frame, text="VNA connection")
        conn_frame.grid(row=0, column=0, sticky="new")

        ttk.Label(conn_frame, text="VNA IP adress").grid(row=0, column=0, sticky="e")
        self.ip_adress = ttk.Entry(conn_frame)
        self.ip_adress.grid(row=0, column=1, sticky="w")
        # self.test_conn_button = ttk.Button(conn_frame, text="Test connection")
        # self.test_conn_button.grid(row=1, column=1)

        gui_frame = ttk.Labelframe(frame, text="GUI options")
        gui_frame.grid(row=1, column=0, sticky="new")
        self.show_softkeys = tk.BooleanVar(self)
        ttk.Checkbutton(gui_frame, text="Show softkeys", variable=self.show_softkeys,
                        onvalue=True, offvalue=False).grid(row=0, column=0, columnspan=2)


class IMSweepSoftkeys(ZVASoftkeys):
    def __init__(self, main_window, **kwargs):
        super().__init__(**kwargs)
        self.main_window = main_window
        ttk.Label(self.top_frame, text="RSS IM Sweep", background="white").pack(fill="x")

    def show_power_entry(self):
        for child in self.top_frame.winfo_children():
            child.destroy()
        w = PowerSpinbox(self.top_frame, valuevar=self.main_window.add_var("base_power"))
        w.pack()
        w.focus_set()

    def show_if_entry(self):
        for child in self.top_frame.winfo_children():
            child.destroy()
        w = IFFreqSpinbox(self.top_frame, valuevar=self.main_window.add_var("if_bandwidth"))
        w.pack()
        w.focus_set()


class CalibrationFrame(ttk.Labelframe):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self['text'] = "Calibration"

        ttk.Label(self, text="Cal group name").grid(row=0, column=0, sticky="e")
        self.calgroup_select = ttk.Combobox(self)
        self.calgroup_select.grid(row=0, column=1, sticky="w")

        ttk.Label(self, text="Cal base power").grid(row=1, column=0, sticky="e")
        self.power_level = PowerEntry(self, valuevar=master.add_var("cal_power", -10, type_=tk.DoubleVar))
        self.power_level.grid(row=1, column=1, sticky="w")

        self.create_cal_button = ttk.Button(self, text="Create cal channel")
        self.create_cal_button.grid(row=10, column=0)
        self.apply_cal_button = ttk.Button(self, text="Apply calibration")
        self.apply_cal_button.grid(row=11, column=0, columnspan=2)
        self.delete_cal_button = ttk.Button(self, text="Delete cal channel")
        self.delete_cal_button.grid(row=10, column=1)

    def ask_verify_delete(self):
        return messagebox.askokcancel(
            message="The current calibration is not linked to a cal group. Delete cal channel anyway?",
            icon="question", title="Really delete cal channel?", parent=self)


class ZVAControlFrame(ttk.Labelframe):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self["text"] = "ZVA control, applies immediately to all IM channels"

        grid_c1 = {"column": 1, "padx": 3, "pady": 1, "sticky": "w"}
        row = 0
        self.rf_off = ttk.Button(self, text="RF OFF!")
        self.rf_off.grid(row=row, column=0, sticky="e")
        self.rf_on = ttk.Button(self, text="RF ON")
        self.rf_on.grid(row=row, **grid_c1)

        row += 1
        ttk.Label(self, text="Channel base power").grid(row=row, column=0, sticky="e")
        PowerSpinbox(self, valuevar=master.add_var("base_power", type_=tk.DoubleVar), increment=1, width=10)\
            .grid(row=row, **grid_c1)

        self.pulse_mod_enabled = tk.StringVar(value="off")
        #  ttk.Checkbutton(fr_zva_control, text="Enable pulse modulation", variable=self.pulse_mod_enabled,
        #                  onvalue="on", offvalue="off").grid(column=0, row=1, columnspan=2)

        row += 1
        ttk.Label(self, text="IF bandwidth").grid(column=0, row=row, sticky="e")
        IFFreqSpinbox(self, valuevar=master.add_var("if_bandwidth", type_=tk.DoubleVar), width=10).grid(row=row, **grid_c1)

        row += 1
        fr_selectivity = ttk.Frame(self)
        fr_selectivity.grid(column=1, row=row, sticky="w")
        ttk.Label(self, text="Selectivity").grid(column=0, row=row, sticky="e")
        ttk.Radiobutton(fr_selectivity, variable=master.add_var("if_selectivity", "high"), text="High", value="high").grid(column=1, row=row)
        ttk.Radiobutton(fr_selectivity, variable=master.add_var("if_selectivity"), text="Normal", value="norm").grid(column=2, row=row)

        row += 1
        ttk.Label(self, text="Trigger").grid(column=0, row=row, sticky="e")
        ttk.Combobox(self, textvariable=master.add_var("trigger_source"), width=10,
                     values=("Free run", "Pulse"), state="readonly").grid(row=row, **grid_c1)


class TraceConfigDialog(Dialog):
    def body(self, master):
        pass

class TraceConfigFrame(ttk.Labelframe):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self["text"] = "Trace config"

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=0, column=0, sticky="w")
        self.add_btn = ttk.Button(btn_frame, text="Add")
        self.add_btn.pack(side="left")
        self.remove_btn = ttk.Button(btn_frame, text="Remove")
        self.remove_btn.pack(side="left")
        self.modify_btn = ttk.Button(btn_frame, text="Modify")
        self.modify_btn.pack(side="left")
        self.apply_btn = ttk.Button(btn_frame, text="Apply")
        self.apply_btn.pack(side="left")

        t = self.tree = ttk.Treeview(self, columns=["name", "measurement", "window"], height=5)
        t.heading("name", text="Name")
        t.heading("measurement", text="Measurement")
        t.heading("window", text="Window")
        t.column("#0", minwidth=0, width=0)
        t.column("name", width=100)
        t.column("measurement", width=100)
        t.column("window", anchor="center", width=70)
        t.grid(row=1, column=0, sticky="new")

        self.add_trace("t0", "IM3L_OR", 1)
        self.remove_trace("t0")
        self.add_trace("t1", "IM3L_OR", 1)

    def add_trace(self, name, measurement, window):
        self.tree.insert("", "end", iid=name, values=(name, measurement, window))

    def remove_trace(self, name):
        self.tree.delete(name)


class MainMenubar(tk.Menu):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.commands = {}

        file = tk.Menu(self)
        self.add_cascade(menu=file, label="File")
        file.add_command(label="Exit", command=self.set_command("exit"))

        self.add_command(label="Settings...", command=self.set_command("settings"))

        help = tk.Menu(self)
        self.add_cascade(menu=help, label="Help")
        help.add_command(label="About")

    def set_command(self, cmd_name, func=lambda: None):
        self.commands[cmd_name] = func
        return lambda: self.commands[cmd_name]()


class MainWindow(ttk.Frame):

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)

        self.vars = {}

        # Initialize the menubar
        self.menu = MainMenubar(master)
        master['menu'] = self.menu

        # Buttons at the top of the window
        fr_top_buttons = ttk.Frame(self)
        fr_top_buttons.grid(column=0, row=0, columnspan=2, sticky="ew")
        fr_top_buttons.columnconfigure(4, weight=2)
        self.connect_button = ttk.Button(fr_top_buttons, text="Connect")
        self.connect_button.grid(row=0, column=0)

        self.minimize_btn = ttk.Button(fr_top_buttons, text="Minimize")
        self.minimize_btn.grid(row=0, column=1)

        connection_status = ttk.Label(fr_top_buttons, text="Not connected")
        connection_status.grid(row=1, column=0, columnspan=5, sticky="w")
        self.link_textvar(connection_status, "connection_status")

        # Create the meas setup frame
        fr_meas_setup = ttk.Labelframe(self, text="Measurement setup description", padding=0)
        fr_meas_setup.grid(column=0, row=1, sticky="ns")
        fr_meas_setup.columnconfigure(0, weight=2)
        fr_meas_setup.columnconfigure(1, weight=2)
        ttk.Label(fr_meas_setup, text="Source port, f_low").grid(column=0, row=0, sticky="w")
        ttk.Label(fr_meas_setup, text="Source port, f_high").grid(column=0, row=1, sticky="w")
        ttk.Label(fr_meas_setup, text="DUT output port").grid(column=0, row=3, sticky="w")

        vna_ports = ("1", "2", "3", "4")
        ttk.Combobox(fr_meas_setup, textvariable=self.add_var("src_tl"), values=vna_ports, width=4).grid(column=1, row=0, sticky="w")
        ttk.Combobox(fr_meas_setup, textvariable=self.add_var("src_tu"), values=vna_ports, width=4).grid(column=1, row=1, sticky="w")
        ttk.Combobox(fr_meas_setup, textvariable=self.add_var("port_dut_out"), values=vna_ports, width=4).grid(column=1, row=3, sticky="w")

        ttk.Checkbutton(fr_meas_setup, text="f_high can be measured by the a_x receiver",
                        variable=self.add_var("combiner_mode", "internal"),
                        onvalue="external", offvalue="internal").grid(column=0, row=2, columnspan=2)

        # Sweep settings frame
        fr_sweep = ttk.Labelframe(self, text="Sweep settings")
        fr_sweep.grid(column=0, row=2, sticky="nesw")
        ttk.Label(fr_sweep, text="Center frequency").grid(column=0, row=0, sticky="e")
        ttk.Label(fr_sweep, text="Spacing start").grid(column=0, row=1, sticky="e")
        ttk.Label(fr_sweep, text="Spacing stop").grid(column=0, row=2, sticky="e")
        ttk.Label(fr_sweep, text="Sweep points").grid(column=0, row=3, sticky="e")

        FreqEntry(fr_sweep, valuevar=self.add_var("center_freq", type_=tk.DoubleVar), prefix="g").grid(column=1, row=0)
        FreqEntry(fr_sweep, valuevar=self.add_var("spacing_start", type_=tk.DoubleVar), prefix="m").grid(column=1, row=1)
        FreqEntry(fr_sweep, valuevar=self.add_var("spacing_stop", type_=tk.DoubleVar), prefix="m").grid(column=1, row=2)
        IntEntry(fr_sweep, intvar=self.add_var("sweep_points", type_=tk.IntVar)).grid(column=1, row=3)

        self.apply_sweep = ttk.Button(fr_sweep, text="Apply")
        self.apply_sweep.grid(column=1, row=10, sticky="e")

        self.trace_config = TraceConfigFrame(self)
        self.trace_config.grid(column=0, row=3, sticky="new")

        # ZVA control pane
        self.zva_ctrl = ZVAControlFrame(self)
        self.zva_ctrl.grid(column=1, row=1, sticky="new")

        # Calibration frame
        self.cal_frame = CalibrationFrame(self)
        self.link_textvar(self.cal_frame.calgroup_select, "calgroup")
        self.cal_frame.grid(row=2, column=1, sticky="news")

    def add_var(self, var_name, value=None, type_=tk.StringVar):
        """

        :param var_name:
        :param value:
        :param class type_:
        :return:
        """
        self.vars[var_name] = self.vars.get(var_name, type_(value=value))
        return self.vars[var_name]

    def link_textvar(self, widget, var_name, var=None):
        """
        :param widget: The widget we will assign textvariable on
        :param var_name: the name of the variable in self.vars
        :param var: If this parameter is provided it will be assigned to self.vars
        """
        if var is None:
            var = self.vars.get(var_name, tk.StringVar())
        self.vars[var_name] = var
        widget['textvariable'] = var

    def set_calpool(self, calpool):
        """
        Call this method to update the list in the GUI with the cal groups available in the cal pool

        :param calpool: A list of string representing the cal groups
        """
        self.cal_frame.calgroup_select['values'] = calpool
