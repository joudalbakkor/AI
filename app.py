import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from io import BytesIO
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# عنوان التطبيق
st.set_page_config(page_title="خريطة فرص التوسع - السعودية", layout="wide")
st.title("🗺️ نظام توصية التوسع الجغرافي - بيانات حية من Google Sheets")

st.info("""
**كيف يعمل النظام؟**
يقوم النموذج بتحليل بيانات حية من:
1. 📊 Google Sheets (مُحدّثة لحظياً)
2. 📍 OpenStreetMap (الإحداثيات الجغرافية)
""")

# =========================
# 1. الاتصال بـ Google Sheets
# =========================

@st.cache_data(ttl=300)
def get_saudi_cities_data():
    """
    جلب البيانات من Google Sheets
    """
    try:
        # نطاق الصلاحيات
        scope = ["https://spreadsheets.google.com/feeds",
                 "https://www.googleapis.com/auth/drive"]
        
        # محاولة قراءة بيانات الاعتماد من Streamlit Secrets
        if hasattr(st, 'secrets') and 'GCP_SERVICE_ACCOUNT' in st.secrets:
            creds_dict = st.secrets["GCP_SERVICE_ACCOUNT"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            # الحصول على اسم الـ Sheet من secrets أو استخدام الافتراضي
            sheet_name = st.secrets.get("SHEET_NAME", "Saudi Cities Data")
            sheet = client.open(sheet_name).sheet1
            
            # قراءة البيانات
            records = sheet.get_all_records()
            df = pd.DataFrame(records)
            
            # التأكد من أسماء الأعمدة
            df.columns = ['المنطقة', 'عدد_السكان', 'عدد_الشركات', 'معدل_النمو_السكاني']
            
            # تحويل الأعمدة للأرقام
            df['عدد_السكان'] = pd.to_numeric(df['عدد_السكان'], errors='coerce')
            df['عدد_الشركات'] = pd.to_numeric(df['عدد_الشركات'], errors='coerce')
            df['معدل_النمو_السكاني'] = pd.to_numeric(df['معدل_النمو_السكاني'], errors='coerce')
            
            return df
        
        else:
            # بيانات احتياطية للعرض المحلي
            st.warning("⚠️ لم يتم العثور على بيانات الاعتماد، يتم استخدام بيانات تجريبية")
            return pd.DataFrame({
                'المنطقة': ['الرياض', 'جدة', 'مكة', 'المدينة', 'الدمام'],
                'عدد_السكان': [7600000, 4700000, 2100000, 1600000, 1300000],
                'عدد_الشركات': [180000, 95000, 45000, 35000, 40000],
                'معدل_النمو_السكاني': [3.2, 2.8, 2.5, 2.1, 1.9]
            })
    
    except Exception as e:
        st.error(f"⚠️ خطأ في الاتصال بـ Google Sheets: {str(e)}")
        return pd.DataFrame({
            'المنطقة': ['الرياض', 'جدة'],
            'عدد_السكان': [7600000, 4700000],
            'عدد_الشركات': [180000, 95000],
            'معدل_النمو_السكاني': [3.2, 2.8]
        })

@st.cache_data(ttl=3600)
def get_coordinates(cities_list):
    """
    الحصول على الإحداثيات الحقيقية للمدن
    """
    geolocator = Nominatim(user_agent="saudi_opportunity_mapper")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
    
    coordinates = []
    
    for city in cities_list:
        try:
            location = geocode(f"{city}, Saudi Arabia")
            if location:
                coordinates.append({
                    'city': city,
                    'lat': location.latitude,
                    'lon': location.longitude
                })
            else:
                coordinates.append({'city': city, 'lat': 24.7136, 'lon': 46.6753})
        except:
            coordinates.append({'city': city, 'lat': 24.7136, 'lon': 46.6753})
        time.sleep(1)
    
    return pd.DataFrame(coordinates)

@st.cache_data(ttl=3600)
def calculate_opportunity_score(row):
    """
    حساب درجة الفرصة
    """
    pop_score = min(row['عدد_السكان'] / 1000000, 10)
    growth_score = row['معدل_النمو_السكاني'] * 2
    business_score = min(row['عدد_الشركات'] / 20000, 10)
    
    total_score = (pop_score * 0.40) + (growth_score * 0.35) + (business_score * 0.25)
    
    return round(total_score, 2)

# =========================
# 2. معالجة البيانات
# =========================

status_container = st.empty()
progress_bar = st.progress(0)

with status_container:
    st.markdown("### ⏳ جاري تحميل البيانات من Google Sheets...")

df_cities = get_saudi_cities_data()
progress_bar.progress(33)

df_cities['درجة_الفرصة'] = df_cities.apply(calculate_opportunity_score, axis=1)
progress_bar.progress(66)

if not df_cities.empty:
    df_coords = get_coordinates(df_cities['المنطقة'].tolist())
    df_merged = pd.merge(df_cities, df_coords, left_on='المنطقة', right_on='city', how='left')
else:
    df_merged = df_cities

progress_bar.progress(100)

time.sleep(0.5)
status_container.empty()
progress_bar.empty()

st.success("✅ تم تحميل البيانات بنجاح من Google Sheets!")
time.sleep(2)
st.empty()

# =========================
# 3. الفلاتر
# =========================

st.markdown("---")

with st.expander("🔍 فلاتر البحث المتقدمة", expanded=False):
    col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
    
    with col_f1:
        min_population = st.slider("الحد الأدنى للسكان", 0, 8000000, 500000, step=100000)
    
    with col_f2:
        min_growth = st.slider("معدل النمو الأدنى %", 0.0, 5.0, 1.5, step=0.1)
    
    with col_f3:
        max_results = st.slider("عدد النتائج المعروضة", 3, 12, 5)

df_filtered = df_merged[
    (df_merged['عدد_السكان'] >= min_population) & 
    (df_merged['معدل_النمو_السكاني'] >= min_growth)
].copy()

if not df_filtered.empty:
    df_filtered = df_filtered.nlargest(max_results, 'درجة_الفرصة')

# =========================
# 4. عرض النتائج
# =========================

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("🏆 أفضل المناطق المقترحة")
    
    if not df_filtered.empty:
        for idx, row in df_filtered.iterrows():
            with st.container():
                st.markdown(f"""
                <div style='background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px; border-right: 5px solid #1f77b4;'>
                    <h3 style='margin: 0; color: #1f77b4;'>📍 {row['المنطقة']}</h3>
                    <p style='margin: 5px 0;'><b>درجة الفرصة:</b> {row['درجة_الفرصة']}%</p>
                    <p style='margin: 5px 0;'><b>عدد السكان:</b> {row['عدد_السكان']:,} نسمة</p>
                    <p style='margin: 5px 0;'><b>معدل النمو:</b> {row['معدل_النمو_السكاني']}%</p>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander(f"📊 تحليل {row['المنطقة']}"):
                    st.write(f"**عدد الشركات:** {row['عدد_الشركات']:,}")
                    
                    if row['معدل_النمو_السكاني'] > 3:
                        st.success("🚀 منطقة سريعة النمو - فرصة استثمارية عالية")
                    elif row['عدد_السكان'] > 1000000:
                        st.info("📈 سوق كبير - منافسة متوقعة")
                    else:
                        st.warning("⚠️ سوق ناشئ - يحتاج دراسة أعمق")
                
                st.markdown("---")
    else:
        st.warning("⚠️ لا توجد مناطق تطابق الفلاتر المحددة")

with col2:
    st.subheader("📊 تحليل مقارن")
    
    if not df_filtered.empty:
        chart_data = df_filtered.set_index('المنطقة')[['درجة_الفرصة', 'معدل_النمو_السكاني']]
        st.bar_chart(chart_data * 10)
        
        st.subheader("📈 جدول البيانات الكامل")
        st.dataframe(
            df_filtered[['المنطقة', 'عدد_السكان', 'عدد_الشركات', 'معدل_النمو_السكاني', 'درجة_الفرصة']],
            use_container_width=True,
            height=400
        )
    else:
        st.info("💡 عدّل الفلاتر لعرض النتائج")

# =========================
# 5. الخريطة
# =========================

st.markdown("---")
st.subheader("🗺️ التوزيع الجغرافي للفرص")

if not df_filtered.empty and 'lat' in df_filtered.columns:
    map_data = df_filtered[['lat', 'lon', 'المنطقة', 'درجة_الفرصة']].copy()
    map_data = map_data.rename(columns={'lat': 'latitude', 'lon': 'longitude'})
    
    st.map(map_data)
    
    st.info("""
    💡 **كيفية قراءة الخريطة:**
    - كل نقطة تمثل منطقة
    - حجم النقطة يعكس درجة الفرصة
    """)
else:
    st.warning("⚠️ لا توجد بيانات كافية لعرض الخريطة")

# =========================
# 6. التصدير
# =========================

st.markdown("---")
st.subheader("📥 تصدير النتائج")

col1, col2 = st.columns(2)

with col1:
    if not df_filtered.empty:
        csv_data = df_filtered.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 تحميل كـ CSV",
            data=csv_data,
            file_name=f"فرص_التوسع_{time.strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

with col2:
    if not df_filtered.empty:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_filtered.to_excel(writer, index=False)
        excel_data = output.getvalue()
        
        st.download_button(
            label="📥 تحميل كـ Excel",
            data=excel_data,
            file_name=f"فرص_التوسع_{time.strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# =========================
# 7. المعلومات
# =========================

with st.expander("📚 عن النظام"):
    st.markdown("""
    ### مصادر البيانات:
    1. **Google Sheets**: بيانات مُحدّثة لحظياً
    2. **OpenStreetMap**: إحداثيات جغرافية Live
    
    ### المميزات:
    - تحديث البيانات تلقائياً كل 5 دقائق
    - إمكانية تعديل البيانات من Google Sheets مباشرة
    """)

st.markdown("---")
st.caption("تم التطوير بواسطة: جود البكور | نظام ذكاء اصطناعي لتحليل فرص التوسع")
