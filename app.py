import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
import time
import io
import os
from supabase import create_client, Client

# --- 1. AYARLAR ---
st.set_page_config(page_title="EcomPro SaaS", layout="wide", page_icon="💎")

# --- 2. SUPABASE BAĞLANTISI (Senin Verdiğin Bilgiler) ---
SUPABASE_URL = "https://wdofobaykygdyrylpojb.supabase.co"
SUPABASE_KEY = "sb_secret_TJhARgFPar9OoUNkVJ7T8w_G9i_yxpL"

# Bağlantı Testi
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Sistem Hatası: Veritabanına bağlanılamadı. API Key formatını kontrol edin (Genelde 'ey...' ile başlar). Hata: {e}")
    st.stop()

# --- CSS VE TASARIM ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .auth-box { background: rgba(30, 30, 40, 0.9); border: 1px solid rgba(100, 100, 255, 0.2); border-radius: 15px; padding: 40px; }
    h1, h2, h3 { font-family: 'Inter', sans-serif; color: #fff; }
    .stButton>button { width: 100%; border-radius: 8px; height: 45px; font-weight: bold; background: linear-gradient(90deg, #4F46E5, #7C3AED); color: white; border: none; }
    .stTextInput>div>div>input { background-color: #262730; color: white; border: 1px solid #4B5563; }
</style>
""", unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
def barkod_temizle(b):
    if pd.isna(b): return ""
    b = str(b).strip()
    if "." in b: b = b.split(".")[0]
    return b

def sayi_temizle(x):
    """Excel'den gelen '1.250,50' veya '100' formatlarını temizler"""
    if pd.isna(x) or str(x).strip() == "": return 0.0
    x = str(x).replace("TL", "").replace("tl", "").strip()
    # Türkçe format: 1.250,50 -> 1250.50
    if "." in x and "," in x: x = x.replace(".", "").replace(",", ".")
    elif "," in x: x = x.replace(",", ".")
    try: return float(x)
    except: return 0.0

# --- VERİTABANI İŞLEMLERİ ---
def get_user_api_keys(user_id):
    try:
        response = supabase.table('user_settings').select("*").eq('user_id', user_id).execute()
        if response.data: return response.data[0]
        return None
    except: return None

def save_user_api_keys(user_id, s_id, a_key, a_sec):
    data = {"user_id": user_id, "satici_id": s_id, "api_key": a_key, "api_secret": a_sec}
    supabase.table('user_settings').upsert(data).execute()

def get_db_products(user_id):
    try:
        response = supabase.table('user_products').select("*").eq('user_id', user_id).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['barkod'] = df['barkod'].astype(str).apply(barkod_temizle)
            # Sayısal zorlama (0 gelmemesi için)
            cols = ['maliyet', 'kargo', 'komisyon', 'platform', 'alis_kdv']
            for c in cols:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
        return df
    except: return pd.DataFrame()

def upload_to_db(df, user_id):
    data_list = []
    # Mükerrer sütunları temizle (Örn: İki tane 'Komisyon' varsa)
    df = df.loc[:, ~df.columns.duplicated()]
    
    for _, row in df.iterrows():
        # Excel'den okuma
        maliyet = sayi_temizle(row.get('Maliyet'))
        kargo = sayi_temizle(row.get('Kargo'))
        kom = sayi_temizle(row.get('Komisyon')) 
        
        # Eğer Excel'de komisyon yoksa varsayılan 21
        if kom == 0 and pd.isna(row.get('Komisyon')): kom = 21.0
        
        plt_bedel = sayi_temizle(row.get('Platform'))
        kdv = sayi_temizle(row.get('Alis_KDV'))
        if kdv == 0: kdv = 10.0 # Varsayılan (Senin Excel'e göre)

        data_list.append({
            "user_id": user_id,
            "barkod": barkod_temizle(row['Barkod']),
            "urun_adi": str(row.get('Ürün Adı', '')),
            "maliyet": maliyet,
            "kargo": kargo,
            "komisyon": kom,
            "platform": plt_bedel,
            "alis_kdv": kdv
        })
    
    try:
        chunk_size = 1000
        for i in range(0, len(data_list), chunk_size):
            chunk = data_list[i:i + chunk_size]
            supabase.table('user_products').upsert(chunk, on_conflict='user_id, barkod').execute()
        return True, len(data_list)
    except Exception as e:
        return False, str(e)

# --- EKRANLAR ---
def auth_page():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br><h1 style='text-align: center;'>💎 EcomPro</h1>", unsafe_allow_html=True)
        tab1, tab2 = st.tabs(["Giriş Yap", "Kayıt Ol"])
        with tab1:
            with st.form("login"):
                email = st.text_input("E-Posta")
                password = st.text_input("Şifre", type="password")
                if st.form_submit_button("Giriş"):
                    try:
                        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                        if res.user:
                            st.session_state['user'] = res.user
                            st.rerun()
                    except: st.error("Giriş başarısız. Lütfen bilgileri kontrol edin.")
        with tab2:
            with st.form("signup"):
                email = st.text_input("E-Posta")
                password = st.text_input("Şifre", type="password")
                if st.form_submit_button("Kayıt Ol"):
                    try:
                        res = supabase.auth.sign_up({"email": email, "password": password})
                        st.success("Kayıt başarılı! Giriş yapabilirsiniz.")
                    except: st.error("Kayıt hatası.")

def onboarding_page(user):
    st.markdown("<div class='auth-box'>", unsafe_allow_html=True)
    st.title("Hoşgeldiniz!")
    st.info("Lütfen Trendyol API bilgilerinizi giriniz.")
    with st.form("api"):
        s_id = st.text_input("Satıcı ID")
        a_key = st.text_input("API Key")
        a_sec = st.text_input("API Secret", type="password")
        if st.form_submit_button("Kaydet"):
            save_user_api_keys(user.id, s_id, a_key, a_sec)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

def dashboard_page(user, api_data):
    satici_id = api_data['satici_id']
    api_key = api_data['api_key']
    api_secret = api_data['api_secret']

    with st.sidebar:
        st.title("🎛️ Panel")
        if st.button("Çıkış"):
            supabase.auth.sign_out()
            del st.session_state['user']
            st.rerun()
        st.divider()
        bugun = datetime.now()
        baslangic = st.date_input("Başlangıç", bugun - timedelta(days=30))
        bitis = st.date_input("Bitiş", bugun)

    tab_analiz, tab_urun = st.tabs(["📊 Karlılık Analizi", "📦 Maliyet Yönetimi"])

    # --- MALİYET YÖNETİMİ ---
    with tab_urun:
        st.header("Maliyet Yönetimi")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("☁️ Trendyol Ürün Listesini İndir"):
                df = pd.DataFrame(columns=["Barkod", "Ürün Adı", "Alış Maaliyeti", "Kargo Ücreti", "Komisyon", "Platorm Bedeli", "Alış kdv"])
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False)
                st.download_button("Şablon İndir", buffer, "Maliyet_Sablonu.xlsx")
                
        with c2:
            uploaded = st.file_uploader("Excel Yükle (Yeni Maliyet.xlsx Formatı)", type=["xlsx", "csv"])
            if uploaded:
                if st.button("Veritabanına Kaydet"):
                    try:
                        if uploaded.name.endswith('.csv'): 
                            try: df_up = pd.read_csv(uploaded, sep=None, engine='python', dtype=str)
                            except: df_up = pd.read_csv(uploaded, sep=',', dtype=str)
                        else: 
                            df_up = pd.read_excel(uploaded, dtype=str)
                        
                        # --- YENİ MALİYET.XLSX BAŞLIKLARI EŞLEŞTİRME ---
                        renames = {}
                        for c in df_up.columns:
                            cl = c.lower().strip()
                            if "alış maaliyeti" in cl or "alis maaliyeti" in cl: renames[c] = "Maliyet"
                            elif "maaliyet" in cl: renames[c] = "Maliyet"
                            elif "kargo ücreti" in cl: renames[c] = "Kargo"
                            elif "komisyon" in cl and "oran" not in cl and "kdv" not in cl: renames[c] = "Komisyon" # Tutar olanı al
                            elif "platorm" in cl or "platform" in cl: renames[c] = "Platform"
                            # Eğer KDV Oranı sütunu varsa onu al, yoksa Alış KDV'yi al
                            elif "alış kdv" in cl or "alis kdv" in cl: renames[c] = "Alis_KDV" 
                            elif "kdv oranı" in cl: renames[c] = "Alis_KDV_Oran" # Eğer oran sütunu varsa
                            elif "barkod" in cl: renames[c] = "Barkod"
                            elif "ürün adı" in cl: renames[c] = "Ürün Adı"
                        
                        df_up.rename(columns=renames, inplace=True)
                        
                        # Veritabanına Yükle
                        if 'Barkod' in df_up.columns:
                            success, count = upload_to_db(df_up, user.id)
                            if success:
                                st.success(f"✅ {count} ürün başarıyla yüklendi!")
                                time.sleep(1)
                                st.rerun()
                            else: st.error(f"Kayıt Hatası: {count}")
                        else: st.error("Hata: Excel'de 'Barkod' sütunu bulunamadı.")
                    except Exception as e: st.error(f"Dosya okuma hatası: {e}")
        
        # Tablo
        db_df = get_db_products(user.id)
        if not db_df.empty:
            st.dataframe(db_df)

    # --- ANALİZ (SENİN EXCEL FORMÜLÜNE GÖRE) ---
    with tab_analiz:
        st.header("Net Karlılık Raporu")
        if st.button("ANALİZİ BAŞLAT", type="primary"):
            db_df = get_db_products(user.id)
            if db_df.empty:
                st.error("Lütfen önce maliyet yükleyin.")
                st.stop()
            
            p_map = db_df.set_index('barkod').to_dict('index')
            
            def ts(d, t): return int(time.mktime(datetime.combine(d, datetime.strptime(t, "%H:%M:%S").time()).timetuple()) * 1000)
            url = f"https://api.trendyol.com/sapigw/suppliers/{satici_id}/orders"
            params = {"startDate": ts(baslangic,"00:00:00"), "endDate": ts(bitis,"23:59:59"), "size": 50, "orderBy": "CreatedDate", "order": "DESC"}
            
            try:
                r = requests.get(url, auth=HTTPBasicAuth(api_key, api_secret), params=params)
                if r.status_code == 200:
                    orders = r.json().get("content", [])
                    report = []
                    totals = {"Ciro": 0, "Net": 0}
                    
                    for o in orders:
                        if o["status"] in ["Cancelled", "UnSupplied", "Returned"]: continue
                        
                        for item in o["lines"]:
                            brk = barkod_temizle(item["barcode"])
                            fiyat = float(item["price"]) # KDV Dahil Satış
                            satis_kdv_orani = float(item.get("vatRate", 20)) # Trendyol'dan gelen oran (Örn: 10 veya 20)
                            
                            # Veritabanından verileri çek
                            cost = 0; kargo = 0; kom_tutar = 0; platform = 0; alis_kdv_orani = 10.0
                            durum = "❌"
                            
                            if brk in p_map:
                                p = p_map[brk]
                                cost = float(p.get('maliyet', 0))
                                kargo = float(p.get('kargo', 0)) # Excel'deki Net Kargo (90)
                                kom_tutar = float(p.get('komisyon', 0)) # Excel'deki Komisyon Tutarı (215)
                                platform = float(p.get('platform', 0)) # Excel'deki Platform (8.39)
                                
                                # Eğer Excel'den Alış KDV Oranı (örn: 10) geliyorsa onu kullan
                                # Senin Excel'de "Alış kdv" hesaplanmış (9.09), bu %10 demektir.
                                # Biz burada dinamik hesap için oranı kullanacağız.
                                # Veritabanına 'alis_kdv' sütununa oranı kaydetmiştik.
                                alis_kdv_orani = float(p.get('alis_kdv', 10)) 
                                
                                if cost > 0: durum = "✅"
                            
                            # --- FORMÜL (Senin Excel Dosyana Birebir Uygun) ---
                            # 1. Satış (KDV Dahil)
                            satis = fiyat 
                            
                            # 2. Stopaj (%1)
                            satis_kdv_haric = satis / (1 + satis_kdv_orani/100)
                            stopaj = satis_kdv_haric * 0.01 
                            
                            # 3. KDV Hesabı (Net KDV = Satış KDV - İndirilecekler)
                            satis_kdv_tutar = satis - satis_kdv_haric
                            
                            # İndirilecek KDV'ler
                            alis_kdv_tutar = cost - (cost / (1 + alis_kdv_orani/100))
                            
                            # Komisyon KDV'si (Komisyon tutarının içindeki %20)
                            komisyon_kdv_tutar = kom_tutar - (kom_tutar / 1.20)
                            
                            # Kargo KDV'si (Senin Excel'de Kargo 90, KDV 18. Yani Kargo * 0.20)
                            kargo_kdv_tutar = kargo * 0.20
                            
                            indirilecek_kdv = alis_kdv_tutar + komisyon_kdv_tutar + kargo_kdv_tutar
                            odenecek_kdv = max(0, satis_kdv_tutar - indirilecek_kdv)
                            
                            # 4. NET KAR (Excel: 549.53 TL Mantığı)
                            # Satış - Maliyet(Brüt) - Kargo(Net) - Komisyon(Brüt) - Platform - Stopaj - Ödenecek KDV
                            
                            # Not: Senin Excel'de Kargo 90 düşülüyor (Net). Bizim DB'de kargo 90.
                            # Not: Senin Excel'de Komisyon 215 düşülüyor (Brüt). Bizim DB'de 215.
                            
                            giderler = cost + kargo + kom_tutar + platform + stopaj + odenecek_kdv
                            net_kar = satis - giderler
                            
                            report.append({
                                "Sipariş": o["orderNumber"], "Barkod": brk, "Ürün": item.get("productName")[:20],
                                "Satış": round(satis, 2), "Maliyet": round(cost, 2), 
                                "Kargo": kargo, "Komisyon": kom_tutar, "Platform": platform,
                                "Net Kar": round(net_kar, 2), "Durum": durum
                            })
                            totals["Ciro"] += satis
                            totals["Net"] += net_kar
                    
                    c1, c2 = st.columns(2)
                    c1.metric("Ciro", f"{totals['Ciro']:,.2f} TL")
                    c2.metric("Net Kar", f"{totals['Net']:,.2f} TL")
                    st.dataframe(pd.DataFrame(report))
                else: st.error(f"API Hatası: {r.status_code}")
            except Exception as e: st.error(f"Hata: {e}")

if 'user' in st.session_state:
    user = st.session_state['user']
    api_data = get_user_api_keys(user.id)
    if api_data: dashboard_page(user, api_data)
    else: onboarding_page(user)
else: auth_page()