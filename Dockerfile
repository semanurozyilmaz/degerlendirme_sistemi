# 1. Aşama: Hafif bir Python imajı
FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
# 2. Aşama: C Derleyicisi kurulumu (Mac'ten bağımsız çalışması için)
RUN apt-get update && apt-get install -y gcc build-essential

# 3. Aşama: Çalışma dizini oluştur ve içine gir
WORKDIR /app

# 4. Aşama: Önce klasör içindeki gereksinimleri kopyala ve kur
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Aşama: yukleyici_sistemi klasörünün içindeki her şeyi /app içine kopyala
# Bu satır kritik! Klasörün kendisini değil, İÇİNDEKİLERİ kopyalıyoruz.
COPY yukleme_sistemi/ .

# 6. Aşama: Dosyalar gerçekten geldi mi diye kontrol amaçlı listeletme (Loglarda görürsün)
RUN ls -la /app

# 7. Aşama: Flask portunu aç
EXPOSE 5000

# 8. Aşama: Uygulamayı çalıştır (Artık dosya doğrudan /app/app.py oldu)
CMD ["python", "app.py"]