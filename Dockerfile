FROM python:3.9

# Çalışma dizinini ayarla
WORKDIR /app

# 1. Önce dışarıdaki gereksinim dosyasını kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Her şeyi (yukleme_sistemi klasörü dahil) kopyala
COPY . .

# 3. Python'a uygulamanın nerede olduğunu söyle
# Klasörün içindeki app.py'yi çalıştırıyoruz
EXPOSE 7860
CMD ["python", "yukleme_sistemi/app.py"]