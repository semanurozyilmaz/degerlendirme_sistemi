from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from groq import Groq
import re
import subprocess
import os
import json
import stat
from dotenv import load_dotenv

app = Flask(__name__,template_folder='templates',
            static_folder='static')
load_dotenv()
app.secret_key = os.getenv("SECRET_KEY")
database_url = os.getenv("DATABASE_URL")
API = os.getenv("GROQ")
default_key = os.getenv("DEFAULT_YETKILI_SIFRE")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///local.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
with app.app_context():
    db.create_all()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('yetkili_giris'):
            flash("Lütfen önce giriş yapın!", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- VERİTABANI MODELİ ---
class Odev(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    baslik = db.Column(db.String(200), nullable=False)
    tanim = db.Column(db.Text, nullable=False)
    kriterler = db.Column(db.Text, nullable=False) # AI'ya gidecek kriterler
    is_active = db.Column(db.Boolean, default=True) # Öğrenci görsün mü?
    teslimler = db.relationship('OdevTeslim', backref='odev_tanimi', lazy=True)

class OdevTeslim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    odev_id = db.Column(db.Integer, db.ForeignKey('odev.id')) # Hangi ödevin teslimi?
    ogrenci_ad = db.Column(db.String(100))
    ogrenci_no = db.Column(db.String(20))
    puan = db.Column(db.Integer)
    geri_bildirim = db.Column(db.Text)
    kod_icerik = db.Column(db.Text)
    tarih = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

class Ayarlar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    yonetici_sifre = db.Column(db.String(100), default=default_key) # Varsayılan şifre

# Tabloyu ilk kez oluştururken varsayılan bir şifre ekleyelim
with app.app_context():
    db.create_all()
    if not Ayarlar.query.first():
        default_sifre = os.getenv("DEFAULT_YETKILI_SIFRE")
        varsayilan_ayar = Ayarlar(yonetici_sifre=default_sifre)
        db.session.add(varsayilan_ayar)
        db.session.commit()

# --- AI DEĞERLENDİRME FONKSİYONU ---
import json

def ai_degerlendir(kod, calisma_sonucu,odev):
    try:
        client = Groq(api_key=API) 
        
        odev_tanimi = odev.tanim
        kriterler = odev.kriterler
        yanit = ""

        print(f"AI'ya giden kriterler: {odev.kriterler}")
        # AI için detaylı bir talimat 
        sistem_mesaji = (
            "Sen bir C dili eğitmenisin. Öğrenci kodlarını hem mantıksal yapı hem de çalışma başarısı "
            "açısından değerlendirirsin. Yanıtlarını sadece JSON formatında verirsin."
        )
        
        kullanici_mesaji = f"""
        ÖDEV: {odev_tanimi}\nKRİTERLER: {kriterler}\nKOD: {kod}\nSONUÇ: {calisma_sonucu}...
        LÜTFEN SADECE AŞAĞIDAKİ JSON FORMATINDA CEVAP VER:
                {{
                "toplam_puan": (0-100 arası sayı),
                "degerlendirme": {{
                    "kriter_adi": puan
                }},  
                "aciklama": "Öğrenciye genel geri bildirim"
                }}
                NOT: JSON dışında hiçbir açıklama metni ekleme. Anahtar isminin mutlaka "toplam_puan" olduğundan emin ol.
        """

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": sistem_mesaji},
                {"role": "user", "content": kullanici_mesaji}
            ],
            temperature=0.1 # Daha tutarlı puanlar 
        )
        
        # ... AI yanıtını aldığın satırdan sonrası ...
        yanit = completion.choices[0].message.content
        print(yanit)
        # Markdown bloklarını temizle (eğer varsa)
        if "```json" in yanit:
            yanit = yanit.split("```json")[1].split("```")[0].strip()
        
        data = json.loads(yanit)
        
        # AI'dan gelen anahtarlara göre veriyi çekiyoruz
        # Sözlükte 'toplam_puan' yoksa 0, 'aciklama' yoksa 'Yorum yok' döner
        puan = data.get('toplam_puan', data.get('puan', 0))
        not_mesaji = data.get('aciklama', data.get('degerlendirme', data.get('yorum', 'Değerlendirme yok.')))
        
        # Eğer 'oneri' kısmı da varsa onu da mesaja ekleyelim (Opsiyonel)
        if 'oneri' in data:
            not_mesaji += f"\nÖneri: {data['oneri']}"
            
        return puan, not_mesaji

    except Exception as e:
        print(f"JSON Ayrıştırma Hatası: {e} | Gelen Yanıt: {yanit}")
        return 0, f"Değerlendirme formatı hatalı: {str(e)}"
    
    # completion.choices[0].message.content satırından hemen sonra:
    print(f"AI'DAN GELEN HAM CEVAP: {yanit}")
    

def kod_calistir_ve_test_et(kod_metni):
    file_name = "temp_code.c"
    exec_name = "temp_exec"
    
    # 1. Kod dosyasını UTF-8 olarak oluştur
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(kod_metni)
    
    try:
        # 2. Derleme adımı
        derleme = subprocess.run(
            ['gcc', file_name, '-o', exec_name], 
            capture_output=True, 
            text=True
        )
        
        if derleme.returncode != 0:
            return False, f"Derleme Hatası:\n{derleme.stderr}"

        # 3. İzinleri Ayarlama
        if os.path.exists(exec_name):
            st = os.stat(exec_name)
            os.chmod(exec_name, st.st_mode | stat.S_IEXEC)

        # 4. Çalıştırma adımı
        test_input = "10\n20\n30\n40\n50\n60\n70\n80\n90\n100\n" 
        
        calistirma = subprocess.run(
            ['./' + exec_name], 
            input=test_input, 
            capture_output=True, 
            text=True, 
            timeout=3  
        )
        
        if calistirma.returncode != 0:
            return False, f"Çalışma Hatalı (Runtime Error):\n{calistirma.stderr}"
            
        return True, calistirma.stdout

    except subprocess.TimeoutExpired:
        return False, "Hata: Kod zaman aşımına uğradı (Sonsuz döngü ihtimali)."
    except Exception as e:
        return False, f"Beklenmedik Sistem Hatası: {str(e)}"
    finally:
        # 5. Temizlik 
        if os.path.exists(file_name): os.remove(file_name)
        if os.path.exists(exec_name): os.remove(exec_name)

# --- SAYFALAR ---
@app.route('/')
def index():
    aktif_odevler = Odev.query.filter_by(is_active=True).all()
    return render_template('index.html', aktif_odevler=aktif_odevler)

@app.route('/yukle', methods=['POST'])
def yukle():
    try:
        # Form verilerini al
        odev_id = request.form.get('odev_id')
        ad = request.form.get('ad')
        no = request.form.get('no')
        dosya = request.files.get('dosya')
        
        if not dosya or not odev_id:
            # Teknik hata göstermeden sonuç sayfasına hata durumunu gönder
            return render_template('sonuc.html', durum='hata')

        kod_metni = dosya.read().decode('utf-8', errors='ignore')
        secilen_odev = Odev.query.get(odev_id)
        
        # 1. Kod Derleme ve Çalıştırma
        basarili, sonuc_mesaji = kod_calistir_ve_test_et(kod_metni)
        print(sonuc_mesaji)
        # 2. AI Değerlendirmesi
        puan, mesaj = ai_degerlendir(kod_metni, sonuc_mesaji, secilen_odev)
        
        # 3. Veritabanına Kayıt
        yeni_teslim = OdevTeslim(
            odev_id=odev_id,
            ogrenci_ad=ad,
            ogrenci_no=no,
            puan=puan,
            geri_bildirim=mesaj,
            kod_icerik=kod_metni
        )
        db.session.add(yeni_teslim)
        db.session.commit()
        
        # BAŞARI DURUMU
        print("Kayıt başarılı!")
        return render_template('sonuc.html', durum='basarili', puan=puan, mesaj=mesaj)
        
    except Exception as e:
        print(f"KRİTİK HATA: {e}")
        db.session.rollback()
        # BAŞARISIZLIK DURUMU
        return render_template('sonuc.html', durum='hata')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        girilen_sifre = request.form.get('sifre')
        # Veritabanındaki şifreyi çek
        ayar = Ayarlar.query.first()
        
        if girilen_sifre == ayar.yonetici_sifre:
            session['yetkili_giris'] = True
            return redirect(url_for('yetkili'))
        else:
            flash("Hatalı şifre!", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('yetkili_giris', None)
    flash("Oturum kapatıldı.", "info")
    return redirect(url_for('login'))

@app.route('/yetkili')
@login_required
def yetkili():
    if not session.get('yetkili_giris'):
        return redirect(url_for('login'))
    tum_odevler = Odev.query.all() 
    teslimler = OdevTeslim.query.all()
    
    return render_template('yetkili.html', tum_odevler=tum_odevler, teslimler=teslimler)

@app.route('/yetkili/odev-ekle', methods=['POST'])
@login_required
def odev_ekle():
    baslik = request.form.get('baslik')
    tanim = request.form.get('tanim')
    kriterler = request.form.get('kriterler')
    
    yeni_odev = Odev(baslik=baslik, tanim=tanim, kriterler=kriterler)
    db.session.add(yeni_odev)
    db.session.commit()
    return redirect(url_for('yetkili'))

@app.route('/yetkili/toggle-odev/<int:id>')
@login_required
def toggle_odev(id):
    odev = Odev.query.get(id)
    odev.is_active = not odev.is_active
    db.session.commit()
    return redirect(url_for('yetkili'))

@app.route('/yetkili/sifre-degistir', methods=['POST'])
@login_required
def sifre_degistir():
    yeni_sifre = request.form.get('yeni_sifre')
    if yeni_sifre:
        ayar = Ayarlar.query.first()
        ayar.yonetici_sifre = yeni_sifre
        db.session.commit()
        flash("Şifre başarıyla güncellendi!", "success")
    return redirect(url_for('yetkili'))

@app.route('/reset-password-to-default')
def reset_password():
    ayar = Ayarlar.query.first()
    if ayar:
        ayar.yonetici_sifre = "123"
        db.session.commit()
        flash("Şifre varsayılan olarak sıfırlandı!", "warning")
    return redirect(url_for('login'))

@app.route('/yetkili/sil/<int:id>', methods=['POST'])
def sil_teslim(id):
    if not session.get('yetkili_giris'):
        return redirect(url_for('login'))

    teslim = OdevTeslim.query.get_or_404(id)
    try:
        db.session.delete(teslim)
        db.session.commit()
        return redirect(url_for('yetkili'))
    except Exception as e:
        db.session.rollback()
        return f"Silme işlemi sırasında hata oluştu: {e}"
    
@app.route('/yetkili/sil-odev/<int:id>', methods=['POST'])
def sil_odev(id):
    if not session.get('yetkili_giris'):
        return redirect(url_for('login'))
    odev = Odev.query.get_or_404(id)
    try:
        db.session.delete(odev)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Hata: {e}")
        
    return redirect(url_for('yetkili'))
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=7860)