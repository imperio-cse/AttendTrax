# 🏆 AttendTrax Enterprise – Summit Presentation & Live Demo Cheat Sheet

> **For the Principal, Vice-Principal & Academic Coordinators Demonstration**  
> *Everything below is 100% live, connected to Supabase PostgreSQL (12,558 records), and synchronized in real time with Google Sheets.*

---

## 1. Quick Access Links

| Portal / Service | Live URL / Access | Description |
| :--- | :--- | :--- |
| **Institutional Web Portal** | `https://attendtrax-frontend.vercel.app` (or `http://localhost:5500`) | Multi-role portal for Admin, Faculty & Students |
| **Backend API Engine** | `https://attendtrax-api.onrender.com` (or `http://127.0.0.1:8000/docs`) | FastAPI high-speed backend |
| **Supabase Cloud DB** | `db.ubkvrgwwelrrwqtlmqcq.supabase.co:5432` | **12,558 live records across 8 departments** |
| **Main Gate Security Scanner** | `https://attendtrax-frontend.vercel.app/gatepass.html` | High-contrast outpass QR gate scanner & warden queue |
| **Live Google Sheet Register** | [Google Sheets Projector Link](https://docs.google.com/spreadsheets/d/1BKKiXO1LDadRIOBg6o16t72tpFabOMEq85-rVlXIJcQ) | Visual spreadsheet reflecting live attendance marks |

---

## 2. Institutional Demo Credentials Cheat Sheet

### 🏛️ Executive C-Suite (Principal & Vice-Principal)
| Role | Username | Password | Designated Portal | Features to Show |
| :--- | :--- | :--- | :--- | :--- |
| **Principal** | `principal` | `Principal@2026` | `admin.html` (Executive Cockpit) | 8-Dept Leaderboard, Defaulter Radar, 1-Click Leave Sign-Off |
| **Vice Principal** | `viceprincipal` | `VP@2026` | `admin.html` (Executive Cockpit) | Macro campus statistics, today's class compliance |
| **Central Admin** | `admin` | `AttendTrax@2026` | `admin.html` | System administration & user management |

### 🏢 Department Heads (HODs)
| Department | Username | Password | Focus |
| :--- | :--- | :--- | :--- |
| **CSE HOD** | `hod.cse` | `Hod@2026` | Computer Science Department & Faculty review |
| **ECE HOD** | `hod.ece` | `Hod@2026` | Electronics & Communication Department |
| **EEE HOD** | `hod.eee` | `Hod@2026` | Electrical & Electronics Department |
| **MECH HOD** | `hod.mech` | `Hod@2026` | Mechanical Engineering Department |
| **CIVIL HOD** | `hod.civil` | `Hod@2026` | Civil Engineering Department |
| **IT HOD** | `hod.it` | `Hod@2026` | Information Technology Department |
| **AI&DS HOD** | `hod.aids` | `Hod@2026` | Artificial Intelligence & Data Science |
| **CSBS HOD** | `hod.csbs` | `Hod@2026` | CS & Business Systems Department |

### 🛡️ Campus Wardens & Gate Security
| Role | Username | Password | Portal | Key Task |
| :--- | :--- | :--- | :--- | :--- |
| **Boys Hostel Warden** | `warden.boys` | `Warden@2026` | `gatepass.html` | Approves outpasses for hostellers |
| **Girls Hostel Warden** | `warden.girls` | `Warden@2026` | `gatepass.html` | Approves outpasses for hostellers |
| **Main Gate Security** | *(Use Warden or Admin)* | `Warden@2026` | `gatepass.html` | Scans 32-char QR tokens for exit/entry |

### 👨‍🏫 Faculty & 🎓 Students
| Role | Username | Password | Portal |
| :--- | :--- | :--- | :--- |
| **CSE Faculty** | `fathima.cse` | `Staff@2026` | `faculty.html` |
| **ECE Faculty** | `senthil.ece` | `Staff@2026` | `faculty.html` |
| **Student (CSE 3A)** | `410123104041` | `Student@2026` *(or `410123104041@CSE`)* | `student.html` |
| **Student (ECE 2A)** | `410125106001` | `Student@2026` | `student.html` |

---

## 3. The 3-Minute Live Knockout Demonstration Script

### Act 1: Live Classroom Attendance & Dual Sync (1 minute)
1. Open the **Google Sheet** on the projector screen.
2. On your mobile phone, go to `index.html` and sign in as **`fathima.cse`** / `Staff@2026`.
3. Select **CSE 3A (III Year A)** and click **Load Students**.
4. Toggle 2 students as **Absent (A)** and 1 as **On-Duty (OD)**.
5. Click **Submit Attendance**.
6. **The Wow Moment**: Point to the projector screen—the Google Sheet turns green, red, and orange in real time, while the backend records the data in Supabase in under 10 milliseconds!

### Act 2: Smart Student Outpass & Gate Security Scanner (1 minute)
1. On phone 2 (or incognito window), sign in as student **`410123104041`** / `Student@2026`.
2. Click **Apply for Leave / Outpass**, select **Gate Pass (Outpass)**, choose date and enter reason: *"Weekend project presentation"*. Click **Submit**.
3. Sign in as **`warden.boys`** / `Warden@2026` on `gatepass.html`.
4. Click **Issue Pass**.
5. Back on the student screen, refresh: **A dynamic cryptographic QR Gatepass with countdown validity appears!**
6. On `gatepass.html`, paste or scan the pass token in the **Security Terminal** and click **Verify & Log Exit**.
7. Status immediately turns **EXIT RECORDED** with gate clearance timestamp.

### Act 3: Principal Executive Cockpit & 1-Click Sign-Off (1 minute)
1. On the laptop/projector, sign in as **`principal`** / `Principal@2026`.
2. The page automatically launches the **Executive Academic Intelligence Cockpit**:
   - Show the **8-Department Comparison Leaderboard** (Bar charts showing CSE 92%, AI&DS 89%, ECE 87%, etc.).
   - Show the **Campus Attendance Gauge (88.9%)** and **Defaulter Risk Matrix (<65% Critical)**.
   - Use the **Department Scope Switcher** to drill down into `Mechanical` or `ECE`.
3. Scroll to **HOD-Endorsed Faculty Leaves Queue**:
   - Point out Prof. Fathima's leave application for doctoral committee meeting (already endorsed by HOD Dr. Antony Sudha).
   - Click **✓ Approve**.
   - The badge instantly turns green: **"Approved by Principal"**!

---

## 4. Setting Render Backend to use Supabase (1 Minute Step)

To ensure your live deployed Render backend uses your Supabase database:
1. Log into your [Render Dashboard](https://dashboard.render.com).
2. Click your **`attendtrax-api`** service.
3. Click **Environment** on the left menu.
4. Add or update the variable:
   - **Key**: `DATABASE_URL`
   - **Value**: `postgresql+asyncpg://postgres:bY69u08s7eu0aKZo@db.ubkvrgwwelrrwqtlmqcq.supabase.co:5432/postgres`
5. Click **Save Changes**.
6. Render will automatically deploy in ~60 seconds with 100% Supabase connectivity!

---

## 5. Local 1-Click Startup (Backup if Internet is Down)

If the presentation hall Wi-Fi has issues:
1. Double-click `run_local.bat` or run in PowerShell:
   ```powershell
   # Terminal 1 (Backend):
   cd backend
   .\venv\Scripts\activate
   uvicorn main:app --reload --port 8000

   # Terminal 2 (Frontend):
   cd frontend
   python -m http.server 5500
   ```
2. Open `http://localhost:5500` in Google Chrome. Everything works identically!
