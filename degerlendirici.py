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

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": os.getenv("CONTENT")
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
                {os.getenv("RESPONSE_FORMAT")}
                """
            }
        ],
        temperature=0.1,
    )

    return completion.choices[0].message.content
