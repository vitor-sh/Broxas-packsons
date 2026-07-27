"""
Detector de instalacoes de Minecraft
====================================

Varre os locais mais comuns dos launchers e devolve TODAS as instancias
encontradas, para o jogador escolher a certa numa lista (em vez de
adivinhar uma unica pasta).

Suporta: .minecraft padrao, TLauncher (inclusive perfis com pasta custom),
Launcher oficial (perfis com gameDir), CurseForge, Prism, MultiMC,
Modrinth App, GDLauncher, ATLauncher.
"""

import json
import os
from pathlib import Path


def _env(name, fallback=""):
    return os.getenv(name) or fallback


def _count_jars(mods_dir: Path) -> int:
    try:
        return len(list(mods_dir.glob("*.jar")))
    except Exception:
        return 0


def _mk(label, path, source):
    """Monta o registro de uma instancia, se a pasta existir."""
    path = Path(path)
    if not path.exists():
        return None
    mods = path / "mods"
    return {
        "label": label,
        "path": str(path),
        "source": source,
        "mods": _count_jars(mods) if mods.exists() else 0,
        "has_mods_dir": mods.exists(),
    }


# ---------------------------------------------------------------------
# Leitores de arquivos de perfil
# ---------------------------------------------------------------------

def _profiles_from_json(json_path: Path, source: str, default_dir: Path):
    """
    Le launcher_profiles.json (oficial) ou TlauncherProfiles.json (TLauncher).
    Ambos guardam perfis que podem ter 'gameDir' proprio.
    """
    out = []
    if not json_path.exists():
        return out
    try:
        with open(json_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except Exception:
        return out

    profiles = data.get("profiles") or {}
    if not isinstance(profiles, dict):
        return out

    for key, prof in profiles.items():
        if not isinstance(prof, dict):
            continue
        name = prof.get("name") or key
        game_dir = prof.get("gameDir")
        target = Path(game_dir) if game_dir else default_dir
        version = prof.get("lastVersionId") or prof.get("version") or ""
        label = f"{source} - perfil \"{name}\""
        if version:
            label += f" ({version})"
        rec = _mk(label, target, source)
        if rec:
            out.append(rec)
    return out


def _scan_instances(base: Path, source: str, inner_names=("minecraft", ".minecraft")):
    """
    Varre uma pasta de instancias (CurseForge, Prism, MultiMC...).
    Cada subpasta e uma instancia; a pasta do jogo pode ser a propria
    subpasta ou uma pasta interna tipo 'minecraft'/'.minecraft'.
    """
    out = []
    if not base.exists():
        return out
    try:
        subdirs = [d for d in base.iterdir() if d.is_dir()]
    except Exception:
        return out

    for inst in sorted(subdirs):
        target = None
        for inner in inner_names:
            if (inst / inner).exists():
                target = inst / inner
                break
        if target is None:
            if (inst / "mods").exists():
                target = inst
            else:
                continue
        rec = _mk(f"{source} - {inst.name}", target, source)
        if rec:
            out.append(rec)
    return out


# ---------------------------------------------------------------------
# Deteccao principal
# ---------------------------------------------------------------------

def detect_instances():
    appdata = Path(_env("APPDATA", str(Path.home())))
    local = Path(_env("LOCALAPPDATA", str(Path.home())))
    home = Path.home()
    docs = home / "Documents"

    found = []

    # 1) .minecraft padrao (usado por TLauncher e pelo launcher oficial)
    dot_mc = appdata / ".minecraft"
    rec = _mk(".minecraft (pasta padrao)", dot_mc, "Padrao")
    if rec:
        found.append(rec)

    # 2) Perfis com pasta customizada
    found += _profiles_from_json(dot_mc / "TlauncherProfiles.json", "TLauncher", dot_mc)
    found += _profiles_from_json(dot_mc / "launcher_profiles.json", "Minecraft Launcher", dot_mc)

    # 3) Pastas de instancias dos launchers
    found += _scan_instances(home / "curseforge" / "minecraft" / "Instances", "CurseForge", ())
    found += _scan_instances(docs / "curseforge" / "minecraft" / "Instances", "CurseForge", ())
    found += _scan_instances(appdata / "PrismLauncher" / "instances", "Prism")
    found += _scan_instances(local / "PrismLauncher" / "instances", "Prism")
    found += _scan_instances(appdata / "MultiMC" / "instances", "MultiMC")
    found += _scan_instances(home / "MultiMC" / "instances", "MultiMC")
    found += _scan_instances(appdata / "com.modrinth.theseus" / "profiles", "Modrinth App", ())
    found += _scan_instances(appdata / "ModrinthApp" / "profiles", "Modrinth App", ())
    found += _scan_instances(appdata / "gdlauncher_next" / "instances", "GDLauncher", ())
    found += _scan_instances(appdata / "ATLauncher" / "instances", "ATLauncher", ())

    # Remove duplicatas pelo caminho real, mantendo o rotulo mais informativo
    by_path = {}
    for rec in found:
        key = os.path.normcase(os.path.normpath(rec["path"]))
        # Mantem o primeiro rotulo encontrado. A pasta padrao entra primeiro,
        # entao o .minecraft aparece como ".minecraft (pasta padrao)" em vez de
        # herdar o nome de um perfil qualquer, que confunde o jogador.
        if key not in by_path:
            by_path[key] = rec

    result = list(by_path.values())
    # Ordena: quem tem mais mods primeiro (mais provavel de ser a instancia em uso)
    result.sort(key=lambda r: (-r["mods"], r["label"].lower()))
    return result


# ---------------------------------------------------------------------
# Analise de seguranca antes de sincronizar
# ---------------------------------------------------------------------

def parece_minecraft(path) -> bool:
    """Verifica se a pasta tem a cara de uma instalacao de Minecraft."""
    path = Path(path)
    pistas = ["mods", "config", "versions", "saves", "options.txt",
              "resourcepacks", "logs", "launcher_profiles.json"]
    return any((path / p).exists() for p in pistas)


def normalizar_pasta(escolhida):
    """
    Conserta as escolhas erradas mais comuns do jogador.

    - apontou para a pasta 'mods'      -> usa a pasta de cima
    - apontou para a pasta que CONTEM  -> entra no .minecraft / minecraft
      o .minecraft

    Devolve (pasta_corrigida, mensagem). A mensagem e None quando nada mudou.
    """
    p = Path(escolhida)
    if not p.exists():
        return str(p), None

    # Ja e uma instalacao valida? Nao mexe.
    if parece_minecraft(p) and p.name.lower() != "mods":
        return str(p), None

    # Caso 1: escolheu a propria pasta 'mods'
    if p.name.lower() == "mods" and parece_minecraft(p.parent):
        return str(p.parent), (
            f"Voce escolheu a pasta 'mods'. Usando a pasta do jogo: {p.parent}"
        )

    # Caso 2: escolheu a pasta que contem o .minecraft
    for interno in (".minecraft", "minecraft"):
        alvo = p / interno
        if alvo.exists() and parece_minecraft(alvo):
            return str(alvo), f"Entrando em {interno}: {alvo}"

    return str(p), None


def analyze_folder(folder, manifest, folder_state):
    """
    Verifica se a pasta escolhida faz sentido para este pack.
    Devolve (nivel, mensagens) onde nivel = 'ok' | 'aviso' | 'perigo'.
    """
    folder = Path(folder)
    msgs = []
    mods_dir = folder / "mods"

    if not folder.exists():
        return "perigo", ["A pasta selecionada nao existe."]

    # Parece uma pasta de Minecraft?
    if not parece_minecraft(folder) or folder.name.lower() == "mods":
        return "perigo", [
            "Essa pasta nao parece ser uma instalacao de Minecraft.",
            "Escolha a pasta do jogo (a que CONTEM a pasta 'mods'),",
            "normalmente chamada .minecraft",
        ]

    wanted = {m["name"] for m in manifest.get("mods", [])}
    existentes = {p.name for p in mods_dir.glob("*.jar")} if mods_dir.exists() else set()
    ja_gerenciados = set(folder_state.get("managed", []))

    do_pack = existentes & wanted
    estranhos = existentes - wanted - ja_gerenciados
    primeira_vez = not ja_gerenciados

    if not mods_dir.exists():
        msgs.append("A pasta 'mods' sera criada.")

    if primeira_vez and len(estranhos) >= 5 and not do_pack:
        return "aviso", [
            f"Essa pasta tem {len(estranhos)} mods que NAO sao do BroxasSMP "
            f"e nenhum mod do pack.",
            "Isso costuma indicar que e a instancia de OUTRO modpack.",
            "Confirme se e realmente aqui que voce joga no BroxasSMP.",
        ]

    if estranhos:
        msgs.append(
            f"{len(estranhos)} mod(s) extra(s) nesta pasta serao MANTIDOS "
            f"(o updater nao apaga mods que nao instalou)."
        )
    if do_pack:
        msgs.append(f"{len(do_pack)} mod(s) do pack ja presente(s).")

    return "ok", msgs or ["Pasta valida."]


if __name__ == "__main__":
    for inst in detect_instances():
        print(f"[{inst['mods']:3d} mods] {inst['label']}")
        print(f"             {inst['path']}")
