"""
Instalacao automatica do Forge
==============================

Verifica se o Forge do pack ja esta instalado na pasta do jogador.
Se nao estiver, baixa o instalador OFICIAL do Forge (maven da Minecraft Forge)
e roda em modo cliente, sem o jogador precisar fazer nada.

Nao baixa o Minecraft nem mexe em contas: o instalador do Forge apenas
cria o perfil de versao dentro da pasta escolhida.
"""

import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"


def forge_installer_url(mc_version: str, forge_version: str) -> str:
    full = f"{mc_version}-{forge_version}"
    return f"{MAVEN}/{full}/forge-{full}-installer.jar"


def expected_version_ids(mc_version: str, forge_version: str):
    """Nomes de pasta que o Forge pode criar em versions/."""
    return [
        f"{mc_version}-forge-{forge_version}",
        f"forge-{mc_version}-{forge_version}",
        f"{mc_version}-Forge{forge_version}",
    ]


def is_forge_installed(game_dir, mc_version: str, forge_version: str) -> bool:
    versions = Path(game_dir) / "versions"
    if not versions.exists():
        return False
    esperados = [v.lower() for v in expected_version_ids(mc_version, forge_version)]
    try:
        existentes = [d.name.lower() for d in versions.iterdir() if d.is_dir()]
    except Exception:
        return False
    for exp in esperados:
        if exp in existentes:
            return True
    # Nome customizado que cita forge + as duas versoes
    for nome in existentes:
        if "forge" in nome and forge_version in nome and mc_version in nome:
            return True
    # Alguns launchers (ex: TLauncher) criam apenas "Forge 1.20.1", sem o build.
    # Nesse caso consideramos instalado para NAO criar um perfil duplicado.
    for nome in existentes:
        if "forge" in nome and mc_version in nome:
            return True
    return False


def find_java(game_dir) -> str:
    """
    Procura um java utilizavel:
    1) runtime que o proprio launcher do jogador ja baixou
    2) runtime do TLauncher
    3) java do sistema (PATH / JAVA_HOME)
    """
    candidatos = []

    game_dir = Path(game_dir)
    runtime = game_dir / "runtime"
    if runtime.exists():
        candidatos += list(runtime.glob("**/bin/java.exe"))
        candidatos += list(runtime.glob("**/bin/java"))

    appdata = os.getenv("APPDATA")
    if appdata:
        tl = Path(appdata) / ".tlauncher"
        if tl.exists():
            candidatos += list(tl.glob("**/bin/java.exe"))
            candidatos += list(tl.glob("**/bin/java"))

    for c in candidatos:
        if c.is_file():
            return str(c)

    java_home = os.getenv("JAVA_HOME")
    if java_home:
        for exe in ("java.exe", "java"):
            p = Path(java_home) / "bin" / exe
            if p.is_file():
                return str(p)

    # ultimo recurso: confia no PATH
    for cmd in ("java.exe", "java"):
        try:
            subprocess.run([cmd, "-version"], capture_output=True, timeout=15)
            return cmd
        except Exception:
            continue
    return ""


def ensure_launcher_profiles(game_dir):
    """
    O instalador do Forge exige um launcher_profiles.json na pasta.
    Se nao existir (comum em pastas de instancia), cria um minimo.
    """
    path = Path(game_dir) / "launcher_profiles.json"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"profiles": {}, "version": 3}, f, indent=2)


def install_forge(game_dir, mc_version, forge_version, installer_url=None, log=print):
    """
    Baixa e roda o instalador do Forge. Devolve (sucesso, mensagem).
    """
    game_dir = Path(game_dir)
    url = installer_url or forge_installer_url(mc_version, forge_version)

    java = find_java(game_dir)
    if not java:
        return False, (
            "Nao encontrei Java no seu PC.\n\n"
            "Abra seu launcher uma vez e rode qualquer versao do Minecraft "
            "(isso baixa o Java), ou instale o Java 17, e tente de novo."
        )
    log(f"  Java encontrado: {java}")

    ensure_launcher_profiles(game_dir)

    tmpdir = Path(tempfile.gettempdir())
    installer = tmpdir / f"forge-{mc_version}-{forge_version}-installer.jar"
    try:
        log("  Baixando instalador do Forge...")
        import rede
        ok, motivo = rede.baixar(url, installer, log=log)
        if not ok:
            return False, f"Nao consegui baixar o instalador do Forge: {motivo}"
    except Exception as exc:
        return False, f"Nao consegui baixar o instalador do Forge: {exc}"

    try:
        log("  Instalando Forge (pode levar 1-2 minutos)...")
        creation = 0
        if os.name == "nt":
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [java, "-jar", str(installer), "--installClient", str(game_dir)],
            capture_output=True, text=True, timeout=900, creationflags=creation,
        )
        saida = (proc.stdout or "") + (proc.stderr or "")
        for linha in saida.strip().splitlines()[-6:]:
            if linha.strip():
                log(f"    {linha.strip()}")
        if proc.returncode != 0:
            return False, f"O instalador do Forge retornou erro (codigo {proc.returncode})."
    except subprocess.TimeoutExpired:
        return False, "O instalador do Forge demorou demais e foi cancelado."
    except Exception as exc:
        return False, f"Erro ao rodar o instalador do Forge: {exc}"
    finally:
        try:
            installer.unlink()
        except Exception:
            pass

    if is_forge_installed(game_dir, mc_version, forge_version):
        return True, "Forge instalado com sucesso."
    return True, ("Instalador finalizado. Se o perfil nao aparecer no launcher, "
                  "reinicie o launcher.")


def parse_forge_info(manifest: dict):
    """
    Le as infos de Forge do manifest. Aceita:
      "forge": {"version": "47.4.20", "installer_url": "..."}
    ou deduz de "loader": "Forge 47.4.20".
    Devolve (mc_version, forge_version, installer_url) ou (None, None, None).
    """
    mc = manifest.get("minecraft")
    forge = manifest.get("forge") or {}
    version = forge.get("version")
    url = forge.get("installer_url")

    if not version:
        loader = str(manifest.get("loader") or "")
        if "forge" in loader.lower():
            partes = loader.replace("-", " ").split()
            for p in partes:
                if p and p[0].isdigit() and "." in p and p != mc:
                    version = p
                    break
    if not (mc and version):
        return None, None, None
    return mc, version, url
