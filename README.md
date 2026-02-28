F1 LIVE DASHBOARD
========================================================================

KROK 1: PŘÍPRAVA (jen poprvé)
cd c:\Users\matej\Desktop\APP\wa\f7\f1-live-dashboard
pip install -r requirements.txt
python manage.py migrate


KROK 2: SPUSTIT SERVER (Terminal 1)
cd c: f1-live-dashboard
python manage.py runserver

Server běží na: http://127.0.0.1:8000/


KROK 3: SPUSTIT LIVE RACE (Terminal 2)
cd c:\Users\matej\Desktop\APP\wa\f7\f1-live-dashboard
python manage.py live_race --interval 3

Fetchuje live data z OpenF1 API každých 3 sekund.


OVĚŘENÍ V PROHLÍŽEČI
Otevřít: http://127.0.0.1:8000


ZASTAVENÍ
Terminal 1: Ctrl+C (server)
Terminal 2: Ctrl+C (live_race)
