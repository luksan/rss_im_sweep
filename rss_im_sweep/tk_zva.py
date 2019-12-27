# -*- coding: utf-8 -*-
"""

@author: Lukas Sandström
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import tkinter as tk
from math import ceil, log10
from tkinter import ttk

from tkSimpleDialog import Dialog


class ZVAEntry(ttk.Entry):
    prefixes = {"": (1.0, ""), "k": (1e3, "k"), "m": (1e6, "M"), "g": (1e9, "G")}

    def __init__(self, master, valuevar, **kwargs):
        self._prefix = kwargs.pop("prefix", "")
        super().__init__(master, **kwargs)

        self._value_var = valuevar
        self.__value_trace_cb = valuevar.trace_add("write", lambda n1, n2, op: self.set_value(valuevar.get(), update_var=False))
        self.bind("<Destroy>", lambda _ev: self._on_destroy(_ev))  # Use a lambda so that _on_destroy can be subclassed

        self['validatecommand'] = (self.register(self._validate), "%d", "%i", "%s", "%P", "%S")
        self['validate'] = "key"

        self.bind("<FocusOut>", self.lost_focus)
        self.bind("<Return>", lambda x: self._validate("1", "1", self.get(), "", ""))

        self.entry_complete = True
        self.value_format = "%.10g"

    def _on_destroy(self, event):
        self._value_var.trace_remove("write", self.__value_trace_cb)

    def lost_focus(self, event):
        if not self.entry_complete:
            self.refresh_text()  # FIXME: skumt beteende

    def refresh_text(self):
        self.set_value(self.get_value(), update_var=False)

    def get_value(self):
        return self._value_var.get()

    def set_value(self, value, prefix=None, update_var=True):
        if prefix is not None:
            self._prefix = prefix.lower()
        if update_var:
            self._value_var.set(value)
        (scale, unit) = self.prefixes[self._prefix]
        if unit:
            unit = " " + unit
        fmt = self.value_format + "%s"
        self.set_text(fmt % (value / scale, unit))
        self.entry_complete = True

    def _validate(self, action, pos, old, new, diff):
        """
        Callback for validation of the entered text.

        :param str action: 0 = deletion, -1 = focus change, 1 = insertion, but it is a str
        :param str pos:
        :param str old:
        :param str new:
        :param str diff:
        :return: True or False
        """
        if action == "0":
            self.entry_complete = False
        if int(action) < 1:  # 0 = deletion, -1 = focus change, 1 = insertion
            return True
        if len(diff) > 1:  # Not keypress, but set_text()
            return True
        if diff.lower() in self.prefixes:
            strval = old.split(" ", maxsplit=1)[0]
            (scale, unit) = self.prefixes[diff.lower()]
            if strval == "" or self.entry_complete:  # Don't change the frequency if only the unit prefix is changing
                value = self.get_value()
                scale = 1
            else:
                try:
                    value = float(strval)
                except ValueError:
                    return False
            self.set_value(value * scale, diff)
            return True
        if not diff.isnumeric() and diff not in ".eE+-":
            return False
        if self.entry_complete and int(pos) == len(old):  # Clear the old input
            self.set_text(diff)
        self.entry_complete = False
        return True

    def set_text(self, string):
        self.delete(0, "end")
        self.insert(0, string)


class StepsizeDialog(Dialog):
    def __init__(self, parent):
        self.stepsize = tk.DoubleVar()
        super().__init__(parent, title="Step size")

    def body(self, master):
        self.stepsize = tk.StringVar(master)
        entry = ttk.Entry(master, textvariable=self.stepsize)
        entry.insert(0, self.parent["increment"])
        entry.select_range(0, 10000)
        entry.pack()
        return entry

    def apply(self):
        step = float(self.stepsize.get())
        new_prec = ceil(-log10(step))
        if new_prec < 0:
            new_prec = 0
        if new_prec > self.parent.precision:
            self.parent.precision = new_prec
        self.parent["increment"] = step

    def validate(self):
        try:
            return float(self.stepsize.get()) > 0
        except ValueError:
            return False


class ZVAIncrementSpinbox(ZVAEntry):
    def __init__(self, master, **kwargs):
        super().__init__(master, widget='ttk::spinbox', **kwargs)
        self.bind('<s>', self.show_stepsize_dialog)
        self.bind('<Button-2>', self.show_stepsize_dialog)
        self['format'] = '%0.10f'
        self['command'] = self._post_incdec
        self['increment'] = 1.0
        self['from'] = -300
        self['to'] = 300
        self._precision = None
        self.precision = 0

    @property
    def precision(self):
        return self._precision

    @precision.setter
    def precision(self, prec):
        self._precision = prec
        self.value_format = "%%0.%if" % prec
        self.refresh_text()

    def _validate(self, action, pos, old, new, diff):
        ret = super()._validate(action, pos, old, new, diff)
        if self.entry_complete:
            # entry_complete is only true when a value has been entered with the keyboard
            dec = str(self.get_value()).split(".")[1]
            entry_prec = len(dec)
            if all([x == "0" for x in dec]):
                entry_prec = 0
            inc_prec = ceil(-log10(self["increment"]))
            self.precision = max(entry_prec, inc_prec)
            self.refresh_text()
        return ret

    def get(self):
        return self.tk.call(self._w, "get")

    def set(self, value):
        return self.tk.call(self._w, "set", value)

    def _post_incdec(self):
        self.set_value(float(self.get()))

    def show_stepsize_dialog(self, _ev):
        StepsizeDialog(self)


class ZVAValuesSpinbox(ZVAIncrementSpinbox):
    def __init__(self, master, **kwargs):
        super().__init__(master,  **kwargs)
        self.bind('<<Increment>>', self._inc)
        self.bind('<<Decrement>>', self._dec)

    def _inc(self, event):
        self.set(self.get_value())

    def _dec(self, event):
        self.set(self.get_value())


class FreqEntry(ZVAEntry):
    prefixes = {"": (1, "Hz"), "k": (1e3, "kHz"), "m": (1e6, "MHz"), "g": (1e9, "GHz")}


class FreqSpinbox(ZVAValuesSpinbox, FreqEntry):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.__spin_trace = self._value_var.trace_add("write", lambda n1, n2, op: self.adjust_unit())
        self.adjust_unit()

    def _on_destroy(self, event):
        super()._on_destroy(event)
        self._value_var.trace_remove("write", self.__spin_trace)

    def adjust_unit(self):
        new_freq = self.get_value()
        if new_freq < 1e3:
            self._prefix = ""
        elif new_freq < 1e6:
            self._prefix = "k"
        else:
            self._prefix = "m"
        self.refresh_text()


class IFFreqSpinbox(FreqSpinbox):
    def __init__(self, master, max_freq=30e6, **kwargs):
        ifbw_values = [float(10**a*b) for a in range(8) for b in (1, 2, 5) if 10**a*b <= max_freq]
        if max_freq <= 30e6:
            ifbw_values.append(30e6)
        kwargs['values'] = ifbw_values
        super().__init__(master, **kwargs)


class PowerEntry(ZVAEntry):
    prefixes = {"": (1, "dBm"), "k": (1, "dBm"), "m": (1, "dBm"), "g": (1, "dBm")}


class PowerSpinbox(ZVAIncrementSpinbox, PowerEntry):
    pass


class IntEntry(ttk.Entry):
    def __init__(self, master, intvar, *args, **kwargs):
        super().__init__(master, *args, **kwargs)

        self['validatecommand'] = (self.register(self._validate), "%d", "%S", "%P")
        self['validate'] = "key"

        self.intvar = intvar
        intvar.trace_add("write", lambda n1, n2, op: self.set_text("%d" % (intvar.get())))

    def _validate(self, action, diff, new):
        if not (diff.isnumeric() or action != "1"):
            return False
        try:
            self.intvar.set(int(new))
        except ValueError:
            pass
        return True

    def set_text(self, string):
        self.delete(0, "end")
        self.insert(0, string)


class ZVASoftkeys(tk.Toplevel):
    keys = ["<F2>", "<F3>", "<F5>", "<F7>", "<F8>", "<F9>", "<F11>", "<F12>"]

    def __init__(self, **kwargs):
        from functools import partial
        super().__init__(**kwargs)

        self.wm_attributes("-topmost", 1)
        self.overrideredirect(1)
        self.geometry("110x580+690+0")
        self.protocol("WM_DELETE_WINDOW", self._destroy)

        self.top_frame = ttk.Frame(self, height=76, width=110)
        self.top_frame.pack()
        self.top_frame.pack_propagate(0)

        self.button = []
        self.button_frame = []

        for x in range(8):
            fr = ttk.Frame(self, width=110, height=62)
            fr.pack_propagate(0)
            fr.pack()
            self.button_frame.append(fr)
            b = ttk.Button(fr)
            b.bind("<Button>", self.clear_focus)
            self.button.append(b)
            self.bind_all(self.keys[x], partial(self.invoke_button, x))

    def _destroy(self, *args):
        for key in self.keys:
            self.unbind_all(key)

    def set_button(self, n, text, command):
        self.button[n]['text'] = text
        self.button[n]['command'] = command
        self.button[n].pack(fill=tk.BOTH, expand=True, pady=2, padx=2)

    def remove_button(self, n):
        self.button[n].pack_forget()
        self.button[n]["command"] = lambda: None

    def load_buttons(self, buttons):
        """
        :param buttons: A list of tuples (button text, button command)
        """
        for x in range(8):
            self.remove_button(x)
        cnt = 0
        for txt, cmd in buttons:
            if txt:
                self.set_button(cnt, txt, cmd)
            cnt += 1

    def clear_focus(self, _ev=None):
        for x in range(8):
            self.button[x].state(["!focus"])

    def invoke_button(self, n, _ev=None):
        self.button[n].invoke()
        self.clear_focus()
        self.button[n].state(["focus"])
