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
from launchers import detectar_launchers
import preparar_jogo
import rede
import interface as UI

# =====================================================================
# CONFIGURACAO
# Pode editar aqui, OU criar um arquivo "updater_config.json" ao lado
# do executavel com: {"manifest_url": "...", "server_name": "...",
#                     "server_ip": "..."}
# =====================================================================

PACKS_URL = "https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPO/main/packs.json"
MANIFEST_URL = ""          # usado apenas quando nao ha packs.json
SERVER_NAME = "BroxasSMP"
SERVER_IP = "enx-cirion-23.enx.host:10018"

# O GitHub gera o arquivo configuracao.py na hora de compilar, com os valores
# certos. Se ele existir, os valores acima sao substituidos.
try:
    from configuracao import PACKS_URL, SERVER_NAME, SERVER_IP  # noqa: F811
except Exception:
    pass
try:
    from configuracao import MANIFEST_URL  # noqa: F811
except Exception:
    pass

# =====================================================================

APP_DIR = Path(os.getenv("APPDATA") or Path.home()) / ".broxas_updater"
SETTINGS_FILE = APP_DIR / "settings.json"
STATE_FILE = APP_DIR / "state.json"

# As cores e os componentes visuais ficam no modulo interface.py


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
    global MANIFEST_URL, PACKS_URL, SERVER_NAME, SERVER_IP
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    cfg = load_json(base / "updater_config.json", None)
    if isinstance(cfg, dict):
        PACKS_URL = cfg.get("packs_url", PACKS_URL)
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


def get_folder_state(state: dict, folder, pack_id="unico") -> dict:
    """
    O historico e guardado por pack E por pasta, para o app saber a versao
    instalada de cada modpack separadamente.
    """
    chave = f"{pack_id}@{folder_key(folder)}"
    return state.setdefault("folders", {}).setdefault(
        chave, {"managed": [], "pack_version": None}
    )


def mods_de_qualquer_pack(state: dict, folder) -> set:
    """
    Todos os mods que o app ja instalou nesta pasta, de QUALQUER modpack.

    Serve para trocar de modpack usando a mesma pasta: os mods que sobraram do
    outro pack precisam sair, senao o jogo quebra por conflito. Mods que a
    pessoa colocou na mao nunca entram nessa lista, entao nunca sao apagados.
    """
    fim = "@" + folder_key(folder)
    nomes = set()
    for chave, dados in (state.get("folders") or {}).items():
        if chave.endswith(fim):
            nomes.update(dados.get("managed") or [])
    return nomes


def fetch_manifest(url: str) -> dict:
    return json.loads(rede.ler_texto(url, tempo=30))


def fetch_packs() -> list:
    """
    Le o indice de modpacks. Devolve uma lista de dicionarios.
    Se o servidor ainda usar um manifest unico, devolve um pack so.
    """
    if PACKS_URL and "SEU_USUARIO" not in PACKS_URL:
        dados = json.loads(rede.ler_texto(PACKS_URL, tempo=30))
        packs = dados.get("packs") or []
        if packs:
            return packs
    if MANIFEST_URL:
        return [{"id": "unico", "nome": SERVER_NAME, "descricao": "",
                 "ip": SERVER_IP, "manifest": MANIFEST_URL}]
    raise RuntimeError("nenhum modpack configurado")


def download(url: str, dest: Path, sha1=None, log=None):
    ok, motivo = rede.baixar(url, dest, sha1_esperado=sha1, log=log)
    if not ok:
        raise RuntimeError(motivo)
    return motivo


# ---------------------------------------------------------------------
# Sincronizacao de mods
# ---------------------------------------------------------------------

def plan_sync(manifest: dict, game_dir: Path, folder_state: dict, ja_instalados=None):
    """
    Compara o que esta na pasta com o que o modpack pede.

    'ja_instalados' e a lista de mods que o app colocou nessa pasta por
    QUALQUER modpack. Passando isso, trocar de modpack na mesma pasta limpa o
    que sobrou do pack anterior.
    """
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
    if ja_instalados:
        managed |= set(ja_instalados)
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
    de_outros_packs = mods_de_qualquer_pack(state, game_dir)
    to_download, to_remove, ok_count = plan_sync(manifest, game_dir, folder_state,
                                                de_outros_packs)
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
            observacao = download(entry["url"], mods_dir / name,
                                  sha1=entry.get("sha1"), log=log)
            if observacao:
                log(f"    {observacao}")
            result.downloaded.append(name)
        except Exception as exc:
            result.errors.append(f"baixar {name}: {exc}")
            log(f"    ERRO em {name}: {exc}")
        step += 1
        set_progress(step, total)

    presentes = {e["name"] for e in manifest.get("mods", []) if (mods_dir / e["name"]).exists()}
    folder_state["managed"] = sorted(presentes)
    folder_state["pack_version"] = manifest.get("pack_version", "?")

    # Tira do historico dos OUTROS packs os arquivos que acabaram de sair da
    # pasta, para o historico nao ficar cheio de nomes que nao existem mais.
    apagados = set(result.removed)
    if apagados:
        fim = "@" + folder_key(game_dir)
        for chave, dados in (state.get("folders") or {}).items():
            if chave.endswith(fim) and dados is not folder_state:
                restantes = [n for n in (dados.get("managed") or []) if n not in apagados]
                dados["managed"] = restantes

    save_json(STATE_FILE, state)
    return result


# ---------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{SERVER_NAME} - Updater")
        self.geometry("900x760")
        self.minsize(900, 700)
        self.configure(bg=UI.FUNDO)

        self.settings = load_json(SETTINGS_FILE, {})
        self.state_data = load_json(STATE_FILE, {"folders": {}})
        self.manifest = None
        self.busy = False
        self.mode = "check"
        self.pending = ([], [], 0)
        self.forge_needed = False
        self.label_to_path = {}
        self.rotulo_para_launcher = {}
        self.packs = []
        self.pack_atual = None
        self.rotulo_para_pack = {}
        self._pontinhos = 0
        self._log_aberto = False

        UI.aplicar_estilo_combobox(self)
        self._build_ui()
        UI.aparecer(self)
        self._animar_pontinhos()
        self.after(350, self.check_updates)

    # =================================================================
    # Montagem da tela
    # =================================================================
    def _build_ui(self):
        self.cabecalho = UI.Cabecalho(self, SERVER_NAME, f"IP   {SERVER_IP}")
        self.cabecalho.pack(fill="x")

        # O rodape entra ANTES do conteudo: com o pack, quem tem expand=True
        # ocupa todo o espaco restante e empurraria o botao para fora da tela.
        rodape = tk.Frame(self, bg=UI.FUNDO)
        rodape.pack(fill="x", side="bottom", padx=20, pady=(6, 18))
        self.botao = UI.Botao(rodape, texto="VERIFICANDO...", comando=self.on_action,
                              cor=UI.OURO, altura=54, bg=UI.FUNDO)
        self.botao.pack(fill="x")
        self.botao.configurar(ativo=False)

        corpo = tk.Frame(self, bg=UI.FUNDO)
        corpo.pack(fill="both", expand=True, padx=20, pady=(16, 0))

        esquerda = tk.Frame(corpo, bg=UI.FUNDO)
        esquerda.pack(side="left", fill="both", expand=True)

        direita = tk.Frame(corpo, bg=UI.FUNDO, width=262)
        direita.pack(side="right", fill="y", padx=(16, 0))
        direita.pack_propagate(False)

        self._montar_seletor_pack(esquerda)
        self._montar_configuracao(esquerda)
        self._montar_estado(esquerda)
        self._montar_log(esquerda)
        self._montar_noticias(direita)

    def _montar_seletor_pack(self, pai):
        cartao = UI.Cartao(pai, titulo="MODPACK")
        cartao.pack(fill="x")
        interno = tk.Frame(cartao, bg=UI.FUNDO_CARTAO)
        interno.pack(fill="x", padx=14, pady=(10, 13))

        self.pack_var = tk.StringVar(value="Carregando modpacks")
        self.pack_box = ttk.Combobox(interno, textvariable=self.pack_var,
                                     state="readonly", style="Broxas.TCombobox")
        self.pack_box.pack(fill="x")
        self.pack_box.bind("<<ComboboxSelected>>", lambda e: self.on_pack_change())

        self.pack_info = tk.StringVar(value="")
        tk.Label(interno, textvariable=self.pack_info, bg=UI.FUNDO_CARTAO,
                 fg=UI.TEXTO_FRACO, font=(UI.FONTE, 8), anchor="w",
                 justify="left", wraplength=470).pack(fill="x", pady=(6, 0))

    def _montar_configuracao(self, pai):
        cartao = UI.Cartao(pai, titulo="ONDE VOCE JOGA")
        cartao.pack(fill="x", pady=(12, 0))

        interno = tk.Frame(cartao, bg=UI.FUNDO_CARTAO)
        interno.pack(fill="x", padx=14, pady=(10, 13))

        linha1 = tk.Frame(interno, bg=UI.FUNDO_CARTAO)
        linha1.pack(fill="x")
        self.game_var = tk.StringVar()
        self.game_box = ttk.Combobox(linha1, textvariable=self.game_var,
                                     state="readonly", style="Broxas.TCombobox")
        self.game_box.pack(side="left", fill="x", expand=True)
        self.game_box.bind("<<ComboboxSelected>>", lambda e: self.on_folder_change())
        UI.Botao(linha1, texto="Outra pasta", comando=self.pick_game_dir,
                 cor=UI.BORDA_CLARA, cor_texto=UI.TEXTO, altura=30, raio=8,
                 fonte=(UI.FONTE, 9), width=104,
                 bg=UI.FUNDO_CARTAO).pack(side="left", padx=(8, 0))

        self.path_var = tk.StringVar()
        tk.Label(interno, textvariable=self.path_var, bg=UI.FUNDO_CARTAO,
                 fg=UI.TEXTO_FRACO, font=("Consolas", 8), anchor="w",
                 wraplength=470, justify="left").pack(fill="x", pady=(7, 0))

        self.warn_var = tk.StringVar()
        self.warn_lbl = tk.Label(interno, textvariable=self.warn_var,
                                 bg=UI.FUNDO_CARTAO, fg=UI.LARANJA,
                                 font=(UI.FONTE, 8), anchor="w", justify="left",
                                 wraplength=470)
        self.warn_lbl.pack(fill="x", pady=(4, 0))

        cartao2 = UI.Cartao(pai, titulo="SEU LAUNCHER")
        cartao2.pack(fill="x", pady=(12, 0))
        interno2 = tk.Frame(cartao2, bg=UI.FUNDO_CARTAO)
        interno2.pack(fill="x", padx=14, pady=(10, 13))
        linha2 = tk.Frame(interno2, bg=UI.FUNDO_CARTAO)
        linha2.pack(fill="x")
        self.launcher_var = tk.StringVar(value="Procurando launchers")
        self.launcher_box = ttk.Combobox(linha2, textvariable=self.launcher_var,
                                         state="readonly", style="Broxas.TCombobox")
        self.launcher_box.pack(side="left", fill="x", expand=True)
        UI.Botao(linha2, texto="Procurar", comando=self.pick_launcher,
                 cor=UI.BORDA_CLARA, cor_texto=UI.TEXTO, altura=30, raio=8,
                 fonte=(UI.FONTE, 9), width=104,
                 bg=UI.FUNDO_CARTAO).pack(side="left", padx=(8, 0))

    def _montar_estado(self, pai):
        cartao = UI.Cartao(pai)
        cartao.pack(fill="x", pady=(12, 0))
        interno = tk.Frame(cartao, bg=UI.FUNDO_CARTAO)
        interno.pack(fill="x", padx=14, pady=13)

        topo = tk.Frame(interno, bg=UI.FUNDO_CARTAO)
        topo.pack(fill="x")
        self.girador = UI.Girador(topo, tamanho=16, bg=UI.FUNDO_CARTAO)
        self.girador.pack(side="left", padx=(0, 8))
        self.status_var = tk.StringVar(value="Verificando atualizacoes")
        tk.Label(topo, textvariable=self.status_var, bg=UI.FUNDO_CARTAO,
                 fg=UI.TEXTO_SUAVE, font=(UI.FONTE, 10), anchor="w",
                 justify="left", wraplength=420).pack(side="left", fill="x",
                                                      expand=True)

        self.barra = UI.Barra(interno, altura=12, bg=UI.FUNDO_CARTAO)
        self.barra.pack(fill="x", pady=(11, 0))

        selos = tk.Frame(interno, bg=UI.FUNDO_CARTAO)
        selos.pack(fill="x", pady=(11, 0))
        self.selo_pack = UI.Selo(selos, texto="", cor=UI.OURO, width=118,
                                 bg=UI.FUNDO_CARTAO)
        self.selo_pack.pack(side="left")
        self.selo_mods = UI.Selo(selos, texto="", cor=UI.BORDA_CLARA, width=100,
                                 bg=UI.FUNDO_CARTAO)
        self.selo_mods.pack(side="left", padx=(7, 0))
        self.selo_forge = UI.Selo(selos, texto="", cor=UI.BORDA_CLARA, width=136,
                                  bg=UI.FUNDO_CARTAO)
        self.selo_forge.pack(side="left", padx=(7, 0))

    def _montar_log(self, pai):
        self.cartao_log = UI.Cartao(pai)
        self.cartao_log.pack(fill="both", expand=True, pady=(12, 0))

        cabeca = tk.Frame(self.cartao_log, bg=UI.FUNDO_CARTAO)
        cabeca.pack(fill="x", padx=14, pady=(11, 0))
        self.botao_log = tk.Label(cabeca, text="DETALHES  \u25bc", bg=UI.FUNDO_CARTAO,
                                  fg=UI.TEXTO_FRACO, font=(UI.FONTE, 9, "bold"),
                                  cursor="hand2")
        self.botao_log.pack(side="left")
        self.botao_log.bind("<Button-1>", lambda e: self._alternar_log())
        self.botao_log.bind("<Enter>", lambda e: self.botao_log.configure(fg=UI.OURO))
        self.botao_log.bind("<Leave>",
                            lambda e: self.botao_log.configure(fg=UI.TEXTO_FRACO))

        self.moldura_log = tk.Frame(self.cartao_log, bg=UI.FUNDO_CARTAO)
        self.log_box = tk.Text(self.moldura_log, height=8, bg=UI.FUNDO_POCO,
                               fg=UI.TEXTO_FRACO, relief="flat",
                               font=("Consolas", 8), wrap="word", padx=10, pady=8,
                               insertwidth=0, highlightthickness=1,
                               highlightbackground=UI.BORDA)
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_configure("ok", foreground=UI.VERDE_CLARO)
        self.log_box.tag_configure("erro", foreground=UI.VERMELHO_CLARO)
        self.log_box.tag_configure("aviso", foreground=UI.LARANJA)
        self.log_box.configure(state="disabled")
        self._alternar_log(abrir=True)

    def _alternar_log(self, abrir=None):
        self._log_aberto = (not self._log_aberto) if abrir is None else abrir
        if self._log_aberto:
            self.moldura_log.pack(fill="both", expand=True, padx=14, pady=(9, 13))
            self.botao_log.configure(text="DETALHES  \u25b2")
        else:
            self.moldura_log.pack_forget()
            self.botao_log.configure(text="DETALHES  \u25bc")

    def _montar_noticias(self, pai):
        cartao = UI.Cartao(pai, titulo="NOTICIAS DO SERVIDOR")
        cartao.pack(fill="both", expand=True)
        self.news_box = tk.Text(cartao, bg=UI.FUNDO_CARTAO, fg=UI.TEXTO_SUAVE,
                                relief="flat", font=(UI.FONTE, 9), wrap="word",
                                padx=12, pady=10, insertwidth=0,
                                highlightthickness=0, cursor="arrow")
        self.news_box.pack(fill="both", expand=True, padx=2, pady=(8, 8))
        self.news_box.tag_configure("titulo", foreground=UI.OURO,
                                    font=(UI.FONTE, 10, "bold"), spacing1=9,
                                    spacing3=3)
        self.news_box.tag_configure("texto", foreground=UI.TEXTO_SUAVE, spacing3=9,
                                    lmargin1=2, lmargin2=2)
        self.news_box.tag_configure("fraco", foreground=UI.TEXTO_FRACO)
        self.news_box.insert("end", "Carregando...", "fraco")
        self.news_box.configure(state="disabled")

    # =================================================================
    # Animacoes e utilidades de tela
    # =================================================================
    def _animar_pontinhos(self):
        """Faz os pontinhos do texto de espera irem e voltarem."""
        if self.mode == "check" or self.busy:
            self._pontinhos = (self._pontinhos + 1) % 4
            base = self.status_var.get().rstrip(". ")
            if base:
                self.status_var.set(base + "." * self._pontinhos)
        self.after(420, self._animar_pontinhos)

    def _ocupado(self, ligado):
        if ligado:
            self.girador.iniciar()
            self.barra.carregando(True)
        else:
            self.girador.parar()
            self.barra.carregando(False)

    def _no_principal(self, funcao, *args):
        """
        Garante que quem mexe na tela e a thread da interface.
        O tkinter nao aceita widget alterado de outra thread: isso trava ou
        derruba a janela de forma imprevisivel.
        """
        if threading.current_thread() is threading.main_thread():
            funcao(*args)
        else:
            try:
                self.after(0, lambda: funcao(*args))
            except Exception:
                pass

    def set_status(self, texto):
        self._no_principal(self.status_var.set, texto)

    def log(self, text, tag=None):
        self._no_principal(self._escrever_log, text, tag)

    def _escrever_log(self, text, tag=None):
        if tag is None:
            baixo = text.lower()
            if "erro" in baixo or "falh" in baixo:
                tag = "erro"
            elif "aviso" in baixo or "atencao" in baixo:
                tag = "aviso"
            elif "instalado" in baixo or "sucesso" in baixo:
                tag = "ok"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n", tag or "")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def set_progress(self, done, total):
        self._no_principal(self.barra.definir, 1.0 if not total else done / total)

    def atualizar_selos(self):
        m = self.manifest or {}
        if not m:
            return
        self.selo_pack.definir(f"Pack v{m.get('pack_version','?')}", UI.OURO)
        self.selo_mods.definir(f"{len(m.get('mods', []))} mods", UI.BORDA_CLARA)
        forge = (m.get("forge") or {}).get("version", "?")
        if self.forge_needed:
            self.selo_forge.definir(f"Forge {forge} falta", UI.LARANJA)
        else:
            self.selo_forge.definir(f"Forge {forge} pronto", UI.VERDE)

    def render_news(self, noticias):
        self._no_principal(self._escrever_noticias, noticias)

    def _escrever_noticias(self, noticias):
        self.news_box.configure(state="normal")
        self.news_box.delete("1.0", "end")
        if not noticias:
            self.news_box.insert("end", "Nenhuma noticia por agora.", "fraco")
        else:
            for i, n in enumerate(noticias):
                if isinstance(n, str):
                    self.news_box.insert("end", n + "\n", "texto")
                    continue
                titulo = n.get("titulo") or n.get("title") or ""
                texto = n.get("texto") or n.get("text") or ""
                if titulo:
                    prefixo = "" if i == 0 else "\n"
                    self.news_box.insert("end", prefixo + titulo + "\n", "titulo")
                if texto:
                    self.news_box.insert("end", texto + "\n", "texto")
        self.news_box.configure(state="disabled")

    # =================================================================
    # Pastas
    # =================================================================
    def current_folder(self):
        bruta = self.label_to_path.get(self.game_var.get(), "")
        if not bruta:
            return ""
        corrigida, aviso = normalizar_pasta(bruta)
        if aviso and aviso != getattr(self, "_ultimo_aviso_pasta", None):
            self._ultimo_aviso_pasta = aviso
            self.log(f"  {aviso}", "aviso")
        return corrigida

    def update_path_label(self):
        self.path_var.set(self.current_folder() or "(nada selecionado)")

    def populate_instances(self, instances=None):
        if instances is None:
            instances = detect_instances()
        self.label_to_path = {}
        labels = []
        for inst in instances:
            label = f"{inst['label']}   [{inst['mods']} mods]"
            self.label_to_path[label] = inst["path"]
            labels.append(label)

        salvo = self.settings.get("game_dir")
        if salvo and salvo not in self.label_to_path.values():
            label = f"Escolhida por voce   [{salvo}]"
            self.label_to_path[label] = salvo
            labels.insert(0, label)

        self.game_box["values"] = labels
        self.log(f"Instalacoes encontradas: {len(instances)}")
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
        path = filedialog.askdirectory(
            title="Selecione a pasta do jogo (a que CONTEM a pasta mods)")
        if not path:
            return
        label = f"Escolhida por voce   [{path}]"
        self.label_to_path[label] = path
        valores = list(self.game_box["values"])
        if label not in valores:
            valores.insert(0, label)
            self.game_box["values"] = valores
        self.game_var.set(label)
        self.on_folder_change()

    # =================================================================
    # Launchers
    # =================================================================
    def _aplicar_launchers(self, encontrados):
        self.rotulo_para_launcher = {}
        rotulos = []
        for item in encontrados:
            rotulo = f"{item['nome']}   -   {item['caminho']}"
            self.rotulo_para_launcher[rotulo] = item["caminho"]
            rotulos.append(rotulo)

        salvo = self.settings.get("launcher")
        if (salvo and Path(salvo).is_file()
                and salvo not in self.rotulo_para_launcher.values()):
            rotulo = f"Escolhido por voce   -   {salvo}"
            self.rotulo_para_launcher[rotulo] = salvo
            rotulos.insert(0, rotulo)

        self.launcher_box["values"] = rotulos
        if not rotulos:
            self.launcher_var.set("Nenhum encontrado - use o botao Procurar")
            self.log("  Nenhum launcher encontrado. Use o botao Procurar.", "aviso")
            return

        escolhido = None
        if salvo:
            for r, c in self.rotulo_para_launcher.items():
                if os.path.normcase(c) == os.path.normcase(salvo):
                    escolhido = r
                    break
        self.launcher_var.set(escolhido or rotulos[0])
        self.log(f"  {len(rotulos)} launcher(s) na lista")

    def current_launcher(self):
        return self.rotulo_para_launcher.get(self.launcher_var.get(), "")

    def pick_launcher(self):
        path = filedialog.askopenfilename(
            title="Selecione o executavel do launcher que voce usa",
            filetypes=[("Executavel", "*.exe"), ("Todos", "*.*")])
        if not path:
            return
        rotulo = f"Escolhido por voce   -   {path}"
        self.rotulo_para_launcher[rotulo] = path
        valores = list(self.launcher_box["values"])
        if rotulo not in valores:
            valores.insert(0, rotulo)
            self.launcher_box["values"] = valores
        self.launcher_var.set(rotulo)
        self.save_settings()

    def on_folder_change(self):
        self.update_path_label()
        self.save_settings()
        if self.manifest:
            self.evaluate()

    def save_settings(self):
        folder = self.current_folder()
        if folder:
            self.settings["game_dir"] = folder
        alvo = self.current_launcher()
        if alvo:
            self.settings["launcher"] = alvo
        save_json(SETTINGS_FILE, self.settings)

    # =================================================================
    # Estado do botao
    # =================================================================
    def set_mode(self, mode):
        self._no_principal(self._aplicar_modo, mode)

    def _aplicar_modo(self, mode):
        self.mode = mode
        self._ocupado(False)
        if mode == "update":
            texto = "INSTALAR E ATUALIZAR" if self.forge_needed else "ATUALIZAR"
            self.botao.configurar(texto=texto, cor=UI.OURO, cor_texto="#15151d",
                                  ativo=True)
            self.botao.pulsar(True)
        elif mode == "play":
            self.botao.pulsar(False)
            self.botao.configurar(texto="JOGAR", cor=UI.VERDE, cor_texto="#ffffff",
                                  ativo=True)
            self.barra.definir(1.0)
        else:
            self.botao.pulsar(False)
            self.botao.configurar(texto="TENTAR DE NOVO", cor=UI.VERMELHO,
                                  cor_texto="#ffffff", ativo=True)
        self.atualizar_selos()

    # =================================================================
    # Fluxo
    # =================================================================
    def check_updates(self):
        """
        Busca e varredura acontecem em segundo plano; o resultado e entregue
        para a thread da interface montar a tela.
        """
        self.mode = "check"
        self._ocupado(True)
        self.botao.configurar(texto="VERIFICANDO...", ativo=False)

        def trabalho():
            try:
                if not self.packs:
                    self.packs = fetch_packs()
                    self.log(f"{len(self.packs)} modpack(s) disponivel(is)")
                    # A escolha e feita AQUI, nao no _aplicar_packs. O
                    # _aplicar_packs so mexe na tela e roda depois, na thread
                    # da interface; se a escolha dependesse dele, o app baixaria
                    # sempre o primeiro pack da lista em vez do que a pessoa
                    # escolheu na ultima vez.
                    if self.pack_atual is None:
                        self.pack_atual = self._escolher_pack(self.packs)
                    self._no_principal(self._aplicar_packs, self.packs)
                escolhido = self.pack_atual or self.packs[0]
                self.pack_atual = escolhido
                self.log(f"Modpack: {escolhido.get('nome', escolhido.get('id'))}")
                manifest = fetch_manifest(escolhido["manifest"])
            except Exception as exc:
                self._no_principal(self._verificacao_falhou, exc)
                return
            try:
                instancias = detect_instances()
            except Exception as exc:
                self.log(f"  (nao consegui listar instalacoes: {exc})", "erro")
                instancias = []
            self._no_principal(self._verificacao_pronta, manifest, instancias)

            # A busca de launcher vem depois, para a tela ja aparecer preenchida
            self.log("Procurando launchers instalados")
            try:
                encontrados = detectar_launchers(log=self.log)
            except Exception as exc:
                self.log(f"  (nao consegui procurar launchers: {exc})", "erro")
                encontrados = []
            self._no_principal(self._aplicar_launchers, encontrados)

        threading.Thread(target=trabalho, daemon=True).start()

    def _escolher_pack(self, packs):
        """
        Decide qual modpack usar: o que a pessoa escolheu na ultima vez, ou o
        primeiro da lista. Nao mexe na tela, por isso pode ser chamado de
        qualquer thread.
        """
        salvo = self.settings.get("pack_id")
        if salvo:
            for p in packs:
                if p.get("id") == salvo:
                    return p
        return packs[0]

    def _aplicar_packs(self, packs):
        """Coloca a lista de modpacks na tela. So mexe na interface."""
        self.rotulo_para_pack = {}
        rotulos = []
        for p in packs:
            rotulo = f"{p.get('nome', p.get('id'))}   ({p.get('mods','?')} mods)"
            self.rotulo_para_pack[rotulo] = p
            rotulos.append(rotulo)
        self.pack_box["values"] = rotulos

        if self.pack_atual is None and packs:
            self.pack_atual = self._escolher_pack(packs)

        alvo = (self.pack_atual or {}).get("id")
        for rotulo, p in self.rotulo_para_pack.items():
            if p.get("id") == alvo:
                self.pack_var.set(rotulo)
                break
        self._mostrar_info_pack()

    def _mostrar_info_pack(self):
        p = self.pack_atual or {}
        try:
            self.cabecalho.definir_subtitulo(f"{self.pack_nome()}   |   IP {self.pack_ip()}")
        except Exception:
            pass
        partes = []
        if p.get("descricao"):
            partes.append(p["descricao"])
        if p.get("ip"):
            partes.append(f"servidor {p['ip']}")
        if p.get("loader"):
            partes.append(p["loader"])
        self.pack_info.set("  |  ".join(partes))

    def pack_id(self):
        return (self.pack_atual or {}).get("id") or "unico"

    def pack_ip(self):
        return (self.pack_atual or {}).get("ip") or SERVER_IP

    def pack_nome(self):
        return (self.pack_atual or {}).get("nome") or SERVER_NAME

    def on_pack_change(self):
        novo = self.rotulo_para_pack.get(self.pack_var.get())
        if not novo or novo is self.pack_atual:
            return
        self.pack_atual = novo
        self.settings["pack_id"] = novo.get("id")
        save_json(SETTINGS_FILE, self.settings)
        self._mostrar_info_pack()
        self.log(f"Trocando para o modpack: {novo.get('nome')}")
        self.manifest = None
        self.set_status("Carregando o modpack")
        self.check_updates()

    def _verificacao_falhou(self, exc):
        self.set_status("Nao consegui verificar atualizacoes")
        self.log(f"ERRO: {exc}", "erro")
        self.render_news([])
        self.set_mode("error")

    def _verificacao_pronta(self, manifest, instancias):
        self.manifest = manifest
        m = manifest
        self.log(f"Pack v{m.get('pack_version','?')} | Minecraft "
                 f"{m.get('minecraft','?')} | {m.get('loader','?')} | "
                 f"{len(m.get('mods', []))} mods")
        self.render_news(m.get("noticias") or m.get("news") or [])
        self.populate_instances(instancias)
        self.evaluate()

    def evaluate(self):
        folder = self.current_folder()
        if not folder:
            self.set_status("Selecione onde voce joga o BroxasSMP")
            self.set_mode("error")
            return

        fstate = get_folder_state(self.state_data, folder, self.pack_id())
        nivel, msgs = analyze_folder(folder, self.manifest, fstate)
        if nivel == "perigo":
            self.warn_lbl.configure(fg=UI.VERMELHO_CLARO)
            self.warn_var.set("ATENCAO: " + " ".join(msgs))
            self.set_status("Escolha outra pasta para continuar")
            self.set_mode("error")
            return
        self.warn_lbl.configure(fg=UI.LARANJA if nivel == "aviso" else UI.TEXTO_FRACO)
        self.warn_var.set(("AVISO: " if nivel == "aviso" else "") + " ".join(msgs))

        mc, fv, _ = parse_forge_info(self.manifest)
        self.forge_needed = False
        if mc and fv:
            if is_forge_installed(folder, mc, fv):
                self.log(f"Forge {fv} ja instalado", "ok")
            else:
                self.forge_needed = True
                self.log(f"Forge {mc}-{fv} nao encontrado, sera instalado", "aviso")

        try:
            de_outros = mods_de_qualquer_pack(self.state_data, folder)
            to_dl, to_rm, ok = plan_sync(self.manifest, Path(folder), fstate, de_outros)
        except Exception as exc:
            self.set_status("Erro ao comparar arquivos")
            self.log(f"ERRO: {exc}", "erro")
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
            self.set_status("Falta " + ", ".join(partes) + f".   {ok} ja em dia.")
            self.barra.definir(0.0)
            self.set_mode("update")
        else:
            self.set_status(
                f"Tudo em dia! Pack v{self.manifest.get('pack_version','?')}.")
            self.set_mode("play")

    def on_action(self):
        if self.busy:
            return
        self.save_settings()

        if self.mode == "play":
            self.launch()
            return
        if self.mode == "error":
            self.log("Verificando de novo")
            self.set_status("Verificando")
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
        self.botao.pulsar(False)
        self.botao.configurar(texto="TRABALHANDO...", ativo=False)
        self.girador.iniciar()

        def work():
            try:
                if self.forge_needed:
                    mc, fv, url = parse_forge_info(self.manifest)
                    self.set_status("Instalando o Forge")
                    self.barra.carregando(True)
                    self.log("Instalando o Forge")
                    ok_forge, msg = install_forge(folder, mc, fv, url, log=self.log)
                    self.log(f"  {msg}", "ok" if ok_forge else "erro")
                    if not ok_forge:
                        self.set_status("Falha ao instalar o Forge")
                        messagebox.showerror("Forge", msg)
                        self.busy = False
                        self.set_mode("update")
                        return
                    self.forge_needed = False
                    self.barra.carregando(False)

                self.set_status("Sincronizando os mods")
                fstate = get_folder_state(self.state_data, folder, self.pack_id())
                self.log(f"Sincronizando em {folder}")
                res = do_sync(self.manifest, Path(folder), self.state_data, fstate,
                              self.log, self.set_progress)
                self.log(f"Fim: {len(res.downloaded)} baixados, "
                         f"{len(res.removed)} removidos, {res.kept} ja estavam ok")
                if res.errors:
                    self.set_status(
                        f"Concluido com {len(res.errors)} erro(s). Veja os detalhes.")
                    for e in res.errors:
                        self.log(f"  ! {e}", "erro")
                    self._alternar_log(abrir=True)
                    self.set_mode("update")
                else:
                    self.log("Preparando o jogo")
                    for m in self.preparar_jogo_para_entrar():
                        self.log(f"  {m}")
                    self.set_status("Tudo pronto! Bom jogo.")
                    self.set_progress(1, 1)
                    self.set_mode("play")
            finally:
                self.busy = False
                self.girador.parar()

        threading.Thread(target=work, daemon=True).start()

    def preparar_jogo_para_entrar(self):
        """
        Poupa trabalho de quem vai jogar: coloca o servidor na lista de
        multijogador e deixa o perfil do Forge pre-selecionado no launcher.
        """
        pasta = self.current_folder()
        if not pasta:
            return []
        mc, fv, _ = parse_forge_info(self.manifest or {})
        try:
            return preparar_jogo.preparar(pasta, mc or "1.20.1", fv or "",
                                          self.pack_nome(), self.pack_ip(),
                                          log=self.log)
        except Exception as exc:
            self.log(f"  (nao consegui preparar o jogo: {exc})", "erro")
            return []

    def launch(self):
        path = self.current_launcher().strip()
        mc = (self.manifest or {}).get("minecraft", "1.20.1")
        loader = (self.manifest or {}).get("loader", "Forge")

        self.log("Preparando o jogo")
        avisos = self.preparar_jogo_para_entrar()
        for m in avisos:
            self.log(f"  {m}")
        if not path or not Path(path).exists():
            messagebox.showwarning(
                "Launcher nao encontrado",
                "Seus mods JA estao atualizados! Voce pode abrir o launcher "
                "que costuma usar e jogar normalmente.\n\n"
                "Se quiser que este programa abra o launcher para voce, clique "
                "em Procurar e selecione o executavel dele "
                "(TLauncher.exe, CurseForge.exe, etc).")
            return
        try:
            subprocess.Popen([path], close_fds=True)
            self.log(f"Abrindo launcher: {path}")
            resumo = "\n".join(f"- {m}" for m in avisos) if avisos else ""
            messagebox.showinfo(
                "Bom jogo!",
                f"Launcher aberto!\n\n"
                f"O perfil {loader} ({mc}) ja esta selecionado: basta apertar "
                f"em Play.\n\n"
                f"Dentro do jogo, va em Multijogador: o {self.pack_nome()} ja "
                f"esta na lista.\n\n"
                + (f"O que foi preparado:\n{resumo}" if resumo else ""))
        except Exception as exc:
            messagebox.showerror("Erro", f"Nao consegui abrir o launcher:\n{exc}")


if __name__ == "__main__":
    load_external_config()
    App().mainloop()
