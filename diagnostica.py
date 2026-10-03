import requests
from urllib.parse import quote

BASE_URL = "https://www.farmasave.it"

PRODOTTI = [
    {
        "nome": "Sun Secure Eau Solaire SPF50",
        "url": f"{BASE_URL}/sun-secure-eau-solaire-spf50.html",
        "ricerca": "Sun Secure Eau Solaire SPF50"
    },
    {
        "nome": "Supradyn Ricarica 60 compresse",
        "url": f"{BASE_URL}/supradyn-ricarica-integratore-di-vitamine-e-sali-minerali-60-compresse-rivestite.html",
        "ricerca": "Supradyn Ricarica 60 compresse"
    },
    {
        "nome": "Citoethyl 3 flaconi 15 ml",
        "url": f"{BASE_URL}/citoethyl-3fl-15ml.html",
        "ricerca": "Citoethyl"
    }
]

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"
}


def test_get(nome, url):
    print("\n" + "=" * 70)
    print(f"TEST: {nome}")
    print(f"URL:  {url}")
    print("=" * 70)

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
            allow_redirects=True
        )

        print(f"HTTP status : {r.status_code}")
        print(f"Content-Type: {r.headers.get('content-type')}")
        print(f"URL finale  : {r.url}")
        print(f"Dimensione  : {len(r.content)} byte")

        testo = r.text.lower()

        indicatori = {
            "anti-bot": [
                "verify that you're not a robot",
                "verifying you are human",
                "checking your browser",
                "captcha"
            ],
            "JSON-LD": [
                'application/ld+json'
            ],
            "schema prezzo": [
                'itemprop="price"',
                '"price"',
                '"lowprice"',
                '"highprice"'
            ]
        }

        for categoria, valori in indicatori.items():
            trovato = any(x in testo for x in valori)
            print(
                f"{categoria:<15}: "
                f"{'SI' if trovato else 'NO'}"
            )

        anteprima = " ".join(r.text[:500].split())

        print("\nAnteprima risposta:")
        print(anteprima)

    except requests.RequestException as e:
        print(f"ERRORE REQUEST: {e}")


def test_graphql():
    print("\n" + "=" * 70)
    print("TEST GRAPHQL")
    print("=" * 70)

    url = f"{BASE_URL}/graphql"

    query = """
    {
      products(
        search: "Citoethyl"
        pageSize: 5
      ) {
        total_count
        items {
          name
          sku
          price_range {
            minimum_price {
              final_price {
                value
                currency
              }
            }
          }
        }
      }
    }
    """

    try:
        r = requests.post(
            url,
            headers={
                **HEADERS,
                "Content-Type": "application/json"
            },
            json={"query": query},
            timeout=20
        )

        print(f"HTTP status : {r.status_code}")
        print(f"Content-Type: {r.headers.get('content-type')}")
        print(f"Dimensione  : {len(r.content)} byte")

        try:
            dati = r.json()

            print("\nRisposta JSON:")
            print(dati)

        except ValueError:
            print("\nLa risposta NON è JSON.")
            print(
                "Anteprima:",
                " ".join(r.text[:700].split())
            )

    except requests.RequestException as e:
        print(f"ERRORE GRAPHQL: {e}")


def main():

    print("=" * 70)
    print("       DIAGNOSTICA FARMASAVE")
    print("=" * 70)

    # 1. Homepage
    test_get(
        "Homepage",
        BASE_URL
    )

    # 2. Schede prodotto
    for prodotto in PRODOTTI:
        test_get(
            f"PRODOTTO - {prodotto['nome']}",
            prodotto["url"]
        )

    # 3. Ricerca interna Farmasave
    for prodotto in PRODOTTI:
        ricerca = quote(prodotto["ricerca"])

        test_get(
            f"RICERCA - {prodotto['nome']}",
            f"{BASE_URL}/catalogsearch/result/?q={ricerca}"
        )

    # 4. Endpoint Magento GraphQL
    test_graphql()

    print("\n" + "=" * 70)
    print("DIAGNOSTICA TERMINATA")
    print("=" * 70)


if __name__ == "__main__":
    main()
