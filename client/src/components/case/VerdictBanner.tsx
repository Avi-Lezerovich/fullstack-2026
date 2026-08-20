import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import GavelIcon from "@mui/icons-material/Gavel";

import { VERDICT_LABELS, type Verdict } from "../../types";
import { DOC_FONT } from "../../theme";

interface Props {
  verdict: Verdict | null;
  sentenceText: string | null;
  judgeName?: string | null;
}

/**
 * The permanent result badge on a decided case.
 *
 * Renders nothing before a verdict exists, so a page can drop it in
 * unconditionally without checking the phase first.
 */
const VerdictBanner = ({ verdict, sentenceText, judgeName }: Props) => {
  if (!verdict) return null;

  const guilty = verdict === "guilty";

  return (
    <Alert
      severity={guilty ? "error" : "success"}
      icon={<GavelIcon fontSize="inherit" />}
      variant="outlined"
      data-testid="verdict-banner"
      data-verdict={verdict}
      sx={{ borderWidth: 2, alignItems: "flex-start" }}
    >
      <AlertTitle sx={{ fontWeight: 700, fontSize: "1.15rem" }}>
        פסק דין: {VERDICT_LABELS[verdict]}
      </AlertTitle>

      {sentenceText && (
        <Box sx={{ mt: 0.5 }}>
          <Typography variant="body2" sx={{ fontFamily: DOC_FONT }} data-testid="verdict-sentence">
            {sentenceText}
          </Typography>
        </Box>
      )}

      {judgeName && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          ניתן על ידי {judgeName}
        </Typography>
      )}
    </Alert>
  );
}; export default VerdictBanner;
