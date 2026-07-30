# BroxasSMP — Guia rápido do repositório

Este repositório é o "servidor de arquivos" dos modpacks. Você mexe aqui, o robô
do GitHub faz o resto, e o `.exe` da galera atualiza sozinho.

---

## Os 2 modpacks

| | Guerra Medieval | Magia e Tecnologia |
|---|---|---|
| Pasta | `packs/guerra/` | `packs/magia/` |
| Mods | 139 | 163 |
| Download | ~283 MB | ~598 MB |
| RAM recomendada | 6 GB | **8 a 10 GB** |

No launcher aparece um seletor **MODPACK** no topo. A pessoa escolhe, o app
baixa só aquele pack, e lembra a escolha na próxima vez.

> **Dá pra usar a mesma pasta pros dois?** Dá, mas não recomendo. Se trocar de
> pack na mesma pasta, o app remove os mods do pack anterior e baixa os do novo
> (leva tempo e gasta banda). Melhor cada pack na sua pasta.
> Mods que **você** colocou na mão nunca são apagados.

---

## Como adicionar ou remover um mod

Tudo acontece **dentro da pasta do pack**, nunca na raiz.

### Mod de até 25 MB
1. Entre em `packs/guerra/mods` (ou `packs/magia/mods`)
2. **Add file → Upload files**, arraste o `.jar`
3. **Commit changes**
4. Espere o ✅ na aba **Actions** (2 a 4 minutos)

Pronto. O botão da galera vira **ATUALIZAR** sozinho.

### Remover um mod
- Se o arquivo está em `packs/<pack>/mods/`: clique nele → ícone de lixeira → *Commit changes*
- Se **não** está lá, ele vem por link: abra `packs/<pack>/mods_externos.json`,
  apague o bloco `{ "name": ..., "url": ..., "sha1": ..., "size": ... }` do mod
  e faça commit

### Mod acima de 25 MB
O navegador do GitHub não deixa. Me chame: eu procuro o link oficial (Modrinth
ou CurseForge) e adiciono no `mods_externos.json` do pack. Aí você não precisa
enviar arquivo nenhum.

> ⚠️ **Dependências:** quase todo mod grande depende de outro (biblioteca). Se
> adicionar um mod na mão e o jogo não abrir, provavelmente falta a dependência.
> Me manda o nome que eu resolvo.

---

## Escrever notícias

Cada pack tem as suas. Edite `packs/guerra/noticias.txt` ou
`packs/magia/noticias.txt` pelo lápis:

```
# Cerco neste sábado
A janela é das 19h às 22h. Preparem os exércitos.
```

Linha com `#` é o título, o resto é o texto. Aparece no painel direito do app.

---

## Mudar IP, versão do Forge ou nome do pack

Edite `packs/<pack>/pack.json`:

```json
{
  "nome": "Guerra Medieval",
  "ip": "enx-cirion-23.enx.host:10018",
  "minecraft": "1.20.1",
  "forge": "47.4.20",
  "descricao": "Clas, cercos e guerra medieval"
}
```

O `launcher.json` da raiz guarda só o nome e o IP padrão do **aplicativo** (é o
que vira o nome do `.exe`).

---

## Criar um terceiro pack

1. Crie a pasta `packs/nome-do-pack/`
2. Coloque dentro: `pack.json` (copie de outro e edite) e a pasta `mods/`
3. Commit → o robô detecta sozinho e o pack aparece no seletor do launcher

---

## Pegar o `.exe`

Página inicial → **Releases** → **BroxasSMP Updater** → baixe o
`BroxasSMP-Updater.exe`.

O link do Releases é fixo: sempre aponta pra versão mais nova. Manda ele no
Discord uma vez e nunca mais precisa mexer.

---

## O que cada arquivo faz

| Arquivo | Pra quê |
|---|---|
| `packs/<id>/mods/` | Os `.jar` que você envia (até 25 MB cada) |
| `packs/<id>/mods_externos.json` | Mods baixados por link oficial (não ocupam espaço aqui) |
| `packs/<id>/pack.json` | Nome, IP, Minecraft e Forge daquele pack |
| `packs/<id>/noticias.txt` | Notícias daquele pack |
| `packs/<id>/manifest.json` | **Gerado pelo robô.** Não edite |
| `packs.json` | **Gerado pelo robô.** Índice que o launcher lê |
| `launcher.json` | Nome e IP padrão do aplicativo |
| `broxas_updater.py` | O aplicativo que a galera usa |
| `interface.py` | Aparência do aplicativo |
| `detector.py` | Acha as instalações de Minecraft do PC |
| `launchers.py` | Acha o launcher instalado (TLauncher, CurseForge, oficial...) |
| `forge_setup.py` | Instala o Forge automaticamente |
| `preparar_jogo.py` | Adiciona o servidor na lista e pré-seleciona o perfil |
| `rede.py` | Downloads (com o conserto do erro de certificado) |
| `gerar_packs.py` | Monta os `manifest.json` e o `packs.json` |
| `verificar_manifest.py` | Testa se todo mod do pack baixa, antes de publicar |
| `.github/workflows/publicar.yml` | O robô que faz tudo isso e compila o `.exe` |

---

## Se der erro

**❌ vermelho na aba Actions**
Clique no item pra ler a mensagem. Causas comuns:
- `O pack 'x' nao tem nenhum mod` → a pasta `mods` do pack está vazia
- `Falta o arquivo packs/x/pack.json` → criou a pasta mas esqueceu o `pack.json`
- `mods que nao podem ser baixados` → um link do `mods_externos.json` morreu (o
  autor apagou a versão). Nada é publicado nesse caso, então a galera continua
  com a versão anterior funcionando. Me chame pra achar o link novo.

**`Commit failed — file is too large`**
Arquivo acima de 25 MB. Me manda o nome que eu coloco por link.

**Um mod não baixa no updater**
O nome do arquivo em `packs/<pack>/mods/` tem que ser **idêntico** ao que está
no `manifest.json`. Renomeou o `.jar`? Suba de novo com o nome original.

**Antivírus reclamou do `.exe`**
Falso-positivo comum de programa feito com PyInstaller. Avise a galera.
