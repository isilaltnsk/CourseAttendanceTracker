# app.py
import streamlit as st
import pandas as pd
import datetime as dt
import hashlib
from pathlib import Path
import plotly.graph_objects as go
import subprocess
import os

# ================== Dosya / sabitler ==================
USER_DB = Path("users.csv")
ATTENDANCE_DB = Path("attendance.csv")
SCHEDULE_DB = Path("schedule.csv")

DAYS_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
DAY_IDX = {d: i for i, d in enumerate(DAYS_TR)}
HOUR_START = 8
HOUR_END = 19
SCHOOL_START_DATE = dt.date(2025, 9, 29)  # okulun başladığı tarih

# ================== Yardımcı fonksiyonlar ==================
def hash_password(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()

def _time_to_hours(hhmm: str) -> float:
    hh, mm = hhmm.split(":")
    return int(hh) + int(mm) / 60

def run_cmd(cmd, check=True, cwd=None):
    """subprocess.run helper - returns CompletedProcess"""
    return subprocess.run(cmd, capture_output=True, text=True, check=check, cwd=cwd)

# ================== GIT / PUSH ==================
def git_push(auto_commit_message="Auto-save from app"):
    """
    Git push helper.
    Requires Streamlit secrets:
      - MY_GITHUB_REPO_URL  (e.g. https://github.com/username/repo.git)
      - MY_GITHUB_TOKEN     (personal access token with repo scope)
    If .git doesn't exist, tries to init and add remote.
    Returns (ok: bool, msg: str)
    """
    repo_url = st.secrets.get("MY_GITHUB_REPO_URL")
    token = st.secrets.get("MY_GITHUB_TOKEN")
    if not repo_url or not token:
        return False, "Secrets eksik (MY_GITHUB_REPO_URL / MY_GITHUB_TOKEN)."

    # ensure we're in repo root (same directory as this app)
    repo_dir = Path.cwd()

    try:
        # if .git missing -> init and add remote
        if not (repo_dir / ".git").exists():
            run_cmd(["git", "init"], check=True, cwd=repo_dir)
            run_cmd(["git", "remote", "add", "origin", repo_url], check=True, cwd=repo_dir)

        # git config user if secrets provide
        git_name = st.secrets.get("MY_GIT_NAME")
        git_email = st.secrets.get("MY_GIT_EMAIL")
        if git_name:
            run_cmd(["git", "config", "user.name", git_name], check=False, cwd=repo_dir)
        if git_email:
            run_cmd(["git", "config", "user.email", git_email], check=False, cwd=repo_dir)

        # stage changed CSVs only (safer)
        run_cmd(["git", "add", ATTENDANCE_DB.as_posix(), SCHEDULE_DB.as_posix(), USER_DB.as_posix()], check=False, cwd=repo_dir)

        # commit (allow no changes)
        commit = run_cmd(["git", "commit", "-m", auto_commit_message], check=False, cwd=repo_dir)
        # it's okay if commit returned non-zero (no changes), continue to push attempt

        # construct auth URL with token injected
        auth_url = repo_url.replace("https://", f"https://{token}@")

        # detect current branch (fallback to main)
        br = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=False, cwd=repo_dir)
        branch = br.stdout.strip() if br.returncode == 0 and br.stdout.strip() else "main"

        # push
        push = run_cmd(["git", "push", auth_url, f"HEAD:{branch}"], check=True, cwd=repo_dir)
        return True, "Push başarılı."
    except subprocess.CalledProcessError as e:
        # return stderr for debugging (but not token)
        stderr = (e.stderr or "").strip()
        # hide token from message if present
        if token and isinstance(stderr, str):
            stderr = stderr.replace(token, "[TOKEN]")
        return False, f"Push hatası: {stderr or str(e)}"
    except Exception as e:
        return False, f"Beklenmeyen hata: {e}"

# ================== CSV load/save ==================
def load_users():
    if USER_DB.exists():
        return pd.read_csv(USER_DB)
    return pd.DataFrame(columns=["username", "password"])

def save_users(df: pd.DataFrame):
    df.to_csv(USER_DB, index=False)
    ok, msg = git_push("Kullanıcılar güncellendi")
    if not ok:
        st.warning(f"Git push başarısız: {msg}")

def load_attendance():
    if ATTENDANCE_DB.exists():
        df = pd.read_csv(ATTENDANCE_DB)
        if "date" in df.columns:
            # normalize to date (no time)
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        return df
    return pd.DataFrame(columns=["username", "course", "date"])

def save_attendance(df: pd.DataFrame):
    df.to_csv(ATTENDANCE_DB, index=False)
    ok, msg = git_push("Attendance güncellendi")
    if not ok:
        st.warning(f"Git push başarısız: {msg}")

def load_schedule():
    if SCHEDULE_DB.exists():
        return pd.read_csv(SCHEDULE_DB)
    return pd.DataFrame(columns=["username", "course", "day", "start", "end"])

def save_schedule(df: pd.DataFrame):
    df.to_csv(SCHEDULE_DB, index=False)
    ok, msg = git_push("Program güncellendi")
    if not ok:
        st.warning(f"Git push başarısız: {msg}")

# ================== Takvim görseli ==================
def timetable_grid_figure(schedule_df: pd.DataFrame, title: str = "Haftalık Program"):
    fig = go.Figure()
    fig.update_layout(template="plotly_white", height=700,
                      margin=dict(l=70, r=40, t=50, b=40), title=title,
                      xaxis=dict(range=[-0.5, len(DAYS_TR)-0.5],
                                 tickmode="array", tickvals=list(range(len(DAYS_TR))), ticktext=DAYS_TR,
                                 showgrid=True, dtick=1, zeroline=False),
                      yaxis=dict(range=[HOUR_END, HOUR_START], tick0=HOUR_START, dtick=1,
                                 tickformat="02d:00", showgrid=True, zeroline=False),
                      showlegend=False)
    if schedule_df.empty:
        return fig
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
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
        fig.add_shape(type="rect", x0=x-0.45, x1=x+0.45, y0=y0, y1=y1,
                      line=dict(color=c, width=1.5), fillcolor=c, opacity=0.88)
        fig.add_annotation(x=x, y=(y0+y1)/2, text=f"{r['course']}<br>{r['start']}–{r['end']}",
                           showarrow=False, font=dict(color="white", size=12), xanchor="center", yanchor="middle")
    return fig

# ================== UI: Giriş / Kayıt ==================
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
            ok = users_df[(users_df["username"] == username) & (users_df["password"] == hashed)]
            if not ok.empty:
                st.session_state["username"] = username
                st.rerun()
            else:
                st.error("Geçersiz kullanıcı adı/şifre.")

# ================== Dashboard ==================
def dashboard(username: str):
    st.sidebar.write(f"Hoş geldin, **{username}**")
    if st.sidebar.button("Çıkış Yap"):
        st.session_state.clear()
        st.rerun()

    menu = ["Ders Programı", "Katılım İşaretle", "İstatistikler", "Sıralama"]
    choice = st.sidebar.radio("Menü", menu)

    schedule_df = load_schedule()
    attendance_df = load_attendance()
    my_sched = schedule_df[schedule_df["username"] == username].copy()

    # Ders Programı
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
        my_sched = schedule_df[schedule_df["username"] == username].copy()
        if not my_sched.empty:
            st.subheader("Ders Sil")
            del_course = st.selectbox("Silmek istediğiniz ders", my_sched["course"].unique())
            if st.button("Sil"):
                schedule_df = schedule_df[~((schedule_df["username"] == username) & (schedule_df["course"] == del_course))]
                save_schedule(schedule_df)
                st.success(f"{del_course} silindi.")
                st.rerun()

        my_sched = schedule_df[schedule_df["username"] == username].copy()
        fig = timetable_grid_figure(my_sched, "Haftalık Program")
        st.plotly_chart(fig, use_container_width=True)

    # Katılım İşaretle
    elif choice == "Katılım İşaretle":
        st.header("Katılım İşaretle")
        if my_sched.empty:
            st.info("Önce ders ekleyin.")
            return

        fig = timetable_grid_figure(my_sched, "Haftalık Program")
        st.plotly_chart(fig, use_container_width=True)

        sel_date = st.date_input("Tarih", value=dt.date.today())
        weekday = sel_date.weekday()
        if weekday > 4:
            st.info("Hafta içi program gösteriliyor.")
        weekday_tr = DAYS_TR[min(weekday, 4)]

        todays = my_sched[my_sched["day"] == weekday_tr].sort_values("start")
        if todays.empty:
            st.info(f"{weekday_tr} günü ders yok.")
        else:
            st.write(f"{weekday_tr} dersleri:")
            # attendance_df["date"] already normalized to date
            my_att_today = attendance_df[(attendance_df["username"] == username) & (attendance_df["date"] == sel_date)]
            for _, r in todays.iterrows():
                label = f"{r['course']}  {r['start']}-{r['end']}"
                already = not my_att_today[my_att_today["course"] == r["course"]].empty
                checked = st.checkbox(label, value=already, key=f"att_{username}_{r['course']}_{sel_date}")
                if checked and not already:
                    add = pd.DataFrame([{"username": username, "course": r["course"], "date": sel_date}])
                    attendance_df = pd.concat([attendance_df, add], ignore_index=True)
                    save_attendance(attendance_df)
                    st.toast(f"{r['course']} için katılım kaydedildi.")
                elif not checked and already:
                    attendance_df = attendance_df[~((attendance_df["username"] == username) &
                                                    (attendance_df["course"] == r["course"]) &
                                                    (attendance_df["date"] == sel_date))]
                    save_attendance(attendance_df)
                    st.toast(f"{r['course']} katılımı silindi.")

    # İstatistikler (bugüne kadar)
    elif choice == "İstatistikler":
        st.header("Katılım İstatistikleri (Bugüne Kadar)")
        my_att = attendance_df[attendance_df["username"] == username].copy()
        if my_sched.empty:
            st.info("Önce program ekleyin.")
            return
        if my_att.empty:
            st.info("Henüz katılım verisi yok.")
            return

        today = dt.date.today()
        # bugünden önce ve bugün dahil gerçekleşmiş derslerin sayısını hesapla
        total_possible = 0
        # iterate from SCHOOL_START_DATE to today inclusive
        for d in pd.date_range(SCHOOL_START_DATE, today):
            if d.weekday() > 4:
                continue
            weekday_tr = DAYS_TR[d.weekday()]
            daily = my_sched[my_sched["day"] == weekday_tr]
            total_possible += len(daily)

        total_attended = len(my_att[my_att["date"] <= today])
        percentage = (total_attended / total_possible * 100) if total_possible > 0 else 0

        summary = my_att.groupby("course")["date"].nunique().reset_index(name="Katılım Sayısı")
        st.dataframe(summary, use_container_width=True)
        st.metric("Toplam Katılım", int(total_attended))
        st.metric("Katılım Oranı", f"{percentage:.1f}%")

    # Sıralama (genel)
    else:
        st.header("Genel Sıralama (Bugüne Kadar)")
        all_sched = load_schedule()
        all_att = load_attendance()
        if all_sched.empty or all_att.empty:
            st.info("Henüz veri yok.")
            return
        today = dt.date.today()
        results = []
        for user in all_sched["username"].unique():
            user_sched = all_sched[all_sched["username"] == user]
            user_att = all_att[all_att["username"] == user]
            # hesapla: bugüne kadar kaç ders olmalıydı
            total_possible = 0
            for d in pd.date_range(SCHOOL_START_DATE, today):
                if d.weekday() > 4:
                    continue
                weekday_tr = DAYS_TR[d.weekday()]
                total_possible += len(user_sched[user_sched["day"] == weekday_tr])
            total_attended = len(user_att[user_att["date"] <= today])
            perc = (total_attended / total_possible * 100) if total_possible > 0 else 0
            results.append({"Kullanıcı": user, "Toplam Katılım": int(total_attended), "Oran %": round(perc, 1)})
        ranking = pd.DataFrame(results).sort_values("Oran %", ascending=False).reset_index(drop=True)
        st.dataframe(ranking, use_container_width=True)

# ================== Main ==================
st.set_page_config(page_title="Ders Katılım", layout="wide")
if "username" not in st.session_state:
    login_ui()
else:
    dashboard(st.session_state["username"])
