from flask import Flask, Response, render_template, request, redirect, url_for, session, flash
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from groq import Groq
import re
import subprocess
import os
import json
import stat
import threading
import time
from dotenv import load_dotenv

app = Flask(__name__, template_folder='templates', static_folder='static')
load_dotenv()

# --- YAPILANDIRMA ---
app.secret_key = os.getenv("SECRET_KEY")
database_url = os.getenv("DATABASE_URL")
API = os.getenv("GROQ")
default_key = os.getenv("DEFAULT_YETKILI_SIFRE")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///local.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- VERİTABANI MODELLERİ ---

class Odev(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    baslik = db.Column(db.String(200), nullable=False)
    tanim = db.Column(db.Text, nullable=False)
    kriterler = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    teslimler = db.relationship('OdevTeslim', backref='odev_tanimi', lazy=True, cascade="all, delete-orphan")
    test_case = db.Column(db.Text)

class OdevTeslim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    odev_id = db.Column(db.Integer, db.ForeignKey('odev.id'))
    ogrenci_ad = db.Column(db.String(100))
    ogrenci_no = db.Column(db.String(20))
    puan = db.Column(db.Integer, default=0)
    geri_bildirim = db.Column(db.Text, default="Sıraya alındı, değerlendirme bekleniyor...")
    kod_icerik = db.Column(db.Text)
    puan_detay = db.Column(db.Text, default="{}")
    # Durum: 'bekliyor', 'isleniyor', 'tamamlandi', 'hata'
    durum = db.Column(db.String(20), default='bekliyor')
    tarih = db.Column(db.DateTime, default=datetime.utcnow)

class Ayarlar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    yonetici_sifre = db.Column(db.String(100), default=default_key)

# --- YARDIMCI FONKSİYONLAR ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('yetkili_giris'):
            flash("Lütfen önce giriş yapın!", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def test_senaryosu_olustur(odev_tanimi, kriterler):
    try:
        client = Groq(api_key=API)
        prompt = f"C programlama ödevi için sadece girdi (input) senaryosu hazırla.\nÖDEV: {odev_tanimi}\nKRİTERLER: {kriterler}\nSadece saf girdi metni ver."
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Test case oluşturma hatası: {e}")
        return ""

def kod_calistir_ve_test_et(kod_metni, test_input=None):
    # Çakışmayı önlemek için thread-safe isimlendirme
    unique_id = f"{int(time.time())}_{os.getpid()}"
    file_name = f"temp_code_{unique_id}.c"
    exec_name = f"./temp_exec_{unique_id}"
    
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(kod_metni)
    
    try:
        derleme = subprocess.run(['gcc', file_name, '-o', exec_name], capture_output=True, text=True)
        if derleme.returncode != 0:
            return False, f"Derleme Hatası:\n{derleme.stderr}"

        if os.path.exists(exec_name):
            os.chmod(exec_name, stat.S_IRWXU)

        calistirma = subprocess.run([exec_name], input=test_input, capture_output=True, text=True, timeout=3)
        return True, calistirma.stdout
    except subprocess.TimeoutExpired:
        return False, "Hata: Kod zaman aşımına uğradı."
    except Exception as e:
        return False, f"Sistem Hatası: {str(e)}"
    finally:
        if os.path.exists(file_name): os.remove(file_name)
        if os.path.exists(exec_name):
            try: os.remove(exec_name)
            except: pass

def ai_degerlendir(kod, calisma_sonucu, odev, kullanilan_input):
    try:
        client = Groq(api_key=API)
        test_durumu = f"Kullanılan Girdiler: {kullanilan_input}" if kullanilan_input else "Test girişi yok."
        sistem_mesaji = os.getenv("SYSTEM_PROMPT", "Sen bir C programlama öğretmenisin.")
        
        kullanici_mesaji = f"""
        ÖDEV: {odev.tanim}\nKRİTERLER: {odev.kriterler}\nKOD: {kod}\nTEST SENARYOSU: {test_durumu}\nSONUÇ: {calisma_sonucu}
        LÜTFEN SADECE AŞAĞIDAKİ JSON FORMATINDA CEVAP VER:
        {{
            "puan_dagilimi": {{"kriter": puan}},
            "aciklama": "Değerlendirme yorumu"
        }}
        """

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": sistem_mesaji},
                {"role": "user", "content": kullanici_mesaji}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        data = json.loads(completion.choices[0].message.content)
        dagilim = data.get('puan_dagilimi', {})
        puan = sum(v for v in dagilim.values() if isinstance(v, (int, float)))
        puan = max(0, min(100, int(puan)))
        aciklama = data.get('aciklama', 'Değerlendirme tamamlandı.')
        
        return puan, aciklama, dagilim
    except Exception as e:
        print(f"AI Değerlendirme Hatası: {e}")
        return None, None, None

def odev_isleyici_worker():
    """Veritabanındaki bekleyen ödevleri sırayla işleyen arka plan görevi."""
    with app.app_context():
        print("🤖 Arka plan işçisi aktif hale getirildi...")
        while True:
            try:
                # Bekleyen en eski ödevi bul
                teslim = OdevTeslim.query.filter_by(durum='bekliyor').order_by(OdevTeslim.tarih.asc()).first()
                
                if teslim:
                    print(f"📝 İşleniyor: {teslim.ogrenci_ad} ({teslim.ogrenci_no})")
                    teslim.durum = 'isleniyor'
                    db.session.commit()
                    
                    secilen_odev = Odev.query.get(teslim.odev_id)
                    hazir_input = getattr(secilen_odev, 'test_case', None)

                    # 1. Kod Çalıştırma Testi
                    basarili, sonuc_mesaji = kod_calistir_ve_test_et(teslim.kod_icerik, test_input=hazir_input)
                    
                    # 2. AI Değerlendirmesi
                    puan, mesaj, dagilim = ai_degerlendir(teslim.kod_icerik, sonuc_mesaji, secilen_odev, hazir_input)
                    
                    if puan is not None:
                        teslim.puan = puan
                        teslim.geri_bildirim = mesaj
                        teslim.puan_detay = json.dumps(dagilim)
                        teslim.durum = 'tamamlandi'
                        print(f"✅ Tamamlandı: {teslim.ogrenci_ad} - Puan: {puan}")
                    else:
                        # API hatası durumunda sıraya geri koy (veya 'hata' olarak işaretle)
                        teslim.durum = 'bekliyor'
                        print(f"⚠️ {teslim.ogrenci_ad} için AI hatası, tekrar denenecek.")
                    
                    db.session.commit()
                    
                    # Her ödevden sonra 10 saniye bekle
                    time.sleep(10)
                else:
                    # Bekleyen yoksa 5 saniye uyu
                    time.sleep(5)
            except Exception as e:
                print(f"Worker hatası: {e}")
                time.sleep(10)

def database_sifirla():
    with app.app_context():
        print("Veritabanı siliniyor...")
        db.drop_all() 
        print("Veritabanı güncel modellerle yeniden oluşturuluyor...")
        db.create_all()
        print("İşlem başarıyla tamamlandı!")

# --- SAYFALAR ---

@app.template_filter('from_json')
def from_json_filter(s):
    try: return json.loads(s)
    except: return {}

@app.route('/')
def index():
    aktif_odevler = Odev.query.filter_by(is_active=True).all()
    return render_template('index.html', aktif_odevler=aktif_odevler)

@app.route('/yukle', methods=['POST'])
def yukle():
    try:
        odev_id = request.form.get('odev_id')
        ad = request.form.get('ad')
        no = request.form.get('no')
        dosya = request.files.get('dosya')
        
        if not all([ad, no, odev_id, dosya]) or not dosya.filename.endswith('.c'):
            flash("Lütfen tüm alanları ve geçerli bir .c dosyası girin.", "danger")
            return redirect(url_for('index'))

        kod_metni = dosya.read().decode('utf-8', errors='ignore')
        
        # ASENKRON KAYIT: AI'yı beklemeden doğrudan veritabanına yaz
        yeni_teslim = OdevTeslim(
            odev_id=odev_id,
            ogrenci_ad=ad,
            ogrenci_no=no,
            kod_icerik=kod_metni,
            durum='bekliyor'
        )
        db.session.add(yeni_teslim)
        db.session.commit()
        
        return render_template('sonuc.html', durum='basarili', mesaj="Ödevin alındı! Arka planda sıraya konuldu, puanın birazdan yönetim panelinde görünecek.")
        
    except Exception as e:
        db.session.rollback()
        return render_template('sonuc.html', durum='hata')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        girilen_sifre = request.form.get('sifre')
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
    return redirect(url_for('login'))

@app.route('/yetkili')
@login_required
def yetkili():
    tum_odevler = Odev.query.all()
    teslimler = OdevTeslim.query.order_by(OdevTeslim.tarih.desc()).all()
    return render_template('yetkili.html', tum_odevler=tum_odevler, teslimler=teslimler)

@app.route('/yetkili/odev-ekle', methods=['POST'])
@login_required
def odev_ekle():
    baslik = request.form.get('baslik')
    tanim = request.form.get('tanim')
    kriterler = request.form.get('kriterler')
    hazir_test_case = test_senaryosu_olustur(tanim, kriterler)
    yeni_odev = Odev(baslik=baslik, tanim=tanim, kriterler=kriterler, test_case=hazir_test_case)
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

@app.route('/yetkili/sil-odev/<int:id>', methods=['POST'])
@login_required
def sil_odev(id):
    odev = Odev.query.get_or_404(id)
    OdevTeslim.query.filter_by(odev_id=id).delete()
    db.session.delete(odev)
    db.session.commit()
    return redirect(url_for('yetkili'))

@app.route('/yetkili/odev-indir/<int:id>')
@login_required
def odev_indir(id):
    odev = Odev.query.get_or_404(id)
    teslimler = OdevTeslim.query.filter_by(odev_id=id).all()
    
    dosya_icerigi = f"RAPOR: {odev.baslik}\n" + "="*30 + "\n"
    for i, t in enumerate(teslimler, 1):
        dosya_icerigi += f"{i}. {t.ogrenci_ad} ({t.ogrenci_no}) - Puan: {t.puan}\nDurum: {t.durum}\nGeribildirim: {t.geri_bildirim}\n{'-'*20}\n{t.kod_icerik}\n\n"
    
    return Response(dosya_icerigi, mimetype="text/plain", headers={"Content-disposition": f"attachment; filename={odev.id}_Rapor.txt"})

# --- BAŞLATMA ---

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Ayarlar.query.first():
            db.session.add(Ayarlar(yonetici_sifre=default_key))
            db.session.commit()
    
    # İşçi Thread'ini Başlat
    worker_thread = threading.Thread(target=odev_isleyici_worker, daemon=True)
    worker_thread.start()
    
    app.run(debug=False, host='0.0.0.0', port=7860)

