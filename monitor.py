import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


FILE_PRODOTTI = "prodotti.json"

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
BREVO_SENDER = os.environ.get("BREVO_SENDER")


def carica_prodotti():
    """Carica l'elenco dei prodotti dal file JSON."""
    try:
        with open(FILE_PRODOTTI, "r", encoding="utf-8") as file:
            prodotti = json.load(file)

        if not isinstance(prodotti, list):
            raise ValueError("prodotti.json deve contenere una lista.")

        return prodotti

    except (OSError, json.JSONDecodeError, ValueError) as errore:
        print(f"ERRORE durante la lettura di {FILE_PRODOTTI}: {errore}")
        sys.exit(1)


def converti_prezzo(valore):
    """
    Converte prezzi come:
    14,79 €
    € 14,79
    14.79
    in Decimal('14.79').
    """
    if valore is None:
        return None

    testo = str(valore).strip()

    match = re.search(r"(\d{1,4}[.,]\d{2})", testo)

    if not match:
        return None

    numero = match.group(1).replace(",", ".")

    try:
        return Decimal(numero)
    except InvalidOperation:
        return None


def rileva_prezzo(page, prodotto):
    """Apre la pagina del prodotto e cerca il prezzo."""

    nome = prodotto["nome"]
    url = prodotto["url"]

    print(f"\nControllo: {nome}")
    print(f"URL: {url}")

    try:
        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45000
        )

        if response is None:
            print("ERRORE: nessuna risposta HTTP.")
            return None

        print(f"HTTP status: {response.status}")

        # Attendiamo che eventuale JavaScript della pagina venga eseguito.
        page.wait_for_timeout(5000)

        contenuto = page.content()

        # Individuazione esplicita di una possibile pagina anti-bot.
        indicatori_antibot = [
            "verify you are not a robot",
            "verifying you are human",
            "enable javascript",
            "checking your browser",
            "captcha"
        ]

        contenuto_lower = contenuto.lower()

        for indicatore in indicatori_antibot:
            if indicatore in contenuto_lower:
                print(
                    "ERRORE: Farmasave ha restituito "
                    "una pagina di verifica/anti-bot."
                )
                return None

        # Prima strategia:
        # meta tag comunemente utilizzati dai siti e-commerce.
        selettori = [
            'meta[property="product:price:amount"]',
            'meta[itemprop="price"]',
            '[itemprop="price"]',
            '.price'
        ]

        for selettore in selettori:
            elementi = page.locator(selettore)

            try:
                numero_elementi = elementi.count()
            except Exception:
                continue

            for i in range(min(numero_elementi, 10)):
                elemento = elementi.nth(i)

                valore = elemento.get_attribute("content")

                if not valore:
                    try:
                        valore = elemento.inner_text(timeout=2000)
                    except Exception:
                        continue

                prezzo = converti_prezzo(valore)

                if prezzo is not None:
                    print(
                        f"Prezzo individuato con '{selettore}': "
                        f"{prezzo:.2f} €"
                    )
                    return prezzo

        print("ERRORE: nessun prezzo attendibile individuato.")
        return None

    except PlaywrightTimeoutError:
        print("ERRORE: timeout durante il caricamento della pagina.")
        return None

    except Exception as errore:
        print(f"ERRORE durante il controllo della pagina: {errore}")
        return None


def recupera_destinatari(prodotto):
    """
    Traduce i nomi presenti in prodotti.json:
    ALERT_EMAIL_1, ALERT_EMAIL_2...
    nei veri indirizzi conservati nei Secrets.
    """

    destinatari = []

    for nome_secret in prodotto.get("destinatari", []):
        email = os.environ.get(nome_secret)

        if not email:
            print(
                f"ATTENZIONE: la variabile {nome_secret} "
                "non è disponibile."
            )
            continue

        destinatari.append(email)

    return destinatari


def invia_alert(prodotto, prezzo, destinatari):
    """Invia l'alert tramite API Brevo."""

    if not BREVO_API_KEY:
        print("ERRORE: BREVO_API_KEY non disponibile.")
        return False

    if not BREVO_SENDER:
        print("ERRORE: BREVO_SENDER non disponibile.")
        return False

    if not destinatari:
        print("ERRORE: nessun destinatario configurato.")
        return False

    soglia = Decimal(str(prodotto["soglia"]))

    destinatari_brevo = [
        {"email": email}
        for email in destinatari
    ]

    subject = (
        f"Price Monitor - {prodotto['nome']} "
        f"a {prezzo:.2f} €"
    )

    testo = f"""
ALERT PREZZO

Prodotto:
{prodotto['nome']}

Prezzo rilevato:
{prezzo:.2f} €

Soglia impostata:
{ soglia:.2f} €

Il prezzo è sceso sotto la soglia impostata.

Link al prodotto:
{prodotto['url']}
""".strip()

    payload = {
        "sender": {
            "name": "Price Monitor",
            "email": BREVO_SENDER
        },
        "to": destinatari_brevo,
        "subject": subject,
        "textContent": testo
    }

    try:
        risposta = requests.post(
            BREVO_API_URL,
            headers={
                "accept": "application/json",
                "api-key": BREVO_API_KEY,
                "content-type": "application/json"
            },
            json=payload,
            timeout=30
        )

        if risposta.status_code in (200, 201, 202):
            print("EMAIL DI ALERT INVIATA.")
            return True

        print(
            f"ERRORE BREVO: HTTP {risposta.status_code} - "
            f"{risposta.text}"
        )
        return False

    except requests.RequestException as errore:
        print(f"ERRORE durante l'invio dell'email: {errore}")
        return False


def main():

    prodotti = carica_prodotti()

    print("======================================")
    print("        PRICE MONITOR")
    print("======================================")
    print(f"Prodotti da controllare: {len(prodotti)}")

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        context = browser.new_context(
    locale="it-IT"
    )

        page = context.new_page()

        for prodotto in prodotti:

            try:
                soglia = Decimal(str(prodotto["soglia"]))
            except (KeyError, InvalidOperation):
                print(
                    f"\nERRORE: soglia non valida per "
                    f"{prodotto.get('nome', 'prodotto sconosciuto')}."
                )
                continue

            prezzo = rileva_prezzo(page, prodotto)

            if prezzo is None:
                print("Controllo non concluso: nessun alert inviato.")
                continue

            print(f"Soglia: {soglia:.2f} €")

            if prezzo < soglia:

                print("PREZZO SOTTO SOGLIA!")

                destinatari = recupera_destinatari(prodotto)

                invia_alert(
                    prodotto,
                    prezzo,
                    destinatari
                )

            else:
                print("Prezzo non inferiore alla soglia.")

        context.close()
        browser.close()

    print("\n======================================")
    print("Controllo terminato.")
    print("======================================")


if __name__ == "__main__":
    main()
