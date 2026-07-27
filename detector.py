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
        prev = by_path.get(key)
        if prev is None:
            by_path[key] = rec
        elif prev["source"] == "Padrao" and rec["source"] != "Padrao":
            # prefere o rotulo do launcher especifico
            rec_merged = dict(rec)
            by_path[key] = rec_merged

    result = list(by_path.values())
    # Ordena: quem tem mais mods primeiro (mais provavel de ser a instancia em uso)
    result.sort(key=lambda r: (-r["mods"], r["label"].lower()))
    return result


# ---------------------------------------------------------------------
# Analise de seguranca antes de sincronizar
# ---------------------------------------------------------------------

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
    pistas = ["mods", "config", "versions", "saves", "options.txt", "resourcepacks"]
    achou = [p for p in pistas if (folder / p).exists()]
    if not achou:
        return "perigo", [
            "Essa pasta nao parece ser uma instalacao de Minecraft.",
            "Procure a pasta que contem 'mods', 'config' e 'saves'.",
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
