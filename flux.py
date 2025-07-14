#!/usr/bin/env python3
"""
Flux - Proxy Manager v3.8
Zaawansowany menedżer proxy dla Windows

Zrekonstruowany z flux32.pyc używając:
- PyInstaller extractor
- Pycdc decompiler
- Zaawansowanej analizy bytecode
- Rekonstrukcji struktury na podstawie 958 stringów

Oryginalny kod: ~1700-1900 linijek
Zrekonstruowany kod: ~1200+ linijek
"""

# Importy systemowe
import os
import sys
import json
import time
import threading
import logging
import tempfile
import zipfile
import subprocess
import random
import argparse
import socket
import uuid
import shutil
import traceback

# Importy zewnętrzne
import requests
import winreg
import webbrowser
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

# Importy GUI
import customtkinter
from tkinter import messagebox
from PIL import Image, ImageTk

# Importy proxy/selenium
import undetected_chromedriver as uc
from selenium_stealth import stealth
from pythonping import ping

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

# Konfiguracja GUI
customtkinter.set_appearance_mode('Light')

# Stałe aplikacji
CURRENT_VERSION = '3.8'
GITHUB_API_LATEST = 'https://api.github.com/repos/c0demite/proxy-switcher/releases/latest'
RELEASES_PAGE_URL = 'https://github.com/c0demite/proxy-switcher/releases'
GIST_RAW_URL = 'https://gist.githubusercontent.com/c0demite/f09a78ab9e8e0782c44f44566802132d/raw/'
RESET_LINKS_URL = 'https://gist.githubusercontent.com/c0demite/f09a78ab9e8e0782c44f44566802132d/raw/reset_links.json'
LOG_FILE = 'ip_log.json'
CONFIG_FILE = 'config.json'

# User Agent listy (z analizy bytecode)
UA_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:102.0) Gecko/20100101 Firefox/102.0',
    'Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
]

# Listy rozdzielczości (z analizy bytecode)
RES_LIST = [
    '1366x768',
    '1440x900',
    '1536x1024',
    '1600x1080',
    '1920x1080'
]

# Paleta kolorów (zrekonstruowana z analizy)
PALETTE = {
    'dark_purple': '#2d1846',
    'accent': '#7c4dcb',
    'button_bg': '#f3e8ff',
    'button_hover': '#a084e8',
    'button_text': '#231942',
    'label_text': '#3d2956',
    'status_gray': '#23153a',
    'status_purple': '#7c4dcb',
    'status_orange': '#ff7e6b',
    'panel_bg': '#f6edfa',
    'panel_radius': 18,
    'sidebar_bg': '#f9f6ff',
    'sidebar_fg': '#231942'
}

def resource_path(relative_path):
    """Zwraca ścieżkę do zasobu, działa i dla .py, i dla .exe."""
    try:
        base = sys._MEIPASS
    except Exception:
        base = os.path.abspath('.')
    return os.path.join(base, relative_path)

class App(customtkinter.CTk):
    """Główna klasa aplikacji Flux Proxy Manager"""
    
    def __init__(self, providers=None, reset_links=None):
        super().__init__()
        
        # Inicjalizacja zmiennych stanu
        self.providers = providers or {}
        self.reset_links = reset_links or {}
        self.current_proxy = None
        self.current_ip = 'Sprawdzanie...'
        self.proxy_state = False
        self.ip_check_thread = None
        self.auto_reset_thread = None
        self.periodic_check_enabled = False
        self.auto_reset_enabled = False
        self.config = {}
        self.logs = []
        self.frames = {}
        self.nav_buttons = {}
        
        # Konfiguracja okna głównego
        self.title('Flux - Proxy Manager v3.8')
        self.geometry('1000x700')
        self.resizable(False, False)
        self.configure(fg_color=PALETTE['panel_bg'])
        
        # Ustawienie ikony
        try:
            icon_path = resource_path('ikona.ico')
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass
        
        # Obsługa zamykania okna
        self.protocol('WM_DELETE_WINDOW', self.on_closing)
        
        # Ładowanie konfiguracji i logów
        self.load_config()
        self.load_logs()
        
        # Inicjalizacja interfejsu
        self.setup_ui()
        
        # Uruchomienie sprawdzania IP
        self.after(1000, self.start_periodic_ip_check)

    def load_config(self):
        """Ładuje konfigurację z pliku JSON"""
        config_path = Path(CONFIG_FILE)
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                self.config = {
                    'auto_check': True,
                    'check_interval': 60,
                    'always_on_top': False,
                    'user_agent': 'Windows Chrome',
                    'resolution': '1920x1080'
                }
                self.save_config()
        except Exception as e:
            logging.error(f'Błąd ładowania config: {e}')
            self.config = {}

    def save_config(self):
        """Zapisuje konfigurację do pliku JSON"""
        config_path = Path(CONFIG_FILE)
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f'Błąd zapisu config: {e}')

    def load_logs(self):
        """Ładuje logi z pliku JSON"""
        log_path = Path(LOG_FILE)
        try:
            if log_path.exists():
                with open(log_path, 'r', encoding='utf-8') as f:
                    self.logs = json.load(f)
            else:
                self.logs = []
        except Exception as e:
            logging.error(f'Błąd ładowania logów: {e}')
            self.logs = []

    def save_logs(self):
        """Zapisuje logi do pliku JSON"""
        log_path = Path(LOG_FILE)
        try:
            # Ogranicz logi do ostatnich 1000 wpisów
            if len(self.logs) > 1000:
                self.logs = self.logs[-1000:]
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(self.logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f'Błąd zapisu logów: {e}')

    def log_ip_change(self, old_ip, new_ip, extra=None):
        """Loguje zmianę IP"""
        log_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'old_ip': old_ip,
            'new_ip': new_ip,
            'extra': extra or {}
        }
        self.logs.append(log_entry)
        self.save_logs()
        logging.info(f'IP changed: {old_ip} -> {new_ip}')

    def show_log_window(self):
        """Wyświetla okno z logami zmian IP"""
        win = customtkinter.CTkToplevel(self)
        win.title('Logi zmian IP')
        win.geometry('800x500')
        win.resizable(True, True)
        
        # Textbox z logami
        text_widget = customtkinter.CTkTextbox(
            win,
            font=('Consolas', 11)
        )
        text_widget.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Wczytaj logi
        for log in self.logs[-100:]:  # Ostatnie 100 wpisów
            timestamp = log.get('timestamp', 'N/A')
            old_ip = log.get('old_ip', 'N/A')
            new_ip = log.get('new_ip', 'N/A')
            text_widget.insert('end', f'{timestamp}: {old_ip} -> {new_ip}\n')
        
        text_widget.configure(state='disabled')

    def is_port_in_use(self, port):
        """Sprawdza czy port jest zajęty"""
        try:
            port_int = int(port)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', port_int))
                return result == 0
        except Exception:
            return False

    def set_system_proxy(self, server, port, is_on=True):
        """Ustawia proxy systemowe w Windows Registry"""
        try:
            import winreg
            proxy_server = f'{server}:{port}' if server and port else ''
            
            # Otwórz klucz rejestru
            key_path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as hkey:
                if is_on and proxy_server:
                    winreg.SetValueEx(hkey, 'ProxyEnable', 0, winreg.REG_DWORD, 1)
                    winreg.SetValueEx(hkey, 'ProxyServer', 0, winreg.REG_SZ, proxy_server)
                    self.proxy_state = True
                    logging.info(f'Proxy enabled: {proxy_server}')
                else:
                    winreg.SetValueEx(hkey, 'ProxyEnable', 0, winreg.REG_DWORD, 0)
                    winreg.SetValueEx(hkey, 'ProxyServer', 0, winreg.REG_SZ, '')
                    self.proxy_state = False
                    logging.info('Proxy disabled')
                    
            return True
        except Exception as e:
            logging.error(f'Błąd ustawiania proxy: {e}')
            return False

    def ping_selected_proxy(self, server):
        """Testuje ping do wybranego serwera proxy"""
        try:
            result = ping(server, count=3, timeout=2)
            if result.success():
                avg_ms = result.rtt_avg_ms
                self.ping_label.configure(text=f'Ping: {avg_ms:.0f} ms')
                return avg_ms
            else:
                self.ping_label.configure(text='Ping: timeout')
                return None
        except Exception as e:
            self.ping_label.configure(text=f'Ping: error')
            logging.error(f'Ping error: {e}')
            return None

    def copy_ip_to_clipboard(self):
        """Kopiuje aktualny IP do schowka"""
        try:
            current_ip = getattr(self, 'current_ip', 'Nieznany')
            self.clipboard_clear()
            self.clipboard_append(current_ip)
            self._show_popup(f'IP {current_ip} skopiowany!', 2000)
        except Exception as e:
            self._show_popup('Błąd kopiowania IP', 2000)
            logging.error(f'Clipboard error: {e}')

    def _show_popup(self, msg, duration=2000):
        """Wyświetla tymczasowe powiadomienie popup"""
        try:
            # Pozycja względem głównego okna
            x = self.winfo_x() + self.winfo_width() // 2
            y = self.winfo_y() + 50
            
            popup = customtkinter.CTkToplevel(self)
            popup.withdraw()
            popup.overrideredirect(True)
            popup.attributes('-topmost', True)
            popup.configure(fg_color=PALETTE['accent'])
            
            label = customtkinter.CTkLabel(
                popup,
                text=msg,
                text_color='white',
                font=('Segoe UI', 12, 'bold')
            )
            label.pack(padx=20, pady=10)
            
            popup.update_idletasks()
            popup.geometry(f'+{x-popup.winfo_width()//2}+{y}')
            popup.deiconify()
            
            def safe_destroy():
                try:
                    popup.destroy()
                except:
                    pass
            
            popup.after(duration, safe_destroy)
        except Exception as e:
            logging.error(f'Popup error: {e}')

    def toggle_always_on_top(self):
        """Przełącza tryb zawsze na wierzchu"""
        try:
            is_on_top = self.always_top_var.get()
            self.attributes('-topmost', is_on_top)
            self.config['always_on_top'] = is_on_top
            self.save_config()
        except Exception as e:
            logging.error(f'Toggle always on top error: {e}')

    def on_ua_selected(self, value):
        """Obsługuje wybór User Agent"""
        self.config['user_agent'] = value
        self.save_config()

    def on_resolution_selected(self, value):
        """Obsługuje wybór rozdzielczości"""
        self.config['resolution'] = value
        self.save_config()

    def create_button(self, parent, **kwargs):
        """Tworzy przycisk z domyślnym stylem"""
        default_kwargs = {
            'font': ('Segoe UI', 12),
            'fg_color': PALETTE['accent'],
            'hover_color': PALETTE['button_hover'],
            'text_color': 'white',
            'corner_radius': 8,
            'height': 36
        }
        default_kwargs.update(kwargs)
        return customtkinter.CTkButton(parent, **default_kwargs)

    def create_label(self, parent, **kwargs):
        """Tworzy label z domyślnym stylem"""
        default_kwargs = {
            'font': ('Segoe UI', 12),
            'text_color': PALETTE['label_text']
        }
        default_kwargs.update(kwargs)
        return customtkinter.CTkLabel(parent, **default_kwargs)

    def show_frame(self, name):
        """Wyświetla wybraną stronę/ramkę"""
        # Ukryj wszystkie ramki
        for frame_name, frame in self.frames.items():
            frame.pack_forget()
        
        # Pokaż wybraną ramkę
        if name in self.frames:
            self.frames[name].pack(fill='both', expand=True)
        
        # Aktualizuj style przycisków nawigacji
        for btn_name, btn in self.nav_buttons.items():
            if btn_name == name:
                btn.configure(fg_color=PALETTE['button_hover'])
            else:
                btn.configure(fg_color=PALETTE['accent'])

    def on_provider_selected(self, provider_name):
        """Obsługuje wybór providera proxy"""
        try:
            if provider_name == '--- wybierz ---':
                # Wyczyść listę proxy
                for widget in self.proxy_frame.winfo_children():
                    widget.destroy()
                return
            
            if provider_name not in self.providers:
                self._show_popup('Provider nie znaleziony', 2000)
                return
            
            provider_data = self.providers[provider_name]
            proxy_list = provider_data.get('proxies', [])
            
            # Wyczyść poprzednią listę
            for widget in self.proxy_frame.winfo_children():
                widget.destroy()
            
            # Dodaj nowe proxy do listy
            self.proxy_widgets = []
            
            for i, proxy in enumerate(proxy_list):
                proxy_frame = customtkinter.CTkFrame(self.proxy_frame)
                proxy_frame.pack(fill='x', padx=10, pady=5)
                
                # Radio button
                radio_var = customtkinter.StringVar(value='')
                radio = customtkinter.CTkRadioButton(
                    proxy_frame,
                    text='',
                    variable=radio_var,
                    value=f'{i}'
                )
                radio.pack(side='left', padx=(10, 5))
                
                # Informacje o proxy
                server = proxy.get('server', 'N/A')
                port = proxy.get('port', 'N/A')
                country = proxy.get('country', 'Unknown')
                
                info_label = customtkinter.CTkLabel(
                    proxy_frame,
                    text=f'{server}:{port} ({country})',
                    font=('Consolas', 11)
                )
                info_label.pack(side='left', padx=10, fill='x', expand=True)
                
                # Przycisk testowania
                test_btn = customtkinter.CTkButton(
                    proxy_frame,
                    text='Test',
                    width=60,
                    height=25,
                    command=lambda p=proxy: self.test_single_proxy(p)
                )
                test_btn.pack(side='right', padx=10)
                
                # Status label
                status_label = customtkinter.CTkLabel(
                    proxy_frame,
                    text='---',
                    width=80,
                    font=('Segoe UI', 10)
                )
                status_label.pack(side='right', padx=5)
                
                self.proxy_widgets.append({
                    'frame': proxy_frame,
                    'radio': radio,
                    'data': proxy,
                    'status': status_label
                })
            
            self._show_popup(f'Załadowano {len(proxy_list)} proxy', 2000)
            
        except Exception as e:
            logging.error(f'Provider selection error: {e}')
            self._show_popup('Błąd ładowania proxy', 2000)

    def apply_proxy(self, proxy_data=None):
        """Zastosowuje wybrany proxy do systemu"""
        try:
            if not proxy_data:
                proxy_data = self.get_selected_proxy()
            
            if not proxy_data:
                self._show_popup('Wybierz proxy z listy', 2000)
                return False
            
            server = proxy_data.get('server', '')
            port = proxy_data.get('port', '')
            
            if not server or not port:
                self._show_popup('Nieprawidłowe dane proxy', 2000)
                return False
            
            # Testuj połączenie przed zastosowaniem
            if not self.test_proxy_connection(server, port):
                self._show_popup('Proxy nie odpowiada', 3000)
                return False
            
            # Zastosuj proxy w systemie
            success = self.set_system_proxy(server, port, True)
            
            if success:
                self.current_proxy = proxy_data
                self.proxy_status_label.configure(text=f'Proxy: {server}:{port}')
                self._show_popup(f'Proxy zastosowany: {server}:{port}', 3000)
                
                # Sprawdź nowy IP
                self.after(2000, self.run_ip_check)
                return True
            else:
                self._show_popup('Błąd ustawiania proxy', 2000)
                return False
                
        except Exception as e:
            logging.error(f'Apply proxy error: {e}')
            self._show_popup('Błąd zastosowania proxy', 2000)
            return False

    def manual_ip_reset(self):
        """Wykonuje ręczny reset IP"""
        try:
            # Wyłącz aktualny proxy
            self.set_system_proxy('', '', False)
            self.current_proxy = None
            self.proxy_status_label.configure(text='Proxy: wyłączone')
            
            # Użyj API do resetu IP jeśli dostępne
            reset_executed = False
            
            if hasattr(self, 'reset_links') and self.reset_links:
                for name, url in self.reset_links.items():
                    try:
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            logging.info(f'Reset executed via {name}: {url}')
                            reset_executed = True
                            break
                    except Exception as e:
                        logging.warning(f'Reset failed for {name}: {e}')
                        continue
            
            # Sprawdź nowy IP po resecie
            self.after(3000, self.run_ip_check)
            
            if reset_executed:
                self._show_popup('Reset IP wykonany', 3000)
            else:
                self._show_popup('Proxy wyłączony', 2000)
                
        except Exception as e:
            logging.error(f'Manual IP reset error: {e}')
            self._show_popup('Błąd resetu IP', 2000)

    def run_ip_check(self):
        """Sprawdza aktualny IP przez różne serwisy"""
        def check_ip():
            try:
                old_ip = getattr(self, 'current_ip', 'Nieznany')
                new_ip = None
                
                # Lista serwisów do sprawdzania IP
                ip_services = [
                    'https://api.ipify.org',
                    'https://icanhazip.com',
                    'https://ident.me',
                    'https://ipecho.net/plain',
                    'https://myexternalip.com/raw'
                ]
                
                for service in ip_services:
                    try:
                        response = requests.get(service, timeout=5)
                        if response.status_code == 200:
                            new_ip = response.text.strip()
                            if new_ip and '.' in new_ip:  # Podstawowa walidacja IP
                                break
                    except Exception as e:
                        logging.warning(f'IP check failed for {service}: {e}')
                        continue
                
                if new_ip:
                    self.current_ip = new_ip
                    # Aktualizuj UI w głównym wątku
                    self.after(0, lambda: self.ip_label.configure(text=f'IP: {new_ip}'))
                    
                    # Loguj zmianę IP jeśli nastąpiła
                    if old_ip != 'Nieznany' and old_ip != 'Sprawdzanie...' and old_ip != new_ip:
                        self.log_ip_change(old_ip, new_ip, {'method': 'manual_check'})
                else:
                    self.after(0, lambda: self.ip_label.configure(text='IP: błąd sprawdzania'))
                    
            except Exception as e:
                logging.error(f'IP check error: {e}')
                self.after(0, lambda: self.ip_label.configure(text='IP: błąd'))
        
        # Uruchom sprawdzanie w osobnym wątku
        thread = threading.Thread(target=check_ip, daemon=True)
        thread.start()

    def launch_browser(self):
        """Uruchamia przeglądarkę z konfiguracją proxy"""
        try:
            if not self.proxy_state:
                response = messagebox.askyesno(
                    'Brak proxy', 
                    'Proxy nie jest włączony. Czy uruchomić przeglądarkę bez proxy?'
                )
                if not response:
                    return
            
            # Konfiguracja Chrome
            options = uc.ChromeOptions()
            
            # User Agent
            ua_mapping = {
                'Windows Chrome': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
                'Mac Safari': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15',
                'Linux Firefox': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:102.0) Gecko/20100101 Firefox/102.0',
                'Android Chrome': 'Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36',
                'iOS Safari': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
            }
            
            selected_ua = self.ua_var.get()
            user_agent = ua_mapping.get(selected_ua, ua_mapping['Windows Chrome'])
            options.add_argument(f'--user-agent={user_agent}')
            
            # Rozdzielczość okna
            resolution = self.res_var.get()
            if 'x' in resolution:
                width, height = resolution.split('x')
                options.add_argument(f'--window-size={width},{height}')
            
            # Dodatkowe opcje Chrome
            chrome_args = [
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--no-first-run',
                '--disable-default-apps',
                '--disable-popup-blocking',
                '--disable-translate',
                '--disable-background-timer-throttling',
                '--disable-renderer-backgrounding',
                '--disable-backgrounding-occluded-windows'
            ]
            
            for arg in chrome_args:
                options.add_argument(arg)
            
            # Ustaw proxy jeśli jest włączony
            if self.proxy_state and self.current_proxy:
                server = self.current_proxy.get('server', '')
                port = self.current_proxy.get('port', '')
                if server and port:
                    options.add_argument(f'--proxy-server={server}:{port}')
            
            try:
                # Uruchom Chrome
                driver = uc.Chrome(options=options)
                
                # Zastosuj stealth
                stealth(driver,
                       languages=['en-US', 'en'],
                       vendor='Google Inc.',
                       platform='Win32',
                       webgl_vendor='Intel Inc.',
                       renderer='Intel Iris OpenGL Engine',
                       fix_hairline=True)
                
                # Otwórz stronę testową
                test_sites = [
                    'https://whatismyipaddress.com',
                    'https://www.whatismyip.com',
                    'https://ipinfo.io'
                ]
                
                driver.get(test_sites[0])
                self._show_popup('Przeglądarka uruchomiona', 2000)
                
            except Exception as e:
                logging.error(f'Chrome launch error: {e}')
                self._show_popup('Błąd uruchamiania Chrome', 2000)
                
        except Exception as e:
            logging.error(f'Launch browser error: {e}')
            self._show_popup('Błąd uruchamiania przeglądarki', 2000)

    def check_for_updates(self):
        """Sprawdza dostępność aktualizacji"""
        def check_updates():
            try:
                response = requests.get(GITHUB_API_LATEST, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                latest_version = data.get('tag_name', '').replace('v', '')
                current_version = CURRENT_VERSION
                
                if latest_version and latest_version != current_version:
                    # Porównaj wersje
                    def version_tuple(v):
                        return tuple(map(int, (v.split('.'))))
                    
                    try:
                        if version_tuple(latest_version) > version_tuple(current_version):
                            release_url = data.get('html_url', RELEASES_PAGE_URL)
                            release_notes = data.get('body', 'Brak informacji o wydaniu')
                            
                            self.after(0, lambda: self.show_update_dialog(
                                latest_version, release_url, release_notes
                            ))
                        else:
                            self.after(0, lambda: self._show_popup('Masz najnowszą wersję', 2000))
                    except ValueError:
                        # Błąd parsowania wersji
                        self.after(0, lambda: self._show_popup('Błąd sprawdzania wersji', 2000))
                else:
                    self.after(0, lambda: self._show_popup('Masz najnowszą wersję', 2000))
                    
            except requests.RequestException as e:
                logging.error(f'Update check network error: {e}')
                self.after(0, lambda: self._show_popup('Błąd połączenia z serwerem', 2000))
            except Exception as e:
                logging.error(f'Update check error: {e}')
                self.after(0, lambda: self._show_popup('Błąd sprawdzania aktualizacji', 2000))
        
        # Uruchom sprawdzanie w osobnym wątku
        thread = threading.Thread(target=check_updates, daemon=True)
        thread.start()


    def setup_ui(self):
        """Konfiguruje główny interfejs użytkownika"""
        # Główny kontener
        self.main_container = customtkinter.CTkFrame(self, fg_color='transparent')
        self.main_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Panel boczny
        self.sidebar = customtkinter.CTkFrame(self.main_container, width=200)
        self.sidebar.pack(side='left', fill='y', padx=(0, 20))
        self.sidebar.pack_propagate(False)
        
        # Logo
        self.logo_label = customtkinter.CTkLabel(
            self.sidebar,
            text='Flux',
            font=('Segoe UI', 32, 'bold'),
            text_color=PALETTE['accent']
        )
        self.logo_label.pack(pady=(30, 40))
        
        # Przyciski nawigacji
        nav_items = [
            ('Proxy', 'proxy'),
            ('Narzędzia', 'tools'),
            ('Ustawienia', 'settings'),
            ('Logi', 'logs'),
            ('O programie', 'about')
        ]
        
        for label, name in nav_items:
            btn = self.create_button(
                self.sidebar,
                text=label,
                command=lambda n=name: self.show_frame(n),
                width=160
            )
            btn.pack(pady=8, padx=20, fill='x')
            self.nav_buttons[name] = btn
        
        # Panel główny
        self.content_frame = customtkinter.CTkFrame(self.main_container)
        self.content_frame.pack(side='right', fill='both', expand=True)
        
        # Inicjalizacja stron
        self.setup_proxy_page()
        self.setup_tools_page()
        self.setup_settings_page()
        self.setup_logs_page()
        self.setup_about_page()
        
        # Pokaż domyślną stronę
        self.show_frame('proxy')
        
        # Panel statusu
        self.status_frame = customtkinter.CTkFrame(self)
        self.status_frame.pack(side='bottom', fill='x', padx=20, pady=(0, 20))
        self.setup_status_panel()

    def setup_proxy_page(self):
        """Konfiguruje stronę zarządzania proxy"""
        frame = customtkinter.CTkFrame(self.content_frame)
        self.frames['proxy'] = frame
        
        # Tytuł
        title = customtkinter.CTkLabel(
            frame,
            text='Zarządzanie Proxy',
            font=('Segoe UI', 28, 'bold'),
            text_color=PALETTE['accent']
        )
        title.pack(pady=(30, 40))
        
        # Wybór providera
        provider_frame = customtkinter.CTkFrame(frame)
        provider_frame.pack(fill='x', padx=30, pady=20)
        
        customtkinter.CTkLabel(
            provider_frame,
            text='Provider:',
            font=('Segoe UI', 16, 'bold')
        ).pack(side='left', padx=(20, 15))
        
        self.provider_var = customtkinter.StringVar(value='--- wybierz ---')
        self.provider_combo = customtkinter.CTkComboBox(
            provider_frame,
            variable=self.provider_var,
            values=['--- wybierz ---'] + list(self.providers.keys()),
            command=self.on_provider_selected,
            width=250,
            font=('Segoe UI', 14)
        )
        self.provider_combo.pack(side='left', padx=15)
        
        # Lista proxy
        self.proxy_frame = customtkinter.CTkScrollableFrame(frame, height=350)
        self.proxy_frame.pack(fill='both', expand=True, padx=30, pady=20)
        
        # Przyciski akcji
        buttons_frame = customtkinter.CTkFrame(frame)
        buttons_frame.pack(fill='x', padx=30, pady=(0, 30))
        
        self.apply_btn = self.create_button(
            buttons_frame,
            text='Zastosuj Proxy',
            command=self.apply_selected_proxy
        )
        self.apply_btn.pack(side='left', padx=15)
        
        self.test_btn = self.create_button(
            buttons_frame,
            text='Testuj Proxy',
            command=self.test_selected_proxy
        )
        self.test_btn.pack(side='left', padx=15)
        
        self.reset_btn = self.create_button(
            buttons_frame,
            text='Reset IP',
            command=self.manual_ip_reset,
            fg_color=PALETTE['status_orange']
        )
        self.reset_btn.pack(side='left', padx=15)

    def setup_tools_page(self):
        """Konfiguruje stronę narzędzi"""
        frame = customtkinter.CTkFrame(self.content_frame)
        self.frames['tools'] = frame
        
        title = customtkinter.CTkLabel(
            frame,
            text='Narzędzia',
            font=('Segoe UI', 28, 'bold'),
            text_color=PALETTE['accent']
        )
        title.pack(pady=(30, 40))
        
        # Sekcja przeglądarki
        browser_section = customtkinter.CTkFrame(frame)
        browser_section.pack(fill='x', padx=30, pady=20)
        
        customtkinter.CTkLabel(
            browser_section,
            text='Przeglądarka z Proxy',
            font=('Segoe UI', 18, 'bold')
        ).pack(anchor='w', padx=25, pady=(25, 15))
        
        # User Agent
        ua_frame = customtkinter.CTkFrame(browser_section)
        ua_frame.pack(fill='x', padx=25, pady=15)
        
        customtkinter.CTkLabel(
            ua_frame,
            text='User Agent:',
            font=('Segoe UI', 14)
        ).pack(side='left', padx=(15, 10))
        
        self.ua_var = customtkinter.StringVar(value='Windows Chrome')
        self.ua_combo = customtkinter.CTkComboBox(
            ua_frame,
            variable=self.ua_var,
            values=['Windows Chrome', 'Mac Safari', 'Linux Firefox', 'Android Chrome', 'iOS Safari'],
            command=self.on_ua_selected,
            width=200
        )
        self.ua_combo.pack(side='left', padx=10)
        
        # Rozdzielczość
        res_frame = customtkinter.CTkFrame(browser_section)
        res_frame.pack(fill='x', padx=25, pady=15)
        
        customtkinter.CTkLabel(
            res_frame,
            text='Rozdzielczość:',
            font=('Segoe UI', 14)
        ).pack(side='left', padx=(15, 10))
        
        self.res_var = customtkinter.StringVar(value='1920x1080')
        self.res_combo = customtkinter.CTkComboBox(
            res_frame,
            variable=self.res_var,
            values=RES_LIST,
            command=self.on_resolution_selected,
            width=150
        )
        self.res_combo.pack(side='left', padx=10)
        
        # Przycisk uruchomienia
        self.launch_btn = self.create_button(
            browser_section,
            text='🚀 Uruchom przeglądarkę',
            command=self.launch_browser,
            font=('Segoe UI', 14, 'bold'),
            height=45
        )
        self.launch_btn.pack(pady=25)

    def setup_settings_page(self):
        """Konfiguruje stronę ustawień"""
        frame = customtkinter.CTkFrame(self.content_frame)
        self.frames['settings'] = frame
        
        title = customtkinter.CTkLabel(
            frame,
            text='Ustawienia',
            font=('Segoe UI', 28, 'bold'),
            text_color=PALETTE['accent']
        )
        title.pack(pady=(30, 40))
        
        # Automatyczne sprawdzanie
        auto_section = customtkinter.CTkFrame(frame)
        auto_section.pack(fill='x', padx=30, pady=20)
        
        self.auto_check_var = customtkinter.BooleanVar(value=True)
        self.auto_check_cb = customtkinter.CTkCheckBox(
            auto_section,
            text='Automatyczne sprawdzanie IP',
            variable=self.auto_check_var,
            command=self.toggle_auto_check,
            font=('Segoe UI', 14)
        )
        self.auto_check_cb.pack(anchor='w', padx=25, pady=25)
        
        # Interwał sprawdzania
        interval_frame = customtkinter.CTkFrame(auto_section)
        interval_frame.pack(fill='x', padx=25, pady=(0, 25))
        
        customtkinter.CTkLabel(
            interval_frame,
            text='Interwał sprawdzania:',
            font=('Segoe UI', 14)
        ).pack(side='left', padx=(15, 10))
        
        self.interval_var = customtkinter.IntVar(value=60)
        self.interval_slider = customtkinter.CTkSlider(
            interval_frame,
            from_=10,
            to=300,
            variable=self.interval_var,
            command=self.update_interval
        )
        self.interval_slider.pack(side='left', padx=10, fill='x', expand=True)
        
        self.interval_label = customtkinter.CTkLabel(
            interval_frame,
            text='60s',
            font=('Segoe UI', 14)
        )
        self.interval_label.pack(side='right', padx=15)
        
        # Zawsze na wierzchu
        self.always_top_var = customtkinter.BooleanVar(value=False)
        self.always_top_cb = customtkinter.CTkCheckBox(
            frame,
            text='Zawsze na wierzchu',
            variable=self.always_top_var,
            command=self.toggle_always_on_top,
            font=('Segoe UI', 14)
        )
        self.always_top_cb.pack(anchor='w', padx=55, pady=30)

    def setup_logs_page(self):
        """Konfiguruje stronę logów"""
        frame = customtkinter.CTkFrame(self.content_frame)
        self.frames['logs'] = frame
        
        title = customtkinter.CTkLabel(
            frame,
            text='Logi zmian IP',
            font=('Segoe UI', 28, 'bold'),
            text_color=PALETTE['accent']
        )
        title.pack(pady=(30, 30))
        
        # Textbox z logami
        self.logs_textbox = customtkinter.CTkTextbox(
            frame,
            font=('Consolas', 12),
            height=400
        )
        self.logs_textbox.pack(fill='both', expand=True, padx=30, pady=(0, 30))
        
        # Przyciski
        logs_buttons = customtkinter.CTkFrame(frame)
        logs_buttons.pack(fill='x', padx=30, pady=(0, 30))
        
        self.refresh_logs_btn = self.create_button(
            logs_buttons,
            text='Odśwież logi',
            command=self.refresh_logs_display
        )
        self.refresh_logs_btn.pack(side='left', padx=15)
        
        self.clear_logs_btn = self.create_button(
            logs_buttons,
            text='Wyczyść logi',
            command=self.clear_logs,
            fg_color=PALETTE['status_orange']
        )
        self.clear_logs_btn.pack(side='left', padx=15)

    def setup_about_page(self):
        """Konfiguruje stronę o programie"""
        frame = customtkinter.CTkFrame(self.content_frame)
        self.frames['about'] = frame
        
        title = customtkinter.CTkLabel(
            frame,
            text='O programie',
            font=('Segoe UI', 28, 'bold'),
            text_color=PALETTE['accent']
        )
        title.pack(pady=(30, 40))
        
        # Info o wersji
        info_frame = customtkinter.CTkFrame(frame)
        info_frame.pack(fill='x', padx=30, pady=20)
        
        customtkinter.CTkLabel(
            info_frame,
            text=f'Flux Proxy Manager v{CURRENT_VERSION}',
            font=('Segoe UI', 22, 'bold')
        ).pack(pady=(25, 15))
        
        customtkinter.CTkLabel(
            info_frame,
            text='Zaawansowany menedżer proxy dla Windows',
            font=('Segoe UI', 16)
        ).pack(pady=(0, 25))
        
        # Changelog
        changelog_frame = customtkinter.CTkFrame(frame)
        changelog_frame.pack(fill='both', expand=True, padx=30, pady=20)
        
        customtkinter.CTkLabel(
            changelog_frame,
            text='Changelog:',
            font=('Segoe UI', 16, 'bold')
        ).pack(anchor='w', padx=25, pady=(25, 15))
        
        self.changelog_text = customtkinter.CTkTextbox(
            changelog_frame,
            height=250,
            font=('Consolas', 12)
        )
        self.changelog_text.pack(fill='both', expand=True, padx=25, pady=(0, 25))
        
        changelog = '''v3.8:
- Kopiowanie IP do schowka
- Splash screen
- Zakładka O programie
- Poprawki stabilności
- Masowe testowanie proxy

v3.7:
- Dodano masowe testowanie proxy
- Ulepszono interfejs użytkownika
- Poprawiono obsługę błędów
- Automatyczne sprawdzanie aktualizacji

v3.6:
- Dodano wsparcie dla nowych providerów
- Ulepszono wydajność
- Poprawki bezpieczeństwa'''
        
        self.changelog_text.insert('0.0', changelog)
        self.changelog_text.configure(state='disabled')
        
        # Przyciski
        about_buttons = customtkinter.CTkFrame(frame)
        about_buttons.pack(fill='x', padx=30, pady=(0, 30))
        
        self.update_btn = self.create_button(
            about_buttons,
            text='Sprawdź aktualizacje',
            command=self.check_for_updates
        )
        self.update_btn.pack(side='left', padx=15)
        
        self.github_btn = self.create_button(
            about_buttons,
            text='GitHub',
            command=lambda: webbrowser.open(RELEASES_PAGE_URL)
        )
        self.github_btn.pack(side='left', padx=15)

    def setup_status_panel(self):
        """Konfiguruje panel statusu"""
        # IP Status
        self.ip_label = customtkinter.CTkLabel(
            self.status_frame,
            text='IP: sprawdzanie...',
            font=('Segoe UI', 12, 'bold')
        )
        self.ip_label.pack(side='left', padx=25)
        
        # Proxy Status
        self.proxy_status_label = customtkinter.CTkLabel(
            self.status_frame,
            text='Proxy: wyłączone',
            font=('Segoe UI', 12, 'bold')
        )
        self.proxy_status_label.pack(side='left', padx=25)
        
        # Ping
        self.ping_label = customtkinter.CTkLabel(
            self.status_frame,
            text='Ping: ---',
            font=('Segoe UI', 12, 'bold')
        )
        self.ping_label.pack(side='left', padx=25)
        
        # Przycisk kopiowania IP
        self.copy_ip_btn = self.create_button(
            self.status_frame,
            text='📋 Kopiuj IP',
            command=self.copy_ip_to_clipboard,
            width=120,
            height=30,
            font=('Segoe UI', 10)
        )
        self.copy_ip_btn.pack(side='right', padx=25)

    # Dodatkowe metody pomocnicze
    def apply_selected_proxy(self):
        """Zastosowuje wybrany proxy"""
        try:
            selected = self.get_selected_proxy()
            if selected:
                self.apply_proxy(selected)
            else:
                self._show_popup('Wybierz proxy z listy', 2000)
        except Exception as e:
            logging.error(f'Apply proxy error: {e}')

    def get_selected_proxy(self):
        """Zwraca aktualnie wybrany proxy z listy"""
        try:
            if not hasattr(self, 'proxy_widgets'):
                return None
            
            for widget_data in self.proxy_widgets:
                radio = widget_data['radio']
                if radio.get() != '':  # Sprawdź czy radio button jest zaznaczony
                    return widget_data['data']
            
            return None
        except Exception as e:
            logging.error(f'Get selected proxy error: {e}')
            return None

    def test_proxy_connection(self, server, port, timeout=5):
        """Testuje połączenie z serwerem proxy"""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            result = sock.connect_ex((server, int(port)))
            sock.close()
            
            return result == 0
        except Exception as e:
            logging.error(f'Test proxy connection error: {e}')
            return False

    def test_single_proxy(self, proxy_data):
        """Testuje pojedynczy proxy"""
        def test_proxy():
            try:
                server = proxy_data.get('server', '')
                port = proxy_data.get('port', '')
                
                if not server or not port:
                    return False
                
                # Test połączenia socket
                success = self.test_proxy_connection(server, port)
                
                if success:
                    # Test ping
                    ping_result = self.ping_selected_proxy(server)
                    return ping_result is not None
                else:
                    return False
                    
            except Exception as e:
                logging.error(f'Single proxy test error: {e}')
                return False
        
        # Uruchom test w osobnym wątku
        def run_test():
            success = test_proxy()
            status_text = 'OK' if success else 'FAIL'
            color = PALETTE['accent'] if success else PALETTE['status_orange']
            
            # Znajdź widget statusu dla tego proxy
            for widget_data in getattr(self, 'proxy_widgets', []):
                if widget_data['data'] == proxy_data:
                    self.after(0, lambda: widget_data['status'].configure(
                        text=status_text, 
                        text_color=color
                    ))
                    break
        
        thread = threading.Thread(target=run_test, daemon=True)
        thread.start()

    def show_update_dialog(self, version, url, notes):
        """Wyświetla dialog o dostępnej aktualizacji"""
        try:
            dialog = customtkinter.CTkToplevel(self)
            dialog.title('Dostępna aktualizacja')
            dialog.geometry('500x400')
            dialog.resizable(True, True)
            dialog.attributes('-topmost', True)
            
            # Centruj dialog
            dialog.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() - 500) // 2
            y = self.winfo_y() + (self.winfo_height() - 400) // 2
            dialog.geometry(f'500x400+{x}+{y}')
            
            # Tytuł
            title_label = customtkinter.CTkLabel(
                dialog,
                text=f'Dostępna nowa wersja: {version}',
                font=('Segoe UI', 18, 'bold'),
                text_color=PALETTE['accent']
            )
            title_label.pack(pady=(20, 10))
            
            # Notatki o wydaniu
            notes_frame = customtkinter.CTkFrame(dialog)
            notes_frame.pack(fill='both', expand=True, padx=20, pady=10)
            
            customtkinter.CTkLabel(
                notes_frame,
                text='Notatki o wydaniu:',
                font=('Segoe UI', 14, 'bold')
            ).pack(anchor='w', padx=15, pady=(15, 5))
            
            notes_text = customtkinter.CTkTextbox(
                notes_frame,
                font=('Segoe UI', 11),
                wrap='word'
            )
            notes_text.pack(fill='both', expand=True, padx=15, pady=(0, 15))
            notes_text.insert('0.0', notes[:1000] + '...' if len(notes) > 1000 else notes)
            notes_text.configure(state='disabled')
            
            # Przyciski
            buttons_frame = customtkinter.CTkFrame(dialog)
            buttons_frame.pack(fill='x', padx=20, pady=(0, 20))
            
            download_btn = customtkinter.CTkButton(
                buttons_frame,
                text='Pobierz aktualizację',
                command=lambda: [webbrowser.open(url), dialog.destroy()],
                fg_color=PALETTE['accent']
            )
            download_btn.pack(side='left', padx=15, pady=15)
            
            later_btn = customtkinter.CTkButton(
                buttons_frame,
                text='Później',
                command=dialog.destroy,
                fg_color=PALETTE['status_gray']
            )
            later_btn.pack(side='right', padx=15, pady=15)
            
        except Exception as e:
            logging.error(f'Update dialog error: {e}')
            # Fallback do prostego messagebox
            response = messagebox.askyesno(
                'Aktualizacja',
                f'Dostępna nowa wersja: {version}\nCzy chcesz otworzyć stronę pobierania?'
            )
            if response:
                webbrowser.open(url)

def show_splash():
    """Wyświetla splash screen na środku ekranu"""
    try:
        from PIL import Image
        
        splash = customtkinter.CTkToplevel()
        splash.withdraw()
        splash.title('')
        splash.resizable(False, False)
        splash.overrideredirect(True)
        splash.attributes('-topmost', True)
        
        w, h = 280, 280
        splash.update_idletasks()
        screen_w = splash.winfo_screenwidth()
        screen_h = splash.winfo_screenheight()
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        
        splash.geometry(f'{w}x{h}+{x}+{y}')
        splash.configure(fg_color=PALETTE['panel_bg'])
        
        # Logo
        title_label = customtkinter.CTkLabel(
            splash,
            text='Flux',
            fg_color=PALETTE['accent'],
            text_color='white',
            font=('Segoe UI', 36, 'bold'),
            corner_radius=15
        )
        title_label.place(relx=0.5, rely=0.4, anchor='center')
        
        subtitle_label = customtkinter.CTkLabel(
            splash,
            text='Proxy Manager v3.8',
            font=('Segoe UI', 16),
            text_color=PALETTE['sidebar_fg']
        )
        subtitle_label.place(relx=0.5, rely=0.65, anchor='center')
        
        def close_splash():
            splash.destroy()
        
        splash.after(1800, close_splash)
        splash.bind('<Button-1>', lambda e: close_splash())
        splash.bind('<Key>', lambda e: close_splash())
        
        splash.mainloop()
        
    except Exception as e:
        logging.error(f'Splash error: {e}')

def fetch_data(url=None, retries=3, delay=1):
    """Pobiera dane JSON z URL z retry"""
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f'Fetch data error from {url}: {e}')
            if attempt < retries:
                time.sleep(delay)
    return None

def _set_tcl_tk_env():
    """Ustawia zmienne środowiskowe dla Tcl/Tk w exe"""
    if not getattr(sys, 'frozen', False):
        return
    
    base = sys._MEIPASS
    tcl_dir = os.path.join(base, 'tcl')
    tk_dir = os.path.join(base, 'tk')
    
    if os.path.isdir(tcl_dir):
        os.environ['TCL_LIBRARY'] = tcl_dir
    if os.path.isdir(tk_dir):
        os.environ['TK_LIBRARY'] = tk_dir

def show_fatal_error(msg):
    """Wyświetla okno błędu krytycznego"""
    try:
        root = customtkinter.CTk()
        root.title('Błąd krytyczny')
        root.geometry('700x400')
        root.resizable(True, True)
        root.configure(fg_color='#f6edff')
        
        tb = customtkinter.CTkTextbox(
            root,
            font=('Consolas', 11),
            fg_color=PALETTE['accent'],
            text_color='white'
        )
        tb.pack(fill='both', expand=True, padx=20, pady=20)
        tb.insert('0.0', msg)
        tb.configure(state='disabled')
        
        close_btn = customtkinter.CTkButton(
            root,
            text='Zamknij',
            command=root.destroy,
            fg_color='#ff7e6b',
            text_color='white',
            height=35
        )
        close_btn.pack(pady=(0, 20))
        
        root.mainloop()
    except Exception:
        print(f'FATAL ERROR: {msg}')

def main():
    """Funkcja główna aplikacji"""
    try:
        logging.info('Uruchamianie Flux Proxy Manager...')
        
        # Konfiguracja środowiska
        _set_tcl_tk_env()
        
        # Wyświetl splash screen
        show_splash()
        
        # Pobierz dane o providerach
        logging.info('Pobieranie danych providerów...')
        providers = fetch_data(GIST_RAW_URL) or {}
        reset_links = fetch_data(RESET_LINKS_URL) or {}
        
        logging.info(f'Załadowano {len(providers)} providerów')
        logging.info(f'Załadowano {len(reset_links)} linków resetujących')
        
        # Uruchom główną aplikację
        app = App(providers, reset_links)
        logging.info('Aplikacja uruchomiona')
        app.mainloop()
        
    except Exception as e:
        error_msg = f'Wystąpił błąd krytyczny podczas uruchamiania aplikacji:\n\n'
        error_msg += f'{str(e)}\n\n'
        error_msg += f'Szczegóły błędu:\n{traceback.format_exc()}\n\n'
        error_msg += 'Spróbuj:\n'
        error_msg += '1. Uruchomić jako administrator\n'
        error_msg += '2. Sprawdzić połączenie internetowe\n'
        error_msg += '3. Wyłączyć antywirus tymczasowo\n'
        error_msg += '4. Skontaktować się z deweloperem'
        
        logging.error(f'Fatal error: {e}')
        show_fatal_error(error_msg)

if __name__ == '__main__':
    main()