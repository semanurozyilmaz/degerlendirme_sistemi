from groq import Groq
import os

# 1. Ayarlar: Groq API Anahtarını buraya gir
client = Groq(os.environ.get("GROQ"))

def ai_ile_puanla_groq(dosya_yolu, odev_tanimi, kriterler):
    # C dosyasını oku
    try:
        with open(dosya_yolu, 'r', encoding='utf-8') as f:
            ogrenci_kodu = f.read()
    except FileNotFoundError:
        return "Hata: C dosyası bulunamadı!"

    # Groq üzerinden Llama 3 70B modelini kullanıyoruz (Zeki ve ücretsiz kotası geniştir)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "Sen titiz bir bilgisayar mühendisliği hocasısın. Kodun hem çalışabilirliğini hem de yapısal kalitesini değerlendirirsin."
            },
            {
                "role": "user",
                "content": f"""
                ÖDEV TANIMI: {odev_tanimi}
                PUANLAMA KRİTERLERİ: {kriterler}
                
                ÖĞRENCİ KODU:
                ```c
                {ogrenci_kodu}
                ```
                
                Lütfen şu formatta cevap ver:
                - TOPLAM PUAN: (0-100 arası bir sayı)
                - KRİTER DEĞERLENDİRMESİ: (Madde madde puan dağılımı)
                - ÖNERİLER: (Öğrenci neyi daha iyi yapabilirdi?)
                """
            }
        ],
        temperature=0.1, # Daha tutarlı ve ciddi cevaplar için düşük sıcaklık
    )

    return completion.choices[0].message.content

# --- TEST KISMI ---
odev = "Girilen 10 sayının ortalamasını alan C kodu."
kriter = "Dizi kullanımı (40p), Döngü (30p), Doğru hesaplama (30p)"
dosya = "odev.c"

print("--- GROQ İLE DEĞERLENDİRME BAŞLIYOR ---")
sonuc = ai_ile_puanla_groq(dosya, odev, kriter)
print(sonuc)