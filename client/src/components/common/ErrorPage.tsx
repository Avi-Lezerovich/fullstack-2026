import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

/**
 * One page for every refusal: a missing docket, a locked door, a link that has
 * expired, a hearing that collapsed mid-sentence.
 *
 * Deliberately the same vocabulary as `EmptyState` above — title, description,
 * action — plus the code, so the two read as one family rather than as two
 * takes on the same idea. Every colour is a theme token, so the palette lives
 * in `theme.ts` and only there.
 */

export const ErrorPage = ({
  code,
  title,
  description,
  action,
}: {
  code: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) => {
  return (
    <Paper
      sx={{ p: { xs: 3, sm: 5 }, maxWidth: 560, mx: "auto", textAlign: "center" }}
      data-testid="error-page"
      data-code={code}
    >
      <Stack spacing={2} alignItems="center">
        {/* Decorative: the code and the title below already say all of this. */}
        <Box
          component="img"
          src={`${import.meta.env.BASE_URL}lolsuit-seal.svg`}
          alt=""
          aria-hidden
          sx={{ height: { xs: 72, sm: 96 }, opacity: 0.9 }}
        />

        <Typography
          variant="h2"
          color="primary.main"
          // The variant carries the face and the weight; only the size needs to
          // bend for a phone, and `variant` cannot be made responsive.
          sx={{ fontSize: { xs: "3rem", sm: "4rem" }, lineHeight: 1 }}
        >
          {code}
        </Typography>

        {/* The AppBar's brass rule, cut short. */}
        <Box sx={{ width: 64, borderBottom: "3px solid", borderColor: "secondary.main" }} />

        <Typography variant="h5" component="h1">
          {title}
        </Typography>

        {description && (
          <Typography color="text.secondary" sx={{ maxWidth: 420 }}>
            {description}
          </Typography>
        )}

        {action && <Box sx={{ pt: 1 }}>{action}</Box>}
      </Stack>
    </Paper>
  );
};
