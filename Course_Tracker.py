# app.py
import streamlit as st
import pandas as pd
import datetime as dt
import hashlib
from pathlib import Path
import plotly.graph_objects as go
import subprocess
import os

# ================== Dosyalar ==================
USER_DB = Path("users.csv")
ATTENDANCE_DB = Path("attendance.csv")
SCHEDULE_DB = Path("schedule.csv")

# ================== Sabitler ==================
DAYS_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
DAY_IDX = {d: i for i, d in enumerate(DAYS_TR)}
HOUR_START = 8
HOUR_END   = 19
SCHOOL_START = dt.date(2025, 9, 29)

# ================== Yardımcılar ==================
def hash_password(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()

def load_users():
    if USER_DB.exists():
        return pd.read_csv(USER_DB)
    return pd.DataFrame(columns=["username", "password"])

def save_users(df: pd.DataFrame):
    df.to_csv(USER_DB, index=False)

def load_attendance():
    if ATTENDANCE_DB.exists():
        df = pd.read_csv(ATTENDANCE_DB)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    return pd.DataFrame(columns=["username", "course", "date"])

def save_attendance(df: pd.DataFrame):
    df.to_csv(ATTENDANCE_DB, index=False)
    github_push_debug()  # Push tetikleme

def load_schedule():
    if SCHEDULE_DB.exists():
        return pd.read_csv(SCHEDULE_DB)
    return pd.DataFrame(columns=["username", "course", "day", "start", "end"])

def save_schedule(df: pd.DataFrame):
    df.to_csv(SCHEDULE_DB, index=False)
    github_push_debug()

def _time_to_hours(hhmm: str) -> float:
    hh, mm = hhmm.split(":")
    return int(hh) + int(mm)/60

# ================== GitHub Push Debug ==================
def github_push_debug():
    token = st.secrets.get("MY_GITHUB_TOKEN")
    repo_url = st.secrets.get("MY_GITHUB_REPO_URL")
    if not token or not repo_url:
        st.warning("GitHub push sırasında hata: repo URL veya token eksik")
        return
    try:
        # Token ile repo URL
        secure_url = repo_url.replace("https://", f"https://{token}@")
        # git add
        subprocess.run(["git", "add", "."], check=True)
        # git commit
        subprocess.run(["git", "commit", "-m", "Update attendance"], check=False)
        # git push
        result = subprocess.run(["git", "push", secure_url, "HEAD:main"], capture_output=True, text=True)
        if result.returncode == 0:
            st.success("Push tetiklendi ve GitHub'a gönderildi")
        else:
            st.error(f"GitHub push sırasında hata oluştu: {result.stderr}")
    except Exception as e:
        st.error(f"GitHub push sırasında hata oluştu: {e}")

# ================== Takvim Görünümü ==================
def timetable_grid_figure(schedule_df: pd.DataFrame, title="Haftalık Program"):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_white",
        height=700,
        margin=dict(l=70,r=40,t=50,b=40),
        title=title,
        xaxis=dict(range=[-0.5,len(DAYS_TR)-0.5], tickmode="array",
                   tickvals=list(range(len(DAYS_TR))), ticktext=DAYS_TR, showgrid=True),
        yaxis=dict(range=[HOUR_END,HOUR_START], tick0=HOUR_START, dtick=1, tickformat="02d:00", showgrid=True),
        showlegend=False
    )
    if schedule_df.empty: return fig
    palette = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf"]
    color_map = {}
    for _, r in schedule_df.iterrows():
        day = r["day"]
        if day not in DAY_IDX: continue
        x = DAY_IDX[day]
        y0 = _time_to_hours(r["start"])
        y1 = _time_to_hours(r["end"])
        if y1 <= y0: continue
        c = color_map.setdefault(r["course"], palette[len(color_map)%len(palette)])
        fig.add_shape(type="rect", x0=x-0.45, x1=x+0.45, y0=y0, y1=y1, line=dict(color=c,width=1.5), fillcolor=c, opacity=0.88)
        fig.add_annotation(x=x, y=(y0+y1)/2, text=f"{r['course']}<br>{r['start']}–{r['end']}", showarrow=False, font=dict(color="white", size=12), xanchor="center", yanchor="middle")
    return fig

# ================== Giriş/Kayıt ==================
def login_ui():
    st.title("Ders Katılım Takip Sistemi")
    tab1, tab2 = st.tabs(["Giriş Yap", "Kayıt Ol"])
    with tab2:
        new_user = st.text_input("Kullanıcı Adı")
        new_pass = st.text_input("Şifre", type="password")
        if st.button("Kayıt Ol"):
            users_df = load_users()
            if not new_user or not new_pass:
                st.warning("Kullanıcı adı ve şifre boş olamaz.")
            elif new_user in users_df.username.values:
                st.warning("Bu kullanıcı adı zaten var.")
            else:
                row = pd.DataFrame([{"username":new_user,"password":hash_password(new_pass)}])
                users_df = pd.concat([users_df,row],ignore_index=True)
                save_users(users_df)
                st.success("Kayıt tamam.")
    with tab1:
        username = st.text_input("Kullanıcı Adı", key="login_user")
        password = st.text_input("Şifre", type="password", key="login_pass")
        if st.button("Giriş Yap"):
            users_df = load_users()
            hashed = hash_password(password)
            ok = users_df[(users_df["username"]==username)&(users_df["password"]==hashed)]
            if not ok.empty:
                st.session_state["username"] = username
                st.rerun()
            else:
                st.error("Geçersiz kullanıcı adı/şifre.")

# ================== Dashboard ==================
def dashboard(username: str):
    st.sidebar.write(f"Hoş geldin, **{username}**")
    if st.sidebar.button("Çıkış Yap"): st.session_state.clear(); st.rerun()
    menu = ["Ders Programı","Katılım İşaretle","İstatistikler","Sıralama"]
    choice = st.sidebar.radio("Menü",menu)
    schedule_df = load_schedule()
    attendance_df = load_attendance()
    my_sched = schedule_df[schedule_df["username"]==username].copy()

    # --- Ders Programı ---
    if choice=="Ders Programı":
        st.header("Ders Programı Ekle / Sil")
        with st.form("add_course", clear_on_submit=True):
            course = st.text_input("Ders Adı")
            day = st.selectbox("Gün", DAYS_TR)
            c1,c2 = st.columns(2)
            with c1: start = st.time_input("Başlangıç", dt.time(13,30), step=dt.timedelta(minutes=30))
            with c2: end = st.time_input("Bitiş", dt.time(16,30), step=dt.timedelta(minutes=30))
            submitted = st.form_submit_button("Ekle")
        if submitted:
            if end<=start: st.error("Bitiş saati başlangıçtan büyük olmalı.")
            elif not course.strip(): st.error("Ders adı boş olamaz.")
            else:
                row = pd.DataFrame([{"username":username,"course":course.strip(),"day":day,"start":start.strftime("%H:%M"),"end":end.strftime("%H:%M")}])
                schedule_df = pd.concat([schedule_df,row],ignore_index=True)
                save_schedule(schedule_df)
                st.success("Ders eklendi."); st.rerun()
        # Ders silme
        if not my_sched.empty:
            st.subheader("Ders Sil")
            del_course = st.selectbox("Silmek istediğiniz ders", my_sched["course"].unique())
            if st.button("Sil"):
                schedule_df = schedule_df[~((schedule_df["username"]==username)&(schedule_df["course"]==del_course))]
                save_schedule(schedule_df)
                st.success(f"{del_course} silindi."); st.rerun()
        my_sched = schedule_df[schedule_df["username"]==username].copy()
        st.plotly_chart(timetable_grid_figure(my_sched),use_container_width=True)

    # --- Katılım İşaretle ---
    elif choice=="Katılım İşaretle":
        st.header("Katılım İşaretle")
        if my_sched.empty: st.info("Önce ders ekleyin."); return
        st.plotly_chart(timetable_grid_figure(my_sched),use_container_width=True)
        sel_date = st.date_input("Tarih", value=dt.date.today())
        weekday_tr = DAYS_TR[min(sel_date.weekday(),4)]
        todays = my_sched[my_sched["day"]==weekday_tr].sort_values("start")
        if todays.empty: st.info(f"{weekday_tr} günü ders yok.")
        else:
            _att_dates = pd.to_datetime(attendance_df["date"], errors="coerce").dt.date
            my_att_today = attendance_df[(attendance_df["username"]==username)&(_att_dates==sel_date)]
            for _, r in todays.iterrows():
                label = f"{r['course']} {r['start']}-{r['end']}"
                already = not my_att_today[my_att_today["course"]==r["course"]].empty
                checked = st.checkbox(label,value=already,key=f"att_{username}_{r['course']}_{sel_date}")
                if checked and not already:
                    add = pd.DataFrame([{"username":username,"course":r["course"],"date":pd.to_datetime(sel_date)}])
                    attendance_df = pd.concat([attendance_df,add],ignore_index=True)
                    save_attendance(attendance_df)
                    st.toast(f"{r['course']} için katılım kaydedildi.")
                elif not checked and already:
                    _att_dates = pd.to_datetime(attendance_df["date"], errors="coerce").dt.date
                    attendance_df = attendance_df[~((attendance_df["username"]==username)&(attendance_df["course"]==r["course"])&(_att_dates==sel_date))]
                    save_attendance(attendance_df)
                    st.toast(f"{r['course']} katılımı silindi.")

    # --- İstatistikler ---
    elif choice=="İstatistikler":
        st.header("Katılım İstatistikleri")
        my_att = attendance_df[attendance_df["username"]==username].copy()
        if my_att.empty: st.info("Katılım verisi yok.")
        else:
            all_sched = my_sched.copy()
            if all_sched.empty: st.info("Önce program ekleyin."); return
            # Bugüne kadar katıldığın derslerin yüzdesi
            today = dt.date.today()
            weeks = ((today - SCHOOL_START).days // 7) + 1
            total_classes = 0
            for w in range(weeks):
                week_start = SCHOOL_START + dt.timedelta(days=7*w)
                week_end = week_start + dt.timedelta(days=6)
                for _, r in all_sched.iterrows():
                    class_day_idx = DAY_IDX[r["day"]]
                    class_date = week_start + dt.timedelta(days=class_day_idx)
                    if class_date <= today:
                        total_classes += 1
            actual_att = len(my_att)
            perc = (actual_att / total_classes * 100) if total_classes>0 else 0
            summary = my_att.groupby("course").date.nunique().reset_index(name="Katılım Sayısı")
            st.dataframe(summary,use_container_width=True)
            st.metric("Toplam Katılım", actual_att)
            st.metric("Katılım Oranı", f"{perc:.1f}%")

    # --- Sıralama ---
    else:
        st.header("Genel Sıralama")
        all_sched = load_schedule()
        all_att = load_attendance()
        if all_sched.empty or all_att.empty: st.info("Henüz veri yok."); return
        today = dt.date.today()
        weeks = ((today - SCHOOL_START).days // 7) + 1
        results = []
        for user in all_sched["username"].unique():
            user_sched = all_sched[all_sched["username"]==user]
            user_att = all_att[all_att["username"]==user]
            total_classes = 0
            for w in range(weeks):
                week_start = SCHOOL_START + dt.timedelta(days=7*w)
                for _, r in user_sched.iterrows():
                    class_day_idx = DAY_IDX[r["day"]]
                    class_date = week_start + dt.timedelta(days=class_day_idx)
                    if class_date <= today:
                        total_classes += 1
            actual_att = len(user_att)
            perc = (actual_att / total_classes *100) if total_classes>0 else 0
            results.append({"Kullanıcı":user,"Toplam Katılım":actual_att,"Oran %":round(perc,1)})
        ranking = pd.DataFrame(results).sort_values("Oran %",ascending=False)
        st.dataframe(ranking,use_container_width=True)

# ================== Main ==================
st.set_page_config(page_title="Ders Katılım", layout="wide")
if "username" not in st.session_state: login_ui()
else: dashboard(st.session_state["username"])
