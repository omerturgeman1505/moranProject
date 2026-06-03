# Moran Job Search Project - מבנה ואיך זה עובד

## מטרה
מערכת חיפוש משרות למורן, Junior R&D Engineer עם B.Sc. Medical Engineering.  
המערכת סורקת משרות, מסננת לפי התאמה לקורות החיים, מסמנת משרות "לוהטות", שומרת ב-Firebase Realtime Database, והאתר מציג טאבים:
- מתאימות למורן
- פחות מתאימות, שוות בדיקה
- חדשות
- לוהטות
- הגשתי

## זרימת עבודה
1. הסריקה רצה דרך GitHub Actions ידני: `.github/workflows/manual-scan.yml`
2. ה-workflow מריץ: `python daily_scan.py`
3. `daily_scan.py` טוען `job_search_platform`, מפעיל `apply_moran_profile(platform)` מ-`moran_profile.py`, מריץ `run_cloud_scan`, מעדכן `/scan_status`
4. `job_search_platform.py` סורק, מסנן, בודק חיות, שולף דרישות, מחשב `is_hot` / `fit_category` / `fit_reason`, שומר ל-`/jobs`, `/job_state`, `/meta`
5. האתר `public/index.html` (Firebase Hosting) קורא מ-`/jobs` ו-`/applied` — **אין** כפתור "הרץ סריקה"

## קבצים חשובים
- `daily_scan.py` — נקודת כניסה לסריקה (GitHub Actions / מקומי)
- `job_search_platform.py` — scraping, filtering, scoring, RTDB
- `moran_profile.py` — פרופיל ההתאמה של מורן (חובה לפני סריקה)
- `job_sections.py` / `public/job_sections.js` — פיצול טקסט משרה לסעיפים דו-לשוניים
- `public/index.html` — דשבורד Firebase Hosting
- `database.rules.json`, `firebase.json`
- `test_job_search_platform.py`, `test_job_sections.py`

## Firebase
- Project: `moran-cce72`
- Hosting: https://moran-cce72.web.app
- RTDB: https://moran-cce72-default-rtdb.europe-west1.firebasedatabase.app
- Nodes: `/jobs`, `/job_state`, `/meta`, `/scan_status`, `/applied`

## GitHub Actions
- Workflow: https://github.com/omerturgeman1505/moranProject/actions/workflows/manual-scan.yml
- Secret: `FIREBASE_SERVICE_ACCOUNT_JSON`

## פקודות
```bash
pip install -r requirements.txt
python -m unittest test_job_sections.py test_job_search_platform.py -v
python daily_scan.py
firebase deploy --only hosting,database --project moran-cce72
```

## כרטיס משרה פתוח — סדר סעיפים
1. למה זה מתאים למורן
2. תיאור / אחריות / דרישות / יתרונות (לפי מה שקיים בטקסט)
3. התאמות שנמצאו
4. מידע נוסף

## לא לשבור
- לא להעלות `.env`, service account JSON, sqlite
- לא להחזיר כפתור סריקה לאתר הציבורי
- `moran_profile.py` חייב להיטען לפני סריקה
- retention: 7 ימים למשרות שלא סומנו "הגשתי"; applied נשמרות
