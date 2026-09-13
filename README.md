# Study — Çift Motivasyonlu Ders Uygulaması

Flask + SQLite, hafif server dostu.

## Yapı
```
study/
  app/            -> Flask uygulaması (git ile sunucuya çekilen kısım)
    app.py
    templates/
    static/
    requirements.txt
  logs/           -> nginx + gunicorn logları (sunucuda dolar)
  nginx.conf      -> bu projeye özel nginx bloğu (çakışmasız port/domain ile oluşturulacak)
```

## Lokal çalıştır
```bash
cd study/app
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py
# http://127.0.0.1:5001
```

## Sunucu (özet)
```bash
git clone https://github.com/drFurkanGuven/Study.git study
cd study/app
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt gunicorn
# systemd + nginx (nginx.conf bu repoda, port/domain çakışmasız)
```
