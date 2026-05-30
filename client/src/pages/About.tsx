import { Link as RouterLink } from "react-router-dom";
import {
  Container,
  Box,
  Typography,
  Paper,
  Stack,
  Button,
  Chip,
  Divider,
} from "@mui/material";
import GavelIcon from "@mui/icons-material/Gavel";
import HowToVoteIcon from "@mui/icons-material/HowToVote";
import GroupsIcon from "@mui/icons-material/Groups";
import ChecklistIcon from "@mui/icons-material/Checklist";

import { isLoggedIn } from "../api";
import { DOC_FONT } from "../theme";

const BASE = import.meta.env.BASE_URL;
/**
 * About / manifest page — route `/about`.
 * Static marketing content: hero, mission, four core principles, glossary, disclaimer, and CTA.
 * No data fetching. Auth state switches CTA between "file a lawsuit" (logged-in) and "sign up" (anon).
 */
const PRINCIPLES = [
  {
    icon: <GavelIcon sx={{ fontSize: 36, color: "secondary.main" }} />,
    title: "הגש תביעה",
    body: "כל תסכול יומיומי הוא כתב אישום בפוטנציה. כלב שלא זז מהספה? חבר שביטל ברגע האחרון? שכן שמנגן את אותם 4 אקורדים בחצות? יש לך זכות לתבוע.",
  },
  {
    icon: <GroupsIcon sx={{ fontSize: 36, color: "secondary.main" }} />,
    title: "חבר המושבעים — זה הקהל",
    body: 'כל משתמש רשום הוא מושבע מן המניין. אין שופט אחד ויחיד. רוב המצביעים קובעים אם הנתבע "חייב" או "זכאי".',
  },
  {
    icon: <HowToVoteIcon sx={{ fontSize: 36, color: "secondary.main" }} />,
    title: "הצבעה אחת לתיק",
    body: "כל מושבע מצביע פעם אחת בתיק. אפשר להחליף עמדה (גם השופט הכי טוב משנה את דעתו), אבל לא אפשר להצביע פעמיים על אותה תביעה.",
  },
  {
    icon: <ChecklistIcon sx={{ fontSize: 36, color: "secondary.main" }} />,
    title: "בעלות ואחריות",
    body: "רק מי שהגיש תביעה יכול למחוק אותה. הקהילה רואה הכל, אבל היד שמחקה היא רק היד שכתבה.",
  },
];

const About = () => {
  return (
    <Container maxWidth="md" sx={{ py: { xs: 3, sm: 5 } }}>
      {/* Hero */}
      <Box
        sx={{
          textAlign: "center",
          mb: 5,
          py: 4,
          px: 2,
          background: "linear-gradient(135deg, rgba(184, 134, 11, 0.06) 0%, rgba(26, 46, 79, 0.06) 100%)",
          border: "1px solid rgba(184, 134, 11, 0.2)",
          borderRadius: 2,
          position: "relative",
        }}
      >
        <Box
          component="img"
          src={`${BASE}lolsuit-lockup-card.svg`}
          alt="LolSuit"
          sx={{
            display: "block",
            mx: "auto",
            mb: 2,
            maxWidth: { xs: 260, sm: 320 },
            width: "100%",
          }}
        />
        <Typography
          component="h1"
          sx={{
            // Visually-hidden h1 for SEO / a11y. The card SVG is the visible "headline".
            position: "absolute",
            left: -9999,
            width: 1,
            height: 1,
            overflow: "hidden",
          }}
        >
          LolSuit
        </Typography>
        <Typography
          sx={{
            color: "text.secondary",
            fontStyle: "italic",
            fontSize: { xs: "1.05rem", sm: "1.2rem" },
            maxWidth: 560,
            mx: "auto",
            fontFamily: DOC_FONT,
          }}
        >
          הרשת החברתית של תביעות מגוחכות. כל פוסט הוא כתב אישום, כל לייק הוא הצבעת מושבע, כל יציאה היא "שחרור באולם".
        </Typography>
        <Stack direction="row" spacing={1} justifyContent="center" sx={{ mt: 3, flexWrap: "wrap", gap: 1 }}>
          <Chip label="פורמלי" variant="outlined" />
          <Chip label="עד-כדי-גיחוך" variant="outlined" />
          <Chip label="קהילתי" variant="outlined" />
          <Chip label="לא-משפטית-באמת" variant="outlined" color="secondary" />
        </Stack>
      </Box>

      {/* Manifesto */}
      <Paper sx={{ p: { xs: 3, sm: 4 }, mb: 4 }}>
        <Typography
          variant="h4"
          sx={{
            fontFamily: '"Frank Ruhl Libre", serif',
            fontWeight: 700,
            color: "primary.main",
            mb: 2,
            position: "relative",
            paddingInlineStart: 2,
            "&::before": {
              content: '""',
              position: "absolute",
              insetInlineStart: 0,
              top: 4,
              bottom: 4,
              width: 4,
              backgroundColor: "secondary.main",
              borderRadius: 2,
            },
          }}
        >
          הצהרת כוונות
        </Typography>
        <Typography sx={{ color: "text.primary", lineHeight: 1.9, fontSize: "1.05rem", fontFamily: DOC_FONT }}>
          החיים מלאים בעוולות קטנות. רובן לא יגיעו לבית משפט, רובן לא ראויות לעורך דין יקר, וכמעט אף אחת מהן
          לא תזכה אותך בפיצויים אמיתיים. אבל זה לא אומר שהן לא מגיעות להן יום בבית המשפט.
          <br />
          <br />
          <strong>LolSuit</strong> הוא בית המשפט הזה. מקום שבו הקופאית שסירבה לפתוח עוד קופה, הילד
          שצרח 11 שעות בטיסה, והאחות שגנבה את המטען — כולם זוכים למשפט הוגן. או לפחות לפוסט מצחיק.
          <br />
          <br />
          הקהילה היא חבר המושבעים. אתה התובע. הצדק יקבע בלייקים.
        </Typography>
      </Paper>

      {/* The four principles */}
      <Typography
        variant="h4"
        sx={{
          fontFamily: '"Frank Ruhl Libre", serif',
          fontWeight: 700,
          mb: 3,
          textAlign: "center",
          color: "primary.dark",
        }}
      >
        איך זה עובד?
      </Typography>

      <Stack spacing={2} sx={{ mb: 5 }}>
        {PRINCIPLES.map((p, i) => (
          <Paper
            key={p.title}
            sx={{
              p: 3,
              display: "flex",
              gap: 2.5,
              alignItems: "flex-start",
              borderInlineStart: "4px solid",
              borderInlineStartColor: "secondary.main",
              backgroundColor: "background.paper",
            }}
          >
            <Box sx={{ flexShrink: 0, pt: 0.5 }}>{p.icon}</Box>
            <Box sx={{ flex: 1 }}>
              <Typography
                variant="h6"
                sx={{
                  fontFamily: '"Frank Ruhl Libre", serif',
                  fontWeight: 700,
                  mb: 0.5,
                  color: "primary.dark",
                  display: "flex",
                  alignItems: "baseline",
                  gap: 1,
                }}
              >
                <Typography
                  component="span"
                  sx={{ color: "secondary.dark", fontFamily: '"Frank Ruhl Libre", serif', fontSize: "1.5rem" }}
                >
                  סעיף {i + 1}.
                </Typography>
                {p.title}
              </Typography>
              <Typography sx={{ color: "text.primary", lineHeight: 1.7, fontFamily: DOC_FONT }}>{p.body}</Typography>
            </Box>
          </Paper>
        ))}
      </Stack>

      {/* Glossary */}
      <Paper sx={{ p: { xs: 3, sm: 4 }, mb: 4 }}>
        <Typography
          variant="h5"
          sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700, mb: 2.5, color: "primary.main" }}
        >
          📜 מילון מונחים משפטיים-מומצאים
        </Typography>
        <Stack divider={<Divider />} spacing={1.5}>
          {[
            ["התייצבות", "כניסה למערכת. כי 'login' זה לחלשים."],
            ["שחרור באולם", "התנתקות. בלי בקשת רשות, בלי נימוסים."],
            ["כתב אישום", "פוסט. רק נשמע יותר רציני."],
            ["מושבעים", "מי שמצביע. כלומר, כל מי שהתייצב."],
            ["תיק", "פרופיל המשתמש."],
            ["הוכרע", "תביעה עם מספיק הצבעות והפרש ברור — הצדק נעשה."],
          ].map(([term, def]) => (
            <Box key={term} sx={{ display: "flex", gap: 2, alignItems: "baseline", flexWrap: "wrap" }}>
              <Typography
                component="dt"
                sx={{
                  fontFamily: '"Frank Ruhl Libre", serif',
                  fontWeight: 700,
                  color: "secondary.dark",
                  minWidth: 130,
                }}
              >
                {term}
              </Typography>
              <Typography component="dd" sx={{ color: "text.primary", flex: 1, m: 0, fontFamily: DOC_FONT }}>
                {def}
              </Typography>
            </Box>
          ))}
        </Stack>
      </Paper>

      {/* Disclaimer */}
      <Paper
        sx={{
          p: 3,
          mb: 4,
          backgroundColor: "rgba(155, 44, 44, 0.05)",
          border: "1px dashed rgba(155, 44, 44, 0.3)",
        }}
      >
        <Typography variant="overline" sx={{ color: "error.main", fontWeight: 700, letterSpacing: 1.5 }}>
          הבהרה משפטית (חצי-רצינית)
        </Typography>
        <Typography sx={{ color: "text.primary", mt: 1, lineHeight: 1.7, fontFamily: DOC_FONT }}>
          האתר הזה הוא בדיחה. שום תביעה כאן לא מחייבת אף אחד משפטית. אם הכלב שלך מסרב לזוז מהספה, אנחנו
          ממליצים על ביסקוויט, לא על עורך דין. שמות הנתבעים הם המצאה ספרותית — אל תזהה אנשים אמיתיים, ואל תזהיר
          את השכן שלי שאני בדרך לתבוע אותו על "Wonderwall".
        </Typography>
      </Paper>

      {/* Official seal mark above the CTA */}
      <Box sx={{ textAlign: "center", py: 3 }}>
        <Box
          component="img"
          src={`${BASE}lolsuit-seal.svg`}
          alt=""
          sx={{ width: { xs: 200, sm: 240 }, opacity: 0.9, display: "inline-block" }}
        />
      </Box>

      {/* CTA */}
      <Box sx={{ textAlign: "center", py: 4 }}>
        <Typography
          variant="h5"
          sx={{
            fontFamily: '"Frank Ruhl Libre", serif',
            fontWeight: 700,
            mb: 2,
            color: "primary.dark",
          }}
        >
          מוכן/ה לפתוח תיק?
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} justifyContent="center">
          {isLoggedIn() ? (
            <Button
              component={RouterLink}
              to="/new-post"
              variant="contained"
              color="secondary"
              size="large"
              startIcon={<GavelIcon />}
            >
              הגש תביעה ראשונה
            </Button>
          ) : (
            <>
              <Button component={RouterLink} to="/signup" variant="contained" color="secondary" size="large">
                הירשם כתובע
              </Button>
              <Button component={RouterLink} to="/login" variant="outlined" size="large">
                התייצב באולם
              </Button>
            </>
          )}
          <Button component={RouterLink} to="/" variant="outlined" size="large">
            לכל הפיד
          </Button>
        </Stack>
      </Box>
    </Container>
  );
};
export default About;