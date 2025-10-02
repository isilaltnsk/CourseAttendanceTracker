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
HOUR_START = 8   # 08:00
HOUR_END   = 19  # 19:00
SCHOOL_START_DATE = dt.date(2025, 9, 29)  # Okulun başladığı tarih

# ================== Yardımcılar ==================
def hash_password(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()

def git_push(file_path: str, commit_msg: str):
    """Dosya değişikliğini GitHub'a pushlar"""
    token = st.secrets.get("GITHUB_TOKEN")
    if not token:
        st.warning("GitHub token bulunamadı. Değişiklikler pushlanamayacak.")
        return
    repo_url = st.secrets.get("GITHUB_REPO_URL")
    if not repo_url:
        st.warning("GitHub repo URL bulunamadı. Değişiklikler pushlanamayacak.")
        return
    try:
        # Git config
        subprocess.run(["git", "config", "--global", "user.email", "streamlit@example.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "Streamlit Bot"], check=True)
        # Add
        subprocess.run(["git", "add", file_path], check=True)
        # Commit
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        # Push
        # Repo URL: https://<TOKEN>@github.com/user/repo.git
        url_with_token = repo_url.replace("https://", f"https://{token}@")
        subprocess.run(["git", "push", url_with_token, "HEAD:main"], check=True)
    except subprocess.CalledProcessError as e:
        st.warning(f"Git push hatası: {e}")

def load_users():
    if USER_DB.exists():
        return pd.read_csv(USER_DB)
    return pd.DataFrame(columns=["username", "password"])

def save_users(df: pd.DataFrame):
    df.to_csv(USER_DB, index=False)
    git_push(USER_DB.as_posix(), "Update users database")

def load_attendance():
    if ATTENDANCE_DB.exists():
        df = pd.read_csv(ATTENDANCE_DB)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=False)
        return df
    return pd.DataFrame(columns=["username", "course", "date"])

def save_attendance(df: pd.DataFrame):
    df.to_csv(ATTENDANCE_DB, index=False)
    git_push(ATTENDANCE_DB.as_posix(), "Update attendance")

def load_schedule():
    if SCHEDULE_DB.exists():
        return pd.read_csv(SCHEDULE_DB)
    return pd.DataFrame(columns=["username", "course", "day", "start", "end"])

def save_schedule(df: pd.DataFrame):
    df.to_csv(SCHEDULE_DB, index=False)
    git_push(SCHEDULE_DB.as_posix(), "Update schedule")

def _time_to_hours(hhmm: str) -> float:
    hh, mm = hhmm.split(":")
    return int(hh) + int(mm) / 60

# ================== Takvim ==================
def timetable_grid_figure(schedule_df: pd.DataFrame, title: str = "Haftalık Program"):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_white",
        height=700,
        margin=dict(l=70, r=40, t=50, b=40),
        title=title,
        xaxis=dict(
            range=[-0.5, len(DAYS_TR) - 0.5],
            tickmode="array",
            tickvals=list(range(len(DAYS_TR))),
            ticktext=DAYS_TR,
            showgrid=True,
            dtick=1,
            zeroline=False,
        ),
        yaxis=dict(
            range=[HOUR_END, HOUR_START],
            tick0=HOUR_START,
            dtick=1,
            tickformat="02d:00",
            showgrid=True,
            zeroline=False,
        ),
        showlegend=False,
    )

    if schedule_df.empty:
        return fig

    palette = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]
    color_map = {}

    for _, r in schedule_df.iterrows():
        day = r["day"]
        if day not in DAY_IDX:
            continue
        x = DAY_IDX[day]
        y0 = _time_to_hours(r["start"])
        y1 = _time_to_hours(r["end"])
        if y1 <= y0:
            continue
        c = color_map.setdefault(r["course"], palette[len(color_map) % len(palette)])
        fig.add_shape(
            type="rect",
            x0=x - 0.45, x1=x + 0.45,
            y0=y0, y1=y1,
            line=dict(color=c, width=1.5),
            fillcolor=c,
            opacity=0.88,
        )
        fig.add_annotation(
            x=x, y=(y0 + y1) / 2,
            text=f"{r['course']}<br>{r['start']}–{r['end']}",
            showarrow=False,
            font=dict(color="white", size=12),
            xanchor="center", yanchor="middle",
        )
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
                row = pd.DataFrame([{"username": new_user, "password": hash_password(new_pass)}])
                users_df = pd.concat([users_df, row], ignore_index=True)
                save_users(users_df)
                st.success("Kayıt tamam. Giriş yapabilirsiniz.")

    with tab1:
        username = st.text_input("Kullanıcı Adı", key="login_user")
        password = st.text_input("Şifre", type="password", key="login_pass")
        if st.button("Giriş Yap"):
            users_df = load_users()
            hashed = hash_password(password)
            ok = users_df[
                (users_df["username"] == username) &
                (users_df["password"] == hashed)
            ]
            if not ok.empty:
                st.session_state["username"] = username
                st.rerun()
            else:
                st.error("Geçersiz kullanıcı adı/şifre.")

# ================== Dashboard ==================
def dashboard(username: str):
    st.sidebar.write(f"Hoş geldin, **{username}**")
    if st.sidebar.button("Çıkış Yap"):
        st.session_state.clear(); st.rerun()
    menu = ["Ders Programı", "Katılım İşaretle", "İstatistikler", "Sıralama"]
    choice = st.sidebar.radio("Menü", menu)
    schedule_df = load_schedule()
    attendance_df = load_attendance()
    my_sched = schedule_df[schedule_df["username"] == username].copy()

    # -------- Ders Programı --------
    if choice == "Ders Programı":
        st.header("Ders Programı Ekle / Gör / Sil")
        with st.form("add_course", clear_on_submit=True):
            course = st.text_input("Ders Adı")
            day = st.selectbox("Gün", DAYS_TR)
            c1, c2 = st.columns(2)
            with c1:
                start = st.time_input("Başlangıç", dt.time(13, 30), step=dt.timedelta(minutes=30))
            with c2:
                end = st.time_input("Bitiş", dt.time(16, 30), step=dt.timedelta(minutes=30))
            submitted = st.form_submit_button("Ekle")
        if submitted:
            if end <= start:
                st.error("Bitiş saati başlangıçtan büyük olmalı.")
            elif not course.strip():
                st.error("Ders adı boş olamaz.")
            else:
                row = pd.DataFrame([{
                    "username": username,
                    "course": course.strip(),
                    "day": day,
                    "start": start.strftime("%H:%M"),
                    "end": end.strftime("%H:%M"),
                }])
                schedule_df = pd.concat([schedule_df, row], ignore_index=True)
                save_schedule(schedule_df)
                st.success("Ders eklendi.")
                st.rerun()
        # Ders silme
        if not my_sched.empty:
            st.subheader("Ders Sil")
            del_course = st.selectbox("Silmek istediğiniz ders", my_sched["course"].unique())
            if st.button("Sil"):
                schedule_df = schedule_df[~(
                    (schedule_df["username"] == username) &
                    (schedule_df["course"] == del_course)
                )]
                save_schedule(schedule_df)
                st.success(f"{del_course} silindi.")
                st.rerun()
        my_sched = schedule_df[schedule_df["username"] == username].copy()
        fig = timetable_grid_figure(my_sched, "Haftalık Program")
        st.plotly_chart(fig, use_container_width=True)

    # -------- Katılım İşaretle --------
    elif choice == "Katılım İşaretle":
        st.header("Katılım İşaretle")
        if my_sched.empty:
            st.info("Önce ders ekleyin.")
            return
        fig = timetable_grid_figure(my_sched, "Haftalık Program")
        st.plotly_chart(fig, use_container_width=True)
        sel_date = st.date_input("Tarih", value=dt.date.today())
        weekday = sel_date.weekday()  # 0=Mon
        if weekday > 4:
            st.info("Hafta içi program gösteriliyor.")
        weekday_tr = DAYS_TR[min(weekday, 4)]
        todays = my_sched[my_sched["day"] == weekday_tr].sort_values("start")
        if todays.empty:
            st.info(f"{weekday_tr} günü ders yok.")
        else:
            st.write(f"{weekday_tr} dersleri:")
            _att_dates = pd.to_datetime(attendance_df["date"], errors="coerce").dt.date
            my_att_today = attendance_df[
                (attendance_df["username"] == username) & (_att_dates == sel_date)
            ]
            for _, r in todays.iterrows():
                label = f"{r['course']}  {r['start']}-{r['end']}"
                already = not my_att_today[my_att_today["course"] == r["course"]].empty
                checked = st.checkbox(label, value=already, key=f"att_{username}_{r['course']}_{sel_date}")
                if checked and not already:
                    add = pd.DataFrame([{
                        "username": username,
                        "course": r["course"],
                        "date": pd.to_datetime(sel_date),
                    }])
                    attendance_df = pd.concat([attendance_df, add], ignore_index=True)
                    save_attendance(attendance_df)
                    st.toast(f"{r['course']} için katılım kaydedildi.")
                elif not checked and already:
                    _att_dates = pd.to_datetime(attendance_df["date"], errors="coerce").dt.date
                    attendance_df = attendance_df[~(
                        (attendance_df["username"] == username) &
                        (attendance_df["course"] == r["course"]) &
                        (_att_dates == sel_date)
                    )]
                    save_attendance(attendance_df)
                    st.toast(f"{r['course']} katılımı silindi.")

    # -------- İstatistikler --------
    elif choice == "İstatistikler":
        st.header("Katılım İstatistikleri")
        my_att = attendance_df[attendance_df["username"] == username].copy()
        if my_att.empty:
            st.info("Katılım verisi yok.")
        else:
            # Bugüne kadar toplam ders sayısı
            all_sched = schedule_df[schedule_df["username"] == username].copy()
            if all_sched.empty:
                st.info("Önce program ekleyin.")
                return
            today = dt.date.today()
            attended = 0
            total = 0
            # Hafta sayısı ve dersleri hesapla
            current_date = SCHOOL_START_DATE
            while current_date <= today:
                weekday_idx = current_date.weekday()
                if weekday_idx <= 4:  # Pazartesi-Cuma
                    weekday_tr = DAYS_TR[weekday_idx]
                    day_courses = all_sched[all_sched["day"] == weekday_tr]
                    total += len(day_courses)
                current_date += dt.timedelta(days=1)
            attended = len(my_att)
            perc = (attended / total * 100) if total > 0 else 0
            summary = my_att.groupby("course").date.nunique().reset_index(name="Katılım Sayısı")
            st.dataframe(summary, use_container_width=True)
            st.metric("Toplam Katılım", attended)
            st.metric("Katılım Oranı", f"{perc:.1f}%")

    # -------- Sıralama --------
    else:
        st.header("Genel Sıralama")
        all_sched = load_schedule()
        all_att = load_attendance()
        if all_sched.empty or all_att.empty:
            st.info("Henüz veri yok.")
            return
        users = all_sched["username"].unique()
        results = []
        today = dt.date.today()
        for user in users:
            user_sched = all_sched[all_sched["username"] == user]
            user_att = all_att[all_att["username"] == user]
            attended = len(user_att)
            total = 0
            current_date = SCHOOL_START_DATE
            while current_date <= today:
                weekday_idx = current_date.weekday()
                if weekday_idx <= 4:
                    weekday_tr = DAYS_TR[weekday_idx]
                    day_courses = user_sched[user_sched["day"] == weekday_tr]
                    total += len(day_courses)
                current_date += dt.timedelta(days=1)
            perc = (attended / total * 100) if total > 0 else 0
            results.append({"Kullanıcı": user, "Toplam Katılım": attended, "Oran %": round(perc, 1)})
        ranking = pd.DataFrame(results).sort_values("Oran %", ascending=False)
        st.dataframe(ranking, use_container_width=True)

# ================== Main ==================
st.set_page_config(page_title="Ders Katılım", layout="wide")
if "username" not in st.session_state:
    login_ui()
else:
    dashboard(st.session_state["username"])
