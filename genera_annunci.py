
import os
import io
import json
from ftplib import FTP
import xml.etree.ElementTree as ET
from urllib.parse import urlparse


def nome(elemento):
    return elemento.tag.split("}")[-1].lower()


def figlio(elemento, percorso):
    if elemento is None:
        return None

    for parte in percorso.split("/"):
        elemento = next(
            (e for e in elemento if nome(e) == parte.lower()),
            None
        ) if elemento is not None else None

    return elemento


def valore(elemento, percorso, default=""):
    e = figlio(elemento, percorso)
    return (e.text or "").strip() if e is not None else default


def numero(testo):
    try:
        return float(str(testo).replace(",", "."))
    except (ValueError, TypeError):
        return None


# DESCRIZIONI: SOLO LINGUA ITALIANA

def commento(annuncio):
    sezione = figlio(annuncio, "comments")

    if sezione is None:
        return ""

    for item in sezione:
        if nome(item) != "adcomments":
            continue

        lingua = valore(item, "language").strip().lower()
        lingua = lingua.replace("_", "-")

        if (
            lingua in ("it", "it-it", "italiano", "italian")
            or lingua.startswith("it-")
        ):
            testo = valore(item, "propertycomment")

            if testo:
                return testo

    # Non utilizzare descrizioni in lingue straniere.
    return ""


# FOTOGRAFIE

def immagini(annuncio):
    sezione = figlio(annuncio, "multimedias")

    if sezione is None:
        return []

    risultati = []

    for item in sezione:
        if nome(item) != "pictures":
            continue

        percorso = valore(item, "multimediapath")

        if percorso.startswith(("https://", "http://")):
            risultati.append({
                "url": percorso,
                "posizione": numero(
                    valore(item, "position")
                ) or 0
            })

    risultati.sort(key=lambda x: x["posizione"])

    return [x["url"] for x in risultati]


# COLLEGAMENTO FTP IDEALISTA

host = os.environ["FTP_HOST"]

host = urlparse(
    host if "://" in host else "ftp://" + host
).hostname

with FTP(timeout=30) as ftp:

    ftp.connect(host, 21)

    ftp.login(
        os.environ["FTP_USER"],
        os.environ["FTP_PASSWORD"]
    )

    ftp.set_pasv(True)

    nomi = ftp.nlst()

    esclusi = (
        "activities",
        "agents",
        "clients",
        "enquiries",
        "groups",
        "operations"
    )

    candidati = [
        n for n in nomi
        if n.lower().endswith(".xml")
        and not any(
            n.lower().endswith("_" + s + ".xml")
            for s in esclusi
        )
    ]

    annunci = []

    for file in candidati:

        dati = io.BytesIO()

        ftp.retrbinary(
            "RETR " + file,
            dati.write
        )

        try:
            radice = ET.fromstring(
                dati.getvalue()
            )
        except ET.ParseError:
            continue

        trovati = [
            e for e in radice.iter()
            if nome(e) == "ad"
        ]

        if trovati:
            annunci = trovati
            break


if not annunci:
    raise RuntimeError("Nessun annuncio trovato")


# GENERAZIONE ANNUNCI

risultati = []

for annuncio in annunci:

    identificativo = valore(annuncio, "id")

    if not identificativo:
        continue

    vendita = numero(
        valore(
            annuncio,
            "prices/byoperation/sale/price"
        )
    )

    affitto = numero(
        valore(
            annuncio,
            "prices/byoperation/rent/price"
        )
    )

    if vendita is not None and vendita > 0:
        operazione = "vendita"
        prezzo = vendita

    elif affitto is not None and affitto > 0:
        operazione = "affitto"
        prezzo = affitto

    else:
        operazione = ""
        prezzo = None

    descrizione_italiana = commento(annuncio)

    if not descrizione_italiana:
        print(
            "ATTENZIONE: descrizione italiana assente "
            "per immobile ID",
            identificativo
        )

    risultati.append({

        "id": identificativo,

        "localita": valore(
            annuncio,
            "property/location/name"
        ),

        "tipologia": valore(
            annuncio,
            "property/propertytype"
        ),

        "operazione": operazione,

        "prezzo": prezzo,

        "superficie": numero(
            valore(
                annuncio,
                "property/housing/propertyarea"
            )
        ),

        "camere": numero(
            valore(
                annuncio,
                "property/housing/bedroomnumber"
            )
        ),

        "bagni": numero(
            valore(
                annuncio,
                "property/housing/bathnumber"
            )
        ),

        "descrizione": descrizione_italiana,

        "immagini": immagini(annuncio)

    })


if not risultati:
    raise RuntimeError("Nessun immobile valido")


# SALVATAGGIO JSON

os.makedirs("data", exist_ok=True)

with open(
    "data/annunci.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        risultati,
        f,
        ensure_ascii=False,
        indent=2
    )


print("Annunci esportati:", len(risultati))

print(
    "Con immagini:",
    sum(bool(a["immagini"]) for a in risultati)
)

print(
    "Con prezzo:",
    sum(a["prezzo"] is not None for a in risultati)
)

print(
    "Con descrizione italiana:",
    sum(bool(a["descrizione"]) for a in risultati)
)
