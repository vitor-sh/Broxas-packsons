"""
BroxasSMP Updater
=================
1. Detecta onde o jogador joga (qualquer launcher)
2. Instala o Forge automaticamente, se faltar
3. Sincroniza os mods com o manifest publicado
4. Mostra as noticias do servidor
5. Abre o launcher que o jogador ja usa

NAO mexe em login/conta: cada jogador continua entrando pelo launcher dele.
"""

import hashlib
import json
import os
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from detector import analyze_folder, detect_instances, normalizar_pasta
from forge_setup import install_forge, is_forge_installed, parse_forge_info

# =====================================================================
# CONFIGURACAO
# Pode editar aqui, OU criar um arquivo "updater_config.json" ao lado
# do executavel com: {"manifest_url": "...", "server_name": "...",
#                     "server_ip": "..."}
# =====================================================================

MANIFEST_URL = "https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPO/main/manifest.json"
SERVER_NAME = "BroxasSMP"
SERVER_IP = "enx-cirion-23.enx.host:10018"

# O GitHub gera o arquivo configuracao.py na hora de compilar, com os valores
# certos. Se ele existir, os valores acima sao substituidos.
try:
    from configuracao import MANIFEST_URL, SERVER_NAME, SERVER_IP  # noqa: F811
except Exception:
    pass

# =====================================================================

APP_DIR = Path(os.getenv("APPDATA") or Path.home()) / ".broxas_updater"
SETTINGS_FILE = APP_DIR / "settings.json"
STATE_FILE = APP_DIR / "state.json"

BG = "#1b1b1f"
BG2 = "#26262c"
BG3 = "#141418"
FG = "#e8e8ea"
MUTED = "#9a9aa5"
GOLD = "#d4a53a"
RED = "#a83232"
GREEN = "#3a8f4a"
ORANGE = "#c9772f"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_external_config():
    """Permite trocar a URL sem recompilar o .exe."""
    global MANIFEST_URL, SERVER_NAME, SERVER_IP
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    cfg = load_json(base / "updater_config.json", None)
    if isinstance(cfg, dict):
        MANIFEST_URL = cfg.get("manifest_url", MANIFEST_URL)
        SERVER_NAME = cfg.get("server_name", SERVER_NAME)
        SERVER_IP = cfg.get("server_ip", SERVER_IP)


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def folder_key(folder) -> str:
    return os.path.normcase(os.path.normpath(str(folder)))


def get_folder_state(state: dict, folder) -> dict:
    return state.setdefault("folders", {}).setdefault(
        folder_key(folder), {"managed": [], "pack_version": None}
    )


def fetch_manifest(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "BroxasUpdater/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "BroxasUpdater/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
        while True:
            chunk = resp.read(1024 * 128)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)


def guess_launchers() -> list:
    appdata = os.getenv("APPDATA") or ""
    local = os.getenv("LOCALAPPDATA") or ""
    pf = os.getenv("ProgramFiles") or r"C:\Program Files"
    pf86 = os.getenv("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    home = str(Path.home())
    candidates = [
        ("TLauncher", Path(appdata) / "TLauncher" / "TLauncher.exe"),
        ("TLauncher", Path(home) / "Desktop" / "TLauncher.exe"),
        ("TLauncher", Path(appdata) / ".tlauncher" / "TLauncher.exe"),
        ("CurseForge", Path(local) / "Programs" / "CurseForge" / "CurseForge.exe"),
        ("Minecraft Launcher", Path(pf86) / "Minecraft Launcher" / "MinecraftLauncher.exe"),
        ("Minecraft Launcher", Path(pf) / "Minecraft Launcher" / "MinecraftLauncher.exe"),
        ("Prism Launcher", Path(local) / "Programs" / "PrismLauncher" / "prismlauncher.exe"),
        ("Prism Launcher", Path(pf) / "Prism Launcher" / "prismlauncher.exe"),
        ("MultiMC", Path(pf) / "MultiMC" / "MultiMC.exe"),
        ("Modrinth App", Path(local) / "Programs" / "Modrinth App" / "Modrinth App.exe"),
    ]
    found, seen = [], set()
    for name, path in candidates:
        if path.exists() and str(path) not in seen:
            seen.add(str(path))
            found.append((name, str(path)))
    return found


# ---------------------------------------------------------------------
# Sincronizacao de mods
# ---------------------------------------------------------------------

def plan_sync(manifest: dict, game_dir: Path, folder_state: dict):
    mods_dir = game_dir / "mods"
    entries = manifest.get("mods", [])
    to_download, ok_count = [], 0
    for entry in entries:
        target = mods_dir / entry["name"]
        expected = (entry.get("sha1") or "").lower()
        if target.exists() and (not expected or sha1_of(target).lower() == expected):
            ok_count += 1
            continue
        to_download.append(entry)
    wanted = {e["name"] for e in entries}
    managed = set(folder_state.get("managed", []))
    to_remove = [n for n in sorted(managed) if n not in wanted and (mods_dir / n).exists()]
    return to_download, to_remove, ok_count


class SyncResult:
    def __init__(self):
        self.downloaded, self.removed, self.errors = [], [], []
        self.kept = 0


def do_sync(manifest, game_dir: Path, state, folder_state, log, set_progress):
    result = SyncResult()
    mods_dir = game_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    to_download, to_remove, ok_count = plan_sync(manifest, game_dir, folder_state)
    result.kept = ok_count
    total, step = len(to_download) + len(to_remove), 0

    for name in to_remove:
        try:
            (mods_dir / name).unlink()
            result.removed.append(name)
            log(f"  - removido: {name}")
        except Exception as exc:
            result.errors.append(f"remover {name}: {exc}")
        step += 1
        set_progress(step, total)

    for entry in to_download:
        name = entry["name"]
        try:
            log(f"  + baixando: {name}")
            download(entry["url"], mods_dir / name)
            expected = (entry.get("sha1") or "").lower()
            if expected and sha1_of(mods_dir / name).lower() != expected:
                result.errors.append(f"{name}: hash diferente do esperado")
            result.downloaded.append(name)
        except Exception as exc:
            result.errors.append(f"baixar {name}: {exc}")
            log(f"    ERRO em {name}: {exc}")
        step += 1
        set_progress(step, total)

    presentes = {e["name"] for e in manifest.get("mods", []) if (mods_dir / e["name"]).exists()}
    folder_state["managed"] = sorted(presentes)
    folder_state["pack_version"] = manifest.get("pack_version", "?")
    save_json(STATE_FILE, state)
    return result


# ---------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{SERVER_NAME} - Updater")
        self.geometry("760x640")
        self.configure(bg=BG)
        self.minsize(760, 640)

        self.settings = load_json(SETTINGS_FILE, {})
        self.state_data = load_json(STATE_FILE, {"folders": {}})
        self.manifest = None
        self.busy = False
        self.mode = "check"
        self.pending = ([], [], 0)
        self.forge_needed = False
        self.label_to_path = {}

        self._build_ui()
        self.after(300, self.check_updates)

    def _build_ui(self):
        header = tk.Frame(self, bg=BG2, height=84)
        header.pack(fill="x")
        tk.Label(header, text=SERVER_NAME, bg=BG2, fg=GOLD,
                 font=("Segoe UI", 22, "bold")).pack(pady=(12, 0))
        tk.Label(header, text=f"IP: {SERVER_IP}", bg=BG2, fg=MUTED,
                 font=("Segoe UI", 9)).pack()

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=16, pady=10)

        # ---- Coluna esquerda: configuracao e log ----
        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="Onde voce joga o BroxasSMP?", bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        row1 = tk.Frame(left, bg=BG)
        row1.pack(fill="x", pady=(2, 2))
        self.game_var = tk.StringVar()
        self.game_box = ttk.Combobox(row1, textvariable=self.game_var, state="readonly")
        self.game_box.pack(side="left", fill="x", expand=True, ipady=2)
        self.game_box.bind("<<ComboboxSelected>>", lambda e: self.on_folder_change())
        tk.Button(row1, text="Outra", command=self.pick_game_dir, bg=BG2, fg=FG,
                  relief="flat", padx=8).pack(side="left", padx=(5, 0))

        self.path_var = tk.StringVar()
        tk.Label(left, textvariable=self.path_var, bg=BG, fg=MUTED,
                 font=("Consolas", 8), anchor="w", wraplength=420,
                 justify="left").pack(fill="x")

        self.warn_var = tk.StringVar()
        self.warn_lbl = tk.Label(left, textvariable=self.warn_var, bg=BG, fg=ORANGE,
                                 font=("Segoe UI", 8), anchor="w", justify="left",
                                 wraplength=420)
        self.warn_lbl.pack(fill="x", pady=(2, 6))

        tk.Label(left, text="Seu launcher", bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        row2 = tk.Frame(left, bg=BG)
        row2.pack(fill="x", pady=(2, 6))
        self.launcher_var = tk.StringVar(value=self.settings.get("launcher") or "")
        self.launcher_box = ttk.Combobox(row2, textvariable=self.launcher_var)
        found = guess_launchers()
        self.launcher_box["values"] = [p for _, p in found]
        if not self.launcher_var.get() and found:
            self.launcher_var.set(found[0][1])
        self.launcher_box.pack(side="left", fill="x", expand=True, ipady=2)
        tk.Button(row2, text="Procurar", command=self.pick_launcher, bg=BG2, fg=FG,
                  relief="flat", padx=8).pack(side="left", padx=(5, 0))

        self.status_var = tk.StringVar(value="Verificando...")
        tk.Label(left, textvariable=self.status_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9), anchor="w", wraplength=420,
                 justify="left").pack(fill="x", pady=(4, 2))

        self.bar = ttk.Progressbar(left, mode="determinate", maximum=100)
        self.bar.pack(fill="x", pady=(0, 6))

        self.log_box = tk.Text(left, height=10, bg=BG3, fg=MUTED, relief="flat",
                               font=("Consolas", 8), wrap="word")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")

        # ---- Coluna direita: noticias ----
        right = tk.Frame(main, bg=BG, width=250)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        tk.Label(right, text="NOTICIAS DO SERVIDOR", bg=BG, fg=GOLD,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self.news_box = tk.Text(right, bg=BG3, fg=FG, relief="flat",
                                font=("Segoe UI", 8), wrap="word", padx=8, pady=8)
        self.news_box.pack(fill="both", expand=True)
        self.news_box.tag_configure("titulo", foreground=GOLD,
                                   font=("Segoe UI", 9, "bold"), spacing1=6, spacing3=2)
        self.news_box.tag_configure("texto", foreground="#c9c9d1", spacing3=6)
        self.news_box.insert("end", "Carregando...\n", "texto")
        self.news_box.configure(state="disabled")

        self.action_btn = tk.Button(self, text="VERIFICANDO...", command=self.on_action,
                                    bg=GOLD, fg="#1b1b1f", relief="flat",
                                    font=("Segoe UI", 13, "bold"), pady=10)
        self.action_btn.pack(fill="x", side="bottom", padx=16, pady=(0, 14))

    # ---------------- helpers ----------------
    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def set_progress(self, done, total):
        self.bar["value"] = 100 if not total else int(done / total * 100)
        self.update_idletasks()

    def render_news(self, noticias):
        self.news_box.configure(state="normal")
        self.news_box.delete("1.0", "end")
        if not noticias:
            self.news_box.insert("end", "Nenhuma noticia por agora.\n", "texto")
        else:
            for n in noticias:
                if isinstance(n, str):
                    self.news_box.insert("end", n + "\n", "texto")
                    continue
                titulo = n.get("titulo") or n.get("title") or ""
                texto = n.get("texto") or n.get("text") or ""
                if titulo:
                    self.news_box.insert("end", titulo + "\n", "titulo")
                if texto:
                    self.news_box.insert("end", texto + "\n", "texto")
        self.news_box.configure(state="disabled")

    def current_folder(self):
        """Devolve a pasta escolhida, corrigindo os erros comuns de escolha."""
        bruta = self.label_to_path.get(self.game_var.get(), "")
        if not bruta:
            return ""
        corrigida, aviso = normalizar_pasta(bruta)
        if aviso and aviso != getattr(self, "_ultimo_aviso_pasta", None):
            self._ultimo_aviso_pasta = aviso
            self.log(f"  {aviso}")
        return corrigida

    def update_path_label(self):
        self.path_var.set(self.current_folder() or "(nada selecionado)")

    def populate_instances(self):
        instances = detect_instances()
        self.label_to_path = {}
        labels = []
        for inst in instances:
            label = f"{inst['label']}  [{inst['mods']} mods]"
            self.label_to_path[label] = inst["path"]
            labels.append(label)

        salvo = self.settings.get("game_dir")
        if salvo and salvo not in self.label_to_path.values():
            label = f"Escolhida por voce  [{salvo}]"
            self.label_to_path[label] = salvo
            labels.insert(0, label)

        self.game_box["values"] = labels
        self.log(f"Instalacoes detectadas: {len(instances)}")
        for inst in instances:
            self.log(f"  . {inst['label']} ({inst['mods']} mods)")

        escolha = None
        if salvo:
            for lb, pth in self.label_to_path.items():
                if folder_key(pth) == folder_key(salvo):
                    escolha = lb
                    break
        if escolha is None and labels:
            escolha = labels[0]
        if escolha:
            self.game_var.set(escolha)
        self.update_path_label()

    def pick_game_dir(self):
        path = filedialog.askdirectory(title="Selecione a pasta do Minecraft (a que tem 'mods')")
        if not path:
            return
        label = f"Escolhida por voce  [{path}]"
        self.label_to_path[label] = path
        vals = list(self.game_box["values"])
        if label not in vals:
            vals.insert(0, label)
            self.game_box["values"] = vals
        self.game_var.set(label)
        self.on_folder_change()

    def pick_launcher(self):
        path = filedialog.askopenfilename(
            title="Selecione o executavel do launcher",
            filetypes=[("Executavel", "*.exe"), ("Todos", "*.*")])
        if path:
            self.launcher_var.set(path)

    def on_folder_change(self):
        self.update_path_label()
        self.save_settings()
        if self.manifest:
            self.evaluate()

    def save_settings(self):
        folder = self.current_folder()
        if folder:
            self.settings["game_dir"] = folder
        self.settings["launcher"] = self.launcher_var.get()
        save_json(SETTINGS_FILE, self.settings)

    def set_mode(self, mode):
        self.mode = mode
        if mode == "update":
            texto = "INSTALAR / ATUALIZAR" if self.forge_needed else "ATUALIZAR"
            self.action_btn.configure(text=texto, bg=GOLD, fg="#1b1b1f", state="normal")
        elif mode == "play":
            self.action_btn.configure(text="JOGAR", bg=GREEN, fg="white", state="normal")
        else:
            self.action_btn.configure(text="TENTAR DE NOVO", bg=RED, fg="white", state="normal")

    # ---------------- fluxo ----------------
    def check_updates(self):
        def work():
            try:
                self.manifest = fetch_manifest(MANIFEST_URL)
            except Exception as exc:
                self.status_var.set("Nao consegui verificar atualizacoes (sem internet?).")
                self.log(f"ERRO: {exc}")
                self.render_news([])
                self.set_mode("error")
                return
            m = self.manifest
            self.log(f"Pack remoto: v{m.get('pack_version','?')} | "
                     f"Minecraft {m.get('minecraft','?')} | {m.get('loader','?')} | "
                     f"{len(m.get('mods', []))} mods")
            self.render_news(m.get("noticias") or m.get("news") or [])
            self.populate_instances()
            self.evaluate()

        threading.Thread(target=work, daemon=True).start()

    def evaluate(self):
        folder = self.current_folder()
        if not folder:
            self.status_var.set("Selecione onde voce joga o BroxasSMP.")
            self.set_mode("error")
            return

        fstate = get_folder_state(self.state_data, folder)
        nivel, msgs = analyze_folder(folder, self.manifest, fstate)
        if nivel == "perigo":
            self.warn_lbl.configure(fg=RED)
            self.warn_var.set("ATENCAO: " + " ".join(msgs))
            self.status_var.set("Escolha outra pasta para continuar.")
            self.set_mode("error")
            return
        self.warn_lbl.configure(fg=ORANGE if nivel == "aviso" else MUTED)
        self.warn_var.set(("AVISO: " if nivel == "aviso" else "") + " ".join(msgs))

        # Forge
        mc, fv, _ = parse_forge_info(self.manifest)
        self.forge_needed = False
        if mc and fv:
            if is_forge_installed(folder, mc, fv):
                self.log(f"Forge {fv} ja instalado.")
            else:
                self.forge_needed = True
                self.log(f"Forge {mc}-{fv} NAO encontrado -> sera instalado.")

        try:
            to_dl, to_rm, ok = plan_sync(self.manifest, Path(folder), fstate)
        except Exception as exc:
            self.status_var.set("Erro ao comparar arquivos.")
            self.log(f"ERRO: {exc}")
            self.set_mode("error")
            return

        self.pending = (to_dl, to_rm, ok)
        partes = []
        if self.forge_needed:
            partes.append("instalar o Forge")
        if to_dl:
            partes.append(f"baixar {len(to_dl)} mod(s)")
        if to_rm:
            partes.append(f"remover {len(to_rm)}")
        if partes:
            self.status_var.set("Falta: " + ", ".join(partes) + f". ({ok} ja em dia)")
            self.set_mode("update")
        else:
            self.status_var.set(
                f"Tudo em dia! Pack v{self.manifest.get('pack_version','?')}. Pode jogar.")
            self.set_mode("play")

    def on_action(self):
        if self.busy:
            return
        self.save_settings()

        if self.mode == "play":
            self.launch()
            return
        if self.mode == "error":
            self.log("--- verificando de novo ---")
            self.status_var.set("Verificando...")
            self.check_updates()
            return

        folder = self.current_folder()
        to_dl, to_rm, ok = self.pending
        resumo = f"Pasta:\n{folder}\n\n"
        if self.forge_needed:
            mc, fv, _ = parse_forge_info(self.manifest)
            resumo += f"Instalar Forge {mc}-{fv}\n"
        resumo += (f"Baixar: {len(to_dl)} mod(s)\n"
                   f"Remover: {len(to_rm)} mod(s)\n"
                   f"Manter: {ok}\n\nConfirmar?")
        if not messagebox.askokcancel("Confirmar", resumo):
            return

        self.busy = True
        self.action_btn.configure(state="disabled", text="TRABALHANDO...")

        def work():
            try:
                if self.forge_needed:
                    mc, fv, url = parse_forge_info(self.manifest)
                    self.status_var.set("Instalando o Forge...")
                    self.log("--- instalando Forge ---")
                    ok_forge, msg = install_forge(folder, mc, fv, url, log=self.log)
                    self.log(f"  {msg}")
                    if not ok_forge:
                        self.status_var.set("Falha ao instalar o Forge.")
                        messagebox.showerror("Forge", msg)
                        self.busy = False
                        self.set_mode("update")
                        return
                    self.forge_needed = False

                self.status_var.set("Sincronizando mods...")
                fstate = get_folder_state(self.state_data, folder)
                self.log(f"--- sincronizando em {folder} ---")
                res = do_sync(self.manifest, Path(folder), self.state_data, fstate,
                              self.log, self.set_progress)
                self.log(f"--- fim: {len(res.downloaded)} baixados, "
                         f"{len(res.removed)} removidos, {res.kept} ok ---")
                if res.errors:
                    self.status_var.set(f"Concluido com {len(res.errors)} erro(s). Veja o log.")
                    for e in res.errors:
                        self.log(f"  ! {e}")
                    self.set_mode("update")
                else:
                    self.status_var.set("Tudo pronto! Pode jogar.")
                    self.set_progress(1, 1)
                    self.set_mode("play")
            finally:
                self.busy = False

        threading.Thread(target=work, daemon=True).start()

    def launch(self):
        path = self.launcher_var.get().strip()
        mc = (self.manifest or {}).get("minecraft", "1.20.1")
        loader = (self.manifest or {}).get("loader", "Forge")
        if not path or not Path(path).exists():
            messagebox.showwarning(
                "Launcher nao encontrado",
                "Selecione o executavel do launcher que voce usa.\n\n"
                "Seus mods JA estao atualizados: pode abrir o launcher "
                "manualmente e jogar normalmente.")
            return
        try:
            subprocess.Popen([path], close_fds=True)
            self.log(f"Abrindo launcher: {path}")
            messagebox.showinfo(
                "Bom jogo!",
                f"Launcher aberto.\n\nSelecione o perfil {loader} ({mc}) "
                f"e entre no servidor:\n{SERVER_IP}")
        except Exception as exc:
            messagebox.showerror("Erro", f"Nao consegui abrir o launcher:\n{exc}")


if __name__ == "__main__":
    load_external_config()
    App().mainloop()
