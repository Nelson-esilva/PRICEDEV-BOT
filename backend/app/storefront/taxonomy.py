"""Public taxonomy; independent of operational search heuristics."""
CATEGORIES = {
    "celulares": ("Celulares", ("iphone", "smartphone", "celular", "galaxy", "tablet")),
    "informatica": ("Informática", ("ssd", "notebook", "processador", "placa", "memória", "memoria", "teclado", "mouse", "monitor", "gabinete")),
    "eletronicos": ("Eletrônicos", ("fone", "headphone", "headset", "bluetooth", "smartwatch", "televis", "smart tv", "câmera", "camera", "caixa de som")),
    "casa": ("Casa & cozinha", ("panela", "cafeteira", "air fryer", "geladeira", "cozinha", "aspirador", "casa", "sofá", "sofa", "cama", "ventilador")),
    "moda": ("Moda", ("tênis", "tenis", "camisa", "roupa", "calça", "bolsa", "sandália", "vestido")),
    "beleza": ("Beleza", ("perfume", "shampoo", "creme", "sérum", "serum", "maquiagem", "desodorante")),
    "games": ("Games", ("playstation", "xbox", "nintendo", "console", "controle", "jogo")),
    "esportes": ("Esportes", ("bicicleta", "halter", "whey", "academia", "esporte", "fitness")),
    "infantil": ("Infantil", ("bebê", "bebe", "fralda", "brinquedo", "infantil", "lego")),
    "pets": ("Pets", ("ração", "racao", "pet", "cachorro", "gato")),
}


def category_of(name: str, declared: str | None) -> str | None:
    if declared in CATEGORIES:
        return declared
    haystack = f"{name} {declared or ''}".lower()
    for key, (_, words) in CATEGORIES.items():
        if any(word in haystack for word in words):
            return key
    return None
