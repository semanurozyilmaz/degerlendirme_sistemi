import requests
import os
import time

# --- AYARLAR ---
TARGET_URL = "https://buubm-lab.hf.space/yukle" 
FILE_NAME = "odev.c" 
OGRENCI_SAYISI = 20    # Toplam kaç öğrenci gönderilecek
BEKLEME_SURESI = 6     # Her istek arası 6 saniye (6 * 10 = 60 saniye / 1 dakika)
AKTIF_ODEV_ID = 1      # Panelden kontrol ettiğin doğru ID

def safe_upload():
    if not os.path.exists(FILE_NAME):
        print(f"❌ {FILE_NAME} bulunamadı.")
        return

    print(f"🚀 Güvenli test başlatılıyor: Dakikada ~10 istek hızıyla...")
    
    for i in range(1, OGRENCI_SAYISI + 1):
        payload = {
            'ad': f'Guvenli Bot {i}',
            'no': f'2026{i:04d}',
            'odev_id': str(AKTIF_ODEV_ID)
        }

        try:
            with open(FILE_NAME, 'rb') as f:
                files = {'dosya': (FILE_NAME, f, 'text/x-csrc')}
                
                start_time = time.time()
                # allow_redirects=False: Başarılı kayıtta 302 döner
                response = requests.post(TARGET_URL, data=payload, files=files, allow_redirects=False)
                end_time = time.time()
                
                if response.status_code == 302:
                    print(f"✅ [{i}/{OGRENCI_SAYISI}] Başarılı! (İşlem: {end_time-start_time:.2f} sn)")
                else:
                    print(f"⚠️ [{i}/{OGRENCI_SAYISI}] Beklenmeyen yanıt: {response.status_code}")
                
        except Exception as e:
            print(f"❌ [{i}/{OGRENCI_SAYISI}] Bağlantı hatası: {e}")

        # Bir sonraki istek öncesi zorunlu bekleme
        if i < OGRENCI_SAYISI:
            print(f"☕ {BEKLEME_SURESI} saniye bekleniyor...")
            time.sleep(BEKLEME_SURESI)

    print("\n🏁 Güvenli test tamamlandı.")

if __name__ == "__main__":
    safe_upload()