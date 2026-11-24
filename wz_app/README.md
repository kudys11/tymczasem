# WZ – aplikacja do wystawiania i archiwizacji dokumentów

## Funkcje wersji startowej
- aplikacja WWW w języku polskim;
- baza odbiorców i materiałów;
- wystawianie WZ z dowolną liczbą pozycji;
- numeracja roczna: `WZ/001/2026`;
- archiwum z wyszukiwaniem po numerze, odbiorcy i dacie;
- podgląd i ponowne pobieranie PDF;
- dokument PDF zawiera oryginał i kopię na jednej stronie A4;
- brak gospodarki stanami magazynowymi.

## Uruchomienie na Debianie
1. Skopiuj katalog projektu na serwer, np. do `/opt/docker/wz`.
2. `cp .env.example .env`
3. `docker compose up -d --build`
4. Otwórz `http://ADRES_SERWERA:8457`

Dane SQLite są przechowywane w wolumenie Docker `wz_data` i przetrwają odtworzenie kontenera.

## Ważne
To wersja MVP do testów. Przed wdrożeniem produkcyjnym należy dodać logowanie użytkowników, role/uprawnienia, kopie zapasowe bazy oraz testy procesu numerowania dokumentów przy równoczesnym wystawianiu.
