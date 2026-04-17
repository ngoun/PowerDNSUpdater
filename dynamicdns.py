# -*- coding: utf-8 -*-
"""
PowerDNS Dynamic IP Updater - Windows system tray app for automatic PowerDNS updates.
Updates A/AAAA records in your PowerDNS authoritative server when your IP changes.
"""

import json
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import requests
from PIL import Image, ImageDraw, ImageFont
import pystray
from pystray import MenuItem as Item

SETTINGS_FILE = os.path.join(os.environ.get('APPDATA', '.'), 'PowerDNSUpdater', 'settings.json')

DEFAULT_SETTINGS = {
    'hostname': '',
    'zone': '',
    'pdns_url': 'http://localhost:8081',
    'api_key': '',
    'record_type': 'A',
    'ttl': 3600,
    'interval': 300,
    'enabled': True,
    'autostart': False,
    'last_ipv4': '',
    'last_ipv6': '',
    'last_update': '',
    'last_status': 'Not configured',
}

AUTOSTART_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
APP_NAME = 'PowerDNSUpdater'


class PowerDNSUpdater:
    def __init__(self):
        self.settings = self._load_settings()
        self.stop_event = threading.Event()
        self.update_thread = None
        self.icon = None
        self.status = self.settings.get('last_status', 'Idle')
        self._settings_window = None

    # ── Settings persistence ──────────────────────────────────────────────────

    def _load_settings(self):
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    merged = DEFAULT_SETTINGS.copy()
                    merged.update(json.load(f))
                    return merged
            except Exception:
                pass
        return DEFAULT_SETTINGS.copy()

    def _save_settings(self):
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=2)

    def _delete_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                os.remove(SETTINGS_FILE)
                self.settings = DEFAULT_SETTINGS.copy()
                self._set_status('Config deleted')
                return True
            except Exception as e:
                self._set_status(f'Error deleting config: {str(e)[:40]}')
                return False
        return True

    # ── Windows autostart ─────────────────────────────────────────────────────

    def _set_autostart(self, enable: bool):
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}" "{os.path.abspath(__file__)}"')
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f'Autostart error: {e}')

    # ── Network helpers ───────────────────────────────────────────────────────

    def _get_public_ipv4(self):
        services = [
            'https://api.ipify.org',
            'https://icanhazip.com',
            'https://checkip.amazonaws.com',
            'https://ipecho.net/plain',
        ]
        for url in services:
            try:
                r = requests.get(url, timeout=8)
                ip = r.text.strip()
                if ip and self._is_valid_ipv4(ip):
                    return ip
            except Exception:
                continue
        return None

    def _get_public_ipv6(self):
        services = [
            'https://api64.ipify.org',
            'https://icanhazip.com',
            'https://checkip.amazonaws.com',
        ]
        for url in services:
            try:
                r = requests.get(url, timeout=8)
                ip = r.text.strip()
                if ip and self._is_valid_ipv6(ip):
                    return ip
            except Exception:
                continue
        return None

    @staticmethod
    def _is_valid_ipv4(ip: str) -> bool:
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            return False

    @staticmethod
    def _is_valid_ipv6(ip: str) -> bool:
        try:
            import ipaddress
            ipaddress.IPv6Address(ip)
            return True
        except Exception:
            return False

    def _do_pdns_update(self, record_type: str, ip: str) -> bool:
        hostname = self.settings['hostname'].rstrip('.')
        zone = self.settings['zone'].rstrip('.')
        api_key = self.settings['api_key']
        pdns_url = self.settings['pdns_url'].rstrip('/')
        ttl = int(self.settings.get('ttl', 3600))

        if not all([hostname, zone, api_key, pdns_url]):
            self._set_status('Not configured')
            return False

        # Build FQDN (fully qualified domain name) with trailing dot
        if not hostname.endswith(zone):
            fqdn = f'{hostname}.{zone}.'
        else:
            fqdn = hostname if hostname.endswith('.') else f'{hostname}.'

        # PowerDNS API expects trailing dot on zone name
        zone_with_dot = f'{zone}.'

        url = f'{pdns_url}/api/v1/servers/localhost/zones/{zone_with_dot}'
        headers = {
            'X-API-Key': api_key,
            'Content-Type': 'application/json',
        }

        rrsets = {
            'rrsets': [
                {
                    'name': fqdn,
                    'type': record_type,
                    'changetype': 'REPLACE',
                    'ttl': ttl,
                    'records': [
                        {
                            'content': ip,
                            'disabled': False,
                        }
                    ],
                }
            ]
        }

        try:
            r = requests.patch(url, json=rrsets, headers=headers, timeout=15)

            if r.status_code == 204:
                self._set_status(f'Updated {record_type} -> {ip}')
                if record_type == 'A':
                    self.settings['last_ipv4'] = ip
                elif record_type == 'AAAA':
                    self.settings['last_ipv6'] = ip
                self.settings['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
                self._save_settings()
                return True

            elif r.status_code == 401:
                self._set_status('Error: invalid API key')
            elif r.status_code == 404:
                self._set_status('Error: zone or hostname not found')
            elif r.status_code == 400:
                try:
                    err = r.json().get('error', 'bad request')
                    self._set_status(f'Error: {err[:50]}')
                except Exception:
                    self._set_status('Error: bad request (400)')
            else:
                self._set_status(f'Error: HTTP {r.status_code}')

            return False

        except requests.exceptions.ConnectionError:
            self._set_status('Error: cannot reach PowerDNS server')
            return False
        except requests.exceptions.Timeout:
            self._set_status('Error: PowerDNS server timeout')
            return False
        except Exception as e:
            self._set_status(f'Error: {str(e)[:50]}')
            return False

    def _do_pdns_update_multi(self, updates: dict) -> bool:
        """Update multiple record types (A and/or AAAA) in a single API call.
        updates: dict like {'A': '203.0.113.45', 'AAAA': '2001:db8::1'}
        """
        hostname = self.settings['hostname'].rstrip('.')
        zone = self.settings['zone'].rstrip('.')
        api_key = self.settings['api_key']
        pdns_url = self.settings['pdns_url'].rstrip('/')
        ttl = int(self.settings.get('ttl', 3600))

        if not all([hostname, zone, api_key, pdns_url]):
            self._set_status('Not configured')
            return False

        # Build FQDN (fully qualified domain name) with trailing dot
        if not hostname.endswith(zone):
            fqdn = f'{hostname}.{zone}.'
        else:
            fqdn = hostname if hostname.endswith('.') else f'{hostname}.'

        zone_with_dot = f'{zone}.'
        url = f'{pdns_url}/api/v1/servers/localhost/zones/{zone_with_dot}'
        headers = {
            'X-API-Key': api_key,
            'Content-Type': 'application/json',
        }

        # Build RRsets array with all record types
        rrsets_list = []
        for record_type, ip in updates.items():
            rrsets_list.append({
                'name': fqdn,
                'type': record_type,
                'changetype': 'REPLACE',
                'ttl': ttl,
                'records': [{'content': ip, 'disabled': False}],
            })

        payload = {'rrsets': rrsets_list}

        try:
            r = requests.patch(url, json=payload, headers=headers, timeout=15)

            if r.status_code == 204:
                types_str = ', '.join(updates.keys())
                self._set_status(f'Updated {types_str}')
                if 'A' in updates:
                    self.settings['last_ipv4'] = updates['A']
                if 'AAAA' in updates:
                    self.settings['last_ipv6'] = updates['AAAA']
                self.settings['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
                self._save_settings()
                return True

            elif r.status_code == 401:
                self._set_status('Error: invalid API key')
            elif r.status_code == 404:
                self._set_status('Error: zone or hostname not found')
            elif r.status_code == 400:
                try:
                    err = r.json().get('error', 'bad request')
                    self._set_status(f'Error: {err[:50]}')
                except Exception:
                    self._set_status('Error: bad request (400)')
            else:
                self._set_status(f'Error: HTTP {r.status_code}')

            return False

        except requests.exceptions.ConnectionError:
            self._set_status('Error: cannot reach PowerDNS server')
            return False
        except requests.exceptions.Timeout:
            self._set_status('Error: PowerDNS server timeout')
            return False
        except Exception as e:
            self._set_status(f'Error: {str(e)[:50]}')
            return False

    def _set_status(self, msg: str):
        self.status = msg
        self.settings['last_status'] = msg
        if self.icon:
            self.icon.title = f'PowerDNS Updater\n{msg}'

    # ── Background update loop ────────────────────────────────────────────────

    def _update_loop(self):
        self.stop_event.wait(3)

        while not self.stop_event.is_set():
            if self.settings.get('enabled') and self.settings.get('hostname') and self.settings.get('zone'):
                record_type = self.settings.get('record_type', 'A')

                if record_type == 'BOTH':
                    self._set_status('Checking IPv4 and IPv6...')
                    if self.icon:
                        self.icon.update_menu()

                    ipv4 = self._get_public_ipv4()
                    ipv6 = self._get_public_ipv6()
                    updates = {}

                    if ipv4 and self._is_valid_ipv4(ipv4) and ipv4 != self.settings.get('last_ipv4'):
                        updates['A'] = ipv4
                    if ipv6 and self._is_valid_ipv6(ipv6) and ipv6 != self.settings.get('last_ipv6'):
                        updates['AAAA'] = ipv6

                    if updates:
                        self._do_pdns_update_multi(updates)
                    else:
                        if not ipv4 or not ipv6:
                            self._set_status('Error: cannot detect IP address')
                        else:
                            self._set_status(f'IPs unchanged')

                else:
                    self._set_status(f'Checking {record_type} IP...')
                    if self.icon:
                        self.icon.update_menu()

                    if record_type == 'A':
                        ip = self._get_public_ipv4()
                        field = 'last_ipv4'
                    elif record_type == 'AAAA':
                        ip = self._get_public_ipv6()
                        field = 'last_ipv6'
                    else:
                        ip = None
                        field = None

                    if ip:
                        if ip != self.settings.get(field):
                            self._do_pdns_update(record_type, ip)
                        else:
                            self._set_status(f'{record_type} unchanged ({ip})')
                    else:
                        self._set_status(f'Error: cannot detect {record_type} address')

                if self.icon:
                    self.icon.update_menu()
            else:
                self._set_status('Disabled' if not self.settings.get('enabled') else 'Not configured')

            self.stop_event.wait(self.settings.get('interval', 300))

    def _restart_loop(self):
        self.stop_event.set()
        if self.update_thread:
            self.update_thread.join(timeout=5)
        self.stop_event.clear()
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()

    # ── Tray menu actions ─────────────────────────────────────────────────────

    def _action_update_now(self, icon=None, item=None):
        def _run():
            record_type = self.settings.get('record_type', 'A')

            if record_type == 'BOTH':
                self._set_status('Checking IPv4 and IPv6...')
                if self.icon:
                    self.icon.update_menu()

                ipv4 = self._get_public_ipv4()
                ipv6 = self._get_public_ipv6()
                updates = {}

                if ipv4 and self._is_valid_ipv4(ipv4):
                    updates['A'] = ipv4
                if ipv6 and self._is_valid_ipv6(ipv6):
                    updates['AAAA'] = ipv6

                if updates:
                    self._do_pdns_update_multi(updates)
                else:
                    self._set_status('Error: cannot detect IP address')
            else:
                self._set_status('Checking IP...')
                if self.icon:
                    self.icon.update_menu()
                if record_type == 'A':
                    ip = self._get_public_ipv4()
                else:
                    ip = self._get_public_ipv6()
                if ip:
                    self._do_pdns_update(record_type, ip)
                else:
                    self._set_status('Error: cannot detect IP address')

            if self.icon:
                self.icon.update_menu()
        threading.Thread(target=_run, daemon=True).start()

    def _action_open_settings(self, icon=None, item=None):
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.lift()
            self._settings_window.focus_force()
            return
        threading.Thread(target=self._show_settings, daemon=True).start()

    def _action_quit(self, icon, item):
        self.stop_event.set()
        icon.stop()

    # ── Settings window ───────────────────────────────────────────────────────

    def _show_settings(self):
        root = tk.Tk()
        root.title('PowerDNS Updater — Settings')
        root.resizable(False, False)
        self._settings_window = root

        WIN_W, WIN_H = 380, 520
        root.update_idletasks()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f'{WIN_W}x{WIN_H}+{(sw - WIN_W) // 2}+{(sh - WIN_H) // 2}')

        style = ttk.Style(root)
        style.theme_use('vista')

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(root, bg='#E63946', height=40)
        hdr.pack(fill='x')
        tk.Label(hdr, text='PowerDNS Updater', bg='#E63946', fg='white',
                 font=('Segoe UI', 12, 'bold')).pack(side='left', padx=12, pady=8)

        # ── Buttons at top ─────────────────────────────────────────────────────
        def _save(close=True):
            self.settings['pdns_url'] = vars_['pdns_url'].get().strip()
            self.settings['api_key'] = vars_['api_key'].get()
            self.settings['zone'] = vars_['zone'].get().strip()
            self.settings['hostname'] = vars_['hostname'].get().strip()
            self.settings['record_type'] = vars_['record_type'].get()
            self.settings['ttl'] = max(60, ttl_var.get())
            iv = max(60, interval_var.get())
            self.settings['interval'] = iv
            self.settings['enabled'] = enabled_var.get()
            self.settings['autostart'] = autostart_var.get()
            self._save_settings()
            self._set_autostart(autostart_var.get())
            self._restart_loop()
            if close:
                root.destroy()

        def _update_only():
            self._action_update_now()

        def _save_and_update():
            _save(close=False)
            self._action_update_now()
            root.destroy()

        def _delete_config():
            if messagebox.askyesno('Delete Config', 'Remove all saved settings?\nThis cannot be undone.'):
                self._delete_settings()
                self._restart_loop()
                root.destroy()

        btn_frame = ttk.Frame(root, padding=3)
        btn_frame.pack(fill='x')

        row1 = ttk.Frame(btn_frame)
        row1.pack(fill='x', pady=2)
        ttk.Button(row1, text='Save', command=_save, width=9).pack(side='left', padx=2)
        ttk.Button(row1, text='Update', command=_update_only, width=9).pack(side='left', padx=2)
        ttk.Button(row1, text='Cancel', command=root.destroy, width=9).pack(side='left', padx=2)

        row2 = ttk.Frame(btn_frame)
        row2.pack(fill='x', pady=2)
        ttk.Button(row2, text='Save & Update', command=_save_and_update, width=18).pack(side='left', padx=2)
        ttk.Button(row2, text='Delete Config', command=_delete_config, width=18).pack(side='left', padx=2)

        # ── Scrollable content ─────────────────────────────────────────────────
        canvas = tk.Canvas(root, highlightthickness=0, bg='white')
        scrollbar = ttk.Scrollbar(root, orient='vertical', command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind(
            '<Configure>',
            lambda e: canvas.configure(scrollregion=canvas.bbox('all'))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True, padx=12, pady=(0, 8))
        scrollbar.pack(side='right', fill='y')

        # ── Form ──────────────────────────────────────────────────────────────
        conn = ttk.LabelFrame(scrollable_frame, text='PowerDNS Connection', padding=8)
        conn.pack(fill='x', pady=(0, 3))

        conn_fields = [
            ('API URL', 'pdns_url', False),
            ('API Key', 'api_key', True),
        ]
        vars_ = {}
        row = 0
        for label, key, is_secret in conn_fields:
            ttk.Label(conn, text=label + ':', width=16, anchor='e').grid(row=row, column=0, padx=5, pady=2, sticky='e')
            v = tk.StringVar(value=self.settings.get(key, ''))
            vars_[key] = v
            kw = {'show': '●'} if is_secret else {}
            ttk.Entry(conn, textvariable=v, width=28, **kw).grid(row=row, column=1, pady=2, sticky='w')
            row += 1

        # ── DNS section ───────────────────────────────────────────────────────
        dns = ttk.LabelFrame(scrollable_frame, text='DNS Record', padding=8)
        dns.pack(fill='x', pady=3)

        dns_fields = [
            ('Zone', 'zone', False),
            ('Hostname', 'hostname', False),
        ]
        row = 0
        for label, key, is_secret in dns_fields:
            ttk.Label(dns, text=label + ':', width=16, anchor='e').grid(row=row, column=0, padx=5, pady=2, sticky='e')
            v = tk.StringVar(value=self.settings.get(key, ''))
            vars_[key] = v
            ttk.Entry(dns, textvariable=v, width=28).grid(row=row, column=1, pady=2, sticky='w')
            row += 1

        # Record type
        ttk.Label(dns, text='Record Type:', width=16, anchor='e').grid(row=row, column=0, padx=5, pady=2, sticky='e')
        rtype_var = tk.StringVar(value=self.settings.get('record_type', 'A'))
        vars_['record_type'] = rtype_var
        ttk.Combobox(dns, textvariable=rtype_var, values=['A', 'AAAA', 'BOTH'], state='readonly', width=32).grid(
            row=row, column=1, pady=2, sticky='w')
        row += 1

        # TTL
        ttk.Label(dns, text='TTL (seconds):', width=16, anchor='e').grid(row=row, column=0, padx=5, pady=2, sticky='e')
        ttl_var = tk.IntVar(value=self.settings.get('ttl', 3600))
        vars_['ttl'] = ttl_var
        ttk.Spinbox(dns, from_=60, to=86400, textvariable=ttl_var, width=33).grid(row=row, column=1, pady=2, sticky='w')

        # ── Options ───────────────────────────────────────────────────────────
        opts = ttk.LabelFrame(scrollable_frame, text='Options', padding=8)
        opts.pack(fill='x', pady=3)

        interval_var = tk.IntVar(value=self.settings.get('interval', 300))
        enabled_var = tk.BooleanVar(value=self.settings.get('enabled', True))
        autostart_var = tk.BooleanVar(value=self.settings.get('autostart', False))

        ttk.Label(opts, text='Check interval:', anchor='e', width=16).grid(row=0, column=0, padx=5, pady=1, sticky='e')
        ifrm = ttk.Frame(opts)
        ifrm.grid(row=0, column=1, pady=1, sticky='w')
        ttk.Spinbox(ifrm, from_=60, to=86400, textvariable=interval_var, width=8).pack(side='left')
        ttk.Label(ifrm, text=' seconds (min 60)').pack(side='left')

        ttk.Checkbutton(opts, text='Enable automatic updates', variable=enabled_var).grid(
            row=1, column=0, columnspan=2, padx=5, pady=1, sticky='w')
        ttk.Checkbutton(opts, text='Start with Windows', variable=autostart_var).grid(
            row=2, column=0, columnspan=2, padx=5, pady=1, sticky='w')

        # ── Status ────────────────────────────────────────────────────────────
        stat = ttk.LabelFrame(scrollable_frame, text='Last Status', padding=8)
        stat.pack(fill='x', pady=3)

        last_v4 = self.settings.get('last_ipv4') or '—'
        last_v6 = self.settings.get('last_ipv6') or '—'
        last_ts = self.settings.get('last_update') or 'never'
        tk.Label(stat, text=f'IPv4: {last_v4}   |   IPv6: {last_v6}',
                 font=('Segoe UI', 9)).pack(anchor='w')
        tk.Label(stat, text=f'Last update: {last_ts}',
                 font=('Segoe UI', 9)).pack(anchor='w')
        tk.Label(stat, text=f'Status: {self.status}',
                 font=('Segoe UI', 9), fg='#E63946').pack(anchor='w')

        root.protocol('WM_DELETE_WINDOW', root.destroy)
        root.mainloop()
        self._settings_window = None

    # ── Tray icon image ───────────────────────────────────────────────────────

    @staticmethod
    def _make_icon() -> Image.Image:
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Red circle background
        d.ellipse([2, 2, size - 2, size - 2], fill=(230, 57, 70))

        # Simple "P" letter
        try:
            font = ImageFont.truetype('segoeui.ttf', 32)
        except Exception:
            font = ImageFont.load_default()

        text = 'P'
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - 2),
               text, font=font, fill='white')

        # Small green dot indicator (bottom-right)
        d.ellipse([44, 44, 60, 60], fill=(76, 175, 80), outline='white', width=2)

        return img

    def _make_menu(self):
        return pystray.Menu(
            Item(f'Status: {self.status}', None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item('Update Now', self._action_update_now),
            Item('Settings...', self._action_open_settings),
            pystray.Menu.SEPARATOR,
            Item('Quit', self._action_quit),
        )

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self):
        self._restart_loop()

        icon_img = self._make_icon()

        self.icon = pystray.Icon(
            APP_NAME,
            icon_img,
            f'PowerDNS Updater\n{self.status}',
            self._make_menu(),
        )
        self.icon.run()


if __name__ == '__main__':
    PowerDNSUpdater().run()
