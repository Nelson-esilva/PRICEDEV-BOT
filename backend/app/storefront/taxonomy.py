"""Public taxonomy; independent of operational search heuristics."""
import re
import unicodedata

CATEGORIES = {
    "celulares": ("Celulares", ("iphone", "smartphone", "celular", "galaxy", "redmi", "motorola moto", "tablet", "ipad")),
    "informatica": ("Informática", ("ssd", "notebook", "processador", "placa de video", "placa mae", "memoria ram", "memória",
        "teclado", "mouse", "monitor", "gabinete", "fonte atx", "water cooler", "cooler", "impressora", "roteador", "pendrive",
        "hd externo", "webcam", "cadeira gamer", "cadeira de escritorio", "headset gamer")),
    "eletronicos": ("Eletrônicos", ("fone", "headphone", "headset", "earbuds", "smartwatch", "smart watch", "relogio inteligente",
        "televisor", "smart tv", "tv", "camera", "caixa de som", "soundbar", "projetor", "echo dot", "alexa", "kindle", "drone",
        "microfone", "ring light", "carregador", "power bank", "cabo usb", "filtro de linha", "regua", "estabilizador", "fones")),
    "casa": ("Casa & cozinha", ("panela", "frigideira", "cafeteira", "air fryer", "fritadeira", "geladeira", "liquidificador",
        "batedeira", "micro-ondas", "microondas", "aspirador", "ventilador", "ar condicionado", "cooktop", "fogao", "forno",
        "potes", "pote", "garrafa termica", "copo termico", "lixeira", "jogo de cama", "lencol", "toalha", "travesseiro",
        "colchao", "cama", "sofa", "cadeira", "mesa", "fechadura", "lampada", "organizador", "lanterna", "chuveiro",
        "espelho", "cortina", "tapete", "mop", "vaso", "varal", "prateleira", "estante", "arara", "torneira", "chaleira",
        "forma", "fatiador", "batedor", "passadeira", "luminaria", "ar condicionado", "btus", "arvore de natal", "decoracao",
        "utensilios", "faqueiro", "talheres", "cozinha", "casa")),
    "moda": ("Moda", ("tenis", "camisa", "camiseta", "calca", "bermuda", "short", "vestido", "saia", "jaqueta", "moletom",
        "blusa", "sandalia", "chinelo", "bota", "sapato", "bolsa", "mochila", "carteira", "cueca", "calcinha", "meia", "relogio", "oculos", "roupa")),
    "beleza": ("Beleza", ("perfume", "shampoo", "condicionador", "creme", "serum", "maquiagem", "batom", "base liquida",
        "protetor solar", "hidratante", "desodorante", "secador", "chapinha", "escova secadora", "barbeador", "aparador",
        "depilador", "lente de contato", "colageno", "inalador", "nebulizador", "escova de cabelo", "esmalte")),
    "games": ("Games", ("playstation", "ps5", "ps4", "xbox", "nintendo", "switch", "console", "controle", "joystick", "jogo", "game")),
    "esportes": ("Esportes", ("bicicleta", "bike", "halter", "anilha", "whey", "creatina", "suplemento", "academia", "esteira",
        "balanca", "bioimpedancia", "tatame", "patinete", "bola", "esporte", "fitness", "corrida", "proteina", "bebida lactea")),
    "infantil": ("Infantil", ("bebe", "fralda", "brinquedo", "boneca", "carrinho de bebe", "infantil", "lego", "pelucia", "figurinhas")),
    "pets": ("Pets", ("racao", "pet", "cachorro", "caes", "gato", "areia sanitaria", "coleira", "pedigree", "whiskas")),
    "mercado": ("Mercado", ("cafe", "whisky", "cerveja", "vinho", "vodka", "gin", "biscoito", "chocolate", "bebida",
        "refrigerante", "leite", "azeite", "arroz", "papel higienico", "sabao", "detergente", "amaciante", "percarbonato",
        "limpeza", "cesta", "capsulas de cafe", "achocolatado")),
    "ferramentas": ("Ferramentas & auto", ("furadeira", "parafusadeira", "serra", "rocadeira", "lavadora de alta pressao",
        "alta pressao", "lavadora", "chave", "alicate", "bomba", "compressor", "multimetro", "ferramenta", "bateria moto",
        "pneu", "capacete", "moto", "carro", "automotivo", "solda")),
    "livros": ("Livros & papelaria", ("biblia", "livro", "lapis", "caneta", "caderno", "papelaria", "estojo", "agenda", "marca texto")),
}

# Nome de categoria do hub/ML (rótulo) -> chave pública, para quando o título não decide.
_LABELS = (
    ("celular", "celulares"), ("informatica", "informatica"), ("eletronico", "eletronicos"), ("audio e video", "eletronicos"),
    ("eletrodomestico", "casa"), ("casa", "casa"), ("ferramenta", "ferramentas"), ("calcado", "moda"), ("roupa", "moda"),
    ("beleza", "beleza"), ("game", "games"), ("esporte", "esportes"), ("brinquedo", "infantil"), ("bebe", "infantil"),
    ("animal", "pets"), ("pet", "pets"), ("alimento", "mercado"), ("bebida", "mercado"), ("supermercado", "mercado"),
    ("livro", "livros"), ("papelaria", "livros"), ("veiculo", "ferramentas"), ("acessorios para veiculos", "ferramentas"),
)
# A partir daqui o título fala de compatibilidade/acessório: "Controle ... compatível com celular".
_ACCESSORY = re.compile(r"\b(compativel|para|pra|p/|com|serve)\b")


def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " " + re.sub(r"[^a-z0-9/]+", " ", folded).strip() + " "


_FOLDED = {key: tuple(_fold(word).strip() for word in words) for key, (_, words) in CATEGORIES.items()}


def category_of(name: str, declared: str | None, official: str | None = None) -> str | None:
    """Categoria pública. Ordem: o título (a palavra-chave que aparece PRIMEIRO, antes de
    "compatível/para/com"), depois a categoria oficial do ML, depois o rótulo da loja."""
    if declared in CATEGORIES:
        return declared
    title = _fold(name)
    cut = _ACCESSORY.search(title, 4)
    head = title[: cut.start() + 1] if cut else title
    best: tuple[int, int, str] | None = None
    for key, words in _FOLDED.items():
        for word in words:
            # Aceita plural: "calças", "panelas", "fones".
            at = min((i for i in (head.find(f" {word} "), head.find(f" {word}s "), head.find(f" {word}es ")) if i >= 0), default=-1)
            # Mais cedo vence; no empate, a expressão mais longa ("cadeira gamer" > "cadeira").
            if at >= 0 and (best is None or (at, -len(word)) < best[:2]):
                best = (at, -len(word), key)
    if best:
        return best[2]
    if official in CATEGORIES:
        return official
    label = _fold(declared or "")
    return next((key for needle, key in _LABELS if needle in label), None)


# Categoria raiz do Mercado Livre -> categoria pública. Vale mais que palavra-chave no título:
# "Monitor" de bebê não é Informática, "Controle" de portão não é Games.
ML_ROOT_KEYS = {
    "MLB1051": "celulares",
    "MLB1648": "informatica",
    "MLB1000": "eletronicos",
    "MLB1574": "casa",
    "MLB5726": "casa",
    "MLB1276": "esportes",
    "MLB1246": "beleza",
    "MLB1144": "games",
    "MLB1132": "infantil",
    "MLB1384": "infantil",
    "MLB1071": "pets",
    "MLB1430": "moda",
    "MLB263532": "ferramentas",
    "MLB5672": "ferramentas",
    "MLB1403": "mercado",
    "MLB3025": "livros",
}
