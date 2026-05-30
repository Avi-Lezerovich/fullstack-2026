/**
 * In-memory mock backend.
 * Lets the whole app run with no server: data lives in localStorage so signups
 * and new posts survive a page reload. api.ts routes here when USE_MOCK_DATA is on.
 */
import type {
  AuthResponse,
  Post,
  User,
  UserListItem,
  UserProfileResponse,
} from "./types";

type StoredUser = User & { password: string };

type MockState = {
  users: StoredUser[];
  posts: Post[];
  nextUserId: number;
  nextPostId: number;
};

const STORAGE_KEY = "lolsuit_mock_state_v3";

const now = Date.now();
const hoursAgo = (hours: number): string => new Date(now - hours * 3_600_000).toISOString();
const daysAgo = (days: number): string => new Date(now - days * 86_400_000).toISOString();

const createDefaultState = (): MockState => {
  const users: StoredUser[] = [
    { id: 1, name: "דנה כהן", email: "dana@example.com", password: "demo123", created_at: daysAgo(30) },
    { id: 2, name: "יואב לוי", email: "yoav@example.com", password: "demo123", created_at: daysAgo(29) },
    { id: 3, name: "מאיה שטרן", email: "maya@example.com", password: "demo123", created_at: daysAgo(28) },
    { id: 4, name: "איתי אברמוב", email: "itay@example.com", password: "demo123", created_at: daysAgo(27) },
    { id: 5, name: "רוני גולן", email: "roni@example.com", password: "demo123", created_at: daysAgo(26) },
    { id: 6, name: "נועה פרידמן", email: "noa@example.com", password: "demo123", created_at: daysAgo(25) },
    { id: 7, name: "אלון ברק", email: "alon@example.com", password: "demo123", created_at: daysAgo(24) },
    { id: 8, name: "מיכל שלו", email: "michal@example.com", password: "demo123", created_at: daysAgo(23) },
    { id: 9, name: "תומר אזולאי", email: "tomer@example.com", password: "demo123", created_at: daysAgo(22) },
    { id: 10, name: "עדי בלום", email: "adi@example.com", password: "demo123", created_at: daysAgo(21) },
    { id: 11, name: "גיא מזרחי", email: "guy@example.com", password: "demo123", created_at: daysAgo(20) },
    { id: 12, name: "ליהי שדה", email: "lihi@example.com", password: "demo123", created_at: daysAgo(19) },
  ];

  const posts: Post[] = [
    {
      id: 1,
      title: "הכלב שסירב לזוז מהספה",
      body: "הוריתי בנימוס לנתבע לפנות את הספה. הוא הביט בי, נאנח, וסירב להזיז גף אחד. נאלצתי לישון בכורסה הקטנה כמו פליט בביתי שלי. ניסיתי לפתות אותו בחטיף יוקרתי, אך הוא לקח את החטיף, התמתח לכל אורך הספה, והביט בי במבט של מי שיודע שהחוק לצידו. בית המשפט הנכבד מתבקש להכריע, אחת ולתמיד, מי בעל הבית בסלון הזה — האדם ששילם על הספה, או הכלב שישן עליה.",
      defendant: "קוקי הגולדן",
      location: "סלון, דירה 4 קומה ב",
      charges: ["רשלנות פלילית", "עיכוב כרוני"],
      author_id: 1,
      author_name: "דנה כהן",
      created_at: hoursAgo(2),
    },
    {
      id: 2,
      title: "החבר שביטל יום לפני הטיול",
      body: "הזמנו צימר. שילמנו מקדמה. תכננתי ארבעה חודשים. יום לפני הוא כתב שהוא נשאר בבית. תובע פיצוי על נזק נפשי, אובדן חופשה ועלבון אישי. הסיבה שמסר הייתה 'לא בא לי בסוף', כאילו מדובר בהזמנת פיצה ולא בטיול שתוכנן בקפידה במשך חודשים. כבר קניתי כובע מצחיה תואם וערכתי פלייליסט. בית המשפט מתבקש לקבוע שביטול ברגע האחרון הוא לא זכות, אלא עוולה חברתית לכל דבר ועניין.",
      defendant: "דניאל מ.",
      location: "WhatsApp, 23:14",
      charges: ["בגידה חברתית", "הפרת שלוות נפש", "מניפולציה רגשית"],
      author_id: 2,
      author_name: "יואב לוי",
      created_at: hoursAgo(5),
    },
    {
      id: 3,
      title: "השכן שמנגן גיטרה בחצות",
      body: "בכל לילה ב-23:58 הוא מנגן את אותם ארבעה אקורדים של Wonderwall. לא מסיים את השיר. רק האינטרו. אני שומע אותו גם בחלומות. ניסיתי לדפוק בקיר, לשלוח פתק מנומס מתחת לדלת, ואפילו להשמיע בחזרה שיר אחר בעוצמה — אך שום דבר לא עוצר אותו. נדמה שהוא מאמין שיום אחד, אם רק ינגן את האינטרו מספיק פעמים, השיר סוף סוף יסתיים מעצמו. בית המשפט מתבקש להגן על שלוות הלילה של כל הבניין.",
      defendant: "השכן מקומה 3",
      location: "בניין ברחוב הירקון, תל אביב",
      charges: ["הפרת שלוות נפש", "ייאוש מכוון"],
      author_id: 3,
      author_name: "מאיה שטרן",
      created_at: daysAgo(1),
    },
    {
      id: 4,
      title: "הברמן ששפך עליי קפה ולא התנצל",
      body: "הזמנתי קפוצ'ינו. הברמן החליק, שפך חצי עליי, אמר 'טוב נו' וחזר לבר. החולצה הלבנה החדשה שלי הפכה למפת גלקסיה חומה. לא התנצלות, לא מגבת, לא הצעה לנקות — רק 'טוב נו' שנאמר בנימה של מי שעושה לי טובה. ישבתי שם רטוב, מבוייש ומריח כמו בית קפה שלם, בעוד הוא ממשיך להקציף חלב כאילו דבר לא קרה. בית המשפט מתבקש לקבוע ש'טוב נו' אינו פיצוי מספק על חולצה הרוסה.",
      defendant: "הברמן עם הקוקו",
      location: "בית קפה ברחוב דיזנגוף",
      charges: ["רשלנות פלילית", "מניפולציה רגשית"],
      author_id: 4,
      author_name: "איתי אברמוב",
      created_at: hoursAgo(27),
    },
    {
      id: 5,
      title: "האחות הקטנה שגנבה את הטעינה",
      body: "המטען נשאר בחדרי לבטח, מחובר לשקע. בשובי מהמקלחת הוא נעלם. הנתבעת שיחקה ב-Roblox כאילו לא קרה דבר. כששאלתי, היא ענתה 'איזה מטען?' בעיניים תמימות מדי בשביל ילדה שמחזיקה את הכבל שלי ביד. זו הפעם השלישית החודש, ולמותר לציין שהמטען שלה שלה נמצא בדיוק שם, על השולחן, טעון במלואו. בית המשפט מתבקש לקבוע גבולות ברורים בנושא בעלות על אביזרי טעינה במשק בית משותף.",
      defendant: "נועה (אחותי)",
      location: "הבית, חדר ילדים",
      charges: ["בגידה חברתית", "רשלנות פלילית"],
      author_id: 1,
      author_name: "דנה כהן",
      created_at: daysAgo(2),
    },
    {
      id: 6,
      title: "הנהג שעצר באמצע הצומת",
      body: "אור ירוק. הוא עצר. באמצע הצומת. מאחוריו משטרה ו-30 רכבים. בעיני זו הייתה הפעם הראשונה שפגשתי עיכוב כרוני אמיתי. הוא לא בדק טלפון ולא התבלבל — הוא פשוט החליט, ברגע הכי לא מתאים, שזה הזמן לעצור ולחשוב על החיים. הצופר שלי, הצופר של המשטרה, וצופרים של עוד שלושים רכבים לא הזיזו לו. בית המשפט מתבקש לבחון האם יש דבר כזה 'זכות לעצור באמצע צומת' — ואם לא, לקבוע זאת בתקדים מחייב.",
      defendant: "הסובארו הכחולה",
      location: "צומת אחרי קיבוץ יקום",
      charges: ["עיכוב כרוני", "רשלנות פלילית"],
      author_id: 5,
      author_name: "רוני גולן",
      created_at: daysAgo(3),
    },
    {
      id: 7,
      title: "המסעדה שאיבדה את ההזמנה שלי",
      body: "הזמנתי דרך אפליקציה. שילמתי. חיכיתי שעה. 'אופס, לא ראינו את ההזמנה'. הציעו לי 10% הנחה על הזמנה הבאה. שאני לא אזמין מהם שוב.",
      defendant: "המסעדה האסיאתית בקניון",
      location: "אפליקציית 10bis",
      charges: ["רשלנות פלילית", "בגידה חברתית", "ייאוש מכוון"],
      author_id: 2,
      author_name: "יואב לוי",
      created_at: daysAgo(4),
    },
    {
      id: 8,
      title: "האקס שעוקב אחרי בכל פלטפורמה",
      body: "נפרד ממני לפני שנתיים. עוקב אחריי באינסטה, בלינקדאין, בטיקטוק ובפינטרסט. רואה כל story תוך ארבע דקות. אני יודעת שהוא קורא את זה.",
      defendant: "האקס",
      location: "כל הפלטפורמות",
      charges: ["הפרת שלוות נפש", "מניפולציה רגשית"],
      author_id: 3,
      author_name: "מאיה שטרן",
      created_at: daysAgo(5),
    },
    {
      id: 9,
      title: "האב שצופה בטלפון בארוחה משפחתית",
      body: "יום שישי. כל המשפחה. אבא מסתכל בטלפון כל 30 שניות. כשהוא אומר 'סיימתי' הוא כבר חוזר לגלול. אחר כך הוא נואם על 'הדור הזה'.",
      defendant: "אבא",
      location: "שולחן שבת",
      charges: ["בגידה חברתית", "מניפולציה רגשית"],
      author_id: 4,
      author_name: "איתי אברמוב",
      created_at: daysAgo(6),
    },
    {
      id: 10,
      title: "הקופאית בסופר שלא רצתה לפתוח עוד קופה",
      body: "תור של 12 אנשים. ביקשתי שיפתחו עוד קופה. 'זה לא התפקיד שלי' אמרה. 'אני בהפסקה' השיבה, תוך כדי שהיא אוכלת קרם בוה על חשבון העמדה.",
      defendant: "הקופאית עם הציפורניים",
      location: "סופר ברחוב אבן גבירול",
      charges: ["רשלנות פלילית", "עיכוב כרוני"],
      author_id: 5,
      author_name: "רוני גולן",
      created_at: daysAgo(7),
    },
    {
      id: 11,
      title: "המאמן בכושר שצועק 'עוד אחד' 17 פעמים",
      body: "הוא אמר 'עוד אחד אחרון'. עשיתי. הוא אמר שוב. ושוב. ושוב. עד שלא יכולתי להרים את הזרוע לסבון אחר כך. הזרוע שלי עדיין רועדת.",
      defendant: "יוסי המאמן",
      location: "חדר כושר, רחוב אלנבי",
      charges: ["מניפולציה רגשית", "ייאוש מכוון", "רשלנות פלילית"],
      author_id: 6,
      author_name: "נועה פרידמן",
      created_at: daysAgo(8),
    },
    {
      id: 12,
      title: "המתכנת שכתב TODO ועזב את החברה",
      body: "במערכת שקיבלתי ירשתי 847 הערות TODO. עזב לפני 3 שנים. אחת מהן אומרת 'צריך לתקן את כל המערכת'. מאז אני חי עם השאלה הזאת.",
      defendant: "דני, מתכנת לשעבר",
      location: "GitHub, ענף main",
      charges: ["בגידה חברתית", "עיכוב כרוני", "ייאוש מכוון"],
      author_id: 7,
      author_name: "אלון ברק",
      created_at: daysAgo(10),
    },
  ];

  return { users, posts, nextUserId: users.length + 1, nextPostId: posts.length + 1 };
};

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

const loadState = (): MockState => {
  if (typeof localStorage === "undefined") return createDefaultState();
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return createDefaultState();
  try {
    const parsed = JSON.parse(raw) as MockState;
    if (!parsed || !Array.isArray(parsed.users) || !Array.isArray(parsed.posts)) {
      return createDefaultState();
    }
    return parsed;
  } catch {
    return createDefaultState();
  }
};

const state = loadState();

const persistState = (): void => {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
};

const userById = (userId: number): StoredUser | undefined => state.users.find((u) => u.id === userId);

const publicUser = (user: StoredUser): User => ({
  id: user.id,
  name: user.name,
  email: user.email,
  created_at: user.created_at,
});

const normalize = (value: string): string => value.trim().toLowerCase();

// Newest first.
const byNewest = (left: Post, right: Post): number =>
  new Date(right.created_at).getTime() - new Date(left.created_at).getTime();

const paged = <T,>(items: T[], limit?: number, offset?: number): T[] => {
  const start = typeof offset === "number" ? offset : 0;
  const end = typeof limit === "number" ? start + limit : undefined;
  return items.slice(start, end);
};

const readSessionUser = (): User | null => {
  if (typeof localStorage === "undefined") return null;
  const raw = localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
};

const requireSessionUser = (): StoredUser => {
  const sessionUser = readSessionUser();
  if (!sessionUser) throw new Error("נדרשת התחברות");
  const user = userById(sessionUser.id);
  if (!user) throw new Error("המשתמש המחובר לא קיים במאגר ההדגמה");
  return user;
};

const buildAuthResponse = (user: StoredUser): AuthResponse => ({
  token: `mock-token-${user.id}`,
  user: publicUser(user),
});

export const mockLogin = async (email: string, password: string): Promise<AuthResponse> => {
  const user = state.users.find((u) => u.email.toLowerCase() === email.trim().toLowerCase());
  if (!user || user.password !== password) throw new Error("אימייל או סיסמה שגויים");
  return buildAuthResponse(user);
};

export const mockSignup = async (name: string, email: string, password: string): Promise<AuthResponse> => {
  if (state.users.some((u) => u.email.toLowerCase() === email.trim().toLowerCase())) {
    throw new Error("האימייל כבר רשום במערכת");
  }
  const created: StoredUser = {
    id: state.nextUserId++,
    name: name.trim(),
    email: email.trim(),
    password,
    created_at: new Date().toISOString(),
  };
  state.users.push(created);
  persistState();
  return buildAuthResponse(created);
};

export const mockFetchPosts = async (opts: { limit?: number; offset?: number } = {}): Promise<Post[]> => {
  const posts = [...state.posts].sort(byNewest);
  return clone(paged(posts, opts.limit, opts.offset));
};

export const mockCreatePost = async (payload: {
  title: string;
  body: string;
  defendant: string;
  charges?: string[];
}): Promise<Post> => {
  const user = requireSessionUser();
  const post: Post = {
    id: state.nextPostId++,
    title: payload.title,
    body: payload.body,
    defendant: payload.defendant,
    location: null,
    charges: payload.charges && payload.charges.length > 0 ? [...payload.charges] : undefined,
    author_id: user.id,
    author_name: user.name,
    created_at: new Date().toISOString(),
  };
  state.posts.unshift(post);
  persistState();
  return clone(post);
};

export const mockFetchUsers = async (opts: { search?: string; limit?: number; offset?: number } = {}): Promise<UserListItem[]> => {
  const search = normalize(opts.search || "");

  const items = state.users
    .map((user) => ({
      ...publicUser(user),
      post_count: state.posts.filter((post) => post.author_id === user.id).length,
    }))
    .filter((item) => {
      if (!search) return true;
      return normalize(item.name).includes(search) || normalize(item.email).includes(search);
    })
    .sort((left, right) => {
      if (right.post_count !== left.post_count) return right.post_count - left.post_count;
      return left.name.localeCompare(right.name, "he");
    });

  return clone(paged(items, opts.limit, opts.offset));
};

export const mockFetchUserProfile = async (id: number): Promise<UserProfileResponse> => {
  const user = userById(id);
  if (!user) throw new Error("התובע לא נמצא");

  const posts = state.posts.filter((post) => post.author_id === id).sort(byNewest);
  return clone({ user: publicUser(user), posts });
};
