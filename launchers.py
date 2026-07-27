"""
Detector de launchers de Minecraft instalados
=============================================

Procura o launcher do jogador em varias frentes, porque cada launcher se
instala em um lugar diferente (e o TLauncher costuma ficar solto no Desktop
ou na pasta de Downloads):

1. Registro do Windows, chaves de programas instalados
2. Registro do Windows, chave App Paths
3. Atalhos do Menu Iniciar
4. Varredura das pastas onde programas normalmente ficam

Tudo protegido: se uma das frentes falhar, as outras continuam.
"""

import os
import subprocess
from pathlib import Path

# nome amigavel -> (nomes de executavel, palavras no nome do programa)
CONHECIDOS = [
    ("TLauncher",           ["tlauncher.exe"],                      ["tlauncher"]),
    ("Legacy Launcher",     ["legacylauncher.exe", "llauncher.exe"], ["legacy launcher", "llauncher"]),
    ("CurseForge",          ["curseforge.exe"],                     ["curseforge"]),
    ("Minecraft Launcher",  ["minecraftlauncher.exe", "minecraft.exe"],
                            ["minecraft launcher", "minecraft: java", "minecraft para windows"]),
    ("Prism Launcher",      ["prismlauncher.exe"],                  ["prism launcher"]),
    ("PolyMC",              ["polymc.exe"],                         ["polymc"]),
    ("MultiMC",             ["multimc.exe"],                        ["multimc"]),
    ("Modrinth App",        ["modrinth app.exe", "modrinthapp.exe"], ["modrinth"]),
    ("GDLauncher",          ["gdlauncher.exe", "gdlauncher carbon.exe"], ["gdlauncher"]),
    ("ATLauncher",          ["atlauncher.exe"],                     ["atlauncher"]),
    ("SKlauncher",          ["sklauncher.exe"],                     ["sklauncher"]),
    ("Technic Launcher",    ["techniclauncher.exe"],                ["technic"]),
    ("Salwyrr Launcher",    ["salwyrr launcher.exe", "salwyrr.exe"], ["salwyrr"]),
    ("Lunar Client",        ["lunar client.exe"],                   ["lunar client"]),
    ("Badlion Client",      ["badlion client.exe"],                 ["badlion"]),
    ("Feather Launcher",    ["feather launcher.exe", "feather.exe"], ["feather launcher"]),
    ("PineappleLauncher",   ["pineapplelauncher.exe"],              ["pineapple"]),
]

# ordem de preferencia na lista mostrada ao jogador
PRIORIDADE = {nome: i for i, (nome, _, _) in enumerate(CONHECIDOS)}

TODOS_OS_EXES = {}
for _nome, _exes, _ in CONHECIDOS:
    for _e in _exes:
        TODOS_OS_EXES.setdefault(_e.lower(), _nome)


def identificar_por_arquivo(caminho):
    """Descobre o launcher pelo nome do arquivo executavel."""
    return TODOS_OS_EXES.get(Path(caminho).name.lower())


def identificar_por_nome(texto):
    """Descobre o launcher pelo nome com que o programa se registrou."""
    if not texto:
        return None
    t = texto.lower()
    for nome, _, palavras in CONHECIDOS:
        for p in palavras:
            if p in t:
                return nome
    return None


def _achar_exe_na_pasta(pasta, profundidade=2):
    """Procura um executavel conhecido dentro de uma pasta de instalacao."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return None
    try:
        for nivel in range(profundidade + 1):
            padrao = "/".join(["*"] * nivel) + ("/" if nivel else "") + "*.exe"
            for arq in pasta.glob(padrao):
                if identificar_por_arquivo(arq):
                    return str(arq)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------
# Frente 1 e 2: registro do Windows
# ---------------------------------------------------------------------

def _do_registro():
    """Le as chaves de programas instalados (Uninstall)."""
    achados = []
    try:
        import winreg
    except ImportError:
        return achados

    locais = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for raiz, sub in locais:
        try:
            chave = winreg.OpenKey(raiz, sub)
        except OSError:
            continue
        try:
            total = winreg.QueryInfoKey(chave)[0]
        except OSError:
            total = 0
        for i in range(total):
            try:
                nome_sub = winreg.EnumKey(chave, i)
                item = winreg.OpenKey(chave, nome_sub)
            except OSError:
                continue
            dados = {}
            for campo in ("DisplayName", "DisplayIcon", "InstallLocation"):
                try:
                    dados[campo] = winreg.QueryValueEx(item, campo)[0]
                except OSError:
                    dados[campo] = ""
            winreg.CloseKey(item)

            nome = identificar_por_nome(dados.get("DisplayName"))
            if not nome:
                continue

            # DisplayIcon costuma apontar direto para o executavel
            icone = (dados.get("DisplayIcon") or "").split(",")[0].strip('" ')
            if icone.lower().endswith(".exe") and Path(icone).is_file():
                achados.append((nome, icone))
                continue

            local = (dados.get("InstallLocation") or "").strip('" ')
            if local:
                exe = _achar_exe_na_pasta(local)
                if exe:
                    achados.append((nome, exe))
        winreg.CloseKey(chave)
    return achados


def _do_app_paths():
    """Le a chave App Paths, onde programas registram o caminho do exe."""
    achados = []
    try:
        import winreg
    except ImportError:
        return achados

    base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            chave = winreg.OpenKey(raiz, base)
        except OSError:
            continue
        try:
            total = winreg.QueryInfoKey(chave)[0]
        except OSError:
            total = 0
        for i in range(total):
            try:
                nome_sub = winreg.EnumKey(chave, i)
            except OSError:
                continue
            nome = identificar_por_arquivo(nome_sub) or identificar_por_nome(nome_sub)
            if not nome:
                continue
            try:
                item = winreg.OpenKey(chave, nome_sub)
                caminho = winreg.QueryValueEx(item, "")[0].strip('" ')
                winreg.CloseKey(item)
                if caminho.lower().endswith(".exe") and Path(caminho).is_file():
                    achados.append((nome, caminho))
            except OSError:
                continue
        winreg.CloseKey(chave)
    return achados


# ---------------------------------------------------------------------
# Frente 3: atalhos do Menu Iniciar
# ---------------------------------------------------------------------

def _do_menu_iniciar():
    """Resolve atalhos .lnk do Menu Iniciar e da Area de Trabalho."""
    achados = []
    if os.name != "nt":
        return achados

    pastas = []
    for var in ("APPDATA", "ProgramData"):
        base = os.getenv(var)
        if base:
            pastas.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    pastas.append(Path.home() / "Desktop")

    atalhos = []
    for pasta in pastas:
        if not pasta.exists():
            continue
        try:
            for lnk in pasta.glob("**/*.lnk"):
                if identificar_por_nome(lnk.stem):
                    atalhos.append(lnk)
        except Exception:
            continue
    if not atalhos:
        return achados

    # Uma unica chamada ao PowerShell resolve todos os atalhos
    lista = ";".join(f"'{str(a)}'" for a in atalhos[:60])
    script = (
        "$s=New-Object -ComObject WScript.Shell;"
        f"@({lista}) | ForEach-Object {{ try {{ "
        "$t=$s.CreateShortcut($_).TargetPath; if($t){ Write-Output \"$_|$t\" } "
        "} catch {} }"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for linha in (proc.stdout or "").splitlines():
            if "|" not in linha:
                continue
            origem, destino = linha.rsplit("|", 1)
            destino = destino.strip()
            if not destino.lower().endswith(".exe") or not Path(destino).is_file():
                continue
            nome = identificar_por_arquivo(destino) or identificar_por_nome(Path(origem).stem)
            if nome:
                achados.append((nome, destino))
    except Exception:
        pass
    return achados


# ---------------------------------------------------------------------
# Frente 4: varredura das pastas mais comuns
# ---------------------------------------------------------------------

def _raizes_de_busca():
    home = Path.home()
    caminhos = []
    for var in ("LOCALAPPDATA", "APPDATA", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        valor = os.getenv(var)
        if valor:
            caminhos.append(Path(valor))
    local = os.getenv("LOCALAPPDATA")
    if local:
        caminhos.append(Path(local) / "Programs")
    for nome in ("Desktop", "Downloads", "Documents", "Área de Trabalho", "Downloads"):
        caminhos.append(home / nome)
    caminhos.append(home)
    vistos, unicos = set(), []
    for c in caminhos:
        chave = os.path.normcase(str(c))
        if chave not in vistos and c.exists():
            vistos.add(chave)
            unicos.append(c)
    return unicos


def _do_pastas(limite_pastas=6000):
    """
    Varre as pastas onde launcher normalmente fica, com profundidade limitada
    para nao demorar. Cobre o caso do TLauncher solto no Desktop/Downloads.
    """
    achados = []
    visitadas = 0
    for raiz in _raizes_de_busca():
        profundidade_max = 3
        raiz_str = str(raiz)
        try:
            for pasta_atual, subpastas, arquivos in os.walk(raiz_str):
                visitadas += 1
                if visitadas > limite_pastas:
                    return achados

                nivel = pasta_atual[len(raiz_str):].count(os.sep)
                if nivel >= profundidade_max:
                    subpastas[:] = []
                else:
                    # nao entra em pastas que so atrasam a busca
                    subpastas[:] = [
                        s for s in subpastas
                        if not s.startswith(".")
                        and s.lower() not in (
                            "node_modules", "cache", "caches", "logs", "temp", "tmp",
                            "assets", "libraries", "versions", "mods", "saves",
                            "resourcepacks", "shaderpacks", "screenshots", "runtime",
                            "windowsapps", "installer", "packages",
                        )
                    ]

                for arq in arquivos:
                    nome = identificar_por_arquivo(arq)
                    if nome:
                        achados.append((nome, str(Path(pasta_atual) / arq)))
        except Exception:
            continue
    return achados


# ---------------------------------------------------------------------
# Juncao
# ---------------------------------------------------------------------

def detectar_launchers(log=None):
    """
    Devolve uma lista de dicionarios {nome, caminho, origem}, sem repetidos,
    ordenada pela relevancia do launcher.
    """
    frentes = [
        ("registro", _do_registro),
        ("registro (App Paths)", _do_app_paths),
        ("menu iniciar", _do_menu_iniciar),
        ("pastas comuns", _do_pastas),
    ]

    por_caminho = {}
    for origem, funcao in frentes:
        try:
            itens = funcao() or []
        except Exception as exc:
            if log:
                log(f"  (busca por {origem} falhou: {exc})")
            itens = []
        novos = 0
        for nome, caminho in itens:
            try:
                if not Path(caminho).is_file():
                    continue
            except Exception:
                continue
            chave = os.path.normcase(os.path.normpath(caminho))
            if chave not in por_caminho:
                por_caminho[chave] = {"nome": nome, "caminho": caminho, "origem": origem}
                novos += 1
        if log and novos:
            log(f"  {novos} launcher(s) encontrado(s) via {origem}")

    resultado = list(por_caminho.values())
    resultado.sort(key=lambda r: (PRIORIDADE.get(r["nome"], 99), r["nome"].lower()))
    return resultado


if __name__ == "__main__":
    for item in detectar_launchers(log=print):
        print(f"  {item['nome']:22s} {item['caminho']}   [{item['origem']}]")
