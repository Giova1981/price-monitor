import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation

import requests


# ============================================================
# CONFIGURAZIONE
# ============================================================

FILE_PRODOTTI = "prodotti.json"
FILE_STATO = "stato.json"

TINYFISH_URL = "https://api.fetch.tinyfish.ai"
BREVO_URL = "https://api.brevo.com/v3/smtp/email"

# Dopo quanti controlli consecutivi falliti viene inviata
# una notifica di errore.
MAX_ERRORI_CONSECUTIVI = 3


# ============================================================
# GESTIONE FILE JSON
# ============================================================

def carica_json(percorso, default=None):
    try:
        with open(percorso, "r", encoding="utf-8") as file:
            return json.load(file)

    except FileNotFoundError:
        return default

    except json.JSONDecodeError as errore:
        print(
            f"ERRORE: {percorso} contiene JSON non valido: "
            f"{errore}"
        )
        sys.exit(1)


def salva_stato(stato):
    with open(FILE_STATO, "w", encoding="utf-8") as file:
        json.dump(
            stato,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# FUNZIONI PREZZI
# ============================================================

def euro(valore):
    return (
        f"{Decimal(str(valore)):.2f}"
        .replace(".", ",")
        + " €"
    )


def estrai_prezzo_farmasave(testo):
    """
    Cerca esclusivamente il prezzo associato alla dicitura
    'Prezzo Farmasave'.

    In questo modo vengono ignorati:
    - prezzo di listino;
    - prezzo più basso degli ultimi 30 giorni;
    - prezzi di eventuali prodotti correlati.
    """

    pattern = (
        r"Prezzo\s+Farmasave"
        r"[\s*:#\-]*"
        r"(\d{1,4}[.,]\d{2})\s*€"
    )

    match = re.search(
        pattern,
        testo,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    valore = match.group(1).replace(",", ".")

    try:
        prezzo = Decimal(valore)

        if prezzo <= 0:
            return None

        return prezzo

    except InvalidOperation:
        return None


# ============================================================
# TINYFISH
# ============================================================

def recupera_pagine_tinyfish(prodotti):
    api_key = os.environ.get("TINYFISH_API_KEY")

    if not api_key:
        raise RuntimeError(
            "TINYFISH_API_KEY non configurata."
        )

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }

    payload = {
        "urls": [
            prodotto["url"]
            for prodotto in prodotti
        ],
        "format": "markdown"
    }

    risposta = requests.post(
        TINYFISH_URL,
        headers=headers,
        json=payload,
        timeout=120
    )

    risposta.raise_for_status()

    dati = risposta.json()

    pagine = {}

    for pagina in dati.get("results", []):
        url = pagina.get("url")

        if url:
            pagine[url] = pagina

    errori = {}

    for errore in dati.get("errors", []):
        url = errore.get("url")

        if url:
            errori[url] = errore

    return pagine, errori


# ============================================================
# DESTINATARI EMAIL
# ============================================================

def recupera_destinatari(prodotto):
    destinatari = []

    for nome_secret in prodotto.get(
        "destinatari",
        []
    ):
        email = os.environ.get(nome_secret)

        if email:
            destinatari.append({
                "email": email
            })

        else:
            print(
                f"ATTENZIONE: Secret {nome_secret} "
                f"non disponibile."
            )

    return destinatari


# ============================================================
# INVIO EMAIL CON BREVO
# ============================================================

def invia_email(prodotto, oggetto, messaggio):
    api_key = os.environ.get("BREVO_API_KEY")
    mittente = os.environ.get("BREVO_SENDER")

    if not api_key or not mittente:
        print(
            "ERRORE: configurazione Brevo incompleta."
        )
        return False

    destinatari = recupera_destinatari(prodotto)

    if not destinatari:
        print(
            f"ERRORE: nessun destinatario disponibile "
            f"per {prodotto['nome']}."
        )
        return False

    payload = {
        "sender": {
            "name": "Price Monitor",
            "email": mittente
        },
        "to": destinatari,
        "subject": oggetto,
        "textContent": messaggio
    }

    try:
        risposta = requests.post(
            BREVO_URL,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )

        risposta.raise_for_status()

        print("Email inviata correttamente.")

        return True

    except requests.RequestException as errore:
        print(
            f"ERRORE invio email: {errore}"
        )

        return False


# ============================================================
# EMAIL: PREZZO SOTTO SOGLIA
# ============================================================

def email_sotto_soglia(
    prodotto,
    prezzo,
    ulteriore=False
):
    soglia = Decimal(
        str(prodotto["soglia"])
    )

    if ulteriore:
        oggetto = (
            f"📉 Nuovo ribasso: "
            f"{prodotto['nome']} "
            f"a {euro(prezzo)}"
        )

        apertura = (
            "Il prodotto è sceso ulteriormente "
            "di prezzo mentre si trova sotto "
            "la soglia impostata."
        )

    else:
        oggetto = (
            f"🔔 Prezzo sotto soglia: "
            f"{prodotto['nome']} "
            f"a {euro(prezzo)}"
        )

        apertura = (
            "Il prezzo del prodotto è sceso "
            "sotto la soglia impostata."
        )

    messaggio = f"""PRICE MONITOR

{apertura}

Prodotto:
{prodotto['nome']}

Prezzo Farmasave:
{euro(prezzo)}

Soglia:
{euro(soglia)}

Pagina Farmasave:
{prodotto['url']}
"""

    return invia_email(
        prodotto,
        oggetto,
        messaggio
    )


# ============================================================
# EMAIL: PREZZO TORNATO SOPRA SOGLIA
# ============================================================

def email_ritorno_sopra_soglia(
    prodotto,
    prezzo
):
    soglia = Decimal(
        str(prodotto["soglia"])
    )

    oggetto = (
        f"↗️ Prezzo tornato sopra soglia: "
        f"{prodotto['nome']}"
    )

    messaggio = f"""PRICE MONITOR

Il prezzo del prodotto non è più sotto
la soglia impostata.

Prodotto:
{prodotto['nome']}

Prezzo Farmasave:
{euro(prezzo)}

Soglia:
{euro(soglia)}

Non riceverai altre notifiche di questo tipo
finché il prodotto non scenderà nuovamente
sotto soglia.

Pagina Farmasave:
{prodotto['url']}
"""

    return invia_email(
        prodotto,
        oggetto,
        messaggio
    )


# ============================================================
# EMAIL: ERRORE PERSISTENTE
# ============================================================

def email_errore(prodotto):
    oggetto = (
        f"⚠️ Price Monitor: problema con "
        f"{prodotto['nome']}"
    )

    messaggio = f"""PRICE MONITOR

Non è stato possibile controllare correttamente
questo prodotto per {MAX_ERRORI_CONSECUTIVI}
esecuzioni consecutive.

Prodotto:
{prodotto['nome']}

Pagina Farmasave:
{prodotto['url']}

Il monitor continuerà automaticamente a tentare
i controlli successivi.

Non verranno inviati altri avvisi di errore
finché il controllo non tornerà a funzionare.
"""

    return invia_email(
        prodotto,
        oggetto,
        messaggio
    )


# ============================================================
# CREAZIONE STATO NUOVO PRODOTTO
# ============================================================

def nuovo_stato(soglia):
    return {
        "stato": None,
        "ultimo_prezzo": None,
        "minimo_notificato": None,
        "soglia": float(soglia),
        "errori_consecutivi": 0,
        "errore_notificato": False
    }


# ============================================================
# GESTIONE ERRORI
# ============================================================

def registra_errore(
    prodotto,
    stato_prodotto
):
    stato_prodotto[
        "errori_consecutivi"
    ] += 1

    print(
        "Errori consecutivi:",
        stato_prodotto[
            "errori_consecutivi"
        ]
    )

    if (
        stato_prodotto[
            "errori_consecutivi"
        ] >= MAX_ERRORI_CONSECUTIVI
        and not stato_prodotto[
            "errore_notificato"
        ]
    ):
        if email_errore(prodotto):
            stato_prodotto[
                "errore_notificato"
            ] = True


# ============================================================
# ELABORAZIONE SINGOLO PRODOTTO
# ============================================================

def processa_prodotto(
    prodotto,
    pagina,
    stato_prodotto
):
    soglia = Decimal(
        str(prodotto["soglia"])
    )

    testo = pagina.get(
        "text",
        ""
    )

    prezzo = estrai_prezzo_farmasave(
        testo
    )

    if prezzo is None:
        print(
            "ERRORE: Prezzo Farmasave "
            "non individuato."
        )

        registra_errore(
            prodotto,
            stato_prodotto
        )

        return

    titolo = pagina.get(
        "title",
        ""
    )

    print(
        f"Titolo pagina: {titolo}"
    )

    print(
        f"Prezzo Farmasave: "
        f"{euro(prezzo)}"
    )

    print(
        f"Soglia: {euro(soglia)}"
    )

    # Il controllo è riuscito:
    # azzeriamo eventuali errori precedenti.
    stato_prodotto[
        "errori_consecutivi"
    ] = 0

    stato_prodotto[
        "errore_notificato"
    ] = False

    soglia_precedente = Decimal(
        str(
            stato_prodotto.get(
                "soglia",
                soglia
            )
        )
    )

    # --------------------------------------------------------
    # SOGLIA MODIFICATA DALL'UTENTE
    # --------------------------------------------------------

    if soglia != soglia_precedente:
        print(
            "Soglia modificata: "
            f"{euro(soglia_precedente)} "
            f"-> {euro(soglia)}"
        )

        stato_prodotto[
            "soglia"
        ] = float(soglia)

        stato_prodotto[
            "ultimo_prezzo"
        ] = float(prezzo)

        if prezzo < soglia:
            stato_prodotto[
                "stato"
            ] = "sotto"

            stato_prodotto[
                "minimo_notificato"
            ] = float(prezzo)

        else:
            stato_prodotto[
                "stato"
            ] = "sopra"

            stato_prodotto[
                "minimo_notificato"
            ] = None

        print(
            "Stato riallineato alla nuova soglia. "
            "Nessuna email inviata."
        )

        return

    stato_precedente = stato_prodotto.get(
        "stato"
    )

    # --------------------------------------------------------
    # PRIMA RILEVAZIONE DI UN NUOVO PRODOTTO
    # --------------------------------------------------------

    if stato_precedente is None:

        stato_prodotto[
            "ultimo_prezzo"
        ] = float(prezzo)

        stato_prodotto[
            "soglia"
        ] = float(soglia)

        # Nuovo prodotto già sotto soglia:
        # deve essere notificato immediatamente.
        if prezzo < soglia:

            print(
                "Nuovo prodotto già sotto soglia: "
                "invio alert iniziale."
            )

            if email_sotto_soglia(
                prodotto,
                prezzo,
                ulteriore=False
            ):
                stato_prodotto[
                    "stato"
                ] = "sotto"

                stato_prodotto[
                    "minimo_notificato"
                ] = float(prezzo)

            else:
                # Se l'email fallisce NON consideriamo
                # il prodotto notificato.
                # Al prossimo controllo verrà ritentato.
                stato_prodotto[
                    "stato"
                ] = None

                stato_prodotto[
                    "minimo_notificato"
                ] = None

        else:

            stato_prodotto[
                "stato"
            ] = "sopra"

            stato_prodotto[
                "minimo_notificato"
            ] = None

            print(
                "Prima rilevazione: "
                "prodotto sopra soglia. "
                "Nessuna email necessaria."
            )

        return

    # --------------------------------------------------------
    # PRODOTTO ATTUALMENTE SOTTO SOGLIA
    # --------------------------------------------------------

    if prezzo < soglia:

        # Prima era sopra soglia:
        # inviamo l'alert.
        if stato_precedente == "sopra":

            print(
                "Il prezzo è sceso sotto soglia."
            )

            if email_sotto_soglia(
                prodotto,
                prezzo,
                ulteriore=False
            ):
                stato_prodotto[
                    "stato"
                ] = "sotto"

                stato_prodotto[
                    "minimo_notificato"
                ] = float(prezzo)

        # Era già sotto soglia.
        else:

            minimo = stato_prodotto.get(
                "minimo_notificato"
            )

            # Se per qualche motivo non esiste ancora
            # un minimo notificato, consideriamo il prezzo
            # corrente come candidato alla notifica.
            if minimo is None:

                print(
                    "Prodotto sotto soglia ma "
                    "senza precedente prezzo notificato."
                )

                if email_sotto_soglia(
                    prodotto,
                    prezzo,
                    ulteriore=False
                ):
                    stato_prodotto[
                        "minimo_notificato"
                    ] = float(prezzo)

            # Nuovo minimo sotto soglia:
            # inviamo una nuova email.
            elif prezzo < Decimal(
                str(minimo)
            ):

                print(
                    "Nuovo minimo rilevato "
                    "sotto soglia."
                )

                if email_sotto_soglia(
                    prodotto,
                    prezzo,
                    ulteriore=True
                ):
                    stato_prodotto[
                        "minimo_notificato"
                    ] = float(prezzo)

            else:

                print(
                    "Prodotto ancora sotto soglia, "
                    "ma nessun nuovo minimo. "
                    "Nessuna email."
                )

    # --------------------------------------------------------
    # PRODOTTO ATTUALMENTE SOPRA SOGLIA
    # --------------------------------------------------------

    else:

        # Prima era sotto soglia:
        # inviamo una sola email di rientro.
        if stato_precedente == "sotto":

            print(
                "Il prezzo è tornato sopra soglia."
            )

            if email_ritorno_sopra_soglia(
                prodotto,
                prezzo
            ):
                stato_prodotto[
                    "stato"
                ] = "sopra"

                stato_prodotto[
                    "minimo_notificato"
                ] = None

        else:

            stato_prodotto[
                "stato"
            ] = "sopra"

            print(
                "Prodotto sopra soglia. "
                "Nessuna email."
            )

    # Salviamo sempre l'ultimo prezzo
    # rilevato correttamente.
    stato_prodotto[
        "ultimo_prezzo"
    ] = float(prezzo)

    stato_prodotto[
        "soglia"
    ] = float(soglia)


# ============================================================
# PROGRAMMA PRINCIPALE
# ============================================================

def main():

    print("=" * 70)
    print("PRICE MONITOR FARMASAVE")
    print("=" * 70)

    prodotti = carica_json(
        FILE_PRODOTTI
    )

    if not prodotti:
        print(
            "ERRORE: nessun prodotto configurato."
        )
        sys.exit(1)

    # --------------------------------------------------------
    # CONTROLLO ID
    # --------------------------------------------------------

    ids = [
        prodotto.get("id")
        for prodotto in prodotti
    ]

    if (
        None in ids
        or len(ids) != len(set(ids))
    ):
        print(
            "ERRORE: ogni prodotto deve avere "
            "un ID univoco."
        )
        sys.exit(1)

    # --------------------------------------------------------
    # CARICAMENTO STATO
    # --------------------------------------------------------

    stato = carica_json(
        FILE_STATO,
        default={}
    )

    # --------------------------------------------------------
    # ELIMINA DALLO STATO I PRODOTTI RIMOSSI
    # DA prodotti.json
    # --------------------------------------------------------

    ids_attivi = set(ids)

    for id_vecchio in list(
        stato.keys()
    ):
        if id_vecchio not in ids_attivi:

            print(
                "Rimuovo dallo stato prodotto "
                "non più configurato: "
                f"{id_vecchio}"
            )

            del stato[id_vecchio]

    # --------------------------------------------------------
    # CREA AUTOMATICAMENTE LO STATO
    # PER I NUOVI PRODOTTI
    # --------------------------------------------------------

    for prodotto in prodotti:

        prodotto_id = prodotto["id"]

        if prodotto_id not in stato:

            print(
                "Nuovo prodotto rilevato: "
                f"{prodotto['nome']}"
            )

            stato[
                prodotto_id
            ] = nuovo_stato(
                prodotto["soglia"]
            )

    # --------------------------------------------------------
    # RECUPERO PAGINE CON TINYFISH
    # --------------------------------------------------------

    try:

        pagine, errori = (
            recupera_pagine_tinyfish(
                prodotti
            )
        )

    except Exception as errore:

        print(
            "ERRORE TinyFish generale: "
            f"{errore}"
        )

        for prodotto in prodotti:

            registra_errore(
                prodotto,
                stato[
                    prodotto["id"]
                ]
            )

        salva_stato(stato)

        sys.exit(1)

    # --------------------------------------------------------
    # ELABORAZIONE PRODOTTI
    # --------------------------------------------------------

    for prodotto in prodotti:

        print(
            "\n" + "-" * 70
        )

        print(
            f"Controllo: "
            f"{prodotto['nome']}"
        )

        print(
            f"ID: {prodotto['id']}"
        )

        print(
            f"URL: {prodotto['url']}"
        )

        stato_prodotto = stato[
            prodotto["id"]
        ]

        pagina = pagine.get(
            prodotto["url"]
        )

        if pagina is None:

            print(
                "ERRORE: TinyFish non ha "
                "restituito la pagina."
            )

            if prodotto["url"] in errori:

                print(
                    "Dettaglio TinyFish:",
                    errori[
                        prodotto["url"]
                    ]
                )

            registra_errore(
                prodotto,
                stato_prodotto
            )

            continue

        processa_prodotto(
            prodotto,
            pagina,
            stato_prodotto
        )

    # --------------------------------------------------------
    # SALVATAGGIO STATO
    # --------------------------------------------------------

    salva_stato(stato)

    print(
        "\n" + "=" * 70
    )

    print(
        "CONTROLLO TERMINATO"
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":
    main()
