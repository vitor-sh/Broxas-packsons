"""
Gerador de manifest para o BroxasSMP Updater
============================================

Le a pasta de mods, calcula o hash de cada .jar, le as noticias do
arquivo noticias.txt e gera o manifest.json.

Uso simples (Windows): duplo clique em PUBLICAR.bat
Uso manual:
    python gerar_manifest.py --mods "C:/caminho/mods" --base-url "https://..." --versao 1.0.0
"""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def ler_noticias(caminho: Path):
    """
    Le noticias.txt. Formato:

        # Titulo da noticia
        Texto da noticia, pode ter varias linhas.

        # Outra noticia
        Outro texto.
    """
    if not caminho.exists():
        return []
    noticias, atual = [], None
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        s = linha.strip()
        if s.startswith("#"):
            if atual:
                noticias.append(atual)
            atual = {"titulo": s.lstrip("#").strip(), "texto": ""}
        elif s:
            if atual is None:
                atual = {"titulo": "", "texto": ""}
            atual["texto"] = (atual["texto"] + " " + s).strip()
    if atual:
        noticias.append(atual)
    return noticias


def main():
    ap = argparse.ArgumentParser(description="Gera o manifest.json do pack")
    ap.add_argument("--mods", required=True, help="Pasta com os .jar dos mods")
    ap.add_argument("--base-url", required=True, help="URL base onde os .jar estao hospedados")
    ap.add_argument("--versao", required=True, help="Versao do pack (ex: 1.0.0)")
    ap.add_argument("--minecraft", default="1.20.1", help="Versao do Minecraft")
    ap.add_argument("--forge", default="47.4.20", help="Versao do Forge")
    ap.add_argument("--noticias", default="noticias.txt", help="Arquivo de noticias")
    ap.add_argument("--externos", default="mods_externos.json",
                    help="Mods hospedados fora da pasta mods/ (ex: arquivos grandes)")
    ap.add_argument("--saida", default="manifest.json", help="Arquivo de saida")
    args = ap.parse_args()

    mods_dir = Path(args.mods)
    if not mods_dir.is_dir():
        raise SystemExit(f"ERRO: pasta nao encontrada: {mods_dir}")

    base = args.base_url.rstrip("/")
    mods = []
    print("Lendo mods...")
    for jar in sorted(mods_dir.glob("*.jar")):
        mods.append({
            "name": jar.name,
            "url": f"{base}/{quote(jar.name)}",
            "sha1": sha1_of(jar),
            "size": jar.stat().st_size,
        })
        print(f"  + {jar.name}")

    # Mods hospedados fora da pasta mods/ (arquivos grandes, links oficiais, etc.)
    externos_path = Path(args.externos)
    if externos_path.exists():
        try:
            extras = json.load(open(externos_path, encoding="utf-8"))
        except Exception as exc:
            raise SystemExit(f"ERRO ao ler {externos_path}: {exc}")
        ja = {e["name"] for e in mods}
        for item in extras.get("mods", []):
            nome = item.get("name")
            url = item.get("url")
            if not nome or not url:
                print(f"  ! ignorando entrada incompleta em {externos_path.name}")
                continue
            if nome in ja:
                print(f"  ! {nome} ja esta na pasta mods/, ignorando o externo")
                continue
            entrada = {"name": nome, "url": url,
                       "sha1": item.get("sha1", ""),
                       "size": item.get("size", 0)}
            mods.append(entrada)
            print(f"  ~ externo: {nome}")

    if not mods:
        raise SystemExit("ERRO: nenhum .jar encontrado na pasta de mods.")

    full = f"{args.minecraft}-{args.forge}"
    noticias = ler_noticias(Path(args.noticias))

    manifest = {
        "pack_version": args.versao,
        "minecraft": args.minecraft,
        "loader": f"Forge {args.forge}",
        "forge": {
            "version": args.forge,
            "installer_url": f"{FORGE_MAVEN}/{full}/forge-{full}-installer.jar",
        },
        "noticias": noticias,
        "mods": mods,
    }

    out = Path(args.saida)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    total_mb = sum(m["size"] for m in mods) / (1024 * 1024)
    print()
    print("=" * 60)
    print(f"  PRONTO! manifest.json gerado")
    print("=" * 60)
    print(f"  Versao do pack : {args.versao}")
    print(f"  Mods           : {len(mods)}  ({total_mb:.1f} MB)")
    print(f"  Forge          : {full}")
    print(f"  Noticias       : {len(noticias)}")
    print(f"  Salvo em       : {out.resolve()}")
    print()
    print("  AGORA: suba o manifest.json (e os .jar novos) para o seu host.")
    print("=" * 60)


if __name__ == "__main__":
    main()
