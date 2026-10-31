/* Every command for exam day, grouped. Sources: the old topics 16/17/19, the Makefile,
   docker-compose.yml and server/pytest.ini. Shell: ps = PowerShell (Windows 11 default
   terminal), bash = Git Bash, any = both, sql = inside the mysql prompt. */

export type Shell = "ps" | "bash" | "any" | "sql";
export interface Cmd { title: string; cmd: string; shell?: Shell; dir?: string; note?: string; danger?: boolean; keys?: string }
export interface CmdGroup { id: string; title: string; icon: string; intro?: string; items: Cmd[] }

export const SHELL_LABEL: Record<Shell, string> = { ps: "PowerShell", bash: "Git Bash", any: "כל טרמינל", sql: "mysql>" };

export const GROUPS: CmdGroup[] = [
  {
    id: "run", title: "הרצה מקומית (native)", icon: "▶",
    intro: "קודם Docker Desktop ירוק. אחר כך טרמינל לכל תהליך, כולם מתיקיית הפרויקט.",
    items: [
      { title: "מסד נתונים (פעם אחת בכל הפעלה)", cmd: "docker compose up -d db", shell: "any", keys: "db mysql database" },
      { title: "שרת API (פורט 5002)", cmd: "cd server\n.venv\\Scripts\\activate\npython run.py", shell: "ps", note: "אין reload אוטומטי: אחרי שינוי בפייתון Ctrl+C ושוב python run.py.", keys: "server flask backend" },
      { title: "קליינט (פורט 5174)", cmd: "cd client\nnpm run dev", shell: "any", note: "HMR: שומרים קובץ והדפדפן מתעדכן לבד.", keys: "client vite react frontend" },
      { title: "worker (כדי שמשפטים יתקדמו)", cmd: "cd server\n.venv\\Scripts\\activate\npython run_worker.py", shell: "ps", keys: "worker tick scheduler" },
      { title: "לפתוח את האתר", cmd: "start http://localhost:5174", shell: "ps" },
      { title: "משתמשי דמו (בטוח להריץ שוב)", cmd: "cd server\n.venv\\Scripts\\activate\npython -m app.seed", shell: "ps", note: "admin@lolsuit.local · dana@ · yoni@ · maya@lolsuit.local, סיסמה demo1234.", keys: "seed users demo" },
      { title: "משפט שמתקדם בדקות (להוסיף ל־.env, ואז restart לשרת ול־worker)", cmd: "PHASE_MINUTES=2", shell: "any", note: "רק תיקים חדשים מקבלים את הקצב החדש.", keys: "phase minutes trial fast" },
      { title: "פייתון בלי activate", cmd: "cd server\n.venv\\Scripts\\python run.py", shell: "ps", note: "עובד גם כש־activate נחסם (execution policy)." },
    ],
  },
  {
    id: "docker", title: "Docker", icon: "🐳",
    intro: "בדוקר הקוד אפוי בתוך ה־image: אחרי שינוי קוד צריך --build לשירות ששונה.",
    items: [
      { title: "להרים הכול (האתר ב־8080)", cmd: "docker compose up --build -d", shell: "any", keys: "up start" },
      { title: "לבנות מחדש שירות אחד אחרי שינוי קוד", cmd: "docker compose up --build -d server", shell: "any", note: "server = API, web = הקליינט (nginx), worker. שינוי ב־server/app שה־worker משתמש בו: לבנות את שניהם.", keys: "rebuild" },
      { title: "סטטוס קונטיינרים", cmd: "docker compose ps", shell: "any" },
      { title: "לוגים של שירות", cmd: "docker compose logs -f server", shell: "any", note: "להחליף server ב־worker / web / db.", keys: "logs errors" },
      { title: "אתחול שירות (אחרי שינוי .env)", cmd: "docker compose up -d server", shell: "any", note: "restart לא קורא מחדש את .env; up -d כן יוצר את הקונטיינר מחדש עם הערכים החדשים." },
      { title: "לעצור הכול (הנתונים נשמרים)", cmd: "docker compose down", shell: "any" },
      { title: "לעצור רק את מה שמתנגש עם הרצה מקומית", cmd: "docker compose stop server worker web", shell: "any", note: "השרת בדוקר תופס את 5002." },
      { title: "איפוס מלא — מוחק את מסד הנתונים!", cmd: "docker compose down -v\ndocker compose up --build -d", shell: "any", danger: true, note: "init.sql רץ רק על volume ריק, אז זו הדרך להחיל שינוי סכמה.", keys: "reset wipe init.sql" },
      { title: "shell בתוך קונטיינר ה־API", cmd: "docker compose exec server /bin/bash", shell: "any" },
      { title: "seed מחדש בדוקר", cmd: "docker compose run --rm seed", shell: "any" },
    ],
  },
  {
    id: "test", title: "בדיקות", icon: "✓",
    intro: "טסטי integration ו־worker צריכים MySQL על 3307 (הם יוצרים DB זמני lolsuit_test). unit רצים גם בלי DB.",
    items: [
      { title: "כל הטסטים של השרת + כיסוי", cmd: "cd server\n.venv\\Scripts\\python -m pytest --cov", shell: "ps", keys: "pytest coverage" },
      { title: "רק יחידה (מהיר, בלי DB)", cmd: "cd server\n.venv\\Scripts\\python -m pytest -m unit -q", shell: "ps" },
      { title: "רק integration (HTTP דרך Flask)", cmd: "cd server\n.venv\\Scripts\\python -m pytest -m integration -q", shell: "ps" },
      { title: "רק worker", cmd: "cd server\n.venv\\Scripts\\python -m pytest -m worker -q", shell: "ps" },
      { title: "קובץ טסט אחד", cmd: "cd server\n.venv\\Scripts\\python -m pytest tests/unit/test_password_hashing.py -q", shell: "ps" },
      { title: "טסטים לפי שם", cmd: "cd server\n.venv\\Scripts\\python -m pytest -k \"password\" -q", shell: "ps", keys: "-k filter" },
      { title: "רק הטסטים שנכשלו בפעם הקודמת", cmd: "cd server\n.venv\\Scripts\\python -m pytest --lf -q", shell: "ps" },
      { title: "קליינט: טסטים", cmd: "cd client\nnpm test", shell: "any", keys: "vitest" },
      { title: "קליינט: בדיקת טיפוסים (lint)", cmd: "cd client\nnpm run lint", shell: "any", note: "tsc --noEmit עם noUnusedLocals: import מיותר מפיל." },
      { title: "קליינט: קובץ טסט אחד", cmd: "cd client\nnpx vitest run src/components/case/LikeButton.test.tsx", shell: "any" },
    ],
  },
  {
    id: "search", title: "חיפוש בקוד מהטרמינל", icon: "⌕",
    intro: "ב־Windows אין grep. git grep עובד בכל טרמינל, ורק על קבצים ש־git מכיר. בחלון הזה יש גם \"חיפוש בקוד\" ו\"שימושים\".",
    items: [
      { title: "כל המופעים של טקסט", cmd: "git grep -n \"איסוף עדויות\"", shell: "any", keys: "grep find" },
      { title: "רק בתיקייה", cmd: "git grep -n \"MIN_PASSWORD\" -- server/app client/src", shell: "any" },
      { title: "מילה שלמה בלבד", cmd: "git grep -nw \"toggle_like\"", shell: "any" },
      { title: "בלי תלות באותיות גדולות", cmd: "git grep -ni \"page_size\"", shell: "any" },
      { title: "רק שמות קבצים", cmd: "git grep -l \"likes_service\"", shell: "any" },
      { title: "חיפוש בטסטים בלבד", cmd: "git grep -n \"demo1234\" -- server/tests client/src/**/*.test.tsx", shell: "any" },
      { title: "VS Code: קובץ לפי שם / חיפוש בכל הפרויקט", cmd: "Ctrl+P   →  NewCase.tsx:40\nCtrl+Shift+F", shell: "any", note: "ב־Ctrl+P אפשר להדביק נתיב:שורה (כפתור \"העתק נתיב:שורה\" בחלונית הקוד)." },
    ],
  },
  {
    id: "git", title: "Git", icon: "⎇",
    items: [
      { title: "מה השתנה", cmd: "git status\ngit diff", shell: "any" },
      { title: "רק שמות הקבצים ששונו (בשביל בודק ה־diff)", cmd: "git status --short", shell: "any" },
      { title: "סיכום שינויים לפי קובץ", cmd: "git diff --stat", shell: "any" },
      { title: "ביטול שינוי בקובץ אחד", cmd: "git restore path/to/file", shell: "any" },
      { title: "ביטול כל השינויים בקבצים קיימים", cmd: "git checkout .", shell: "any", danger: true, note: "קבצים חדשים לא חוזרים עם זה." },
      { title: "להחביא שינויים ולהחזיר", cmd: "git stash\ngit stash pop", shell: "any" },
      { title: "מה git clean היה מוחק (בלי למחוק)", cmd: "git clean -n", shell: "any" },
      { title: "למחוק קבצים חדשים שלא ב־git", cmd: "git clean -fd", shell: "any", danger: true, note: "מוחק לצמיתות. קודם git clean -n." },
      { title: "ענף, שמירה ושליחה", cmd: "git switch -c feature/my-change\ngit add .\ngit commit -m \"feat: describe the change\"\ngit push -u origin feature/my-change", shell: "any", note: "בשולחן העבודה יש מחולל שממלא את זה מהשינוי שלך." },
      { title: "5 ה־commits האחרונים", cmd: "git log --oneline -5", shell: "any" },
      { title: "מה בדיוק השתנה ב־commit האחרון", cmd: "git show --stat HEAD", shell: "any" },
    ],
  },
  {
    id: "api", title: "API, curl ובדיקה ידנית", icon: "⇄",
    intro: "ב־Windows PowerShell 5.1 המילה curl היא בעצם Invoke-WebRequest. כותבים curl.exe, או משתמשים ב־Invoke-RestMethod.",
    items: [
      { title: "בדיקת בריאות (DB, phase_minutes, worker)", cmd: "curl.exe -s http://localhost:5002/api/health", shell: "ps", keys: "health" },
      { title: "בריאות דרך nginx (דוקר)", cmd: "curl.exe -s http://localhost:8080/api/health", shell: "ps" },
      { title: "התחברות ושמירת העוגייה (PowerShell)", cmd: "$s = New-Object Microsoft.PowerShell.Commands.WebRequestSession\nInvoke-RestMethod -Method Post -Uri http://localhost:5002/api/auth/login -WebSession $s -ContentType 'application/json' -Body '{\"email\":\"dana@lolsuit.local\",\"password\":\"demo1234\"}'", shell: "ps", keys: "login cookie session" },
      { title: "קריאה מחוברת (אחרי השורה הקודמת)", cmd: "Invoke-RestMethod -Uri 'http://localhost:5002/api/cases?limit=2' -WebSession $s | ConvertTo-Json -Depth 5", shell: "ps" },
      { title: "POST מחובר, למשל לייק לתיק 1", cmd: "Invoke-RestMethod -Method Post -Uri http://localhost:5002/api/cases/1/like -WebSession $s", shell: "ps" },
      { title: "לראות שגיאה (400/403) עם הגוף שלה", cmd: "try { Invoke-RestMethod -Method Post -Uri http://localhost:5002/api/cases -WebSession $s -ContentType 'application/json' -Body '{\"title\":\"ab\"}' } catch { $_.ErrorDetails.Message }", shell: "ps", keys: "error validation 400" },
      { title: "התחברות וקריאה (Git Bash)", cmd: "curl -s -c /tmp/c.txt -H 'Content-Type: application/json' -d '{\"email\":\"dana@lolsuit.local\",\"password\":\"demo1234\"}' http://localhost:5002/api/auth/login\ncurl -s -b /tmp/c.txt 'http://localhost:5002/api/cases?limit=2'", shell: "bash" },
    ],
  },
  {
    id: "db", title: "MySQL", icon: "⛁",
    intro: "משתמש lolsuit / lolsuit-dev, DB בשם lolsuit, פורט 3307 במחשב. root: lolsuit-root-dev.",
    items: [
      { title: "prompt של mysql בתוך הקונטיינר", cmd: "docker compose exec db mysql -ulolsuit -plolsuit-dev --default-character-set=utf8mb4 lolsuit", shell: "any", keys: "mysql shell db-shell" },
      { title: "כל הטבלאות", cmd: "SHOW TABLES;", shell: "sql" },
      { title: "המבנה של טבלה", cmd: "DESCRIBE cases;", shell: "sql" },
      { title: "התיקים האחרונים", cmd: "SELECT id, title, status, created_at FROM cases ORDER BY id DESC LIMIT 5;", shell: "sql" },
      { title: "המשתמשים האנושיים", cmd: "SELECT id, name, email, is_admin FROM users WHERE email NOT LIKE '%@bots.lolsuit.local';", shell: "sql" },
      { title: "להוסיף עמודה בלי למחוק נתונים", cmd: "ALTER TABLE cases ADD COLUMN my_field VARCHAR(100) NULL;", shell: "sql", note: "ואותו שינוי גם ב־database/init.sql, כדי שהתקנה חדשה תקבל אותו." },
      { title: "שאילתה אחת בלי להיכנס ל־prompt", cmd: "docker compose exec db mysql -ulolsuit -plolsuit-dev lolsuit -e \"SELECT COUNT(*) FROM cases;\"", shell: "any" },
    ],
  },
  {
    id: "ports", title: "פורטים ותהליכים תקועים", icon: "⚡",
    items: [
      { title: "מי תופס את פורט 5002", cmd: "netstat -ano | findstr :5002", shell: "ps", keys: "port in use" },
      { title: "להרוג תהליך לפי PID", cmd: "taskkill /PID 12345 /F", shell: "ps", danger: true },
      { title: "להרוג את מי שתופס פורט (שורה אחת)", cmd: "Get-NetTCPConnection -LocalPort 5002 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }", shell: "ps", danger: true },
      { title: "activate נחסם (execution policy)", cmd: "Set-ExecutionPolicy -Scope CurrentUser RemoteSigned", shell: "ps" },
      { title: "PowerShell 5.1 בלי && — מחברים עם ;", cmd: "cd server; .venv\\Scripts\\python -m pytest -m unit -q", shell: "ps" },
    ],
  },
  {
    id: "setup", title: "התקנה מאפס", icon: "⚙",
    items: [
      { title: "כלים (פעם אחת)", cmd: "winget install Git.Git\nwinget install Docker.DockerDesktop\nwinget install OpenJS.NodeJS.LTS\nwinget install Python.Python.3.12", shell: "ps" },
      { title: "הפרויקט, מתיקיית השורש", cmd: "copy .env.example .env\ndocker compose up -d db\ncd server\npy -m venv .venv\n.venv\\Scripts\\activate\npip install -r requirements-dev.txt\npython -m app.seed\ncd ..\\client\nnpm install", shell: "ps" },
      { title: "חסר .env (Access denied ל־DB)", cmd: "copy .env.example .env", shell: "ps", keys: "env access denied" },
      { title: "חסרות חבילות", cmd: "cd server\n.venv\\Scripts\\pip install -r requirements-dev.txt\ncd ..\\client\nnpm install", shell: "ps" },
    ],
  },
  {
    id: "release", title: "שחרור ופריסה", icon: "🚀",
    intro: "במחשב בונים ודוחפים images ל־Docker Hub, ובשרת (EC2) מושכים ומפעילים. הסקריפטים רצים ב־Git Bash. אפשרויות: --server-only, --web-only, --no-latest, --git-tag, --allow-dirty, -n/--dry-run.",
    items: [
      { title: "להתחבר ל־Docker Hub (פעם אחת)", cmd: "docker login", shell: "any" },
      { title: "הרצת ניסיון (לא בונה ולא דוחף)", cmd: "./prod/release.sh v5.0.2 --dry-run", shell: "bash" },
      { title: "שחרור אמיתי + tag בגיט", cmd: "./prod/release.sh v5.0.2 --git-tag", shell: "bash", danger: true },
      { title: "בשרת: להפעיל גרסה (חוזר לבד אם health נכשל)", cmd: "cd /opt/lolsuit/prod && ./deploy.sh v5.0.2", shell: "bash" },
      { title: "בשרת: חזרה לגרסה הקודמת", cmd: "cd /opt/lolsuit/prod && ./deploy.sh --rollback", shell: "bash" },
      { title: "איזו גרסה יש (tags)", cmd: "git tag --sort=-v:refname\ngit describe --tags", shell: "any" },
    ],
  },
];
