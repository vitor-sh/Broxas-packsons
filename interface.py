"""
Componentes visuais do BroxasSMP Updater
========================================

Widgets desenhados em Canvas para dar um acabamento melhor do que o padrao do
tkinter: cantos arredondados, reacao ao passar o mouse, barra de progresso com
movimento suave e animacao de carregando.

Tudo usa apenas tkinter puro, sem dependencia externa.
"""

import tkinter as tk

# ---------------------------------------------------------------------
# Paleta (clima medieval: carvao, ouro e pergaminho)
# ---------------------------------------------------------------------

FUNDO = "#111118"
FUNDO_TOPO = "#191922"
FUNDO_CARTAO = "#1b1b25"
FUNDO_POCO = "#0d0d13"
BORDA = "#2b2b3a"
BORDA_CLARA = "#3a3a4d"

TEXTO = "#ece9f2"
TEXTO_FRACO = "#8b8ba1"
TEXTO_SUAVE = "#c6c4d4"

OURO = "#e0b23c"
OURO_CLARO = "#f2c85a"
OURO_ESCURO = "#a8801f"

VERDE = "#3d9b52"
VERDE_CLARO = "#4cb765"
VERMELHO = "#b0433d"
VERMELHO_CLARO = "#c9524b"
LARANJA = "#d1873c"

FONTE = "Segoe UI"


def clarear(cor_hex, fator=0.15):
    """Clareia uma cor #rrggbb."""
    cor_hex = cor_hex.lstrip("#")
    r, g, b = (int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))
    r = min(255, int(r + (255 - r) * fator))
    g = min(255, int(g + (255 - g) * fator))
    b = min(255, int(b + (255 - b) * fator))
    return f"#{r:02x}{g:02x}{b:02x}"


def escurecer(cor_hex, fator=0.15):
    cor_hex = cor_hex.lstrip("#")
    r, g, b = (int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))
    return f"#{int(r * (1 - fator)):02x}{int(g * (1 - fator)):02x}{int(b * (1 - fator)):02x}"


def misturar(cor_a, cor_b, t):
    """Interpola duas cores. t=0 devolve cor_a, t=1 devolve cor_b."""
    a = cor_a.lstrip("#")
    b = cor_b.lstrip("#")
    partes = []
    for i in (0, 2, 4):
        ca = int(a[i:i + 2], 16)
        cb = int(b[i:i + 2], 16)
        partes.append(int(ca + (cb - ca) * t))
    return f"#{partes[0]:02x}{partes[1]:02x}{partes[2]:02x}"


def retangulo_redondo(canvas, x1, y1, x2, y2, raio=10, **kw):
    """Desenha um retangulo de cantos arredondados."""
    raio = max(0, min(raio, (x2 - x1) // 2, (y2 - y1) // 2))
    pontos = [
        x1 + raio, y1, x2 - raio, y1, x2, y1,
        x2, y1 + raio, x2, y2 - raio, x2, y2,
        x2 - raio, y2, x1 + raio, y2, x1, y2,
        x1, y2 - raio, x1, y1 + raio, x1, y1,
    ]
    return canvas.create_polygon(pontos, smooth=True, splinesteps=24, **kw)


# ---------------------------------------------------------------------
# Botao
# ---------------------------------------------------------------------

class Botao(tk.Canvas):
    """Botao arredondado com reacao ao mouse e brilho opcional."""

    def __init__(self, master, texto="", comando=None, cor=OURO, cor_texto="#15151d",
                 altura=52, raio=14, fonte=None, **kw):
        super().__init__(master, height=altura, bg=kw.pop("bg", FUNDO),
                         highlightthickness=0, bd=0, **kw)
        self.comando = comando
        self.cor_base = cor
        self.cor_texto = cor_texto
        self.raio = raio
        self.altura = altura
        self.fonte = fonte or (FONTE, 14, "bold")
        self.texto = texto
        self.ativo = True
        self._sobre = False
        self._pressionado = False
        self._pulso = 0.0
        self._pulsando = False
        self._forma = None
        self._rotulo = None

        self.bind("<Configure>", lambda e: self._desenhar())
        self.bind("<Enter>", self._entrar)
        self.bind("<Leave>", self._sair)
        self.bind("<Button-1>", self._apertar)
        self.bind("<ButtonRelease-1>", self._soltar)

    # ---- aparencia ----
    def _cor_atual(self):
        if not self.ativo:
            return escurecer(self.cor_base, 0.45)
        cor = self.cor_base
        if self._pulsando:
            cor = misturar(cor, clarear(cor, 0.35), self._pulso)
        if self._pressionado:
            return escurecer(cor, 0.18)
        if self._sobre:
            return clarear(cor, 0.12)
        return cor

    def _desenhar(self):
        self.delete("all")
        largura = max(self.winfo_width(), 10)
        altura = max(self.winfo_height(), 10)
        cor = self._cor_atual()

        # sombra sutil embaixo
        retangulo_redondo(self, 2, 4, largura - 2, altura - 1,
                          raio=self.raio, fill=escurecer(cor, 0.55), outline="")
        self._forma = retangulo_redondo(self, 2, 2, largura - 2, altura - 3,
                                        raio=self.raio, fill=cor,
                                        outline=clarear(cor, 0.25))
        cor_texto = self.cor_texto if self.ativo else TEXTO_FRACO
        self._rotulo = self.create_text(largura // 2, altura // 2 - 1,
                                        text=self.texto, fill=cor_texto,
                                        font=self.fonte)

    # ---- eventos ----
    def _entrar(self, _=None):
        self._sobre = True
        if self.ativo:
            self.configure(cursor="hand2")
        self._desenhar()

    def _sair(self, _=None):
        self._sobre = False
        self._pressionado = False
        self._desenhar()

    def _apertar(self, _=None):
        if not self.ativo:
            return
        self._pressionado = True
        self._desenhar()

    def _soltar(self, _=None):
        if not self.ativo:
            return
        estava = self._pressionado
        self._pressionado = False
        self._desenhar()
        if estava and self.comando:
            self.comando()

    # ---- API ----
    def configurar(self, texto=None, cor=None, cor_texto=None, ativo=None):
        if texto is not None:
            self.texto = texto
        if cor is not None:
            self.cor_base = cor
        if cor_texto is not None:
            self.cor_texto = cor_texto
        if ativo is not None:
            self.ativo = ativo
            self.configure(cursor="hand2" if ativo else "arrow")
        self._desenhar()

    def pulsar(self, ligado=True):
        """Liga um brilho suave que vai e volta, para chamar atencao."""
        if ligado and not self._pulsando:
            self._pulsando = True
            self._animar_pulso(0.0, 1)
        elif not ligado:
            self._pulsando = False
            self._pulso = 0.0
            self._desenhar()

    def _animar_pulso(self, valor, direcao):
        if not self._pulsando:
            return
        valor += 0.05 * direcao
        if valor >= 1:
            valor, direcao = 1.0, -1
        elif valor <= 0:
            valor, direcao = 0.0, 1
        self._pulso = valor
        self._desenhar()
        self.after(45, lambda: self._animar_pulso(valor, direcao))


# ---------------------------------------------------------------------
# Barra de progresso
# ---------------------------------------------------------------------

class Barra(tk.Canvas):
    """Barra de progresso com movimento suave e modo carregando."""

    def __init__(self, master, altura=12, cor=OURO, **kw):
        super().__init__(master, height=altura, bg=kw.pop("bg", FUNDO),
                         highlightthickness=0, bd=0, **kw)
        self.altura = altura
        self.cor = cor
        self._alvo = 0.0
        self._atual = 0.0
        self._carregando = False
        self._desloc = 0.0
        self.bind("<Configure>", lambda e: self._desenhar())
        self._animar()

    def definir(self, fracao):
        self._carregando = False
        self._alvo = max(0.0, min(1.0, fracao))

    def carregando(self, ligado=True):
        self._carregando = ligado
        if not ligado:
            self._desloc = 0.0

    def _animar(self):
        if self._carregando:
            self._desloc = (self._desloc + 0.014) % 1.0
        else:
            dif = self._alvo - self._atual
            if abs(dif) > 0.002:
                self._atual += dif * 0.18
            else:
                self._atual = self._alvo
        self._desenhar()
        self.after(16, self._animar)

    def _desenhar(self):
        self.delete("all")
        largura = max(self.winfo_width(), 10)
        altura = max(self.winfo_height(), 6)
        raio = altura // 2

        retangulo_redondo(self, 0, 0, largura, altura, raio=raio,
                          fill=FUNDO_POCO, outline=BORDA)

        if self._carregando:
            comprimento = largura * 0.32
            inicio = -comprimento + (largura + comprimento) * self._desloc
            fim = inicio + comprimento
            inicio = max(1, inicio)
            fim = min(largura - 1, fim)
            if fim - inicio > 2:
                retangulo_redondo(self, inicio, 1, fim, altura - 1, raio=raio,
                                  fill=self.cor, outline="")
            return

        if self._atual > 0.001:
            fim = max(raio * 2 + 1, largura * self._atual)
            retangulo_redondo(self, 1, 1, fim, altura - 1, raio=raio,
                              fill=self.cor, outline="")
            # brilho no topo, dando um leve volume
            if fim - 4 > 4:
                self.create_line(3, 3, fim - 3, 3,
                                 fill=clarear(self.cor, 0.35), width=1)


# ---------------------------------------------------------------------
# Girador de carregando
# ---------------------------------------------------------------------

class Girador(tk.Canvas):
    """Arco girando, usado enquanto o programa verifica algo."""

    def __init__(self, master, tamanho=16, cor=OURO, **kw):
        super().__init__(master, width=tamanho, height=tamanho,
                         bg=kw.pop("bg", FUNDO), highlightthickness=0, bd=0, **kw)
        self.tamanho = tamanho
        self.cor = cor
        self._angulo = 0
        self._rodando = False

    def iniciar(self):
        if not self._rodando:
            self._rodando = True
            self._passo()

    def parar(self):
        self._rodando = False
        self.delete("all")

    def _passo(self):
        if not self._rodando:
            return
        self.delete("all")
        m = 2
        self.create_arc(m, m, self.tamanho - m, self.tamanho - m,
                        start=self._angulo, extent=95, style="arc",
                        outline=self.cor, width=2)
        self._angulo = (self._angulo - 12) % 360
        self.after(40, self._passo)


# ---------------------------------------------------------------------
# Cartao
# ---------------------------------------------------------------------

class Cartao(tk.Frame):
    """Painel com fundo proprio e borda discreta."""

    def __init__(self, master, titulo=None, cor_titulo=OURO, **kw):
        super().__init__(master, bg=FUNDO_CARTAO,
                         highlightbackground=BORDA, highlightthickness=1, bd=0, **kw)
        self.corpo = self
        if titulo:
            topo = tk.Frame(self, bg=FUNDO_CARTAO)
            topo.pack(fill="x", padx=14, pady=(11, 0))
            tk.Label(topo, text=titulo, bg=FUNDO_CARTAO, fg=cor_titulo,
                     font=(FONTE, 9, "bold")).pack(side="left")
            linha = tk.Frame(self, bg=BORDA, height=1)
            linha.pack(fill="x", padx=14, pady=(8, 0))


# ---------------------------------------------------------------------
# Faixa do topo
# ---------------------------------------------------------------------

class Cabecalho(tk.Canvas):
    """Faixa do topo com degrade, titulo e brilho que respira."""

    def __init__(self, master, titulo, subtitulo, altura=104, **kw):
        super().__init__(master, height=altura, bg=FUNDO_TOPO,
                         highlightthickness=0, bd=0, **kw)
        self.titulo = titulo
        self.subtitulo = subtitulo
        self.altura = altura
        self._brilho = 0.0
        self._direcao = 1
        self.bind("<Configure>", lambda e: self._desenhar())
        self._animar()

    def definir_subtitulo(self, texto):
        self.subtitulo = texto
        self._desenhar()

    def _animar(self):
        self._brilho += 0.012 * self._direcao
        if self._brilho >= 1:
            self._brilho, self._direcao = 1.0, -1
        elif self._brilho <= 0:
            self._brilho, self._direcao = 0.0, 1
        self._desenhar()
        self.after(60, self._animar)

    def _desenhar(self):
        self.delete("all")
        largura = max(self.winfo_width(), 10)
        altura = self.altura

        # degrade vertical simples
        passos = 22
        for i in range(passos):
            t = i / (passos - 1)
            cor = misturar(FUNDO_TOPO, FUNDO, t)
            y1 = altura * i / passos
            y2 = altura * (i + 1) / passos + 1
            self.create_rectangle(0, y1, largura, y2, fill=cor, outline="")

        cor_titulo = misturar(OURO, OURO_CLARO, self._brilho)
        self.create_text(largura // 2, 44, text=self.titulo, fill=cor_titulo,
                         font=(FONTE, 26, "bold"))
        self.create_text(largura // 2, 72, text=self.subtitulo, fill=TEXTO_FRACO,
                         font=(FONTE, 9))

        # fio dourado embaixo, com as pontas apagando
        meio = largura // 2
        for i in range(0, meio, 6):
            t = 1 - (i / meio)
            cor = misturar(FUNDO, OURO_ESCURO, t * 0.85)
            self.create_line(meio - i - 6, altura - 1, meio - i, altura - 1,
                             fill=cor, width=2)
            self.create_line(meio + i, altura - 1, meio + i + 6, altura - 1,
                             fill=cor, width=2)


# ---------------------------------------------------------------------
# Selo de estado
# ---------------------------------------------------------------------

class Selo(tk.Canvas):
    """Etiqueta arredondada para mostrar estado, tipo 'Pack v1.0.9'."""

    def __init__(self, master, texto="", cor=OURO, **kw):
        super().__init__(master, height=22, bg=kw.pop("bg", FUNDO_CARTAO),
                         highlightthickness=0, bd=0, **kw)
        self.texto = texto
        self.cor = cor
        self.bind("<Configure>", lambda e: self._desenhar())

    def definir(self, texto=None, cor=None):
        if texto is not None:
            self.texto = texto
        if cor is not None:
            self.cor = cor
        self._desenhar()

    def _desenhar(self):
        self.delete("all")
        if not self.texto:
            return
        largura = max(self.winfo_width(), 10)
        altura = max(self.winfo_height(), 18)
        retangulo_redondo(self, 0, 1, largura - 1, altura - 2, raio=(altura - 3) // 2,
                          fill=escurecer(self.cor, 0.72), outline=escurecer(self.cor, 0.35))
        self.create_text(largura // 2, altura // 2, text=self.texto,
                         fill=clarear(self.cor, 0.25), font=(FONTE, 8, "bold"))


# ---------------------------------------------------------------------
# Texto que aparece suave
# ---------------------------------------------------------------------

def aplicar_estilo_combobox(raiz):
    """Deixa as caixas de selecao com a mesma cara do resto."""
    from tkinter import ttk
    estilo = ttk.Style(raiz)
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass
    estilo.configure(
        "Broxas.TCombobox",
        fieldbackground=FUNDO_POCO,
        background=FUNDO_CARTAO,
        foreground=TEXTO,
        arrowcolor=OURO,
        bordercolor=BORDA,
        lightcolor=BORDA,
        darkcolor=BORDA,
        selectbackground=FUNDO_POCO,
        selectforeground=TEXTO,
        padding=6,
    )
    estilo.map(
        "Broxas.TCombobox",
        fieldbackground=[("readonly", FUNDO_POCO)],
        bordercolor=[("focus", OURO_ESCURO), ("hover", BORDA_CLARA)],
        arrowcolor=[("disabled", TEXTO_FRACO)],
    )
    raiz.option_add("*TCombobox*Listbox.background", FUNDO_POCO)
    raiz.option_add("*TCombobox*Listbox.foreground", TEXTO)
    raiz.option_add("*TCombobox*Listbox.selectBackground", OURO_ESCURO)
    raiz.option_add("*TCombobox*Listbox.selectForeground", "#15151d")
    raiz.option_add("*TCombobox*Listbox.font", (FONTE, 9))
    return estilo


def aparecer(janela, passo=0.08, intervalo=16):
    """Faz a janela surgir suavemente."""
    try:
        janela.attributes("-alpha", 0.0)
    except tk.TclError:
        return

    def subir(valor):
        valor = min(1.0, valor + passo)
        try:
            janela.attributes("-alpha", valor)
        except tk.TclError:
            return
        if valor < 1.0:
            janela.after(intervalo, lambda: subir(valor))

    janela.after(60, lambda: subir(0.0))
