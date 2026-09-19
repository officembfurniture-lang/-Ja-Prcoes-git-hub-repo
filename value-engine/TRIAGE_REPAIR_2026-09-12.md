# HORYZONT — domknięcie naprawy selekcji i przegląd zależności

Stan badań i lokalnej walidacji: 12 września 2026, UTC. Raport dotyczy naprawy istniejącego modułu `value-engine/triage.py`. Jest zapisem przeglądu, a nie nowym kontrolerem ani kanonicznym stanem portfela. Wynik zdalnego CI dla publikowanej rewizji należy odczytać z powiązanego pull requestu.

## Wynik i decyzja

Naprawa usuwa wykazane przypadki, w których metadane wyszukiwania i słowa w adresie URL podnosiły ocenę zgłoszenia, negacja finansowania działała jak jego potwierdzenie, a późniejszy odczyt wypierał nowszą rewizję źródła. Rozróżnia też wybrane raporty z poszukiwań, cudze wnioski grantowe oraz jawne zależności wykonania. Zestaw 24 testów przechodzi lokalnie. Na pierwotnej implementacji ten sam zestaw ujawnia 16 niepowodzeń i 2 błędy; nie są to niezależne etykiety jakości ofert.

Decyzja: przekazać poprawkę do przeglądu i walidacji w istniejącym repozytorium. Nie ma podstaw do uznania wzrostu przychodu, poprawy trafności ekonomicznej ani zakończenia całego HORYZONT. Wdrożenie i akceptacja zmiany wymagają osobnych dowodów. Reguły kwalifikacji, limity uprawnień i liczniki wartości nie zostały zmienione przez tę naprawę.

## Co faktycznie zmieniło się w działającym procesie

Punktem pierwszego odczytu był commit `a8261a7cb681367dc195897d97383612154b2143`: 63 cykle i 2697 obserwacji. Kolejny odczyt, z commitu `cdf77e0849bc1b59d3703a2abbbdff44ce5bf01d`, wykazał 73 cykle i 3120 obserwacji. Ostatni zapis sensora pochodzi z 12 września 2026, 22:15:38 UTC. Pomiędzy odczytami przybyły 423 rekordy; wcześniejsze bajty pozostały dokładnym prefiksem zbioru. [Stan sensora](https://github.com/officembfurniture-lang/-Ja-Prcoes-git-hub-repo/blob/cdf77e0849bc1b59d3703a2abbbdff44ce5bf01d/value-engine/state.json)

Na obu końcach porównania `verified`, `selected`, `produced`, `delivered`, `accepted` i `paid` wynoszą zero. Kod cyklu wykonuje zebranie i normalizację obserwacji, po czym wraca do `IDLE`. To potwierdza pracę sensora, lecz nie wykonanie całego obiegu gospodarczego. Nie zmieniono tych liczników retrospektywnie na podstawie rozmowy. [Kod cyklu](https://github.com/officembfurniture-lang/-Ja-Prcoes-git-hub-repo/blob/cdf77e0849bc1b59d3703a2abbbdff44ce5bf01d/value-engine/cycle.py)

11 września podstawowy moduł triage trafił również na `main`, w commicie `466cbf311767b1a5c81a2bdb24b29893909a119c`. Odczyt 12 września potwierdził, że jego bajty odpowiadają implementacji bazowej z gałęzi eksperymentalnej. Opisana tu poprawka nadal była potrzebna. [Rewizja bazowa na main](https://github.com/officembfurniture-lang/-Ja-Prcoes-git-hub-repo/commit/466cbf311767b1a5c81a2bdb24b29893909a119c)

## Zakres naprawy

| Problem | Zachowanie po poprawce | Granica dowodu |
|---|---|---|
| Zapytanie zawierające „bounty” lub „funded” samo podnosi ocenę | Dodatnie sygnały pochodzą z tytułu i treści; zapytanie pozostaje metadanymi | Treść źródła nadal wymaga osobnej weryfikacji |
| „unfunded” zawiera ciąg „funded” | Jawna negacja finansowania prowadzi do odroczenia, bez dodatniego sygnału finansowania | Parser nie rozstrzyga wszystkich możliwych konstrukcji językowych |
| Raport z poszukiwań lub cudzy wniosek wygląda jak nasze zlecenie | Rozpoznane przypadki zachowują `HOLD_PRIMARY_SOURCE` | Ogłoszenie podobne do raportu nie jest automatycznie usuwane |
| Praca wymaga zasilonego portfela lub niespełnionych warunków | Widoczne `HOLD_CAPITAL_REQUIRED` albo `HOLD_DEPENDENCIES` | Nie założono dostępu do środków, konta ani zgody |
| Błędny lub pozbawiony strefy czasowej znacznik powoduje awarię | Data jest nieznana; poprawne daty są normalizowane do UTC | Nie odgaduje się strefy czasowej |
| Późniejszy fetch wypiera nowszą treść źródła | Pierwszeństwo ma czas rewizji źródła; remisy są deterministyczne | Czas pochodzący ze źródła nie jest dowodem prawdziwości treści |
| Równe oceny ustawiają starsze oferty przed nowszymi | Pierwszeństwo ma nowsza rewizja, potem stabilny adres URL | Świeżość nie dowodzi wartości ani dostępności oferty |

`DROP_LOW_SIGNAL` oznacza pominięcie w bieżącej kolejce triage. Surowe rekordy nie są usuwane. `QUEUE_VERIFY` nie oznacza kwalifikacji, wyboru ani zgody na wykonanie. Nadal obowiązuje sprawdzenie źródła, warunków przyjęcia, dostępności, kosztów i drogi rozliczenia. [Polityka istniejącego silnika](https://github.com/officembfurniture-lang/-Ja-Prcoes-git-hub-repo/blob/cdf77e0849bc1b59d3703a2abbbdff44ce5bf01d/value-engine/policy.json)

## Walidacja i jej ograniczenia

| Próba | Wynik |
|---|---|
| Oryginalny zestaw na oryginalnym kodzie | 8/8 testów |
| Rozszerzony zestaw na oryginalnym kodzie | 24 metody testowe; 16 niepowodzeń i 2 błędy |
| Rozszerzony zestaw na naprawionym kodzie | 24/24 testy |
| Istniejący test Omega | 1 metoda, 6 przypadków, wynik poprawny; stan HOLD zachowany |
| Lokalne próby P-0002–P-0007 | 6/6 prób działania |
| Walidatory Value Engine i Bounty Engine | Kod zakończenia 0 na zbadanych rewizjach |
| `compileall` | Poprawny dla trzech zbadanych drzew |
| `git diff --check` | Poprawny |
| Skan sześciu rodzin wzorców sekretów | 142 instancje śledzonych plików, 0 trafień; skan ograniczony, nie audyt bezpieczeństwa |
| Aplikowalność poprawki do wskazanego `main` | Poprawna; wynikowe bajty kodu i testów zgodne z walidowaną wersją |

Próby sond sprawdzają wyłącznie działanie lokalne: powtarzalność inwentarza plików, syntetyczny harmonogram, strukturalną walidację mandatu i odrzucenie manipulacji, generowanie protokołu pomiaru oraz dwa syntetyczne modele. Nie stanowią niezależnego użycia, pomiaru skutku w rzeczywistości, fizycznego transferu ani zapłaty. W szczególności projekt protokołu P-0005 nie stał się wykonanym eksperymentem.

### Porównanie na tych samych danych

| Zbiór | Rekordy wejściowe | Unikalne URL | Kolejka bazowa | Kolejka po naprawie |
|---|---:|---:|---:|---:|
| Pierwotny odczyt z 11 września | 2697 | 1627 | 386 | 219 |
| Późniejsze rekordy | 423 | 323 | 109 | 57 |
| Wcześniej niewidziane URL w późniejszym odczycie | 236 | 236 | 81 | 44 |
| Pełny odczyt z 12 września | 3120 | 1863 | 433 | 251 |

Kod został zamrożony przed próbą na późniejszych danych. Nie dostrajano na nich progów ani reguł. Sprawdzono niezmienność wyniku po podmianie zapytania wyszukiwarki dla 1627 wcześniejszych i 323 późniejszych źródeł, deterministyczność po odwróceniu wejścia oraz brak awansu etapów. W pierwotnym porównaniu wszystkie 120 istniejących odroczeń pozostało odroczeniami.

Zmniejszenie kolejki jest wynikiem mechanicznym. Bez niezależnego oznaczenia dostępnych i wartościowych ofert nie znamy zmiany precision, recall ani wartości utraconych szans. Testy regresji powstały z rozpoznanych błędów i nie są zbiorem niezależnym od projektowania poprawki. Późniejsze URL dają próbę odporności na nowe wejście, ale również nie mają etykiet jakości. Dodatkowe ograniczenie stanowi 4000 znaków zapisywanego fragmentu treści: istotny warunek może występować dalej.

## Rozliczenie wcześniejszych działań i źródła pierwotne

| Wątek | Najmocniejszy dostępny dowód | Decyzja i następna zależność |
|---|---|---|
| RustChain #13949 — badge | W repozytorium istnieje wcześniejszy commit badge; organizator zaakceptował 2 RTC dla właściwego konta | Zachować akceptację; wypłata nadal niezweryfikowana |
| Sourcey — startup credits | Odczyt strony operatora 11 września: 0/150 wolnych miejsc, zamknięte przyjmowanie zgłoszeń | Nie rozpoczynać pracy na podstawie samego otwartego issue GitHub |
| DIGITAL — screening | Oficjalny dokument naboru określa termin, finansowanie i wymagania konsorcjum | Nie utożsamiać istniejącego kandydata z gotowością do aplikowania |
| Omega — PR #1 | Dostępny test lokalny; wcześniej zapisany HOLD wymaga porównania z bazą i dowodu braku wzrostu obciążenia człowieka | Nie przedstawiać tego jako ukończonego eksperymentu ani automatycznie scalać |
| Blueprint i Portfolio Kernel | Nie uzyskano świeżych bajtów; dwie próby pobrania 11 września zakończyły się HTTP 502 | Osobna blokada dostępu; brak zmiany kanonu i brak deklaracji readbacku |

**RustChain.** Ponowny odczyt oficjalnego wątku 12 września nadal zawiera akceptację właściwego konta na 2 RTC. W przejrzanych komentarzach i korespondencji nie znaleziono nowego potwierdzenia rozliczenia tego roszczenia. Nie obliczono wartości w PLN i nie ponowiono zgłoszenia. Przyjęcie pracy i otrzymanie środków pozostają oddzielnymi zdarzeniami. [Akceptacja organizatora](https://github.com/Scottcjn/rustchain-bounties/issues/13949#issuecomment-5635850706)

**Sourcey.** Bieżąca oferta powinna być rozstrzygana na stronie przyjmującej zgłoszenia. Historyczne rozliczenia oraz otwarte issue kierujące na inną platformę nie dowodzą dostępności miejsca. Raport zachowuje datę odczytu 11 września; nie zakłada późniejszego otwarcia ani zamknięcia bez sprawdzenia. [Oferta operatora](https://gofrantic.com/bounties/120), [issue kierujące do operatora](https://github.com/sourcey/startup-credits/issues/259)

**DIGITAL.** Dokument naboru `DIGITAL-2026-AI-PILOTING-10` wskazuje 1 października 2026, 17:00 CET (Brussels). Dla screening wymaga co najmniej siedmiu niezależnych beneficjentów z pięciu uprawnionych państw, partnera przemysłowego i pięciu placówek medycznych. Poziom finansowania to 50%; wskazany budżet pojedynczego projektu sięga 4,5 mln EUR, przy 36 miesiącach realizacji. Brakuje dowodów konsorcjum, dostępu do danych, zdolności operacyjnej i wkładu finansowego właściwego aplikanta. Nie awansowano kwalifikacji ani nie wyliczono pozornego grantu. [Oficjalny dokument Komisji Europejskiej, odczyt 11 września](https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/digital/wp-call/2026/call-fiche_digital-2026-ai-piloting-10_en.pdf)

### Dlaczego najwyżej ocenione teksty nie były gotowymi zleceniami

Sprawdzono oficjalne treści kilku zgłoszeń wyłonionych przez dotychczasową selekcję. Wnioski dotyczą tych konkretnych tekstów, a nie wszystkich ofert na danych platformach.

- [Uuriko/dasha-desk #111](https://github.com/Uuriko/dasha-desk/issues/111) opisuje pracę nad produktem z niespełnionymi zależnościami. Obecność pojęcia finansowanego bounty w opisie produktu nie jest wynagrodzeniem za wykonanie tego issue.
- [stratum-praxis #141](https://github.com/stratumpraxis/stratum-praxis/issues/141) zawiera zależności portfela i płatnego dostępu. Nie potwierdzono uprawnionego źródła środków ani wykonalnej drogi rozliczenia.
- [autonomous-economic-core #8](https://github.com/engurulabory/autonomous-economic-core/issues/8) jest raportem z poszukiwań bez wybranej możliwości spełniającej warunki. Nie jest samodzielnym zleceniem dla naszego procesu.
- [ZcashCommunityGrants #398](https://github.com/ZcashCommunityGrants/zcashcommunitygrants/issues/398) jest wnioskiem innego podmiotu. Kwota wniosku i etykieta jego zatwierdzenia nie tworzą oferty dla nas.
- [copperhead #66](https://github.com/copperheadhq/copperhead/issues/66) opisuje wynagrodzenie za wymagającą walidację end-to-end. Nie rozpoczęto produkcji bez potwierdzenia aktualnej dostępności, potrzebnych środowisk, finansowania i zasad przyjęcia.

## Kolejność dalszej pracy

1. Związać zdalny wynik CI z dokładnym commitem tej poprawki i przeprowadzić przegląd różnicy. Samo przejście testów nie dowodzi wdrożenia.
2. Zrealizować kwalifikację jednej nadal dostępnej możliwości na pełnym źródle pierwotnym, z osobnym dowodem finansowania, przyjęcia, dostarczenia i rozliczenia. Brak którejkolwiek zależności daje precyzyjne odroczenie tej możliwości, nie blokadę całego portfela.
3. Dla wcześniej zaakceptowanego badge sprawdzić dostępny, autoryzowany dowód rozliczenia. Do czasu jego uzyskania zachować „zaakceptowane”, a nie „zapłacone”.
4. Odtworzyć dostęp do tych samych dwóch artefaktów kanonicznych. Dopiero na świeżych bajtach wykonać SHA-256, kontrolę wersji i proweniencji, `autonomy-plan`, pełne testy kanonu, `verify-chain`, `state-audit` i ewentualny zapis z exact-byte readbackiem. Nie zastępować ich lokalnymi kopiami ani tym raportem.
5. Osobno ocenić zaległy eksperyment Omega i cztery protokoły mechanizmów. Lokalny test działania nie zamyka bramki dowodu eksperymentalnego. [Warunki przeglądu Omega](https://github.com/officembfurniture-lang/-Ja-Prcoes-git-hub-repo/issues/2)

Zakres tego przeglądu był celowany: naprawa, rozliczenie wcześniejszego działania i weryfikacja wybranych zależności. Nie deklaruje pełnego, świeżego skanu siedmiu osi portfela przy niedostępnym kanonie.

## Możliwość zachowana poza oceną pieniężną

Hipoteza do zachowania: skrócenie pracy potrzebnej do odtworzenia kontekstu i sprawdzenia pochodzenia wyniku może stanowić samodzielną wartość procesu. Ten pakiet daje materiał do jej pomiaru, lecz nie potwierdza oszczędności czasu. Kolejna próba powinna mierzyć liczbę ręcznych kroków i czas niezależnego odtworzenia wyniku, przy tym samym kryterium poprawności. Nie przypisano cen, zainteresowania, użycia ani rezultatu. Niska ocena pieniężna lub brak danych nie powodują usunięcia tej hipotezy.

## Proweniencja techniczna

| Element | SHA-256 / rewizja |
|---|---|
| Baza gałęzi eksperymentalnej | `bb49d5f88ed78ddd7bf3022ea5255003f7fe8558` |
| Baza porównania z `main` | `cdf77e0849bc1b59d3703a2abbbdff44ce5bf01d` |
| Bazowy `triage.py` | `05ea8915a39545e86a93d6aa632f175bdceb8ce9e685754c27a68c36108c3de9` |
| Naprawiony `triage.py` | `be42622c408e5555ac10f84edf81e0772ccdd5b8e590fd1782543d389b1ba83e` |
| Rozszerzony `test_triage.py` | `0b0d30416485aa7b5c085350c2d522cc3830bd350bf575f4b1e69b2b9b20116b` |
| Pierwotne obserwacje | `5bdef4291215676501d6dfdc907c20f11aee914b2c966750a3943d00baa3df4b` |
| Pełne obserwacje z późniejszego odczytu | `0348e4b102ca4d8825f63f1ffc8dcc69a268b8be3a747171d060e4c237a853c4` |
| Wyłącznie późniejsze rekordy | `40ed48229ba754d8e26f16451d792f74532e73faf347853a65dff454db0af1f1` |

Maszynowy skrót wyników znajduje się obok, w `triage-repair-evidence-2026-09-12.json`. Wynik można odtworzyć przez `python3 -m unittest -v test_triage.py` w `value-engine` oraz dwa uruchomienia `triage.py` na tym samym zbiorze: bazowe i po poprawce. Należy porównywać `verify_queue_total`, nie ograniczoną do 50 liczbę wyemitowanych wierszy.
